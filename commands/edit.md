---
description: Hand a draft to the editor subagent for a hard, voice-aware read
argument-hint: [file or the text to edit — and the medium if not obvious]
---

Delegate an edit to the **editor** subagent. Draft / target: $ARGUMENTS (if empty, the
draft we've been working on).

Have it load `~/.claude/rules/voice.md`, fix the medium first (never launder my casual register into
essay register), then do a structural pass before a line pass — enforcing my published-prose
taboos, checking that claims carry their sources, and cutting filler.

Relay its structural calls, the taboo fixes, and anything it flagged as unsure of my intent.
It rewrites and critiques; I decide what ships. Don't let it blandify my voice or invent
attribution for a number I didn't source.
