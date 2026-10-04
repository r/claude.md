#!/usr/bin/env python3
"""PermissionDenied hook — keep a record of every auto-mode classifier refusal.

Why: a refusal is the one event that decides whether a hands-off run keeps going,
and until this hook nothing recorded it. Finding out what stopped long runs meant
mining twenty thousand transcripts. One line per refusal in
~/.claude/denials.jsonl makes the next audit a `jq` one-liner:

    jq -r '.reason' ~/.claude/denials.jsonl | sort | uniq -c | sort -rn

What it writes: time, session, cwd, tool name, the refusal reason, and the tool
input truncated to 2 KB. The input can hold whatever the command held, which is
what the transcript already holds; the file is created 0600 and stays local.
It never decides anything and never prints: a denial has already happened.

Bounded: past 5 MB the file rotates to denials.jsonl.1 (one generation kept),
so it cannot fill a disk if forgotten.

STDLIB ONLY and FAIL-OPEN, same contract as every other hook here: every path
exits 0. Python 3.8 floor: typing.Dict/Optional, never PEP 585/604 at runtime.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

MAX_BYTES = 5 * 1024 * 1024
MAX_INPUT_CHARS = 2048
# The harness has spelled the reason a few ways across versions; take the first.
REASON_KEYS = ("reason", "permission_decision_reason", "denial_reason", "message")


def log_path() -> Path:
    override = os.environ.get("CLAUDE_DENIAL_LOG")
    return Path(override) if override else Path.home() / ".claude" / "denials.jsonl"


def record(payload: Dict[str, Any], now: float) -> Dict[str, Any]:
    reason: Optional[str] = None
    for key in REASON_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val:
            reason = val
            break
    raw_input = payload.get("tool_input")
    text = raw_input if isinstance(raw_input, str) else json.dumps(raw_input, sort_keys=True)
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS] + "…[truncated]"
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "event": payload.get("hook_event_name"),
        "session": payload.get("session_id"),
        "cwd": payload.get("cwd"),
        "tool": payload.get("tool_name"),
        "reason": reason,
        "input": text,
    }


def append(path: Path, line: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.stat().st_size > MAX_BYTES:
            os.replace(str(path), str(path) + ".1")
    except FileNotFoundError:
        pass
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")


def main() -> None:
    # CLAUDE_HOOKS_OFF leaves the hook ON; only an exact id match turns it off.
    _hoff = "," + os.environ.get("CLAUDE_HOOKS_OFF", "").replace(" ", "") + ","
    if ",all," in _hoff or ",denial_log," in _hoff:
        return
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict):
            append(log_path(), record(payload, time.time()))
    except Exception:
        pass  # fail open: a logging bug must never surface in a session


if __name__ == "__main__":
    main()
    sys.exit(0)
