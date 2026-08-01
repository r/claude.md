# Software projects — engineering defaults

> **This is an example.** It happens to encode a Python/`uv`/`ruff`/`mypy` stack because that's what
> the author ships. The *shape* is the point — a short, opinionated house style with a hard quality
> gate — not these specific tools. Replace the stack details with yours; keep the doctrine and the
> gate. A project's own CLAUDE.md overrides this.

## Stack
- **Python 3.12+**, `src/` package layout, **`uv`** for env / deps / running (`uv run …`).
- **ruff** (lint + format) and **mypy** (`--strict`) run on **every** Python change — non-negotiable,
  not "later". Code isn't done until both are clean.
- **Any function that does I/O is async** (network, disk, subprocess, DB, long-running work). Never add
  blocking I/O to a sync path.
- **pytest** for tests.
- Type hints on all public functions. Minimal dependencies — justify each new one.

## Doctrine
- **Inventory before implementation; reuse before new code.** Enumerate what already does (or
  half-does) the job and compose or extend it. New code is the last resort.
- **Composability-first:** build small reusable primitives, not one-off scripts.
- **Determinism in tests:** no network, wall-clock, or unseeded randomness in library code or
  tests — inject clocks and seeds. Real-service tests are opt-in and kept out of the default suite.
- **Never weaken a test to make the gate pass.** A change isn't done until lint + types + tests are
  green and the new behavior — including the negative cases — is covered.
- **Provenance matters.** Prefer designs where every derived fact can point back to its source.
  Same instinct for framework APIs: don't code them from memory — verify the pattern against the
  *installed version's* official docs and cite it; flag anything you couldn't verify as `UNVERIFIED:`
  rather than hedging.
- **Change by expansion, not in place.** Renaming or removing a column, endpoint, or public name is
  additive-first: expand (add the new, keep the old) → migrate consumers → contract (drop the old,
  last and alone). Every migration ships with a tested down path — one you can't reverse is a deploy
  you can't roll back.
- **Finish, don't half-build.** No placeholder core behavior left in limbo behind a dead flag.

## Testing discipline
- **Prove it before you fix.** For a bug, write the failing test that reproduces it *first* — it must
  fail without the fix and pass with it. For a feature, red → green → refactor where it fits.
- **Assert state, not interactions.** Test the outcome (what the system now holds or returns), not
  which methods were called — interaction tests break on every refactor and pass while production is
  wrong.
- **DAMP over DRY in tests.** A little descriptive repetition beats a shared helper that hides what's
  actually being verified; a test should read top-to-bottom without a spelunk.
- **Prefer real > fake > stub > mock,** in that order. Over-mocking yields tests that stay green while
  the real integration breaks; reserve mocks for genuinely awkward boundaries (network, paid APIs).
- **Size by resource:** small = no I/O (the default suite), medium = localhost only, large = external
  and opt-in (kept out of the default run — same reason as the determinism rule above).

## Shelling out — the mistakes that actually cost time
Measured, not guessed: an audit of 913 failed tool calls across 34 projects on one machine
(2026-07-26). These are the recurring ones, in order of how much time they burned.

- **Never poll with a foreground `sleep`.** ~74 of those failures were a `sleep`-and-check loop —
  either blocked outright or eating the entire command budget waiting. Background work re-invokes you
  when it finishes; that notification is the signal. If you must wait on something the harness can't
  see, use `Monitor` with an until-loop (`until <check>; do sleep 2; done`), never `sleep N; <check>`.
- **A command you expect to run long gets an explicit timeout.** 114 timeouts, and only 16 of them
  had one set. Builds, `docker build`, a `git push` over a slow link, a first-run dependency sync,
  ssh into a slow box — say the number up front or run it in the background. Discovering the limit by
  hitting it costs the full wait *and* the retry.
- **`pkill -f <pattern>` matches its own wrapper shell.** 57 exit-144s were a command killing itself
  mid-run. Narrow the pattern, or exclude self: `pgrep -f pat | grep -v $$ | xargs -r kill`.
- **Never delete a lock file you haven't proven is orphaned.** A stale `.git/index.lock` blocked 32
  calls across 9 repos, and the transcripts show a blind `rm -f .git/index.lock` before a merge —
  which silently corrupts the index if a real git process *was* holding it. Prove no owner
  (`lsof`/`pgrep`), then clear it, and fix the thing that leaked it. (The leak here was hooks running
  `git status` on a short timeout — see `hooks/test_git_locks.sh`.)
- **Don't assume `python` is on PATH.** Plenty of systems ship only `python3`. A bare `python` in a
  heredoc exits 127 and the edit it was carrying silently never happens.
- **Don't chain an optional command with `&&`.** `cmd && ls docs` returns non-zero and reads as a
  failure when the real work succeeded. Use `;` or `|| true` for the optional tail.
- **Quote ssh payloads with a heredoc, not nested single quotes.** `ssh host '… "$F.bak.$(date)" …'`
  is where the `unexpected EOF` errors come from. `ssh host bash -s <<'EOF'` and let the remote shell
  parse it.

## Observability
Instrument as you build, the way you test — not bolted on after an incident.
- **Define "working" first.** Write the 2–4 questions you'd need answered at 3am ("is checkout
  succeeding? how slow?") *before* adding telemetry; every signal must answer one, or you'll log
  everything and learn nothing.
- **Right signal:** metrics tell you *that* something's wrong, traces tell you *where*, logs tell you
  *why*. Cover RED (Rate, Errors, Duration) for services and USE (Utilization, Saturation, Errors)
  for resources.
- **No unbounded values in metric labels** (user id, URL, error text) — that's a cardinality bomb that
  melts the metrics store. They belong in logs/traces.
- **Alert on symptoms, not causes** — page on what the user feels (error rate, latency), not on CPU.
  If the response to an alert is "ignore it, it self-heals," delete the alert.
- **Verify the telemetry itself:** induce a failure in staging and confirm you can find it from the
  signals alone. Untested instrumentation is untested.

## Commits & documentation
- **Atomic commits.** The code change, its tests, and its doc updates land in the **same** commit.
  A change isn't done until all three move together — never "code now, tests/docs later."
- **Docs are a coherent whole**, not a pile of tacked-on notes. When behavior changes, fold the
  update into the existing narrative so the docs still read as one thought-through package. Delegate
  a sweep to the **doc-steward** agent (`/doc-sweep`) rather than appending patches. A **drift nudge**
  (Stop hook) reminds you to sweep once code has moved substantially since docs were last touched.
- **Capture decisions, not just changes.** A load-bearing architecture/technology choice gets a short
  ADR in `docs/decisions/` (context, the decision, **alternatives considered → rejected because…**,
  consequences). Comments explain *why* (stable), never restate *what* (rots). Don't delete a
  superseded ADR — mark it superseded. This is the "why" the LEDGER's experiment log doesn't hold.

## Process loop (per change)
1. Read the relevant spec / docs first.
2. State the intended change in a sentence or two.
3. Implement the smallest testable slice — surgical scope, not unsolicited renovation. When you spot
   something else worth doing, note it ("NOTICED BUT NOT TOUCHING: …") rather than fixing it in passing.
4. Add or update tests **and docs**; run the quality gate. Don't re-run an unchanged gate hoping for a
   different result — the same command on unchanged code adds no information.
5. Summarize what changed, how to test it, what's still risky, and — briefly — what you deliberately
   **didn't** touch (scope evidence). Commit when the gate is green — code, tests, and docs together.
   Where that lands depends on who started the repo — see below.

## Whose repo is it? (the mainline gate)

The main-push gate in `CLAUDE.md` exists to protect *a human's* mainline: my history, my bisect, my
review. A repo that Claude created and Claude wrote has no such thing to protect, so the gate there
is friction with nothing on the other side of it. Which repo you're in decides the whole shape of
the work:

- **Claude-origin repo** — commit and push **straight to main**. No branch, no approvals queue, no
  asking. Work on main the way you'd work on a scratch branch: the gate plus `git revert` is the
  safety net.
- **Human-origin repo** — unchanged from before. Branch off first (`git switch -c <topic>`),
  commit and push the *branch* freely, and the merge/push to main waits for an explicit ok (in auto
  mode: skip it, append to `NEEDS-APPROVAL.md` with the exact merge command staged, keep going).

**The origin test — run it, don't assume it.** Once per repo, before the first push:

```bash
git -C <repo> log --format='%H %(trailers:key=Co-Authored-By,valueonly,separator=%x2C)' | grep -cv Claude
```

Zero — every commit in history, root included, carries the `Co-Authored-By: Claude` trailer — means
Claude-origin. **One or more and it's mine**, no matter how agent-written the recent work looks.
(Keep the `separator=`; without it git appends a newline per trailer and every blank line scores as
a human commit. Merge commits carry no trailer and so count as mine too — that's the fail-closed
direction, and the marker below is the escape hatch.) The test fails closed by construction: an
empty repo, a shallow clone, a history you can't read, or a repo you never ran it in all count as
mine.

**A marker overrides the test** — for the case the history gets wrong, a repo Claude started that I
later hand-committed into. `.claude/origin.json` in the repo root, same shape as `stage.json`:

```json
{ "origin": "claude", "declared": "2026-08-01", "note": "scaffolded and written by Claude; my commits are typo fixes" }
```

`"origin": "claude"` lifts the gate; `"origin": "human"` reimposes it even on a clean history (use
it for anything I intend to hand off or publish). Like every marker in this setup the declaration is
**read, never inferred** — a repo that merely *looks* agent-generated, or a `claude-`prefixed name,
declares nothing. If I'm in the room and the answer is unclear, ask once and write the marker.

**What stays gated in a Claude-origin repo:** force-push anywhere, a push that *triggers* something
outward (a deploy, a package publish, a release workflow, Pages), and any repo with another
collaborator or a downstream consumer. Origin lifts "whose history is this," not "who feels it."

## Quality gate (unless the repo defines its own)
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
