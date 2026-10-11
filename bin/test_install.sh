#!/usr/bin/env bash
# install.sh into an empty home: the authored config lands, the generated
# settings parse, every hook is executable, the personal templates are seeded
# once and never overwritten, and a second run changes nothing.
set -u
HERE=$(cd -- "$(dirname -- "$0")/.." && pwd)
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
pass=0; fail=0
check() { if [ "$2" = "$3" ]; then echo "  ok    $1"; pass=$((pass+1)); else echo "  FAIL  $1: want [$2] got [$3]"; fail=$((fail+1)); fi; }

D="$W/home/.claude"
out=$(HOME="$W/home" bash "$HERE/install.sh" "$D" 2>&1); rc=$?
check "install.sh exits 0 into an empty home" 0 "$rc"
for f in CLAUDE.md settings.json README.md INSTALL.md rules/software.md rules/containment.md hooks/session_start.sh hooks/statusline.sh bin/run-tests; do
    check "installed: $f" yes "$([ -e "$D/$f" ] && echo yes || echo no)"
done
check "settings.json is JSON" 0 "$(python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$D/settings.json" >/dev/null 2>&1; echo $?)"
check "every hook settings.json names exists and is executable" "" \
    "$(python3 - "$D" <<'PY'
import json, os, re, sys
d = sys.argv[1]
s = json.load(open(os.path.join(d, "settings.json")))
cmds = []
def walk(x):
    if isinstance(x, dict):
        if x.get("type") == "command" and "command" in x: cmds.append(x["command"])
        for v in x.values(): walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)
walk(s)
bad = []
for c in cmds:
    path = c.split()[0].replace("$HOME/.claude", d)
    if not (os.path.isfile(path) and os.access(path, os.X_OK)): bad.append(c)
print(" ".join(bad))
PY
)"
check "the personal templates were seeded" yes "$([ -f "$D/rules/infra.md" ] && [ -f "$D/rules/voice.md" ] && echo yes || echo no)"
echo "mine" > "$D/rules/voice.md"
HOME="$W/home" bash "$HERE/install.sh" "$D" >/dev/null 2>&1
check "a second run keeps a personalised template" mine "$(cat "$D/rules/voice.md")"
check "and leaves the config as installed" yes "$(diff -rq "$HERE/hooks" "$D/hooks" >/dev/null && echo yes || echo no)"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
