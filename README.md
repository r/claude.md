# claude.md — an opinionated Claude Code setup

This is a versioned, opinionated global [Claude Code](https://code.claude.com) configuration you can
copy and make your own. It is not a pile of settings. It is a small system with a point of view about
how to work with an agentic tool across the different kinds of work you actually do: **infrastructure**
you run, **software** you ship, and **knowledge work** — writing, research, deciding — that produces
prose and judgments rather than code.

It started as one person's private `~/.claude`. This is the distilled, secret-free template: the
philosophy and the reusable mechanisms, with everything personal turned into a placeholder you fill in.

> New here? Read this file for the *why*, then follow **[docs/ADOPTING.md](docs/ADOPTING.md)** for the
> 10-minute install.

---

## The one constraint everything follows from

An agent's context window is its working memory, and **performance degrades as it fills**. Every file
loaded at startup, every rule that's always present, every noisy command output is a tax paid on
*every* request. Independent testing converges on a rule of thumb: models reliably honor on the order
of **150–200 standing instructions** before compliance starts to slip, and auto-generated
"include-everything" instruction files measurably *lower* success while *raising* cost.

So the organizing principle is: **say the least that changes behavior, and load depth only when it's
relevant.** Almost every decision below follows from that.

---

## Layout

```
~/.claude/
├── CLAUDE.md            Always-loaded global doctrine. Deliberately short — behavior, not facts.
├── rules/              On-demand deep-dives. Loaded only when the work touches them.
│   ├── agent-orchestration.md Structuring a fleet of subagents — orchestrator owns it, no nesting.
│   ├── infra.md.example   Host map + the safe-change protocol.            (copy → infra.md)
│   ├── knowledge-work.md   Writing / research / decision doctrine.
│   ├── loops.md            Loop doctrine — checker-first, keep-or-rollback, ledgered.
│   ├── security.md         Trust-boundary doctrine — threat-model first, agents are a boundary too.
│   ├── software.md         An example stack doctrine + quality gate.       (adapt to your stack)
│   └── voice.md.example    How to codify YOUR writing voice.               (copy → voice.md)
├── agents/             Subagents — isolated context, fresh eyes.
│   ├── doc-steward.md      Keeps docs accurate and coherent.
│   ├── editor.md           Voice-aware structural + line editor for prose.
│   ├── infra-reviewer.md   Pre-flight review of infra changes.
│   └── thought-partner.md  Pressure-tests a decision before you commit.
├── commands/           Explicit slash-command entry points (whereami, safe-change, resume,
│                        improve-loop, ledger, doc-sweep, edit, think, debug, ideate).
├── hooks/              Deterministic automation wired into settings.json.
│   ├── session_start.sh   Injects host/git/docker context every session.
│   ├── guardrail.py       Safety net over destructive commands (+ rules YAML, + tests).
│   ├── py_autoformat.sh   ruff format+fix on edited Python.
│   ├── statusline.sh      host │ dir ⎇ branch │ model.
│   ├── doc_drift.sh       Nudges when code has outrun docs.
│   └── experimental/      Prototypes, NOT wired into settings.json (webfetch revalidation cache).
├── bin/                Small tracked utilities (morph-mirror + its test).
├── skills/             Model-invoked procedures (add your own; see skills/README.md).
├── settings.json       Wires the hooks + statusline.
└── .gitignore          Whitelist model — tracks config, excludes all secrets/history/transcripts.
```

---

## The mechanisms, and when to reach for each

Claude Code offers several extension points that look interchangeable and are not. The whole setup
rests on matching the mechanism to the *kind* of thing being expressed:

| Mechanism | What it is | Use it for |
|-----------|------------|------------|
| **`CLAUDE.md` / `rules/`** | Text loaded into context | Facts and standing behavior. *Advisory* — the model may still slip. |
| **Hooks** | Shell run on lifecycle events | Things that must happen **every time, deterministically** — a guarantee, not a request. |
| **Subagents** | A separate context window | Work that would pollute the main thread, or that benefits from **fresh, unbiased eyes**. |
| **Skills** | A procedure + bundled files, model-invoked | A reusable playbook the model should **auto-load when relevant**, with scripts attached. |
| **Commands** | A slash-invoked prompt template | An **explicit** entry point you type. |

The load-bearing insight: **"advisory vs. guaranteed."** A rule in `CLAUDE.md` is a request the model
usually honors. A hook is a fact of the environment. So anything that *must* hold — don't wipe a disk,
always format Python, always know which host you're on — is a hook, not a sentence.

---

## Decisions, codified

**Lean global, deep on demand.** `CLAUDE.md` holds only cross-cutting *behavior*. Everything
domain-specific lives in `rules/` and loads only when the work calls for it. This keeps the always-on
budget small and the standing instructions well under the ceiling where compliance decays.

**Three modes, one config.** The setup serves infrastructure (`rules/infra.md`), software
(`rules/software.md`), and knowledge work (`rules/knowledge-work.md` + `rules/voice.md`). The global
file points to whichever is relevant and never loads the others' depth. Keep the modes *you* work in;
delete the rest.

**Hooks fail open.** A safety or quality hook that crashes must never block *every* session on *every*
machine. Every hook exits 0 except a *deliberate* block. A guardrail bug allows the action; it never
wedges the tool.

**The guardrail is data, not code.** Destructive-command patterns live in `guardrail_rules.yaml`
(`action` + `why` + regexes); `guardrail.py` is a ~90-line engine. Tuning it means editing YAML. It
matches at *command-segment start* so a dangerous word buried in an argument doesn't trip it. Two
tiers: **deny** the catastrophic (wipe a disk/root), and **ask** on the destructive-but-legitimate
(destroy a dataset, prune volumes, force-push) and the *agency* cases you never want done unprompted
(a push that lands on **main/master**; schedule an unattended `cron`/`at`/systemd job). Everyday git
is deliberately free: commits and feature-branch pushes never ask — they're local/recoverable, and
the loop doctrine's "keep = commit" depends on them not halting auto mode. The mainline-push rule is
branch-aware (a `guard` the engine evaluates: explicit refspecs read from the command, bare/`HEAD`
pushes resolved against the current branch, unknown treated as "could be main"), and its ask message
carries a `hint` that tells the agent how to keep working — branch off, push the branch, queue the
mainline push in the approvals file — instead of just stopping. That promotes the CLAUDE.md "main is
the edge" rule from advisory prose into a deterministic stop that fires even in bypass mode. It's a safety net for accidents and overreach, explicitly *not* a
security boundary.

**The safe-change protocol is the spine of infra work.** Discover current state and say it back; make
the *most minimal* change; default to reversible + observe-only (log first, flip behavior as a
separate explicit step); never leave an unattended timer that changes behavior or fills a disk; state
which host you're on; back up before replacing and state the rollback. Reinforced at three layers: the
`session_start` banner (which host?), the guardrail (deny/ask), and the `infra-reviewer` subagent
(how do we know we got it right?).

**A loop is only as good as its checker.** Any recurring or autonomous iteration is designed as a
loop — propose → gate → measure → keep-or-rollback → log — and the checker comes *first*: no
high-fidelity feedback, no loop. That checker is either a scalar metric or a boolean quality gate,
paired with trivial rollback, a ledger, and a stop condition that isn't the wall clock. `/improve-loop`
is the executable form for software with a measurable target: it works on a throwaway branch so *keep*
is an atomic commit and *reject* is `git reset --hard`. This is the hot end of an **autonomy slider**
whose cold end is the safe-change protocol — software with a gate and git can iterate on its own
because a bad step reverts for free; infra never loops, because its "checker" is production.

**Knowledge work is a first-class mode.** The output is prose or a judgment, so the mechanisms mirror
the code side one for one. `rules/voice.md` is your writing voice codified — the strict published-prose
rules kept separate from your casual register — and it loads only when you're drafting. The **editor**
subagent is the prose analog of `infra-reviewer`: a fresh, skeptical read that critiques and rewrites
but never decides what ships. The **thought-partner** subagent does the same for a *decision* — finds
the crux, names the load-bearing assumption, steelmans the road not taken. And the autonomy slider
stays **warm, never hot** here: drafting is reversible, but publishing and sending are not, so a human
reads before anything goes out.

**Docs are a designed artifact.** Documentation should read as one thought-through package, never a
sediment of "Update:" notes. The `doc-steward` subagent reconciles docs against the code in a fresh
context; the `doc_drift` hook nudges toward a sweep once code has moved substantially since the docs
were last touched.

**Memory is local; provenance lives in the repo.** Across sessions Claude keeps a per-project memory
store (auto-managed, gitignored). The durable knowledge you *do* want to keep rides in the repo it
belongs to: a `LEDGER.md` records what was *tried* — hypothesis, change, gate result, metric
before→after, verdict — which is provenance for the experiments, not just what shipped. `/resume`
stitches memory, the repo's continuity docs, and the ledger's tail together to reconstruct where you
left off before touching anything.

---

## Secrets & versioning

A live `~/.claude` is full of secrets — credentials, chat history, transcripts, caches. So
`.gitignore` uses a **whitelist**: ignore everything, then re-include only the authored config. Two
things to keep honest: the top-level catch-all only ignores *new top-level* entries, so a file dropped
*inside* a re-included dir **is** tracked; and the re-includes name whole directories. The real secret
defense is a second layer of **pattern ignores** (`*.env`, `*.key`, `*.pem`, `*.crt`, `*.p12`,
`id_rsa*`, plus caches, `.credentials.json`, `history.jsonl`, `sessions/`, `projects/`) that hold
*even inside* a versioned dir. This same file, installed as your real `~/.claude/.gitignore`, keeps
your private state out of git while you version your config in place.

---

## Credit

Distilled from a working private setup, and shared so others can fork a point of view rather than
start from an empty file. Take what's useful, delete what isn't, and make the modes your own. The
throughline worth keeping: **spend context deliberately, make the important things deterministic, keep
a human in the loop for anything hard to undo, and treat the configuration itself as a maintained,
coherent codebase.**

MIT licensed — see [LICENSE](LICENSE).
