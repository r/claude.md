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
- **Finish, don't half-build.** No placeholder core behavior left in limbo behind a dead flag.

## Commits & documentation
- **Atomic commits.** The code change, its tests, and its doc updates land in the **same** commit.
  A change isn't done until all three move together — never "code now, tests/docs later."
- **Docs are a coherent whole**, not a pile of tacked-on notes. When behavior changes, fold the
  update into the existing narrative so the docs still read as one thought-through package. Delegate
  a sweep to the **doc-steward** agent (`/doc-sweep`) rather than appending patches. A **drift nudge**
  (Stop hook) reminds you to sweep once code has moved substantially since docs were last touched.

## Process loop (per change)
1. Read the relevant spec / docs first.
2. State the intended change in a sentence or two.
3. Implement the smallest testable slice.
4. Add or update tests **and docs**; run the quality gate.
5. Summarize what changed, how to test it, and what's still risky. Commit when the gate is green —
   code, tests, and docs together, on a branch (branch off first if you're on main). Pushing the
   feature branch is fine too; anything that lands on main/master waits for an explicit ok.

## Quality gate (unless the repo defines its own)
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
