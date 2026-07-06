---
description: Sweep the docs for accuracy + coherence via the doc-steward agent
argument-hint: [area or docs to focus on — optional]
---

Delegate a documentation sweep to the **doc-steward** subagent. Focus: $ARGUMENTS
(if empty, the whole project's docs).

Have it establish ground truth from the code + recent git history, then make the
docs both accurate and coherent — integrated as one thought-through package, not
tacked-on notes (it removes stale content, dedupes, fixes cross-references and the
index/glossary, and matches the repo's voice).

Relay its summary of what drifted, what it restructured, and any open questions
that need my decision. Don't let it invent features or churn prose for its own sake.
