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

## State is an artifact, not a transcript
The one thing the "graphs, not loops" crowd is right about: a fleet whose only memory is its context
window forgets. Subagents die, contexts compact, sessions get killed. Edges carry *state*, and state
has to live somewhere you can read after the fact.

- **A fan-out over more than a handful of items writes run-state to a file.** `.claude/runs/<name>.md`
  in the project (or the `Workflow` journal, which already does this): the work list, per-item status,
  results so far, open questions. Nodes read it and append to it. Same reason `loops.md` demands a
  ledger — it survives compaction, resume, and hand-off, and it's what `/resume` reads.
- **Say how it resumes before you start it.** `Workflow` → `resumeFromRunId` plus
  `<transcriptDir>/journal.jsonl` (the longest unchanged prefix replays from cache). Anything else →
  the run-state file, so a second pass skips what's already done. A fan-out you can't resume costs
  full price every time it dies, and long ones do die.
- **Gate nodes are nodes.** An irreversible step that surfaces mid-fan-out — a deploy, a DNS change,
  a paid call — halts *that branch* and appends to the approvals queue (`NEEDS-APPROVAL.md`); the
  other branches keep flowing. Route around it, never through it. A worker deciding on its own that
  its irreversible step is "probably fine" is the failure this whole setup exists to prevent, and a
  worker is exactly the wrong place to make that call — it has the least context of anyone.
- **Read the state before you diagnose the run.** When a workflow returns something empty or strange,
  the journal says what each agent actually returned. Check it before theorizing about why.

## Anti-patterns
- **Personas orchestrating personas** — nesting hides cost and failure; flatten it.
- **A barrier where a pipeline would do** — don't `parallel()` then transform then `parallel()` again
  when the middle step has no cross-item dependency; it wastes the fast workers' wall-clock.
- **Fan-out with no synthesis** — N reports and no one merges them is N times the tokens for a pile,
  not an answer. Always end with a dedup/synthesis step.
- **Silent truncation** — if you cap coverage (top-N, no-retry, sampling), *say so*; a silent cap
  reads as "covered everything" when it didn't.
- **A long fan-out with no resume path** — thirty items deep, the session dies, and the only option
  is to pay for all thirty again. Decide where state lands *before* you spawn.
- **Running two skill/command routers at once** — they fight over names and routing. Compose
  individual skills, not whole competing frameworks.

## When *not* to orchestrate
A single-context task doesn't need a fleet. Reach for subagents to be **comprehensive** (decompose and
cover in parallel), **confident** (independent adversarial checks), or to handle **scale one context
can't hold** — not for work one agent finishes cleanly. Match the fan-out to the request: a quick
check gets a couple of workers; "audit this thoroughly" earns a larger pool plus a synthesis pass.
