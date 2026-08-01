#!/usr/bin/env python3
"""Stop hook — capture durable knowledge to the vault WITHOUT interrupting the
session, by handing the judgment to a detached background agent.

Why this exists, on top of vault_nudge.py: writing a good vault note is a
judgment call ("is anything here worth keeping six months from now?"), and the
only actor who can make it mid-session is the model — which means a synchronous
model round-trip in the middle of iteration. That pause is the thing that slows
the loop. Enqueuing was already instant and delivery was already backgrounded
(bin/vault-write -> vault-queue -> vault-spooler); the judgment was the last
piece still on the critical path.

So at Stop, if the session did real work and recorded nothing, this fires a
*detached* `claude -p` (Haiku, cheap) that reads a digest of the session and
enqueues vault notes on its own. The interactive session returns immediately
and never waits. The queue + spooler carry them the rest of the way.

Least-agency, because the background agent is driven by transcript content and
transcript content is not fully trusted (see rules/security.md — model/tool
output is untrusted input):
  - it runs with NO permission bypass;
  - --allowedTools scopes it to exactly Read(<the digest>) and
    Bash(<abs path to vault-write> *) — it cannot touch anything else;
  - it gets a digest file, never the raw repo or shell.

Recursion is prevented by CLAUDE_VAULT_CURATOR=1 in the child's environment: the
child's own Stop fires this hook again, which sees the flag and bails before
spawning. That guard holds regardless of which settings the child loads, so it
does not depend on --bare (which we avoid, because --bare disables OAuth and
would break auth under a subscription login).

The spawned thing is this file re-exec'd in --run-curator mode, which runs the
real `claude -p` underneath. That wrapper exists because the log used to lie:
in plain-text output mode it captured only the model's closing prose, so a
vault-write that was denied or errored left no trace and the run read as a
success. Measured 2026-07-31: 1 of 25 logged runs claimed three notes that were
never written anywhere. The child now asks for --output-format stream-json,
renders the tool calls and their results, and — the part that actually catches
it — counts the queue before and after and says outright when a run attempted
writes and the queue did not grow. The interactive session still never waits:
the hook spawns the wrapper and returns.

Degrades safely: if the vault isn't installed, exit silent; if the curator is
disabled (VAULT_CURATOR=0) or the `claude` binary is missing, fall back to the
one-line vault_nudge reminder so a human is still prompted; if anything at all
throws, exit 0. Same fail-open contract as every hook here.

STDLIB ONLY, 3.8-safe (typing.Dict/List, no PEP 585/604 at runtime), every path
exits 0 — this runs at the end of every session on every host.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

HOME = Path.home()
STAMP_DIR = Path(os.environ.get("CLAUDE_CHECKPOINT_DIR") or (HOME / ".claude" / "checkpoints"))
VAULT_WRITE = HOME / ".claude" / "bin" / "vault-write"
LOG_DIR = HOME / ".claude" / "vault-curator"
# Same default and same override as bin/vault-write, so the reconciliation
# below counts the queue the curator actually writes to.
QUEUE_DIR = Path(os.environ.get("VAULT_QUEUE_DIR") or (HOME / ".claude" / "vault-queue"))

# Child-side entry point. main() re-execs this file with this flag rather than
# importing anything, so the "hooks are independently deployable" property holds.
RUN_FLAG = "--run-curator"

# Recursion guard: set in the child's env, checked on entry.
GUARD_ENV = "CLAUDE_VAULT_CURATOR"
# Kill switch. "0"/"off"/"false" disables the background agent (falls back to a
# plain nudge). Anything else — including unset — leaves it on.
ENABLE_ENV = "VAULT_CURATOR"

MODEL = os.environ.get("VAULT_CURATOR_MODEL") or "claude-haiku-4-5-20251001"
SPAWN_TIMEOUT_SECS = 240  # hard wall-clock ceiling on the background agent
MIN_MUTATING_CALLS = 8    # same bar as the nudge: a working session, not a Q&A
MAX_DIGEST_BYTES = 60_000  # bound Haiku's input cost

INFRA_MARKERS = (
    "ssh ", "docker", "systemctl", "nginx", "zfs", "zpool",
    "udm", "unifi", "tailscale", "iptables",
    "mount", "nfs", "dig ", "resolvectl", "compose",
)
MUTATING = ("Bash", "Write", "Edit", "MultiEdit", "NotebookEdit")


# --------------------------------------------------------------------------- #
# transcript reading (mirrors vault_nudge.py — hooks stay independently
# deployable, so they don't import a shared module)
# --------------------------------------------------------------------------- #
def _read_transcript(path: str) -> List[Dict]:
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


def _already_wrote(rows) -> bool:
    """Did the interactive session already record a note itself? Then leave it."""
    for name, tool_input in _iter_tool_uses(rows):
        if name == "Skill" and str(tool_input.get("skill") or "") == "vault-write":
            return True
        if name == "Bash":
            cmd = str(tool_input.get("command") or "")
            if "bin/vault-write" in cmd or "vault-write --" in cmd:
                return True
    return False


def _counts(rows) -> Tuple[int, int]:
    """(mutating tool calls, infra-flavored bash calls)."""
    mutating = 0
    infra = 0
    for name, tool_input in _iter_tool_uses(rows):
        if name not in MUTATING:
            continue
        mutating += 1
        if name == "Bash":
            cmd = str(tool_input.get("command") or "").lower()
            if any(m in cmd for m in INFRA_MARKERS):
                infra += 1
    return mutating, infra


# --------------------------------------------------------------------------- #
# digest — what the background agent reads instead of the raw transcript.
# High signal, low cost: intent (user turns) + the model's own text + the list
# of actions taken. Deliberately NO tool results — they are the bulk and the
# least necessary, and they are where secrets would hide.
# --------------------------------------------------------------------------- #
def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts)
    return ""


def _action_summary(name: str, tool_input: Dict) -> str:
    if name == "Bash":
        return "$ " + " ".join(str(tool_input.get("command") or "").split())[:200]
    if name in ("Edit", "MultiEdit", "Write"):
        return "{} {}".format(name, tool_input.get("file_path") or "")
    if name == "Read":
        return "Read {}".format(tool_input.get("file_path") or "")
    keys = ",".join(sorted(k for k in tool_input.keys()))
    return "{}({})".format(name, keys)


def build_digest(rows) -> str:
    """A compact, chronological session digest. Returns '' if nothing to say."""
    lines = []  # type: List[str]
    for row in rows:
        msg = row.get("message")
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "user":
            txt = _text_of(content).strip()
            # user tool_result turns carry no role text worth keeping
            if txt:
                lines.append("USER: " + " ".join(txt.split())[:1200])
        elif role == "assistant":
            txt = _text_of(content).strip()
            if txt:
                lines.append("CLAUDE: " + " ".join(txt.split())[:1000])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        lines.append(
                            "  ACTION: "
                            + _action_summary(block.get("name") or "", block.get("input") or {})
                        )
    if not lines:
        return ""
    body = "\n".join(lines)
    if len(body.encode("utf-8", "replace")) <= MAX_DIGEST_BYTES:
        return body
    # Over budget: keep the first user turn (the intent) plus the recent tail,
    # which is where the durable conclusion usually lands.
    head = lines[0]
    tail = []  # type: List[str]
    size = len(head.encode("utf-8", "replace"))
    for ln in reversed(lines[1:]):
        size += len(ln.encode("utf-8", "replace")) + 1
        if size > MAX_DIGEST_BYTES:
            break
        tail.append(ln)
    tail.reverse()
    return head + "\n...\n" + "\n".join(tail)


# --------------------------------------------------------------------------- #
# the background agent
# --------------------------------------------------------------------------- #
CURATOR_SYSTEM = (
    "You are the workshop-vault curator. You run in the background after a Claude "
    "Code session and your only job is to record DURABLE knowledge from it into the "
    "vault, using the vault-write tool. You are not a summarizer and you never "
    "narrate the session."
)


def _curator_prompt(digest_path: Path, domain_hint: str, cwd: str) -> str:
    vw = str(VAULT_WRITE)
    return (
        "Read the session digest at {digest}. It is one Claude Code session on host "
        "cwd `{cwd}`.\n\n"
        "Decide what, if anything, is DURABLE — worth having six months from now on a "
        "different machine, after the reasoning has evaporated. Durable means: a "
        "pattern or technique that generalizes past this one task; a load-bearing "
        "decision and the alternatives it beat; a runbook step learned the hard way; "
        "an applied infra change (what, which host, why, rollback, how verified); a "
        "tool verdict; a material change in a project's state.\n\n"
        "NOT durable, do not write: narration of what was done, anything already in "
        "the repo or git history, routine edits, or speculation. When in doubt, write "
        "nothing — the vault is curated, and an empty result is a fine and common "
        "outcome. Usually zero to two notes, never a pile.\n\n"
        "For each durable fact, run the vault-write binary directly (do not wrap it in "
        "a shell pipeline):\n"
        "  {vw} --type <reference|change|decision|runbook|plan|pattern|tool|"
        "project-state|note> --domain <infra|software> --title \"...\" --key "
        "<stable-kebab-key> --confidence <high|medium|low> --body \"...\"\n\n"
        "This session leaned {domain}. Pick the type and domain per fact anyway. "
        "confidence high only for things read directly from output; medium/low route "
        "to review, which is correct for anything inferred. NEVER put a secret, "
        "password, key, or token in a note — reference where it lives. If nothing is "
        "durable, do nothing and stop."
    ).format(digest=str(digest_path), cwd=cwd or "?", vw=vw, domain=domain_hint)


def build_curator_argv(digest_path: Path, domain_hint: str, cwd: str, claude_bin: str) -> List[str]:
    """The exact argv for the detached agent. Factored out so it is testable
    without ever spawning a real model."""
    return [
        "timeout",
        str(SPAWN_TIMEOUT_SECS),
        claude_bin,
        "-p",
        _curator_prompt(digest_path, domain_hint, cwd),
        "--model",
        MODEL,
        "--append-system-prompt",
        CURATOR_SYSTEM,
        # Structured output so the log records what the agent DID, not only what
        # it said it did. In plain text mode a denied or failed vault-write never
        # reaches the log, the model narrates success anyway, and the run is
        # indistinguishable from one that worked. --verbose is required
        # alongside stream-json under -p.
        "--output-format",
        "stream-json",
        "--verbose",
        # least-agency: only these two tools, scoped. No permission bypass.
        "--allowedTools",
        "Read({})".format(digest_path),
        "Bash({} *)".format(VAULT_WRITE),
    ]


def build_runner_argv(curator_argv: List[str], python_bin: str = "") -> List[str]:
    """Wrap the curator in this same file, re-exec'd in --run-curator mode, so
    something is alive to render the stream and reconcile the result against the
    queue. The hook itself still never waits: it spawns this and returns."""
    return [python_bin or sys.executable, os.path.abspath(__file__), RUN_FLAG, "--"] + curator_argv


# --------------------------------------------------------------------------- #
# child side — render the stream, then reconcile the claim against the queue
# --------------------------------------------------------------------------- #
def _queue_count() -> int:
    """Notes that have reached the queue: pending plus already-spooled.

    Counting only the pending half would undercount, since the spooler drains
    every few seconds and can move a note to sent/ before the run even ends."""
    n = 0
    for d in (QUEUE_DIR, QUEUE_DIR / "sent"):
        try:
            n += sum(1 for _ in d.glob("*.md"))
        except Exception:
            continue
    return n


def _result_denials(row: Dict) -> List[Dict]:
    """Permission denials off the final `result` event.

    This is the authoritative signal and the reason the old log could lie: a run
    whose every tool call was denied still reports subtype "success" with
    is_error false, because the *run* succeeded — only the work didn't. Verified
    against a real `claude -p --output-format stream-json` denial,
    2026-07-31: the entries are {tool_name, tool_use_id, tool_input}."""
    if row.get("type") != "result":
        return []
    denials = row.get("permission_denials")
    return [d for d in denials if isinstance(d, dict)] if isinstance(denials, list) else []


def _event_counts(row: Dict) -> Tuple[int, int]:
    """(vault-write attempts, failed tool results) in one stream-json row."""
    attempts = failures = 0
    blocks = (row.get("message") or {}).get("content") or []
    if not isinstance(blocks, list):
        return 0, 0
    for blk in blocks:
        if not isinstance(blk, dict):
            continue
        if blk.get("type") == "tool_use":
            cmd = str((blk.get("input") or {}).get("command") or "")
            if str(VAULT_WRITE) in cmd:
                attempts += 1
        elif blk.get("type") == "tool_result" and blk.get("is_error"):
            failures += 1
    return attempts, failures


def render_event(row: Dict) -> List[str]:
    """One stream-json row -> readable log lines.

    Tool calls and their results are the whole point: a denial has to be legible
    at a glance, because that is exactly what the old text-mode log hid."""
    out = []  # type: List[str]
    kind = row.get("type")
    blocks = (row.get("message") or {}).get("content") or []

    if kind == "assistant" and isinstance(blocks, list):
        for blk in blocks:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "text":
                text = str(blk.get("text") or "").strip()
                if text:
                    out.append(text)
            elif blk.get("type") == "tool_use":
                inp = blk.get("input") or {}
                detail = inp.get("command") or inp.get("file_path") or ""
                out.append("  CALL {}: {}".format(blk.get("name") or "?", str(detail)[:400]))

    elif kind == "user" and isinstance(blocks, list):
        for blk in blocks:
            if not isinstance(blk, dict) or blk.get("type") != "tool_result":
                continue
            body = " ".join(_text_of(blk.get("content")).split())
            marker = "  FAILED:" if blk.get("is_error") else "  ok:"
            out.append("{} {}".format(marker, body[:400] or "(no output)"))

    elif kind == "result":
        # Not gated on is_error: a run where every tool was denied still comes
        # back subtype "success", is_error false.
        for d in _result_denials(row):
            cmd = (d.get("tool_input") or {}).get("command") or ""
            out.append("  DENIED: {} {}".format(d.get("tool_name") or "?", str(cmd)[:300]).rstrip())
        if row.get("is_error"):
            out.append("  RESULT ERROR: {}".format(str(row.get("result") or "")[:400]))

    return out


def run_curator(argv: List[str]) -> None:
    """Child side. Runs the curator, renders its stream to stdout — which the
    parent has already pointed at this session's log — then states plainly
    whether anything actually reached the queue.

    The reconciliation is the reason this exists. Before it, a run whose
    vault-write calls were denied still ended with the model's cheerful summary
    and nothing else, so the log claimed three notes while the vault had none
    and nothing anywhere compared the two."""
    before = _queue_count()
    attempts = failures = rows = denied = 0

    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        print("curator: could not start: {}".format(exc), flush=True)
        return

    try:
        for raw in proc.stdout:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                print(line, flush=True)  # not JSON: keep it rather than drop it
                continue
            if not isinstance(row, dict):
                continue
            rows += 1
            a, f = _event_counts(row)
            attempts += a
            failures += f
            denied += len(_result_denials(row))
            for rendered in render_event(row):
                print(rendered, flush=True)
    except Exception as exc:
        print("curator: stream read failed: {}".format(exc), flush=True)
    finally:
        try:
            proc.stdout.close()  # type: ignore[union-attr]
        except Exception:
            pass

    try:
        rc = proc.wait(timeout=SPAWN_TIMEOUT_SECS + 60)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        rc = -1

    delta = _queue_count() - before

    print("", flush=True)
    if delta < 0:
        print("curator: RECONCILE UNCLEAR - queue shrank by {} mid-run (a sent/ "
              "prune?); {} write attempt(s), {} failed, exit {}."
              .format(-delta, attempts, failures, rc), flush=True)
    elif delta > 0:
        print("curator: OK - {} note(s) reached the queue ({} write attempt(s), "
              "{} failed tool call(s), exit {})."
              .format(delta, attempts, failures, rc), flush=True)
    elif attempts or denied:
        cause = ("{} call(s) were DENIED by the permission system"
                 .format(denied) if denied else
                 "{} tool call(s) reported failure".format(failures))
        print("curator: WROTE NOTHING - {} vault-write attempt(s) ran but the "
              "queue did not grow, so nothing was recorded no matter what the "
              "summary above says. {}. Exit {}."
              .format(attempts, cause, rc), flush=True)
    elif not rows or rc != 0:
        # An honest "nothing here" and a curator that never ran look identical
        # from the vault's side -- both write zero notes. Only this tells them
        # apart, which matters most exactly when a flag name has changed under
        # us and the whole thing has been quietly dead for weeks.
        print("curator: NO OUTPUT - produced {} parsed event(s), exit {}. The "
              "invocation itself may be broken (flag or model name), not the "
              "judgment.".format(rows, rc), flush=True)
    else:
        print("curator: nothing durable - no notes attempted (exit {})."
              .format(rc), flush=True)


def _prune_logs(max_age_days: int = 7) -> None:
    """Bound the log/digest dir — nothing here may fill a disk if forgotten."""
    try:
        cutoff = time.time() - max_age_days * 86400
        for entry in LOG_DIR.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
            except Exception:
                continue
    except Exception:
        pass


def _spawn_detached(argv: List[str], sid: str) -> None:
    """Fire-and-forget. The parent hook must not wait on this."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logf = open(LOG_DIR / ("{}.log".format(sid or "session")), "ab")
    except Exception:
        logf = subprocess.DEVNULL  # type: ignore[assignment]
    env = dict(os.environ)
    env[GUARD_ENV] = "1"  # child (and its own Stop hook) must not re-spawn
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            env=env,
            cwd=str(HOME),
            start_new_session=True,  # detach from this hook's process group
        )
    except Exception:
        pass


def _nudge_fallback(mutating: int, domain_hint: str) -> None:
    """When the background agent can't run, at least prompt a human."""
    half = "Infra (the home network)" if domain_hint == "infra" else "Software (craft knowledge)"
    msg = (
        "\U0001f4d3 This session made {n} changes and recorded nothing in the workshop "
        "vault, and the background curator is unavailable. If anything here is durable, "
        "record it in {half} via the vault-write skill."
    ).format(n=mutating, half=half)
    sys.stdout.write(json.dumps({"systemMessage": msg}) + "\n")


def _disabled() -> bool:
    return str(os.environ.get(ENABLE_ENV, "")).strip().lower() in ("0", "off", "false", "no")


def main() -> None:
    # Child mode, dispatched before the recursion guard on purpose: the runner
    # is spawned WITH the guard set (so the curator's own Stop does not
    # re-spawn), and would otherwise bail here before doing its job.
    if len(sys.argv) > 2 and sys.argv[1] == RUN_FLAG and sys.argv[2] == "--":
        run_curator(sys.argv[3:])
        return

    # Recursion guard, before any work: a curator child's own Stop lands here.
    if os.environ.get(GUARD_ENV):
        return

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    transcript = payload.get("transcript_path")
    session_id = str(payload.get("session_id") or "")
    cwd = str(payload.get("cwd") or "")
    if not transcript or not os.path.exists(transcript):
        return

    # No vault installed on this machine -> nothing to do, silently.
    if not VAULT_WRITE.exists():
        return

    # Once per session. A Stop fires on every turn; act at most once.
    stamp = STAMP_DIR / session_id / ".vault_curated"
    try:
        if stamp.exists():
            return
    except Exception:
        return

    rows = _read_transcript(transcript)
    if not rows:
        return

    mutating, infra = _counts(rows)
    if mutating < MIN_MUTATING_CALLS:
        return
    if _already_wrote(rows):
        return

    domain_hint = "infra" if infra >= 3 else "software"

    # Mark before acting: a spawn failure must not turn into a per-turn retry loop.
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(str(int(time.time())))
    except Exception:
        pass

    claude_bin = shutil.which("claude")
    if _disabled() or not claude_bin:
        _nudge_fallback(mutating, domain_hint)
        return

    digest = build_digest(rows)
    if not digest:
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        _prune_logs()
        digest_path = LOG_DIR / ("{}.digest.md".format(session_id or "session"))
        digest_path.write_text(digest, encoding="utf-8")
    except Exception:
        _nudge_fallback(mutating, domain_hint)
        return

    argv = build_runner_argv(build_curator_argv(digest_path, domain_hint, cwd, claude_bin))
    _spawn_detached(argv, session_id)
    # No systemMessage: the whole point is that the session doesn't wait or get noise.


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
