#!/usr/bin/env python3
"""Tests for denial_log.py, run as a process the way the harness runs it.

Usage: python3 test_denial_log.py
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

HOOK = Path(__file__).resolve().parent / "denial_log.py"
FAILURES: List[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  ok   {}".format(name))
    else:
        print("  FAIL {} {}".format(name, detail))
        FAILURES.append(name)


def run(payload: str, log: Path, extra_env: dict = {}) -> subprocess.CompletedProcess:  # noqa: B006
    env = dict(os.environ, CLAUDE_DENIAL_LOG=str(log))
    env.pop("CLAUDE_HOOKS_OFF", None)
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload.encode(), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
    )


def test_records_a_denial() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "sub" / "denials.jsonl"
        payload = json.dumps({
            "hook_event_name": "PermissionDenied", "session_id": "s1", "cwd": "/repo",
            "tool_name": "Bash", "tool_input": {"command": "git push origin main"},
            "reason": "[Production Deploy]",
        })
        r = run(payload, log)
        check("exit 0, silent", r.returncode == 0 and not r.stdout and not r.stderr, r.stderr.decode())
        lines = log.read_text().splitlines()
        rec = json.loads(lines[0])
        check("one line written", len(lines) == 1)
        check("reason kept", rec["reason"] == "[Production Deploy]")
        check("tool input kept", "git push origin main" in rec["input"])
        check("file is 0600", stat.S_IMODE(log.stat().st_mode) == 0o600, oct(log.stat().st_mode))


def test_truncates_huge_input() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "d.jsonl"
        run(json.dumps({"tool_name": "Write", "tool_input": {"content": "x" * 50000}}), log)
        rec = json.loads(log.read_text())
        check("input truncated", len(rec["input"]) < 2200 and rec["input"].endswith("[truncated]"))


def test_rotates_past_cap() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "d.jsonl"
        log.write_text("x" * (5 * 1024 * 1024 + 1))
        run(json.dumps({"tool_name": "Bash"}), log)
        check("old file rotated to .1", Path(str(log) + ".1").exists())
        check("new file small", log.stat().st_size < 1000)


def test_fails_open_on_garbage() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "d.jsonl"
        r = run("not json{", log)
        check("garbage stdin: exit 0, nothing written", r.returncode == 0 and not log.exists())


def test_switch_off() -> None:
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "d.jsonl"
        run(json.dumps({"tool_name": "Bash"}), log, {"CLAUDE_HOOKS_OFF": "denial_log"})
        check("CLAUDE_HOOKS_OFF=denial_log silences it", not log.exists())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n{} failed: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("\nall green")
