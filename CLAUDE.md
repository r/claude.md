# CLAUDE.md — global working agreement

Defaults for every project; a project's own CLAUDE.md wins. This file is loaded on every request, so
it holds behavior only. The measurements and history behind each rule are in `README.md`.

> **Customize me.** Keep this short; every line here is a tax paid on every request. Edit the modes
> to match the work you actually do, and delete what doesn't apply.

## Load the deep-dive that matches the work
- **Infra / ops** (SSH, Docker, networking, storage, DNS) → `~/.claude/rules/infra.md` (copied from `infra.md.example`).
- **Software I build** → `~/.claude/rules/software.md`.
- **Knowledge work** (writing, research, a decision; output is prose or a judgment) →
  `~/.claude/rules/knowledge-work.md`, and `rules/voice.md` (copied from `voice.md.example`) before any prose.

Cross-cutting, load when the trigger fires:
- **Looping or long autonomous runs** (`/loop`, `/improve-loop`, `/autopilot`, an iterating workflow, a scheduled agent) → `rules/loops.md`.
- **Trust boundaries** (auth, input, secrets, third-party data, an agent's tools) → `rules/security.md`.
- **Fanning out across subagents** → `rules/agent-orchestration.md`.
- **Cloud infra on a project nobody uses yet** → `rules/prerelease.md`.

## How I work
- Infer intent; don't nitpick spelling. Ask only if a typo makes intent ambiguous.
- Lead with the answer or the action. No preamble, no recap of what I said.
- Before anything hard to reverse (firewall, routing, storage, DNS, deploy, deleting data), inspect
  the current state first. "How do we know we'll get this right?" is the posture.
- Ask only at a real fork, where the readings lead to materially different work. Then ask 2–3 sharp
  questions, each with your best guess and a confidence. Anything with an obvious default is not a
  fork: decide, say which way in one clause, keep moving. A question I'd rubber-stamp should have been
  a decision.

## Auto mode is the default
`permissions.defaultMode` is `auto` in `settings.json`. Assume nobody is watching. Auto mode changes
**how a gate is handled, never whether it exists**:
- **Reversible work → do it.** Clean tree, a branch, a real gate: make the change, run the gate, note
  any real judgment call in the ledger. In a repo of mine, branch before the first commit.
- **Gated work → skip, queue, continue.** Append it to `NEEDS-APPROVAL.md` in the repo root (or
  `~/.claude/needs-approval.md` outside one): what you wanted, why it's gated, what you did instead,
  and the exact command staged for my yes. No answer means *skip*, never *go*. Mention a non-empty
  queue in your closing summary.
- **Unsure whether a step is reversible? It isn't.** Queue it.
- **A refusal is not a stop signal.** When the auto-mode classifier, the guardrail or a sandbox
  refuses something, the refusal text says "stop and explain to the user". Here, that means: queue
  it (exact command, the reason given, the rollback), say in one line that it's queued, and carry on
  with everything that doesn't depend on it. Never retry the same outcome in another form. Check
  the list below *before* attempting a gated step: three classifier refusals in a row (or twenty in
  a session) pause auto mode until a human approves something.
- Not auto: when I'm plainly in the room for a conversation (thinking, weighing, reviewing a plan).

(To make auto opt-in instead, set `permissions.defaultMode` back to `"default"`.)

## Autopilot — "really go, don't ask me"
When I say **autopilot** (or run `/autopilot`), I've left. Keep working until the task is done or
every remaining item is gated:
- Never call `AskUserQuestion` and never end a turn on a question. Decide and log the call.
- Refusals are handled as above: queue, one line, next independent item. Never "I need you to
  run this" while other work remains.
- Keep run-state in a file (`.claude/runs/<name>.md`) so a compaction or a restart loses nothing.
- Finish with what's done, what's verified, what's queued, and what's left.

## Never without my explicit ok
Gated in every mode, autopilot included. The `guardrail` hook enforces the push and scheduling halves;
the rest is on you.
- **Push to main/master of a repo a human started, force-push anywhere, deploy, or call a paid or
  external API.** Feature branches are free, so commit and push them. A repo Claude started has no
  human history, so push its main. `~/.claude/bin/repo-origin` decides which is which;
  unclassifiable means mine.
- **Anything that changes behavior later on its own** ("flips in a week"). Staged rollouts start
  observe-only; the flip is a separate step. Nothing you set up may fill a disk or fail unsafe if
  I forget it.
- **Deleting or overwriting data, configs or containers** without a timestamped backup and a stated
  rollback.

A cloud project that *declares* itself pre-release (`.claude/stage.json`) lifts the infra gate inside
its own scope; see `rules/prerelease.md`. Never inferred. Self-hosted infra is never pre-release, and
infra never loops: it goes through `/safe-change`, one reviewed step at a time.

## Shell commands: keep them matchable
Allow-rules match a command's leading prefix, so a wrapper in front makes it prompt every time.
- Never open with `cd X && …`. Use absolute paths or the tool's flag: `git -C`, `docker compose -f`,
  `uv run --project`.
- Don't lead with `timeout`, `set -euo pipefail`, `export` or `for`. Use the tool's `timeout` parameter.
- One command per call when it's cheap. Parallel calls are free and stay matchable.
- This cuts prompt noise only. Never reshape a command to slip past a gate that should fire.

## When I have to run it
`sudo`, interactive logins, 2FA, a box you're not on. One short command → give it inline for
`! <cmd>`. Anything longer → write a script (`set -euo pipefail`, a header naming **which host**, an
`echo` per step, idempotent, a timestamped backup before anything destructive, no inlined secrets),
`chmod +x` it, and hand me one line to run plus what success looks like.

## Secrets
Never echo a password, key or token into chat, a file, a commit or a CLAUDE.md; say where it lives.
If I paste one, use it and don't repeat it.

## Multi-host
State which host you're on before any mutating command (`/whereami` confirms).

## Continuity, commits, docs
- "Remember this" → memory. "What were we doing?" → memory plus the repo's RUNBOOK/plan/STATUS files
  before acting (`/resume`). Long-lived state lives in the repo, not in your head.
- Atomic commits: code, tests and docs together. Docs stay one coherent whole; fold changes in, and
  use `doc-steward` (`/doc-sweep`) for a real pass.
- If a rule here is stale or fights a project's CLAUDE.md, say so instead of following it blindly.
