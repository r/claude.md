# Agent orchestration — structuring a fleet of subagents

Load this when a task fans out across **multiple subagents or a `Workflow`** — a review with several
lenses, a broad search, a migration over many files, a judge panel. It's the harness-level companion
to `loops.md`: loops is about iterating one worker against a checker; this is about how many workers
compose without stepping on each other.

## The one governing rule
**The orchestrator is the main loop (or the slash command). Personas never invoke personas.** A
subagent does its scoped job and returns a result; it does not spawn its own subagents (the harness
forbids nesting anyway). Keep the tree one level deep — orchestrator → workers — so results, budget,
and failure are all accountable in one place.

## Patterns that pull their weight
- **Parallel fan-out for independent work.** Send independent agent calls in a single turn so they
  run concurrently. Use `parallel()` only when you genuinely need *all* results together (a barrier);
  otherwise `pipeline()` so each item flows through its stages without waiting on the slowest peer.
- **Research isolation.** For "read across many files, return the conclusion not the dumps," use the
  read-only `Explore` agent — it keeps the big file contents out of the main context and hands back
  only the finding.
- **Adversarial verify.** For anything load-bearing (a bug, a claim, an infra change), spawn
  independent skeptics prompted to *refute*, and keep the finding only if it survives. Give diverse
  verifiers distinct lenses (correctness / security / does-it-reproduce) rather than N identical ones.
  This is the multi-agent form of "how do we know we're right?"
- **Judge panel.** For a wide-open design call, generate N independent attempts from different angles,
  score with parallel judges, synthesize from the winner. Beats one-attempt-iterated.
- **Worktree isolation** (`isolation: "worktree"`) only when agents mutate files in parallel and would
  otherwise collide — it's real setup cost, not a default.

## Anti-patterns
- **Personas orchestrating personas** — nesting hides cost and failure; flatten it.
- **A barrier where a pipeline would do** — don't `parallel()` then transform then `parallel()` again
  when the middle step has no cross-item dependency; it wastes the fast workers' wall-clock.
- **Fan-out with no synthesis** — N reports and no one merges them is N times the tokens for a pile,
  not an answer. Always end with a dedup/synthesis step.
- **Silent truncation** — if you cap coverage (top-N, no-retry, sampling), *say so*; a silent cap
  reads as "covered everything" when it didn't.
- **Running two skill/command routers at once** — they fight over names and routing. Compose
  individual skills, not whole competing frameworks.

## When *not* to orchestrate
A single-context task doesn't need a fleet. Reach for subagents to be **comprehensive** (decompose and
cover in parallel), **confident** (independent adversarial checks), or to handle **scale one context
can't hold** — not for work one agent finishes cleanly. Match the fan-out to the request: a quick
check gets a couple of workers; "audit this thoroughly" earns a larger pool plus a synthesis pass.
