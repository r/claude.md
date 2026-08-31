#!/usr/bin/env bash
# Regression test: CLAUDE_HOOKS_OFF silences the hook it names, and CANNOT
# silence the guardrail.
#
# Why this exists at all: the switch is three duplicated lines in nine files,
# and the failure mode of a kill switch is silent in both directions. A typo in
# one hook's `case` pattern leaves that hook running when you asked it to stop —
# annoying. A stray `guardrail` in the pattern list disarms the deterministic
# half of the "never do these" list with nothing in the transcript to say so —
# not annoying. So the assertions below are paired: each hook goes quiet when
# named, and the guardrail keeps biting no matter what it is named.
#
# The tests are non-vacuous where it is cheap to make them so: for session_start
# and statusline we assert the hook produces output WITHOUT the switch and none
# WITH it, so a hook that was already silent for an unrelated reason can't pass
# by accident. For the conditional hooks (doc_drift, morph, vault_*) the honest
# assertion is the weaker one — exit 0 and no output — plus a grep that the
# guard is actually present and names the right id.
#
# No network, no real repo, no ~/.claude state touched.
set -u

HOOKS="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0; rc=0; out=""
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

# Every hook reads a JSON payload on stdin. This one is well-formed enough that
# a hook which is NOT switched off will get past its own parsing and do work.
payload() {
  printf '{"session_id":"testsession","cwd":"%s","transcript_path":"%s","hook_event_name":"Stop","tool_name":"Bash","tool_input":{"command":"echo hi"}}' \
    "$TMP" "$TMP/transcript.jsonl"
}
: > "$TMP/transcript.jsonl"

# run <env-value-or-empty> <hook>: sets $rc and $out.
# Deliberately NOT `out=$(run ...)` — a command substitution runs the function in
# a subshell, so the hook's exit code would be lost and $rc would read as unset.
run() {
  local envspec="$1" hook="$2"
  if [ -n "$envspec" ]; then
    payload | env "CLAUDE_HOOKS_OFF=$envspec" HOME="$TMP" "$HOOKS/$hook" >"$TMP/out" 2>/dev/null
  else
    payload | env -u CLAUDE_HOOKS_OFF HOME="$TMP" "$HOOKS/$hook" >"$TMP/out" 2>/dev/null
  fi
  rc=$?
  out=$(cat "$TMP/out")
}

# --- 1. every switchable hook exits 0 and says nothing when named -------------
# id                     file
switchable="
session_start          session_start.sh
py_autoformat          py_autoformat.sh
doc_drift              doc_drift.sh
statusline             statusline.sh
morph_global_stop      morph-global-stop.sh
morph_global_prompt    morph-global-prompt.sh
checkpoint             checkpoint.py
vault_curator          vault_curator.py
vault_nudge            vault_nudge.py
"

while read -r id file; do
  [ -n "${id:-}" ] || continue
  [ -f "$HOOKS/$file" ] || { bad "$file present" "missing"; continue; }

  run "$id" "$file"
  if [ "$rc" -ne 0 ]; then
    bad "$file exits 0 when switched off" "exit $rc"
  elif [ -n "$out" ]; then
    bad "$file silent when switched off" "printed: $(printf '%s' "$out" | head -c 120)"
  else
    ok "$file off via CLAUDE_HOOKS_OFF=$id"
  fi

  run "all" "$file"
  if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
    ok "$file off via CLAUDE_HOOKS_OFF=all"
  else
    bad "$file off via CLAUDE_HOOKS_OFF=all" "exit $rc, printed: $(printf '%s' "$out" | head -c 120)"
  fi
done <<EOF
$switchable
EOF

# --- 2. non-vacuous: these two are loud unless switched off -------------------
for file in session_start.sh statusline.sh; do
  run "" "$file"
  if [ -n "$out" ]; then
    ok "$file actually produces output when NOT switched off (test is non-vacuous)"
  else
    bad "$file actually produces output when NOT switched off" \
        "printed nothing either way — the 'silent when off' assertion above proves nothing"
  fi
done

# --- 3. the guardrail is NOT switchable --------------------------------------
# A push to main of a human-origin repo must be blocked. If any of these three
# spellings gets it through, the switch has become an injection's off-button.
guard_payload='{"session_id":"t","cwd":"'"$TMP"'","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git push origin main"}}'

for spelling in guardrail all "checkpoint,guardrail,doc_drift" "GUARDRAIL" " all "; do
  out=$(printf '%s' "$guard_payload" | env "CLAUDE_HOOKS_OFF=$spelling" "$HOOKS/guardrail.py" 2>/dev/null)
  if printf '%s' "$out" | grep -q '"permissionDecision"[[:space:]]*:[[:space:]]*"ask"'; then
    ok "guardrail still fires with CLAUDE_HOOKS_OFF='$spelling'"
  else
    bad "guardrail still fires with CLAUDE_HOOKS_OFF='$spelling'" \
        "the guardrail was DISARMED by an env var — got: $(printf '%s' "$out" | head -c 200)"
  fi
done

# Belt and braces: no hook file may even mention guardrail as a switchable id.
if grep -l 'CLAUDE_HOOKS_OFF' "$HOOKS"/*.sh "$HOOKS"/*.py 2>/dev/null \
     | xargs grep -n ',guardrail,' 2>/dev/null | grep -v test_hookswitch; then
  bad "no hook treats 'guardrail' as a switchable id" "found a ,guardrail, pattern above"
else
  ok "no hook treats 'guardrail' as a switchable id"
fi

# --- 4. matching is exact, and tolerates spaces -------------------------------
# A prefix must not match: CLAUDE_HOOKS_OFF=doc leaves doc_drift running.
run "doc" "session_start.sh"
if [ -n "$out" ]; then
  ok "a prefix ('doc') does not match a longer id — matching is exact"
else
  bad "a prefix ('doc') does not match a longer id" "session_start went silent for an unrelated id"
fi

run "checkpoint, session_start" "session_start.sh"
if [ "$rc" -eq 0 ] && [ -z "$out" ]; then
  ok "spaces in the list are tolerated"
else
  bad "spaces in the list are tolerated" "'checkpoint, session_start' did not switch session_start off"
fi

# --- 5. an unset switch leaves every hook ON ---------------------------------
missing=0
for f in session_start.sh statusline.sh; do
  run "" "$f"; [ -z "$out" ] && missing=1
done
if [ "$missing" -eq 0 ]; then
  ok "an unset CLAUDE_HOOKS_OFF leaves hooks ON (fails in the safe direction)"
else
  bad "an unset CLAUDE_HOOKS_OFF leaves hooks ON" "a hook was silent with no switch set"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "ok — $pass hookswitch cases passed"
  exit 0
fi
echo "FAILED — $fail of $((pass+fail)) hookswitch cases"
exit 1
