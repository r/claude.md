#!/usr/bin/env bash
# Stop hook — nudge when CODE has drifted ahead of DOCS. Suggest-mode only: it
# never runs the steward, it just surfaces a reminder to consider /doc-sweep.
#
# "Drift" = how much non-doc, non-test change has landed since docs were last
# touched. With atomic commits (code+docs together) this stays quiet; it speaks
# up exactly when code has outrun the docs. Rate-limited to once per 15 min/repo.
set +e

# Every git call below only reads state, so none may take .git/index.lock — a
# Stop hook killed mid-run would orphan it and wedge every later git command in
# the repo. This covers `git status`; see the note at `changed=` for the working
# -tree diff, which needs more than the env var.
export GIT_OPTIONAL_LOCKS=0

cwd=$(pwd)
root=$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0   # git repos only

# rate-limit per repo
stamp="$root/.git/.doc_drift_nudged"
now=$(date +%s 2>/dev/null || echo 0)
last=0; [ -f "$stamp" ] && last=$(cat "$stamp" 2>/dev/null || echo 0)
[ $(( now - last )) -lt 900 ] && exit 0

# last commit that touched any docs; if the repo has no docs, nothing to sync
last_doc=$(git -C "$root" log -1 --format=%H -- '*.md' 'docs/' '*README*' 2>/dev/null)
[ -z "$last_doc" ] && exit 0

# changed files since then (committed + staged + working tree), minus docs/tests
#
# The committed half is a commit-range diff, which never touches the index. The
# uncommitted half deliberately uses `git status` rather than `git diff`: a
# working-tree `git diff` refreshes and REWRITES the index, taking
# .git/index.lock to do it, and — unlike `git status` — it ignores
# GIT_OPTIONAL_LOCKS entirely (verified on git 2.34.1). `status --porcelain
# -uno --no-renames | cut -c4-` yields the same set of paths, lock-free.
changed=$( { git -C "$root" diff --name-only "${last_doc}..HEAD";
             git -C "$root" status --porcelain --untracked-files=no --no-renames \
               | cut -c4-; } 2>/dev/null | sort -u )
code=$(printf '%s\n' "$changed" | grep -vE '\.(md|rst|txt|adoc)$|(^|/)docs/|README|(^|/)tests?/|(^|/)test_|_test\.' | grep -c .)

# approximate lines changed in the committed range
stat=$(git -C "$root" diff --shortstat "${last_doc}..HEAD" 2>/dev/null)
ins=$(printf '%s' "$stat" | grep -oE '[0-9]+ inser' | grep -oE '[0-9]+'); ins=${ins:-0}
del=$(printf '%s' "$stat" | grep -oE '[0-9]+ delet' | grep -oE '[0-9]+'); del=${del:-0}
lines=$(( ins + del ))

if [ "$code" -ge 6 ] || [ "$lines" -ge 200 ]; then
  echo "$now" > "$stamp"
  msg="📝 ${code} code file(s) / ${lines} line(s) changed in $(basename "$root") since the docs were last updated — consider /doc-sweep to reconcile them."
  printf '{"systemMessage":%s}\n' "$(printf '%s' "$msg" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null)"
fi
exit 0
