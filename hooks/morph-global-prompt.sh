#!/usr/bin/env bash
# GLOBAL Claude Code hook: UserPromptSubmit.
#
# Records EVERY Claude Code session into a single silent central morph store
# (~/.claude/morph-traces), regardless of the working directory and regardless
# of whether that directory was ever `morph init`'d. This is deliberately
# separate from any .morph a project may have of its own — the two never
# collide (different repos), so a project's own morph workflow is untouched.
#
# This hook only appends the prompt to a pending file; the Stop hook assembles
# and imports the trace. It must NEVER fail or stall a Claude session: any
# error is swallowed and we exit 0.
#
# Companion: morph-global-stop.sh
set -u

# The silent central store. Everything lands here, keyed by session + cwd.
MORPH_STORE="${MORPH_TRACES_STORE:-$HOME/.claude/morph-traces}"

# Fast bail (cheap, before paying python startup): if the central store isn't
# present, this machine isn't using global trace capture — do nothing. This keeps
# the hook near-zero-cost for anyone (e.g. public-config users) who hasn't opted in.
[ -d "$MORPH_STORE/.morph" ] || exit 0

exec 3<&0  # preserve original stdin before the heredoc replaces it
python3 - "$MORPH_STORE" << 'PY' || true
import json, os, sys
from pathlib import Path
from datetime import datetime

store = Path(sys.argv[1])
morph_dir = store / ".morph"
# If the central store is missing, silently do nothing (never block Claude).
if not morph_dir.is_dir():
    sys.exit(0)

try:
    raw = os.fdopen(3).read().strip()
except Exception:
    sys.exit(0)
if not raw:
    sys.exit(0)
try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

cwd = payload.get("cwd") or "."
session_id = payload.get("session_id") or "unknown"
prompt = payload.get("prompt") or ""
model_name = payload.get("model") or os.environ.get("ANTHROPIC_MODEL") or ""
ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

try:
    hooks_dir = morph_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "logs").mkdir(parents=True, exist_ok=True)
    with open(hooks_dir / "logs" / "global-invoke.log", "a") as f:
        f.write(f"{ts} UserPromptSubmit session_id={session_id} cwd={cwd}\n")
    pending = hooks_dir / f"pending-{session_id}.jsonl"
    line = json.dumps({"ts": ts, "prompt": prompt, "model": model_name, "cwd": cwd}) + "\n"
    with open(pending, "a") as f:
        f.write(line)
except Exception as e:
    sys.stderr.write(f"morph-global-prompt: {e}\n")
    sys.exit(0)
PY
exit 0
