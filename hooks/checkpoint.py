#!/usr/bin/env python3
"""Session checkpoint hook — keep a durable, resumable record of what a session
was doing, so a session that dies loses at most one turn instead of everything.

The problem this solves: morph-global-stop.sh assembles a session's trace only
at Stop. A killed session leaves its prompts in a pending-*.jsonl and nothing
else. This hook writes a small state file continuously instead.

Schema is a deliberate mirror of ~/.claude/jobs/<id>/state.json (state, detail,
needs, resumeSessionId, cwd, transcript cursor) so /resume and anything else
that already understands a job record can read a checkpoint without a new
parser. We mirror that shape; we do not write into jobs/, which is harness-owned.

Wired to three events:
  UserPromptSubmit — the turn boundary. Always writes.
  PostToolUse      — mutating tools only (Bash|Write|Edit|MultiEdit).
  Stop             — marks the session cleanly finished, and prunes old dirs.

A checkpoint that never got a Stop is an interrupted session; that is exactly
what session_start.sh looks for.

STDLIB ONLY and FAIL-OPEN, for the same reasons as guardrail.py: this runs on
every turn on every host, so a bug here must never block a session. Every path
exits 0. Minimum supported Python is 3.8 — the oldest interpreter in the fleet,
not the newest one you happen to test on. Use typing.Dict/Optional, never PEP 585
builtin subscripting or PEP 604 unions, anywhere evaluated at runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(os.environ.get("CLAUDE_CHECKPOINT_DIR") or (Path.home() / ".claude" / "checkpoints"))
GIT_REFRESH_SECS = 60  # how often to pay for the git subprocesses
PRUNE_AFTER_DAYS = 14
DETAIL_MAX = 300
TIMELINE_MAX_BYTES = 4_000_000


def _utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(text: str, limit: int = DETAIL_MAX) -> str:
    """One line, bounded. Timeline entries must not become the transcript."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _git(cwd: str) -> Dict[str, Any]:
    """Branch + dirty flag. The only expensive part of a checkpoint, hence cached."""
    info: Dict[str, Any] = {"branch": None, "dirty": False}
    try:
        branch = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if branch.returncode != 0:
            return info
        info["branch"] = branch.stdout.strip() or None
        status = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True, text=True, timeout=3,
        )
        info["dirty"] = bool(status.stdout.strip())
    except Exception:
        pass
    return info


def _detail_for(event: str, payload: Dict[str, Any]) -> str:
    """A human-readable 'what was happening' line — the field /resume actually reads."""
    if event == "UserPromptSubmit":
        return _clip(payload.get("prompt") or "")
    if event == "PostToolUse":
        tool = payload.get("tool_name") or "tool"
        raw = payload.get("tool_input") or {}
        if isinstance(raw, dict):
            for key in ("command", "file_path", "pattern", "path"):
                if raw.get(key):
                    return _clip("{}: {}".format(tool, raw[key]))
        return _clip(tool)
    if event == "Stop":
        return "session ended cleanly"
    return _clip(event)


def _prune(now: float) -> None:
    """Bound the directory. Nothing here may fill a disk if you forget about it."""
    cutoff = now - PRUNE_AFTER_DAYS * 86400
    try:
        for entry in ROOT.iterdir():
            if not entry.is_dir():
                continue
            state = entry / "state.json"
            stamp = state.stat().st_mtime if state.exists() else entry.stat().st_mtime
            if stamp < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
    except Exception:
        pass


def main() -> None:
    try:
        raw = sys.stdin.read().strip()
    except Exception:
        return
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return

    session_id = payload.get("session_id") or "unknown"
    event = payload.get("hook_event_name") or "unknown"
    cwd = payload.get("cwd") or os.getcwd()
    transcript = payload.get("transcript_path") or ""

    target = ROOT / str(session_id)
    target.mkdir(parents=True, exist_ok=True)
    state_path = target / "state.json"

    prior: Dict[str, Any] = {}
    if state_path.exists():
        try:
            with state_path.open() as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                prior = loaded
        except Exception:
            prior = {}

    now = time.time()
    now_iso = _utc_now()

    # Git info is the only costly part, so refresh it on a 60s cadence and carry
    # the cached value forward otherwise. The cheap state write happens every time
    # — throttling *that* would cost fidelity and save nothing, since the hook
    # process has already been spawned by the time we get here.
    git_info = {"branch": prior.get("branch"), "dirty": prior.get("dirty", False)}
    last_git = float(prior.get("gitCheckedAt") or 0)
    git_checked_at = last_git
    if event in ("UserPromptSubmit", "Stop") or (now - last_git) >= GIT_REFRESH_SECS:
        git_info = _git(cwd)
        git_checked_at = now

    offset: Optional[int] = None
    try:
        if transcript and os.path.exists(transcript):
            offset = os.path.getsize(transcript)
    except Exception:
        offset = None

    detail = _detail_for(event, payload)
    state: Dict[str, Any] = {
        # "completed" only ever set by Stop — anything else means interrupted.
        "state": "completed" if event == "Stop" else "active",
        "detail": detail,
        "needs": prior.get("needs"),
        "resumeSessionId": session_id,
        "cwd": cwd,
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "branch": git_info.get("branch"),
        "dirty": git_info.get("dirty", False),
        "transcriptPath": transcript,
        "transcriptOffset": offset,
        "lastEvent": event,
        "turns": int(prior.get("turns") or 0) + (1 if event == "UserPromptSubmit" else 0),
        "createdAt": prior.get("createdAt") or now_iso,
        "updatedAt": now_iso,
        "gitCheckedAt": git_checked_at,
    }

    # Atomic: a reader must never see a half-written state file.
    tmp = target / "state.json.tmp"
    with tmp.open("w") as fh:
        json.dump(state, fh, indent=2)
    os.replace(str(tmp), str(state_path))

    timeline = target / "timeline.jsonl"
    try:
        if not timeline.exists() or timeline.stat().st_size < TIMELINE_MAX_BYTES:
            with timeline.open("a") as fh:
                fh.write(json.dumps({
                    "at": now_iso,
                    "state": state["state"],
                    "event": event,
                    "detail": detail,
                }) + "\n")
    except Exception:
        pass

    if event == "Stop":
        _prune(now)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail-open, always
        sys.stderr.write("checkpoint: {}\n".format(exc))
    sys.exit(0)
