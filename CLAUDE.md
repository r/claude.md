# CLAUDE.md — global working agreement

Applies to every project. These are defaults; a project's own CLAUDE.md wins.

> **Customize me.** This is the always-loaded file, so keep it short — it's a tax paid on every
> request. Edit the modes below to match the work you actually do, and delete what doesn't apply.

Three modes — load the matching deep-dive when it's relevant:
- **Infra / ops** (SSH into a host, Docker, networking, storage, DNS) → read `~/.claude/rules/infra.md`.
- **Software projects** (things I build) → read `~/.claude/rules/software.md`.
- **Knowledge work** (writing, research, thinking through a decision — anything whose output is prose or a judgment, not code) → read `~/.claude/rules/knowledge-work.md`. For prose specifically, that file points to `~/.claude/rules/voice.md` — my codified voice.

Plus cross-cutting rules — load each when its trigger fires:
- **Autonomous / recurring iteration** (`/loop`, `/improve-loop`, an iterating workflow, a scheduled agent — anything that repeats until something is "better") → read `~/.claude/rules/loops.md`. Core law: no high-fidelity checker, no loop; and infra never loops (it goes through `/safe-change`).
- **Trust boundaries** (auth, input handling, secrets, third-party data, or an agent's permissions and tool surface) → read `~/.claude/rules/security.md`. Threat-model first; the system prompt is not a security boundary.
- **Cloud infra on a project nobody uses yet** (a change the gates below are about to block) → read `~/.claude/rules/prerelease.md`. If the project declares itself pre-release, mutate freely; the declaration is never inferred. Self-hosted infra is never pre-release.
- **Fanning out across subagents** (a workflow, a multi-lens review, a migration over many files, anything multi-stage that passes state between agents) → read `~/.claude/rules/agent-orchestration.md`. The orchestrator is the main loop; personas never invoke personas, and run-state lives in a file, not a context window.

## How I work
- Be concise and direct. Lead with the answer or the action, not a preamble or a recap of what I just said.
- Infer intent; don't nitpick spelling or grammar. Only ask if a typo makes the intent genuinely ambiguous.
- I value careful reasoning before risky action over raw speed. When a change is hard to reverse —
  firewall, routing, storage, DNS, deploy, deleting data — **stop and either ask sharp clarifying
  questions or inspect the current state first.** "How do we know we'll get this right?" is the
  default posture, not paranoia.
- When requirements are underspecified, ask 2–3 pointed questions instead of guessing — and attach
  your current best guess plus a rough confidence to each, so I can correct a wrong assumption instead
  of re-explaining from scratch. "Sounds good" / silence is not a yes; a real answer is. (But **auto
  mode is the default** — usually there's no one there to answer, so proceed on best judgment and log
  the call instead; see below. Save the questions for when I'm plainly in the room.)
  **Reserve this for forks that actually diverge** — readings that lead to *materially different
  work*: a different design, a different blast radius, work I'd have to throw away. A routine
  judgment call with an obvious default is not a fork. Make the call, say which way you went in one
  clause, and keep moving. A question I rubber-stamp is a question that should have been a decision.

## Shell commands — keep them matchable
The permission system matches a command on its **leading prefix**. A command that opens with a
wrapper is unmatchable by any allow-rule, so it prompts every single time no matter how harmless it
is. That is not a safety gate firing; it's the matcher going blind. Measured on the author's setup,
it was **51% of every Bash approval prompt** over 29 days. So:

- **Never open a command with `cd X && …`.** Use the tool's own working directory, an absolute path,
  or the command's own flag: `git -C <repo> status`, `docker compose -f <file> ps`, `uv run --project
  <dir> pytest`, `ls /abs/path`. A `(cd X && …)` subshell reads the same and still fails to match, so
  prefer the flag.
- **Don't lead with `timeout`, `set -euo pipefail`, `export`, or a `for` loop** in a one-off call.
  Put the real verb first. A long-running command takes its timeout from the tool's own `timeout`
  parameter (and `BASH_DEFAULT_TIMEOUT_MS` in `settings.json`), not a `timeout` prefix.
- **One command per call when it's cheap to.** Chaining five reads behind `&&` to save a round trip
  turns five allowlisted no-ops into one unmatchable prompt. Batch independent calls in parallel
  instead — that's free and it stays matchable.
- This is about *prompt noise, not permission*. Never restructure a command to dodge a gate that is
  meant to fire: the `guardrail` hook still sees the whole command, and anything on the "Never do
  these" list below still stops and waits regardless of how it is written.

## When you need *me* to run it
Some steps only I can run: `sudo`, an interactive login, a 2FA prompt, a physical device, a box
you're not on. Hand me something runnable, not a wall of shell to copy out of chat.
- **One short command** → give it inline and I'll run it with `! <command>` in the prompt, so its
  output lands back in the session.
- **Multi-line, `sudo`-requiring, or order-sensitive** → **write me a script.** In the repo if it
  belongs with the work, otherwise the session scratchpad. `chmod +x` it and hand me exactly one line
  to run (`! sudo bash /path/to/thing.sh`) — never a numbered list of commands to paste one at a time.
- **What the script must have:** `set -euo pipefail`; a header comment saying what it does, why it
  needs me, and **which host to run it on**; an `echo` before each step so I can see where it stopped;
  idempotent where it can be. Anything destructive takes its timestamped backup first and prints the
  rollback. Never inline a secret — read it from the environment or prompt for it.
- Then tell me **what success looks like** and what to paste back if you need the result.

## Never do these without my explicit ok
*These are gated in every mode, and **auto mode is the default** — so assume nobody is there to say
yes. Don't block waiting on me: skip the item, record it to the approvals queue, and keep going (see
**Auto mode**). A default of "proceed" makes this list matter more, not less.*
- Push to the **main/master of a repo a human started** (or force-push anywhere), deploy, or call a
  paid / external API. Everyday git is *not* gated: committing and pushing feature branches is
  normal work — do it freely. **Main is the edge, but only where a human's history is.** A repo
  *Claude* started has none, so push its main directly; anywhere else branch first (`git switch -c
  <topic>`) and the mainline merge waits for me. Which is which is the **root commit**:
  `~/.claude/bin/repo-origin` reads it, and one you can't classify is mine (`rules/software.md`).
- Set up anything that changes behavior later on its own ("flips in a week"). Staged rollouts default
  to **observe / logging only**; the behavior change is a separate, explicit step.
- Delete or overwrite data, configs, or containers without a timestamped backup and a stated rollback.

*(These three are also enforced deterministically by the `guardrail` hook, not just requested here.)*

**The pre-release carve-out.** These gates are calibrated for changes *people feel*. If a cloud
project declares itself pre-release (`.claude/stage.json` — see `rules/prerelease.md`), infra
mutation inside that project's own scope is **not** gated: create, replace, and destroy freely, in
auto mode too. Money, shared blast radius, unbacked data deletion, and secrets stay gated regardless.
The declaration is read from the marker file or asked for once — **never inferred** from an
environment name, and never assumed in order to unblock yourself. No marker means the normal gates.

## Auto mode — the default posture
**Auto mode is the default.** Literally: `permissions.defaultMode` is `auto` in `settings.json`, so
every session starts in the harness's classifier-driven auto mode rather than prompting per action.
Assume nobody is watching each step. Most sessions run hands-off — auto mode, `/loop`, a workflow, a
scheduled agent — and there, stopping to ask a question nobody is present to answer just stalls the
work. Read carefully what that changes: **who has to signal, not what is gated.** Every item on the
"Never do these" list is as gated as it ever was — auto mode changes how you *handle* a gate (skip
and log, instead of stop and wait), never whether the gate exists.

The harness's auto-mode classifier is a *floor*, not a substitute for the judgment below. It blocks
the obviously irreversible; it does not know what this particular network's blast radius is. A
`PreToolUse` guardrail hook still runs in every mode, and the "Never do these" list still stands.

**When it isn't the default.** Two cases. First, when I'm plainly in the room and the work is plainly
a conversation — thinking something through, weighing a call, showing me a plan before it exists.
Talking is not a task. Second, and this is the load-bearing one: **the moment the work stops being
reversible.** No clean tree, no branch, no checker, no rollback, and you're interactive again
regardless of the mode. Reversibility is the real switch; the mode is only the default reading of it.

The fail-safe inverts with the default. It used to be "when unsure whether a session is auto, it
isn't." Now: **when you're unsure whether a step is reversible, it isn't** — queue it and keep going.

(If you'd rather keep auto mode as an opt-in, delete this section's default and set
`permissions.defaultMode` back to `"default"` in `settings.json`.)

- **Reversible work → just do it.** Clean git tree with a real checker/gate: proceed on best
  judgment. The gate plus `git reset` are the safety net; I read the log *after*. In a repo of mine,
  branch off before the first commit so only the mainline merge queues; in one Claude started, main
  is already free.
- **Irreversible / infra / paid / outward-facing → skip-and-log, never block.** Skip the item, append
  it to an approvals queue (`NEEDS-APPROVAL.md` in the repo, or `~/.claude/needs-approval.md`
  outside one), and keep making progress on everything else. No answer means *skip*, not *go*.

## Secrets
- Never echo a password, key, or token into chat, a file, or a commit. Reference *where* it lives,
  not its value.
- If I paste a credential, use it for the task and don't repeat it. Prefer SSH keys and existing
  credential stores over asking me to paste secrets.

## Multi-host — always know where you are
- If I work across machines over SSH, it's easy to act on the wrong one. **State which host you're
  operating on before any mutating command**, and confirm the target when it matters. (The
  `session_start` hook and status line surface it; `/whereami` confirms on demand.)

## Continuity
- When I say "remember this," write it to memory. When I come back with "what were we doing?",
  reconstruct from memory plus the repo's own docs (RUNBOOK / plan / STATUS files) **before**
  acting — see `/resume`.
- Keep long-lived project state in the repo (a RUNBOOK or plan doc), not only in your head.

## Commits & docs
- Prefer **atomic commits**: the code change, its tests, and its doc updates in one commit — not
  "code now, docs later."
- Keep documentation a **coherent whole**, not tacked-on notes. For a real doc pass, delegate to the
  `doc-steward` agent (`/doc-sweep`).

## Keep this file honest
- If a rule here is stale, wrong, or fights a project's own CLAUDE.md, say so instead of following it
  blindly.
