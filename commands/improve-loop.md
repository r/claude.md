---
description: Run an autoresearch-style keep-or-rollback loop against a measurable target (software only)
argument-hint: <what to improve, e.g. "cut p95 latency of /search" or "raise parser coverage">
---

Run a Karpathy-style improvement loop on: **$ARGUMENTS**

First read `~/.claude/rules/loops.md` — this command is the executable form of that doctrine. This
is a **software-only, git-backed** loop: rollback must be `git reset`. If the target is infra,
DNS, deploy, or anything outward-facing, **stop** and use `/safe-change` instead — do not loop it.

## Phase 0 — set up the loop (do this, then STOP for my go-ahead)

Do not touch code yet. Establish and report back:

1. **Host + repo check.** Confirm the host (`/whereami` if unsure), that we're in the right repo,
   and that the **working tree is clean**. Create/switch to a **dedicated branch** (e.g.
   `loop/<short-name>`). Never loop on a dirty tree or on `main`/`master`.
2. **The checker — the whole game.** Name it explicitly and confirm it runs fast:
   - **scalar** → the exact command that prints the number, and whether lower or higher wins, or
   - **boolean** → the quality gate command(s) + how you'll judge task-satisfaction.
   If there's no real checker for this target, say so and stop — propose building one first.
3. **The spec** (the leash — autoresearch's `program.md`). Write it to `.claude/loops/<name>.md`:
   goal, the checker command, the **search space** (which files/approaches are fair game), and
   **hard constraints** (what not to touch, "never weaken a test"). This file is stable and
   mine — you edit the code, not the spec.
4. **Baseline.** Run the checker once, record the starting number / confirm the gate is green.
5. **Stop condition + slider.** State the budget or max iterations, the loop-until-dry K (default
   3), and confirm this runs autonomous only *after* I approve this phase.

Report all five, show me the first change you'd propose, and **wait for my go-ahead.**

## Phase 1 — the loop (after go-ahead)

Each iteration:

1. Read the spec + the tail of `LEDGER.md`. Propose **one** smallest-testable change inside the
   search space.
2. Apply it. Run the **quality gate** — this is a hard filter. Red ⇒ roll back (`git reset --hard`),
   log, next iteration. Never loosen the gate or delete a failing test to get green.
3. Run the checker. **Scalar:** keep only if strictly better than best-so-far by a real margin
   (ignore noise). **Boolean:** keep if the gate is green *and* task-satisfaction holds.
4. **Keep** = one atomic commit (change + its tests/docs). **Reject** = `git reset --hard`.
5. Append an entry to `LEDGER.md` (format in `loops.md`): hypothesis, change, gate, metric
   before→after, verdict + commit sha, one-sentence why.
6. Stop when: budget/max-iterations hit, or **K consecutive rejects** (dry). Never run unbounded.

## When it stops

Summarize: net metric baseline→final, how many steps kept vs rolled back, the branch + commits, and
what the ledger says is still worth trying. Leave it on the branch for me to review and merge — don't
merge to `main` or push without my ok.
