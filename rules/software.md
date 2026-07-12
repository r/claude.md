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
   **didn't** touch (scope evidence). Commit when the gate is green — code, tests, and docs together,
   on a branch (branch off first if you're on main). Pushing the feature branch is fine too; anything
   that lands on main/master waits for an explicit ok.

## Quality gate (unless the repo defines its own)
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
