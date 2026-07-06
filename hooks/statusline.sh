#!/usr/bin/env bash
# Statusline:  host │ ~/dir ⎇ branch* │ Model
# Reads Claude Code's session JSON on stdin. Always prints something; never fails.
set +e

input=$(cat)
model=$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print((d.get("model") or {}).get("display_name",""))
except Exception: print("")' 2>/dev/null)
cwd=$(printf '%s' "$input" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin); print((d.get("workspace") or {}).get("current_dir") or d.get("cwd") or "")
except Exception: print("")' 2>/dev/null)
[ -z "$cwd" ] && cwd=$(pwd)

host=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo "?")
short=$(printf '%s' "$cwd" | sed "s|^$HOME|~|")

git_part=""
if br=$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null); then
  star=""; [ -n "$(git -C "$cwd" status --porcelain 2>/dev/null | head -1)" ] && star="*"
  git_part=" ⎇ ${br}${star}"
fi

printf '%s │ %s%s │ %s' "$host" "$short" "$git_part" "${model:-Claude}"
