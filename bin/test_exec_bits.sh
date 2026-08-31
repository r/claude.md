#!/usr/bin/env bash
# Regression test: git's RECORDED mode must match what a file actually is.
#
# WHY THIS EXISTS: this repo is versioned from a home directory with
# core.fileMode=false. That is the correct setting there -- the filesystem's
# exec bits are not trustworthy across it -- but it has a nasty consequence:
# git records every newly added file as 100644 no matter how it sits on disk.
# `chmod +x` locally, `git add`, and git quietly stores it as non-executable.
#
# Nothing notices, because the machine that added the file still has the bit
# set on disk. It only breaks for the next person: a fresh `git clone` checks
# each file out at the mode git RECORDS, so a hook stored 100644 lands
# unexecutable and dies with "permission denied" on every session. The install
# script masked this for years by blind-chmod'ing everything it copied, which
# is exactly why nobody found it -- the mask hid the fault instead of the fault
# hiding itself.
#
# So the assertion is on the recorded mode, read from the index, never from the
# filesystem. A shebang means executable; a systemd unit and a data file mean
# not. Anything else is a bug that will only ever hurt someone else.
#
# Fix for a failure:  git update-index --chmod=+x <file>
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "  ·    not a git checkout — nothing to verify, skipping"
  echo "ok — 0 exec-bit cases (skipped)"
  exit 0
fi

pass=0; fail=0
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

# `git ls-files -s` prints "<mode> <sha> <stage>\t<path>". Parse it once, here,
# rather than shelling out to git again per file -- the naive version ran one
# subprocess per tracked file and took longer than the rest of the suite.
modes=$(git -C "$ROOT" ls-files -s | sed 's/^\([0-9]*\) [0-9a-f]* [0-9]*\t/\1 /')

# --- 1. a shebang must be recorded executable --------------------------------
# Mode 120000 is a symlink, and it is skipped in every check below. A hook can
# legitimately be a symlink into another project; git stores the link itself,
# the exec bit lives on the target, and `chmod +x` on the link is meaningless
# (git refuses it outright). Following the link with `head` and then demanding
# 100755 asserts something that can never be true -- which is exactly what the
# first draft of this test did.
missing=""
while read -r mode path; do
  [ -n "${path:-}" ] || continue
  [ "$mode" = "100755" ] || [ "$mode" = "120000" ] && continue
  [ -f "$ROOT/$path" ] || continue
  head -1 "$ROOT/$path" 2>/dev/null | grep -q '^#!' && missing="$missing $path"
done <<EOF
$modes
EOF

if [ -z "$missing" ]; then
  ok "every tracked file with a shebang is recorded 100755"
else
  bad "every tracked file with a shebang is recorded 100755" \
      "recorded 100644:$missing  — fix: git update-index --chmod=+x <file>"
fi

# --- 2. things that must NOT be executable -----------------------------------
# A systemd unit with the exec bit set is a unit systemd will still read, so
# this one is tidiness rather than breakage -- but it is the other half of the
# same claim, and a rule enforced in one direction only is half a rule.
extra=""
while read -r mode path; do
  [ "$mode" = "100755" ] || continue
  case "$path" in
    *.service|*.md|*.json|*.example|*.txt) extra="$extra $path" ;;
  esac
done <<EOF
$modes
EOF

if [ -z "$extra" ]; then
  ok "no unit or data file is recorded executable"
else
  bad "no unit or data file is recorded executable" \
      "recorded 100755:$extra  — fix: git update-index --chmod=-x <file>"
fi

# --- 3. the wired hooks specifically -----------------------------------------
# The general rule above already covers these. They get their own assertion
# because they are the ones whose failure is silent and total: a hook that
# cannot execute does not warn, it simply never runs, and the guarantee it was
# supposed to provide quietly becomes a suggestion.
broken=""
while read -r mode path; do
  case "$path" in hooks/*.sh|hooks/*.py) ;; *) continue ;; esac
  case "$path" in hooks/guardrail_rules.py) continue ;; esac   # imported, never executed
  [ "$mode" = "100755" ] || [ "$mode" = "120000" ] && continue
  broken="$broken $path"
done <<EOF
$modes
EOF

if [ -z "$broken" ]; then
  ok "every hook is recorded executable"
else
  bad "every hook is recorded executable" \
      "these would land unexecutable in a fresh clone:$broken"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "ok — $pass exec-bit cases passed"
  exit 0
fi
echo "FAILED — $fail of $((pass+fail)) exec-bit cases"
exit 1
