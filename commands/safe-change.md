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

Then **stop and wait for my go-ahead** before making any change.
