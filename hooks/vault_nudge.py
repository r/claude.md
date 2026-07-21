#!/usr/bin/env python3
"""Stop hook — nudge when a session did durable work but wrote nothing to the
workshop vault.

The gap this closes: `vault-write` is a *skill*, and skills are model
discretion. Nothing in the harness ever fires one. So the vault gets an entry
only when the model happens to notice the moment is worth recording — which is
why the vault skews hard toward chunky infra work (23 infra / 6 software over
its first three days) and loses the coding sessions almost entirely. A coding
session ends the same way whether or not it uncovered something durable.

This is the same shape as doc_drift.sh: suggest-mode only. It never writes a
note, never invokes the skill, and never blocks a Stop. It surfaces a reminder
with the domain pre-picked, because the domain is the part that gets guessed
wrong — every folder heuristic misfiles when your infra is itself managed in
repos, so "touched a host" is the signal, not "touched a repo".

Detection is deliberately dumb and read-only:
  did the session do real work?   -> count mutating tool uses in the transcript
  did it already record one?      -> did it invoke the skill / bin/vault-write in-transcript
  which half of the vault?        -> Infra if the session touched hosts/docker/
                                     network, Software otherwise

STDLIB ONLY and FAIL-OPEN, same contract as checkpoint.py and guardrail.py:
this runs at the end of every session on every host, so a bug here must never
eat a Stop. Every path exits 0. Minimum supported Python is 3.8 — target the
oldest interpreter you run anywhere, not the newest one you happen to test on.
Use typing.Dict/List/Optional, never PEP 585 builtin subscripting or PEP 604
unions, anywhere evaluated at runtime.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

# Same env override as checkpoint.py, so the tests never touch the real dir.
STAMP_DIR = Path(
    os.environ.get("CLAUDE_CHECKPOINT_DIR") or (Path.home() / ".claude" / "checkpoints")
)

# A session has to have actually done something. These thresholds are set so a
# question-answering session stays silent and a working session speaks up.
MIN_MUTATING_CALLS = 8

# Substrings that mean the session touched the estate rather than a repo. Kept
# lowercase and matched against Bash command strings only. Add your own host
# names here (e.g. "web-01", "db-prod") so remote work routes to the Infra half.
INFRA_MARKERS = (
    "ssh ", "docker", "systemctl", "nginx", "zfs", "zpool",
    "udm", "unifi", "tailscale", "iptables",
    "mount", "nfs", "dig ", "resolvectl", "compose",
)

MUTATING = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")


def _read_transcript(path: str) -> List[Dict]:
    """Best-effort JSONL read. A malformed line is skipped, never fatal."""
    rows = []  # type: List[Dict]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return []
    return rows


def _iter_tool_uses(rows):
    """Yield (tool_name, input_dict) for every tool_use block in the transcript."""
    for row in rows:
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name") or "", block.get("input") or {}


def _wrote_to_vault(rows) -> bool:
    """Did this session already record something?

    Read from the transcript, not from the queue directory. Queue mtimes are
    not a session signal: vault-spooler.py rewrites a note's mtime when it
    moves it into sent/, so notes from days ago look brand new the moment the
    spooler drains. That false-positive silenced the nudge on every session
    that happened to overlap a delivery.
    """
    for name, tool_input in _iter_tool_uses(rows):
        if name == "Skill" and str(tool_input.get("skill") or "") == "vault-write":
            return True
        if name == "Bash":
            cmd = str(tool_input.get("command") or "")
            # Match an *invocation*, not a mention. `ls ~/.claude/skills/vault-write/`
            # contains the string too, and counting that as a write silenced the
            # nudge on any session that merely looked at the skill.
            if "bin/vault-write" in cmd or "vault-write --" in cmd:
                return True
    return False


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    transcript = payload.get("transcript_path")
    session_id = payload.get("session_id") or ""
    if not transcript or not os.path.exists(transcript):
        return

    # Once per session, ever. A Stop fires on every turn boundary the user
    # interrupts; nagging each time is how a nudge gets ignored.
    stamp = STAMP_DIR / str(session_id) / ".vault_nudged"
    try:
        if stamp.exists():
            return
    except Exception:
        return

    rows = _read_transcript(transcript)
    if not rows:
        return

    mutating = 0
    infra_hits = 0
    for name, tool_input in _iter_tool_uses(rows):
        if name not in MUTATING:
            continue
        mutating += 1
        if name == "Bash":
            cmd = str(tool_input.get("command") or "").lower()
            if any(marker in cmd for marker in INFRA_MARKERS):
                infra_hits += 1

    if mutating < MIN_MUTATING_CALLS:
        return

    if _wrote_to_vault(rows):
        return

    domain = "infra" if infra_hits >= 3 else "software"
    half = "Infra (the home network)" if domain == "infra" else "Software (craft knowledge)"

    msg = (
        "\U0001f4d3 This session made {n} changes and wrote nothing to the workshop vault. "
        "If anything here is durable — a pattern that generalizes, a decision and its "
        "rejected alternatives, a runbook step learned the hard way, an applied change — "
        "record it in {half} via the vault-write skill. If it was all routine, skip it; "
        "the vault is curated, not a session log."
    ).format(n=mutating, half=half)

    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(int(time.time())))
    except Exception:
        pass

    sys.stdout.write(json.dumps({"systemMessage": msg}) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
