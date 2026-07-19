#!/usr/bin/env bash
# SessionStart hook — inject host/git/docker context so Claude always knows
# which machine it's on. Handy the moment you work across more than one box
# (SSH, servers, a homelab). Read-only; always exits 0.
set +e

host=$(hostname 2>/dev/null || echo unknown)
ips=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(10|192\.168|172\.)' | head -4 | tr '\n' ',' | sed 's/,$//; s/,/, /g')
cwd=$(pwd)

git_line=""
if br=$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null); then
  dirty=""; [ -n "$(git -C "$cwd" status --porcelain 2>/dev/null | head -1)" ] && dirty=", dirty"
  git_line=" · git: ${br}${dirty}"
fi

docker_line=""
if command -v docker >/dev/null 2>&1; then
  n=$(timeout 3 docker ps -q 2>/dev/null | wc -l | tr -d ' ')
  [ -n "$n" ] && [ "$n" != "0" ] && docker_line=" · docker: ${n} containers up"
fi

ctx="Host context: you are on ${host} (${ips}) in ${cwd}${git_line}${docker_line}. If this is a multi-host setup, confirm this is the intended machine before any host-mutating command."

# Assemble morph traces for sessions that died before their Stop hook ran.
# Detached and fully backgrounded: starting a session must never wait on morph,
# and the recovery script self-limits (6h min age, 5 per run, lockfile).
if [ -x "$HOME/.claude/bin/morph-recover-orphans" ]; then
  ( "$HOME/.claude/bin/morph-recover-orphans" >/dev/null 2>&1 & ) >/dev/null 2>&1
fi

# Append a continuity line if a previous session in THIS cwd died without a
# clean Stop. checkpoint.py only ever writes state=completed from its Stop hook,
# so anything still "active" is an interruption. Surfacing it here is the whole
# point of checkpointing — a record nobody reads is not resilience.
python3 - "$ctx" "$cwd" <<'PY' 2>/dev/null || true
import json, os, sys
from datetime import datetime, timedelta
from pathlib import Path

ctx, cwd = sys.argv[1], sys.argv[2]
root = Path(os.environ.get("CLAUDE_CHECKPOINT_DIR") or (Path.home() / ".claude" / "checkpoints"))
best = None
try:
    cutoff = datetime.utcnow() - timedelta(days=7)
    for state_file in root.glob("*/state.json"):
        try:
            with state_file.open() as fh:
                s = json.load(fh)
        except Exception:
            continue
        if not isinstance(s, dict) or s.get("state") == "completed":
            continue
        if s.get("cwd") != cwd:
            continue
        try:
            when = datetime.strptime(s.get("updatedAt", ""), "%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue
        if when < cutoff:
            continue
        if best is None or when > best[0]:
            best = (when, s)
except Exception:
    best = None

# Vault queue health. A queue that has silently stopped draining looks exactly
# like a queue with nothing to do, so say something when it needs a human.
try:
    vq = Path(os.environ.get("VAULT_QUEUE_DIR") or (Path.home() / ".claude" / "vault-queue"))
    dead = list((vq / "dead").glob("*.md")) if (vq / "dead").is_dir() else []
    over = (vq / "OVER_CAP").exists()
    pending_n = len(list(vq.glob("*.md"))) if vq.is_dir() else 0
    notes = []
    if dead:
        notes.append("{} vault note(s) were REJECTED by the inbox and are in "
                     "{}/dead/ — they need a look".format(len(dead), vq))
    if over:
        notes.append("the vault queue is over its size cap: nothing was dropped, but new "
                     "entries are being refused until it drains "
                     "(`python3 ~/.claude/bin/vault-spooler.py --status`)")
    elif pending_n > 50:
        notes.append("{} vault note(s) are queued and undelivered — the spooler may not "
                     "be draining".format(pending_n))
    if notes:
        ctx = ctx + " Vault queue: " + "; ".join(notes) + "."
except Exception:
    pass

if best is not None:
    when, s = best
    detail = s.get("detail") or "unknown"
    bits = "A previous session in this directory ended without a clean Stop ({}Z, {} turn(s)). Last activity: {!r}.".format(
        when.strftime("%Y-%m-%d %H:%M"), s.get("turns", "?"), detail)
    if s.get("needs"):
        bits += " It recorded needs: {!r}.".format(s["needs"])
    if s.get("dirty"):
        bits += " The working tree was dirty at the time."
    bits += " Full record: ~/.claude/checkpoints/{}/ (state.json + timeline.jsonl). Consider /resume before starting new work.".format(s.get("resumeSessionId", ""))
    ctx = ctx + " " + bits

print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": ctx,
}}))
PY
exit 0
