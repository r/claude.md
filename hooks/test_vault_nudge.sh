#!/usr/bin/env bash
# Tests for vault_nudge.py — the Stop hook that nudges when a session did
# durable work but recorded nothing in the workshop vault.
#
# Synthetic transcripts, no network, no real vault, no real checkpoint dir.
# Every case here is one that actually bit during development or one that would
# make the nudge either useless (never fires) or hated (fires constantly).
set -u

HOOK="$(dirname "$0")/vault_nudge.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export CLAUDE_CHECKPOINT_DIR="$TMP/checkpoints"

pass=0; fail=0
ok()   { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  FAIL %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

# build_transcript <file> <n_bash> <bash_command> [extra_json_line]
build_transcript() {
  local f=$1 n=$2 cmd=$3 extra=${4:-}
  : > "$f"
  echo '{"timestamp":"2026-07-20T19:00:00.000Z","message":{"role":"user","content":"go"}}' >> "$f"
  for i in $(seq 1 "$n"); do
    python3 - "$f" "$cmd" <<'PY'
import json,sys
row={"timestamp":"2026-07-20T19:0%d:00.000Z"%0,"message":{"role":"assistant","content":[
    {"type":"tool_use","name":"Bash","input":{"command":sys.argv[2]}}]}}
open(sys.argv[1],"a").write(json.dumps(row)+"\n")
PY
  done
  [ -n "$extra" ] && echo "$extra" >> "$f"
  return 0
}

run_hook() { # run_hook <transcript> <session_id> -> stdout
  printf '{"transcript_path":"%s","session_id":"%s"}' "$1" "$2" | python3 "$HOOK"
}

echo "vault_nudge.py"

# --- fires on a working session that recorded nothing -----------------------
build_transcript "$TMP/work.jsonl" 10 "echo building a thing"
out=$(run_hook "$TMP/work.jsonl" s-work)
case "$out" in
  *systemMessage*vault*) ok "fires after substantive work with no vault write" ;;
  *) bad "fires after substantive work with no vault write" "got: '${out:-<silent>}'" ;;
esac

# --- silent on a session that barely touched anything -----------------------
build_transcript "$TMP/quiet.jsonl" 2 "echo just looking"
out=$(run_hook "$TMP/quiet.jsonl" s-quiet)
[ -z "$out" ] && ok "silent on a low-activity session" \
  || bad "silent on a low-activity session" "got: $out"

# --- silent when the session already wrote to the vault ---------------------
build_transcript "$TMP/wrote.jsonl" 10 '~/.claude/bin/vault-write --type pattern --domain software --title x'
out=$(run_hook "$TMP/wrote.jsonl" s-wrote)
[ -z "$out" ] && ok "silent when the session already wrote a note" \
  || bad "silent when the session already wrote a note" "got: $out"

# --- silent when the vault-write SKILL was invoked --------------------------
build_transcript "$TMP/skill.jsonl" 10 "echo work" \
  '{"timestamp":"2026-07-20T19:30:00.000Z","message":{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"vault-write"}}]}}'
out=$(run_hook "$TMP/skill.jsonl" s-skill)
[ -z "$out" ] && ok "silent when the vault-write skill was invoked" \
  || bad "silent when the vault-write skill was invoked" "got: $out"

# --- REGRESSION: a mere mention is not a write ------------------------------
# `ls ~/.claude/skills/vault-write/` contains the string; counting it as a
# write silenced the nudge on every session that looked at the skill.
build_transcript "$TMP/mention.jsonl" 10 "ls ~/.claude/skills/vault-write/"
out=$(run_hook "$TMP/mention.jsonl" s-mention)
case "$out" in
  *systemMessage*) ok "regression: mentioning vault-write does not count as writing" ;;
  *) bad "regression: mentioning vault-write does not count as writing" "hook was silent" ;;
esac

# --- domain routing ---------------------------------------------------------
build_transcript "$TMP/infra.jsonl" 10 "ssh web-01 docker compose up -d"
out=$(run_hook "$TMP/infra.jsonl" s-infra)
case "$out" in
  *Infra*) ok "routes host/docker work to the Infra half" ;;
  *) bad "routes host/docker work to the Infra half" "got: ${out:-<silent>}" ;;
esac

build_transcript "$TMP/soft.jsonl" 10 "uv run pytest tests/"
out=$(run_hook "$TMP/soft.jsonl" s-soft)
case "$out" in
  *Software*) ok "routes repo work to the Software half" ;;
  *) bad "routes repo work to the Software half" "got: ${out:-<silent>}" ;;
esac

# --- once per session, not once per Stop ------------------------------------
build_transcript "$TMP/twice.jsonl" 10 "echo work"
first=$(run_hook "$TMP/twice.jsonl" s-twice)
second=$(run_hook "$TMP/twice.jsonl" s-twice)
if [ -n "$first" ] && [ -z "$second" ]; then
  ok "nudges once per session, not on every Stop"
else
  bad "nudges once per session, not on every Stop" "first='$first' second='$second'"
fi

# --- fail-open: never eat a Stop --------------------------------------------
echo 'not json at all' | python3 "$HOOK" >/dev/null 2>&1
[ $? -eq 0 ] && ok "fail-open on malformed stdin" || bad "fail-open on malformed stdin" "nonzero exit"

run_hook "$TMP/does-not-exist.jsonl" s-missing >/dev/null 2>&1
[ $? -eq 0 ] && ok "fail-open on a missing transcript" || bad "fail-open on a missing transcript" "nonzero exit"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
