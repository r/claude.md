#!/usr/bin/env bash
# Statusline:  host │ ~/dir ⎇ branch* │ Model
# Reads Claude Code's session JSON on stdin. Always prints something; never fails.
set +e

# Kill switch -- CLAUDE_HOOKS_OFF=<id>[,<id>...] or =all silences this hook.
# Full rationale, and why guardrail.py has none, is in doc_drift.sh.
_hoff=",${CLAUDE_HOOKS_OFF:-},"; _hoff=${_hoff// /}
case "$_hoff" in *,all,*|*,statusline,*) exit 0 ;; esac

# The statusline runs constantly and on a short timeout — a SIGKILL mid-`git
# status` orphans a zero-byte .git/index.lock in whatever repo you're in, and
# every later git command then refuses to run. `git status` looks read-only but
# rewrites the index to cache refreshed stat info, taking the lock to do it.
# GIT_OPTIONAL_LOCKS=0 skips that refresh (git(1); git-status(1) recommends
# exactly this for "scripts running status in the background"). Cost: a file
# that is only stat-dirty may show the * for one refresh. Never take a lock we
# might not live long enough to release.
export GIT_OPTIONAL_LOCKS=0

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
