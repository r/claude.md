#!/usr/bin/env bash
# Regression test: no hook may take .git/index.lock in your repos.
#
# Why this exists: `git status` looks read-only but rewrites the index to cache
# refreshed stat info, holding .git/index.lock while it does. The statusline and
# the Stop/PostToolUse hooks run constantly and on short timeouts; a SIGKILL in
# that window leaves a zero-byte .git/index.lock behind and every later git
# command in that repo fails with "Unable to create '.../index.lock'". It bit
# three times before GIT_OPTIONAL_LOCKS=0 was added to these hooks.
#
# The assertion is the *cause*, not the symptom: a hook that never rewrites the
# index never took the lock, so there is nothing to orphan no matter when it
# dies. Checking "did a lock get left behind" instead would be a race, and would
# pass by luck on a fast machine.
#
# Synthetic scratch repo, no network, never touches a real repo of yours.
set -u

HOOKS="$(cd "$(dirname "$0")" && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL %s\n     %s\n' "$1" "$2"; fail=$((fail+1)); }

# A repo whose index is stale: every tracked file's mtime is newer than the
# index, which is precisely what makes `git status` want to rewrite it.
mkrepo() {
  local r="$1"
  mkdir -p "$r"
  git -C "$r" init -q
  git -C "$r" config user.email test@example.com
  git -C "$r" config user.name test
  local i
  for i in 1 2 3 4 5; do echo "hello $i" > "$r/f$i.txt"; done
  echo "# doc" > "$r/README.md"
  git -C "$r" add -A >/dev/null 2>&1
  git -C "$r" commit -qm init
  stale "$r"
}

stale() { # bump tracked mtimes past the index's own
  local r="$1"
  sleep 1.1
  touch "$r"/f*.txt "$r/README.md"
  rm -f "$r/.git/index.lock" "$r/.git/.doc_drift_nudged"
}

index_hash() { md5sum "$1/.git/index" | cut -d' ' -f1; }

# assert_lock_free <label> <repo> <command string, run with cwd=$repo>
assert_lock_free() {
  local label="$1" repo="$2" cmd="$3"
  stale "$repo"
  local before after
  before=$(index_hash "$repo")
  ( cd "$repo" && eval "$cmd" ) >/dev/null 2>&1
  after=$(index_hash "$repo")
  if [ "$before" != "$after" ]; then
    bad "$label does not rewrite the index" \
        "index changed => the hook took .git/index.lock; set GIT_OPTIONAL_LOCKS=0"
  elif [ -e "$repo/.git/index.lock" ]; then
    bad "$label leaves no index.lock" "a .git/index.lock survived the run"
  else
    ok "$label is lock-free"
  fi
}

echo "git index locks"

REPO="$TMP/repo"
mkrepo "$REPO"

# --- guard the test itself --------------------------------------------------
# If git ever stops refreshing the index here, every case below would pass
# vacuously. Prove the detector still detects before trusting it.
stale "$REPO"
h=$(index_hash "$REPO")
git -C "$REPO" status --porcelain >/dev/null 2>&1
if [ "$h" != "$(index_hash "$REPO")" ]; then
  ok "control: a plain 'git status' DOES rewrite the index"
else
  bad "control: a plain 'git status' DOES rewrite the index" \
      "detector is blind on this git ($(git --version)); the cases below prove nothing"
fi

# and that the documented fix is what suppresses it
stale "$REPO"
h=$(index_hash "$REPO")
GIT_OPTIONAL_LOCKS=0 git -C "$REPO" status --porcelain >/dev/null 2>&1
if [ "$h" = "$(index_hash "$REPO")" ]; then
  ok "control: GIT_OPTIONAL_LOCKS=0 suppresses the rewrite"
else
  bad "control: GIT_OPTIONAL_LOCKS=0 suppresses the rewrite" \
      "this git ignores GIT_OPTIONAL_LOCKS; the hooks need a different fix"
fi

# --- the hooks that shell out to git ----------------------------------------
assert_lock_free "statusline.sh" "$REPO" \
  "printf '{\"model\":{\"display_name\":\"Opus\"},\"workspace\":{\"current_dir\":\"$REPO\"}}' | '$HOOKS/statusline.sh'"

assert_lock_free "session_start.sh" "$REPO" \
  "printf '{}' | '$HOOKS/session_start.sh'"

assert_lock_free "doc_drift.sh" "$REPO" \
  "printf '{}' | '$HOOKS/doc_drift.sh'"

assert_lock_free "checkpoint.py" "$REPO" \
  "printf '{\"session_id\":\"lock-test\",\"hook_event_name\":\"Stop\",\"cwd\":\"$REPO\"}' | CLAUDE_CHECKPOINT_DIR='$TMP/checkpoints' python3 '$HOOKS/checkpoint.py'"

echo
if [ "$fail" -eq 0 ]; then
  echo "all git-lock tests passed ($pass checks)"
  exit 0
fi
echo "$fail FAILED, $pass passed"
exit 1
