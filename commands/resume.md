---
description: Reconstruct what we were doing and where we left off — no action yet
---

Reconstruct what we were working on and where we left off. **Take no action yet.**

Read the machine-written state **first** — it records what was actually happening, not what was supposed to happen. Then the human-written docs for intent.

1. **Session checkpoints.** Look in `~/.claude/checkpoints/*/state.json` for entries whose `cwd` matches this directory, newest `updatedAt` first. Any entry whose `state` is not `completed` is an **interrupted session** — read its `detail` (last activity), `needs` (an explicitly recorded blocker), `dirty`, and the tail of its sibling `timeline.jsonl` for the run-up. `transcriptPath` + `transcriptOffset` point at the raw transcript if you need more.
2. **Blocked jobs.** Check `~/.claude/jobs/*/state.json` for a matching `cwd`. These record `state: blocked`, a `needs` string naming the exact command to run, and `resumeSessionId`. A blocked job is the single most direct answer to "what was the next step."
3. **Open tasks.** Check `~/.claude/tasks/<session-id>/*.json` for the session ids you found above — durable per-session todo state, including what was `in_progress` when things stopped.
4. Search your memory for notes about this project or host.
5. Read the repo's continuity docs if present: `RUNBOOK.md`, `TRANSITION.md`, `MIGRATION.md`, `IMPLEMENTATION_PLAN.md`, `docs/STATUS.md`, recent plan files. If a `LEDGER.md` exists, read its tail — it records what was recently *tried* and kept/reverted, which often explains the current state better than the diff does. If a `NEEDS-APPROVAL.md` exists and is non-empty, say so — something is waiting on you.
6. If it's a git repo, check recent history and the working-tree status.

Where the machine state and the docs disagree, trust the machine state for *what happened* and the docs for *what was intended*, and say that they disagree.

Then tell me:
- **(a)** what we were doing,
- **(b)** the last thing that got completed,
- **(c)** the next step we intended,
- **(d)** anything left in a risky or half-done state.

Ask me to confirm before continuing.
