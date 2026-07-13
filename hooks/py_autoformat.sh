#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit) — auto ruff format + check --fix on edited
# .py files, but ONLY inside a project that opts into ruff (has pyproject/ruff
# config). Silent, and always exits 0 (never blocks or fails the turn).
set +e

input=$(cat)
file=$(printf '%s' "$input" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null)

case "$file" in
  *.py) : ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# only format where a project opts into ruff
d=$(dirname "$file"); has_cfg=""
for _ in 1 2 3 4 5 6 7 8; do
  if [ -f "$d/pyproject.toml" ] || [ -f "$d/ruff.toml" ] || [ -f "$d/.ruff.toml" ]; then has_cfg=1; break; fi
  [ "$d" = "/" ] && break
  d=$(dirname "$d")
done
[ -n "$has_cfg" ] || exit 0

if command -v ruff >/dev/null 2>&1; then RUFF="ruff"
elif command -v uv >/dev/null 2>&1; then RUFF="uv run ruff"
else exit 0; fi

timeout 30 $RUFF format "$file"    >/dev/null 2>&1
timeout 30 $RUFF check --fix "$file" >/dev/null 2>&1
exit 0
