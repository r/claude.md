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

python3 - "$ctx" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": sys.argv[1],
}}))
PY
exit 0
