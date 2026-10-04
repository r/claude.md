---
description: Hand the session over — work hands-off until done or everything left is gated
argument-hint: <the task, e.g. "finish the migration in docs/plan.md">
---

**Autopilot.** I've left. Do this until it's finished or every remaining item is gated: **$ARGUMENTS**

This is the `Autopilot` section of `~/.claude/CLAUDE.md`, made explicit. It changes how hard you
push, not what is allowed: everything under "Never without my explicit ok" is exactly as gated as
before. Read `~/.claude/rules/loops.md` if the work repeats against a checker.

## Set up (once, no questions)
1. Say the host and repo. Make sure the tree is clean and you're on a branch, not a human-started
   main (`~/.claude/bin/repo-origin`). Branch if needed.
2. Write the plan to `.claude/runs/<short-name>.md`: the goal, the checker or gate that says an
   item is done, the work list, and a status line per item. This file is your memory, not the
   context window. Update it as each item lands.
3. If the task is underspecified, choose the reading with the smallest blast radius, write the
   choice into the run file, and go.

## Run
- Work the list. Make each change, run the gate, then commit (code, tests and docs together) and
  push the branch. Move to the next item without stopping to report.
- **Never** call `AskUserQuestion`, and never end a turn on a question or a "shall I continue?".
  If you'd ask, decide instead and log the call in the run file.
- **A refusal is a result.** When the auto-mode classifier, the guardrail hook or a sandbox refuses
  something, don't retry it reworded, don't route around it, and don't stop. Append it to
  `NEEDS-APPROVAL.md` (what, why it's gated, the exact command staged for later) and move on to the
  next independent item.
- Gated by rule (main push on a human repo, deploy, paid API, infra, unbacked deletion): queue it
  the same way, without attempting it.
- Fan out with subagents where items are independent (`rules/agent-orchestration.md`).
- Background work re-invokes you when it finishes. Wait for that; never poll with `sleep`.

## Stop when
- every item is done and verified, or
- everything left is queued or depends on something queued, or
- the same gate has gone red three times running with no new idea (log it and stop that item).

## Finish
One summary: what's done and verified (with commits), what's queued in `NEEDS-APPROVAL.md` and why,
what's left, and any judgment calls I should look at first.
