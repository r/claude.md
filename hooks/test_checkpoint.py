#!/usr/bin/env python3
"""Tests for the session checkpoint hook. Run directly (`python3 test_checkpoint.py`)
or under pytest.

Two things are being protected here, in priority order:
  1. FAIL-OPEN. checkpoint.py runs on every turn on every host. Whatever the
     input, it must exit 0 and never stall a session. Most of these cases are
     garbage-in cases for exactly that reason.
  2. The interruption signal. state=completed is written ONLY by Stop, because
     session_start.sh treats anything else as an interrupted session. If that
     invariant breaks, the whole feature silently stops reporting.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

HOOK = Path(__file__).resolve().parent / "checkpoint.py"


def run_hook(payload: Optional[str], root: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_CHECKPOINT_DIR"] = str(root)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input="" if payload is None else payload,
        text=True, capture_output=True, env=env, timeout=30,
    )


def state_of(root: Path, session: str) -> Dict[str, Any]:
    with (root / session / "state.json").open() as fh:
        data: Dict[str, Any] = json.load(fh)
    return data


def event(session: str, name: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {
        "session_id": session, "hook_event_name": name, "cwd": os.getcwd(),
    }
    payload.update(extra)
    return json.dumps(payload)


FAILURES: list[str] = []


def check(label: str, cond: bool) -> None:
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        FAILURES.append(label)


def test_fail_open() -> None:
    """Every malformed input must still exit 0. This is the load-bearing test."""
    print("fail-open:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for label, payload in [
            ("empty stdin", ""),
            ("not json", "}{ not json"),
            ("json but not an object", "[1,2,3]"),
            ("empty object", "{}"),
            ("null", "null"),
            ("wrong types", json.dumps({"session_id": 42, "cwd": ["a"], "prompt": {"x": 1}})),
            ("nonexistent cwd", event("s", "PostToolUse", cwd="/nope/nowhere",
                                      tool_name="Bash", tool_input={"command": "ls"})),
            ("bad transcript path", event("s", "UserPromptSubmit", transcript_path="/nope/t.jsonl")),
        ]:
            proc = run_hook(payload, root)
            check("{} → exit 0".format(label), proc.returncode == 0)

        # An unwritable checkpoint root must not raise either.
        proc = run_hook(event("s", "Stop"), Path("/proc/cannot-possibly-exist"))
        check("unwritable root → exit 0", proc.returncode == 0)


def test_lifecycle() -> None:
    print("lifecycle:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sid = "sess-lifecycle"

        run_hook(event(sid, "UserPromptSubmit", prompt="fix the DNS on host-b"), root)
        s = state_of(root, sid)
        check("prompt recorded as detail", s["detail"] == "fix the DNS on host-b")
        check("state is active, not completed", s["state"] == "active")
        check("turn counted", s["turns"] == 1)
        check("resumeSessionId set", s["resumeSessionId"] == sid)
        created = s["createdAt"]

        run_hook(event(sid, "PostToolUse", tool_name="Bash",
                       tool_input={"command": "docker restart unbound"}), root)
        s = state_of(root, sid)
        check("tool detail includes command", "docker restart unbound" in s["detail"])
        check("still active after tool use", s["state"] == "active")
        check("turns not incremented by tool use", s["turns"] == 1)
        check("createdAt preserved across writes", s["createdAt"] == created)

        run_hook(event(sid, "Stop"), root)
        s = state_of(root, sid)
        check("Stop marks completed", s["state"] == "completed")

        lines = (root / sid / "timeline.jsonl").read_text().strip().split("\n")
        check("timeline has one line per event", len(lines) == 3)
        check("timeline lines are valid json", all(json.loads(x) for x in lines))


def test_only_stop_completes() -> None:
    """The invariant session_start.sh depends on."""
    print("interruption signal:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("UserPromptSubmit", "PostToolUse", "SessionStart", "Notification", "bogus"):
            sid = "sess-" + name
            run_hook(event(sid, name, prompt="x", tool_name="Bash", tool_input={"command": "ls"}), root)
            check("{} does NOT mark completed".format(name),
                  state_of(root, sid)["state"] != "completed")


def test_detail_is_bounded() -> None:
    print("bounded detail:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sid = "sess-huge"
        run_hook(event(sid, "UserPromptSubmit", prompt="A" * 50_000), root)
        detail = state_of(root, sid)["detail"]
        check("long prompt clipped", len(detail) <= 300)
        run_hook(event(sid, "UserPromptSubmit", prompt="line one\nline two\n\tline three"), root)
        check("detail is single-line", "\n" not in state_of(root, sid)["detail"])


def test_atomic_state() -> None:
    print("atomicity:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sid = "sess-atomic"
        run_hook(event(sid, "UserPromptSubmit", prompt="x"), root)
        check("no .tmp file left behind", not (root / sid / "state.json.tmp").exists())


def test_prune() -> None:
    print("prune:")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        old, new = root / "ancient", root / "recent"
        for d in (old, new):
            d.mkdir(parents=True)
            (d / "state.json").write_text('{"state":"active"}')
        long_ago = time.time() - 30 * 86400
        os.utime(old / "state.json", (long_ago, long_ago))
        os.utime(old, (long_ago, long_ago))

        run_hook(event("pruner", "Stop"), root)
        check("30-day-old checkpoint pruned", not old.exists())
        check("recent checkpoint kept", new.exists())


if __name__ == "__main__":
    for fn in (test_fail_open, test_lifecycle, test_only_stop_completes,
               test_detail_is_bounded, test_atomic_state, test_prune):
        fn()
    print()
    if FAILURES:
        print("{} FAILED:".format(len(FAILURES)))
        for f in FAILURES:
            print("  - " + f)
        sys.exit(1)
    print("all checkpoint tests passed")
