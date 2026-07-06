#!/usr/bin/env bash
# Deterministic tests for morph-mirror. No network, no wall-clock assertions.
# The morph-present path is exercised with a FAKE `morph` on PATH that records
# its argv, so we can verify the mirror call without installing real morph.
set -u

HELPER="$(cd "$(dirname "$0")" && pwd)/morph-mirror"
fails=0
check() { # desc, actual-condition already evaluated via $?
  if [ "$1" -eq 0 ]; then printf 'ok   — %s\n' "$2"; else printf 'FAIL — %s\n' "$2"; fails=$((fails+1)); fi
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# A fake `morph` that appends its args to $RECORD, on an isolated bin dir.
fakebin="$work/fakebin"; mkdir -p "$fakebin"
cat >"$fakebin/morph" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "$MORPH_RECORD"
EOF
chmod +x "$fakebin/morph"

# --- case A: not a git repo → silent no-op, exit 0
a="$work/plain"; mkdir -p "$a"
out=$(cd "$a" && "$HELPER" "hello" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ]; check $? "not a git repo: silent no-op"

# --- case B: git repo, no .morph → silent no-op, exit 0
b="$work/git-only"; mkdir -p "$b"; git -C "$b" init -q
out=$(cd "$b" && "$HELPER" "hello" 2>&1); rc=$?
[ $rc -eq 0 ] && [ -z "$out" ]; check $? "git repo without .morph: silent no-op"

# --- case C: git repo + .morph/, morph NOT on PATH → loud warning, exit 0
c="$work/morph-missing"; mkdir -p "$c/.morph"; git -C "$c" init -q
out=$(cd "$c" && PATH="/usr/bin:/bin" "$HELPER" "hello" 2>&1); rc=$?
[ $rc -eq 0 ] && printf '%s' "$out" | grep -q "not installed"; check $? "morph project, morph absent: warns + exit 0"

# --- case D: git repo + .morph/, fake morph present → mirrors `commit -m <msg>`
d="$work/morph-present"; mkdir -p "$d/.morph"; git -C "$d" init -q
export MORPH_RECORD="$work/record.txt"; : >"$MORPH_RECORD"
out=$(cd "$d" && PATH="$fakebin:$PATH" "$HELPER" "my message" 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q "commit -m my message" "$MORPH_RECORD"; check $? "morph project, morph present: mirrors commit"

# --- case E: empty message → refuses, exit 0, no morph call
: >"$MORPH_RECORD"
out=$(cd "$d" && PATH="$fakebin:$PATH" "$HELPER" "" 2>&1); rc=$?
[ $rc -eq 0 ] && printf '%s' "$out" | grep -q "empty message" && [ ! -s "$MORPH_RECORD" ]; check $? "empty message: refuses, no mirror"

echo
if [ "$fails" -eq 0 ]; then echo "ok — all morph-mirror cases passed"; else echo "FAILED: $fails case(s)"; exit 1; fi
