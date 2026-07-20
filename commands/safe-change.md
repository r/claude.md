---
description: Walk an infra change through the staged, reversible, observe-first protocol
argument-hint: <what you're about to change>
---

I'm about to make an infrastructure change: **$ARGUMENTS**

Follow the safe-change protocol in `~/.claude/rules/infra.md`. Before doing anything mutating:

1. Confirm which host we're on and that it's the right target (`/whereami` if unsure).
2. Discover and report the **current state** relevant to this change: config, traffic flows, container status, free disk space, whatever applies.
3. Propose the **most minimal change** that achieves the goal — plus the **timestamped backup** you'll take first and the **exact rollback**.
4. If the change alters behavior, tell me how to run it **observe / logging-first**, and what the separate "flip it on" step would be.

## Don't rationalize the safety off

| The excuse | The reality |
|---|---|
| "It's a tiny change, skip the backup." | Small changes cause the outages nobody rehearsed a rollback for. Timestamped backup first, always. |
| "Just flip it on, we'll watch it." | A behavior flip is a separate, explicit step. New rules go observe / logging-first. |
| "I'm pretty sure this is the right host." | "Pretty sure" is how you act on the wrong machine. Confirm the host before any mutating command. |
| "The rollback's obvious, no need to write it." | If it isn't written before the change, it won't be to hand during the incident. |
| "Nothing's live on this yet, it's basically pre-release." | Pre-release is **declared, not assumed** — a `.claude/stage.json` marker, or you ask. It also only ever applies to cloud project infra, never self-hosted. See `rules/prerelease.md`. |

**Red flags:** a mutating command with no backup taken; a behavior change and its rollout done in one
step; acting before the current state was read back; a rule that changes behavior on a timer if you
forget about it.

Then **stop and wait for my go-ahead** before making any change.
