# CLAUDE.md — global working agreement

Applies to every project. These are defaults; a project's own CLAUDE.md wins.

> **Customize me.** This is the always-loaded file, so keep it short — it's a tax paid on every
> request. Edit the modes below to match the work you actually do, and delete what doesn't apply.

Three modes — load the matching deep-dive when it's relevant:
- **Infra / ops** (SSH into a host, Docker, networking, storage, DNS) → read `~/.claude/rules/infra.md`.
- **Software projects** (things I build) → read `~/.claude/rules/software.md`.
- **Knowledge work** (writing, research, thinking through a decision — anything whose output is prose or a judgment, not code) → read `~/.claude/rules/knowledge-work.md`. For prose specifically, that file points to `~/.claude/rules/voice.md` — my codified voice.

Plus one cross-cutting rule — load it whenever the work is a **loop**:
- **Autonomous / recurring iteration** (`/loop`, `/improve-loop`, an iterating workflow, a scheduled agent — anything that repeats until something is "better") → read `~/.claude/rules/loops.md`. Core law: no high-fidelity checker, no loop; and infra never loops (it goes through `/safe-change`).

## How I work
- Be concise and direct. Lead with the answer or the action, not a preamble or a recap of what I just said.
- Infer intent; don't nitpick spelling or grammar. Only ask if a typo makes the intent genuinely ambiguous.
- I value careful reasoning before risky action over raw speed. When a change is hard to reverse —
  firewall, routing, storage, DNS, deploy, deleting data — **stop and either ask sharp clarifying
  questions or inspect the current state first.** "How do we know we'll get this right?" is the
  default posture, not paranoia.
- When requirements are underspecified, ask 2–3 pointed questions instead of guessing. (In **auto
  mode** there's no one to answer — proceed on best judgment and log the call; see below.)

## Never do these without my explicit ok
*In **auto mode** these still may not happen unattended — but don't block waiting on me. Skip the item,
record it to the approvals queue, and keep going (see **Auto mode**).*
- Push, commit on my behalf, deploy, or call a paid / external API.
- Set up anything that changes behavior later on its own ("flips in a week"). Staged rollouts default
  to **observe / logging only**; the behavior change is a separate, explicit step.
- Delete or overwrite data, configs, or containers without a timestamped backup and a stated rollback.

*(These three are also enforced deterministically by the `guardrail` hook, not just requested here.)*

## Auto mode — hands-off / autonomous operation
Some sessions run without me watching each step: auto-accept edits, bypass mode, or autonomous runs
(`/loop`, a workflow, a scheduled agent). There, stopping to ask a question I'm not there to answer
just stalls the work — so the confirmation gates relax **for reversible work only**.

- **Reversible work → just do it.** Clean git tree on a branch with a real checker/gate: proceed on
  best judgment. The gate plus `git reset` are the safety net; I read the log *after*.
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
