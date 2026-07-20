# Loop engineering — running an agent in a keep-or-rollback loop

Load this before any **recurring or autonomous iteration**: `/loop`, `/improve-loop`, a
`Workflow` that iterates to a target, a cron/`schedule` agent, or any "keep trying until it's
better" task. This is the doctrine; `/improve-loop` is the executable version of it.

The frame (Karpathy's *Software 3.0* / autoresearch): the unit of work is the **task**, not the
prompt. You design a *loop* — propose → run → measure → keep-or-rollback → log → repeat — and you
sit on the **autonomy slider**, as hot or cold as the blast radius allows. The one law:

> **A loop without high-fidelity feedback is an expensive hallucination.**
> Define the checker *before* you start looping. No checker → no loop.

## The five things every loop must have

1. **A checker, defined first.** Either
   - a **scalar** — one command that prints a number where lower-or-higher is unambiguously better
     (p95 latency, bundle bytes, coverage %, benchmark score, failing-test count), or
   - a **boolean gate** — the project's quality gate (`ruff` + `mypy` + `pytest`, or whatever the
     repo defines) plus an explicit task-satisfaction check.
   The scalar is the *gradient* (which candidate wins); the gate is a *hard filter* (any candidate
   that isn't green is rejected outright, no matter what the scalar says). If you can't name the
   checker, you're not ready to loop — stop and build it, or do the work by hand.

2. **A cheap iteration.** Karpathy's worked because one experiment was ~5 minutes. Make the
   checker fast (subset of tests, one endpoint, a micro-benchmark) or the loop is unaffordable.

3. **Trivial rollback.** Loop only where reverting a bad step costs nothing. In practice that means
   **a clean git tree on a dedicated branch**: keep = commit, reject = `git reset --hard`. Never
   loop on a dirty tree, never on `main`. This is *why* autonomous looping is safe for software and
   **not** for infra (see the slider below).

4. **A ledger.** Append every attempt to `LEDGER.md` (see below). The loop's memory is the ledger,
   not your context window — it survives compaction, resume, and hand-off.

5. **A stop condition that isn't the wall clock.** Stop on: budget exhausted, **K consecutive
   rounds with no improvement** (loop-until-dry, default K=3), or a max-iteration cap. Never leave
   an unbounded loop running unattended — that violates the "nothing fills a disk or flips behavior
   if I forget about it" rule in the global agreement.

## The loop, concretely

```
baseline = checker()                      # record starting metric / confirm gate green
best = baseline
repeat until stop:
    propose ONE change                    # smallest testable slice, guided by the spec's search space
    run the quality gate                  # HARD filter — red ⇒ rollback, log, next
    m = checker()                         # scalar measure, or task-satisfaction for boolean loops
    if better(m, best) by a real margin:  # strictly better; ignore noise-level wins
        commit (change + its tests/docs)  # atomic; this is the "keep"
        best = m
    else:
        git reset --hard                  # the "rollback" — clean, total
    append to LEDGER                       # hypothesis, change, gate, metric before→after, kept?, why
```

## The autonomy slider — where each kind of work sits

- **Software with a real gate + git** → hottest safe setting. Autonomous propose/keep/rollback is
  fine because rollback is `git reset` and the gate catches regressions. This is the `/improve-loop`
  zone.
- **Docs / research / content** → warm. Loop to gather or draft, but a human reads before anything
  ships outward.
- **A declared pre-release cloud project** (`.claude/stage.json`, see `prerelease.md`) → the
  software setting, not the infra one. Nobody's using it, `terraform apply` back is the rollback, so
  a real checker (plan diff, smoke test, health check) earns a hot loop. Money, shared blast radius,
  and unbacked deletion still queue. Declared only — never inferred to unblock a loop.
- **Infra, firewall, DNS, storage, deploys, anything outward-facing or paid** → **coldest. Never
  autonomously looped.** Rollback isn't `git reset`, the "checker" is production, and a bad step can
  fill a disk or flip behavior. These go through `/safe-change` (observe-first, timestamped backup,
  explicit go-ahead) — one reviewed step at a time, not a loop.

Say the slider position out loud when you start a loop, and default one notch colder than you think
you need. The first iteration of any *interactive* loop runs in **propose-and-confirm** mode — show
the spec, the checker, and the first proposed change, and get a go-ahead — before it runs hot. A
**fully autonomous** run (cron / scheduled, no human present) can't do that handshake: it relies on
a pre-approved spec, the gate, and the ledger instead, and anything irreversible goes to the
approvals queue rather than blocking (see **Auto mode** in `CLAUDE.md`). Never let a *first-ever*
run of a new spec go fully autonomous — the propose-and-confirm happens once, interactively, before
it's ever scheduled.

## Non-negotiables carried in from the global rules

- **Never weaken the checker to make a step "pass."** Loosening the gate, relaxing the metric, or
  deleting a failing test to get a green is the one way a loop silently rots. A rejected step is a
  *result*, not a problem to engineer around.
- **Keep the spec stable and human-owned.** The steering file (goal + search space + constraints)
  is the leash — the equivalent of autoresearch's `program.md`. The agent rewrites the *artifact*,
  never the spec. If the spec is wrong, that's a conversation, not a loop iteration.
- **Provenance:** every kept change points back to its ledger entry and its commit.

## The experiment ledger (`LEDGER.md`)

Per-project, append-only, repo root (or `docs/` if the project keeps docs there). One block per
attempt — this is provenance and it's what `/resume` reads to reconstruct a loop's history:

```markdown
## 2026-07-03 — <one-line hypothesis>
- **Change:** what was actually edited (files / approach)
- **Gate:** green | red (which check failed)
- **Metric:** <before> → <after>  (checker: `<command>`)
- **Verdict:** kept (commit `<sha>`) | rolled back
- **Why:** the one sentence that makes this entry worth keeping
```

Cheap to write, and it turns a pile of attempts into a searchable record of what was tried and what
the evidence said — the thing you wish you had the *next* time you touch the same code.
