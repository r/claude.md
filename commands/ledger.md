---
description: Append an experiment/decision entry to the project's LEDGER.md (provenance for what was tried)
argument-hint: [the attempt/decision to record — optional; infer from recent work if empty]
---

Record an experiment or decision in the project's append-only ledger: **$ARGUMENTS**

The ledger (`LEDGER.md` at repo root, or `docs/LEDGER.md` if the project keeps docs there) is the
memory of what was *tried* — not just what shipped. It's provenance: the record you'll wish you had
the next time you touch this code. Format and rationale live in `~/.claude/rules/loops.md`.

1. If `LEDGER.md` doesn't exist, create it with a one-line header explaining what it is.
2. Append one dated block (newest at the bottom). If `$ARGUMENTS` is empty, infer the entry from
   the recent work in this session — the hypothesis, what changed, whether the checks passed, and
   whether it was kept or reverted.

```markdown
## <YYYY-MM-DD> — <one-line hypothesis or decision>
- **Change:** what was actually done (files / approach)
- **Gate:** green | red (which check failed) | n/a
- **Metric:** <before> → <after>  (checker: `<command>`)   ← omit if not measurable
- **Verdict:** kept (commit `<sha>`) | rolled back | decided against
- **Why:** the one sentence that makes this worth keeping
```

Keep it terse — a ledger nobody wants to write is a ledger nobody reads. Don't editorialize; record
the evidence and the verdict. Don't commit it unless I ask (it rides along with the change's commit).
