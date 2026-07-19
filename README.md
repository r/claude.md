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
│   ├── session_start.sh   Injects host/git/docker context, an interrupted-session warning, queue health.
│   ├── guardrail.py       Safety net over destructive commands (+ guardrail_rules.py, + tests).
│   ├── checkpoint.py      Writes a resumable state file every turn (+ its test).
│   ├── py_autoformat.sh   ruff format+fix on edited Python.
│   ├── statusline.sh      host │ dir ⎇ branch │ model.
│   ├── doc_drift.sh       Nudges when code has outrun docs.
│   ├── morph-global-*.sh  Prompt/Stop pair that records each session's trace (opt-in).
│   └── experimental/      Prototypes, NOT wired into settings.json (webfetch revalidation cache).
├── bin/                Small tracked utilities, plain scripts with no Claude Code knowledge:
│                        claude-bootstrap (set up a second machine), morph-mirror (+ its test),
│                        morph-recover-orphans (assemble traces for sessions that died),
│                        otel-spooler (offline OTLP buffer), vault-write + vault-spooler
│                        (queue notes offline, deliver on reconnect; + tests, + .service).
├── skills/             Model-invoked procedures (add your own; see skills/README.md).
├── settings.json       Wires the hooks + statusline.
├── checkpoints/        Per-session state.json + timeline.jsonl. Local, pruned at 14 days, unversioned.
├── vault-queue/        Notes awaiting delivery (+ sent/, dead/). Local, unversioned.
└── .gitignore          Whitelist model — tracks config, excludes all secrets/history/transcripts.
```

---

## Commands — what you can type

Slash commands live in `commands/*.md`; the filename **is** the command, and whatever you type after
it lands where the file says `$ARGUMENTS` (invoke bare to work off the current conversation). Rules
and agents are *not* typed — rules auto-load when the work touches them, agents get delegated to.

| Command | Usage | What it does |
|---|---|---|
| `/whereami` | `/whereami` | Report current host / git / docker context so you don't act on the wrong machine. |
| `/resume` | `/resume` | Reconstruct what you were doing and where you left off — no action yet. |
| `/safe-change` | `/safe-change <what you're changing>` | Walk an infra change through the staged, reversible, observe-first protocol. |
| `/improve-loop` | `/improve-loop <what to improve>` | Run an autoresearch-style keep-or-rollback loop against a measurable target (software only). |
| `/ledger` | `/ledger [attempt/decision]` | Append an experiment/decision entry to the project's `LEDGER.md`. |
| `/debug` | `/debug [the failure]` | Root-cause a failure with a disciplined triage instead of guessing or patching symptoms. |
| `/ideate` | `/ideate [idea or problem]` | Diverge then converge on a raw idea — variations, honest evaluation, a sharp "Not Doing" list. |
| `/think` | `/think [decision or argument]` | Pressure-test a decision or argument with the thought-partner subagent. |
| `/edit` | `/edit [draft or file]` | Hand a draft to the editor subagent for a hard, voice-aware read. |
| `/doc-sweep` | `/doc-sweep [area]` | Sweep the docs for accuracy + coherence via the doc-steward agent. |

`/debug` and `/ideate` are the newest, adapted from patterns in
[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills).

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

The corollary is that hooks are also how *state* gets written, not just how decisions get made: the
same guarantee that vets a command is what lets a session leave a durable record of itself without
being asked (`checkpoint.py`). And below all of it sits `bin/` — plain scripts with no Claude Code
knowledge at all, runnable from a shell, a systemd unit, or an agent alike. Anything that has to work
when Claude *isn't* running belongs there rather than in a hook.

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

**The guardrail is data, not code — and it depends on nothing.** Destructive-command patterns live in
`guardrail_rules.py` (`action` + `why` + regexes); `guardrail.py` is a ~190-line engine. The rules are
a plain Python dict literal — data the interpreter itself parses — so tuning the guardrail means
editing a list of regexes, not logic, and it needs no parser and no package. That second half is
load-bearing: the rules used to be YAML, and *fail-open plus a third-party import* is a trap. On a
machine without PyYAML the guardrail couldn't load its rules and silently allowed every destructive
command. A control you can disarm by **not** installing something is not a control. (Raw strings
rather than JSON, too: the rules are regex-heavy, and backslash-doubling in a safety file is an error
hazard.) It matches at *command-segment start* so a dangerous word buried in an argument doesn't
trip it. Two
tiers: **deny** the catastrophic (wipe a disk/root), and **ask** on the destructive-but-legitimate
(destroy a dataset, prune volumes, force-push) and the *agency* cases you never want done unprompted
(a push that lands on **main/master**; schedule an unattended `cron`/`at`/systemd job). Everyday git
is deliberately free: commits and feature-branch pushes never ask — they're local/recoverable, and
the loop doctrine's "keep = commit" depends on them not halting auto mode. The mainline-push rule is
branch-aware (a `guard` the engine evaluates: explicit refspecs read from the command, bare/`HEAD`
pushes resolved against the current branch, unknown treated as "could be main"), and its ask message
carries a `hint` that tells the agent how to keep working — branch off, push the branch, queue the
mainline push in the approvals file — instead of just stopping. That promotes the CLAUDE.md "main is
the edge" rule from advisory prose into a deterministic stop that fires even in bypass mode. It's a
safety net for accidents and overreach, explicitly *not* a security boundary.

**Test a hook the way the harness runs it — the runtime floor is the oldest box you have.** The same
fail-open design that makes a guardrail bug harmless makes a guardrail *import* error invisible:
PreToolUse reads a non-zero exit as a non-blocking error, so a hook that dies at import allows
everything, silently. It did. `guardrail.py` used three constructs that need Python 3.9 or newer
(`dict[str, Any]`, `collections.abc.Callable[...]`, `str.removeprefix`), and on an Ubuntu 20.04 box
running Python 3.8.10 it raised TypeError before it ever read a command. `rm -rf /` sailed through. A
guardrail you think you have is worse than none. The root cause wasn't the annotations; it was the
tests, which did `import guardrail` and so never exercised the interpreter `#!/usr/bin/env python3`
actually resolves to on that machine. `test_end_to_end_under_system_python()` now runs the hook as a
subprocess over stdin and asserts the emitted decision, verified on 3.8.10, 3.11.13, and 3.13.9. Two
rules fell out of it, and they apply to anything you add to `hooks/`: the **runtime** floor is the
oldest interpreter in your fleet — here **3.8**, so `Dict[str, Any]` and `Optional[str]` from
`typing`, never the PEP 585/604 builtins in a runtime assignment; mypy can still check at 3.9, because
`from __future__ import annotations` means annotations are never evaluated and only *runtime*
subscripting is a hazard. And every hook gets at least one test that invokes it as a process, not as
an import.

**Nothing to install.** Every executable piece here — all the hooks, `bin/otel-spooler.py`,
`bin/vault-write` and `bin/vault-spooler.py` — runs on the Python 3 and shell your machine already
has. Zero third-party packages, so there's no pip step, no venv, and nothing to install globally:
unzip it and it works. That began as convenience and became a rule once the guardrail showed the
other edge of it — a dependency you have to remember to install is a dependency that will be missing
somewhere, and the failure is silent. The one thing a clone *can't* carry is the exec bit: if the
repo's origin machine has `core.fileMode=false` (a network home directory, say), `chmod +x` isn't
recorded by git, and a new hook lands 100644 and dies with "permission denied" on a fresh clone.
Adding one means `git update-index --chmod=+x`, and `claude-bootstrap` reasserts the bits on arrival
as a backstop — globbing `bin/` (everything but the `.service` units) rather than naming scripts,
because a hand-written list drifts.

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

**A killed session should cost one turn, not a day.** Sessions die — a dropped SSH pipe, a closed
laptop, a killed terminal — and everything that reconstructs what you were doing used to run only at
`Stop`. So the one case where you most need the record is exactly the case that produced none. The
`checkpoint.py` hook writes a small `state.json` plus a `timeline.jsonl` under
`checkpoints/<session-id>/` on every prompt, after every mutating tool call
(`Bash|Write|Edit|MultiEdit`), and at `Stop`. Three things make it work. Its schema deliberately
**mirrors** the harness's own `jobs/<id>/state.json` — `state`, `detail`, `needs`, `resumeSessionId`,
`cwd`, transcript path and offset — so `/resume` and anything else that already understands a job
record reads a checkpoint with no new parser; it mirrors that shape without writing into `jobs/`,
which the harness owns. `state: completed` is written **only** by the Stop hook, which is what makes a
checkpoint left at `active` mean *interrupted* rather than merely *old* — the whole signal falls out
of having one writer. And the write is cheap enough to afford every turn: only the git branch/dirty
enrichment costs a subprocess, so that's cached on a 60s cadence while the state file itself is
rewritten unthrottled, since by the time the hook has been spawned, skipping the write saves nothing
and costs fidelity. It prunes at 14 days, is stdlib-only, and exits 0 on every path. A record nobody
reads isn't resilience, so `session_start.sh` surfaces a previous session in *this* directory that
ended without a clean Stop, and `/resume` reads machine state **first** before the human-written
continuity docs, and says so when they disagree: machine state for what happened, docs for what was
intended. The same gap swallowed the opt-in session traces, which the `morph-global-*` hooks likewise
assemble only at `Stop`; `bin/morph-recover-orphans` reconstructs the missing Stop payload and pipes
it back into that same hook rather than reimplementing the assembler — one assembler, one set of bugs
— and only touches a session that's been cold for hours, because assembling a *live* one would consume
its pending state and leave the real Stop with nothing. The pattern generalizes past this repo: **if a
record is only written at the end, the failures you most want to see produce no record at all.**

**Memory is local; provenance lives in the repo.** Across sessions Claude keeps a per-project memory
store (auto-managed, gitignored). The durable knowledge you *do* want to keep rides in the repo it
belongs to: a `LEDGER.md` records what was *tried* — hypothesis, change, gate result, metric
before→after, verdict — which is provenance for the experiments, not just what shipped. These are the
*intent* half of what `/resume` reads — memory, the repo's continuity docs, and the ledger's tail,
layered on top of the machine state above to reconstruct where you left off before touching anything.

**Capture to a queue; keep exactly one writer of the canonical store.** For knowledge that should
outlive the repo it came from — an applied infra change, a load-bearing decision, a runbook step
learned the hard way — `bin/vault-write` enqueues one markdown-plus-frontmatter note into
`vault-queue/`, and that is *all* it does. Capture is a plain file write: no daemon, no network, not
even a localhost port, so it behaves identically on a server and on a laptop with no wifi, which means
there's never a reason to skip writing something down "because we're offline." `bin/vault-spooler.py`
drains the queue later over HTTP PUT to whatever endpoint you configure (`VAULT_UPSTREAM`), scoped to
one inbox directory and nothing else; something on the other side files notes from there into their
final home. That scoping is the design: **one writer of the canonical files**, so a two-way merge
never has to exist.

It's a fork of `bin/otel-spooler.py`, which was already a correct store-and-forward implementation,
and the three places it diverges are all the same point: **knowledge is not telemetry.** The OTel
spooler evicts its oldest spool file to stay under its cap — a lossy ring buffer, entirely right for
metrics and silent data loss for a decision record — so here over-cap is a loud refusal at enqueue
time and nothing already queued is ever deleted to make room. Delivery is idempotent rather than
merely at-least-once: the filename carries a content hash, so a crash between the PUT and the cleanup
replays onto the same inbox object instead of duplicating the note, and delivered notes move to
`sent/` rather than being unlinked, so a failed cleanup can't resurrect one either. And failure is
visible: a non-empty `dead/` (a 4xx quarantine, so one poison note can't wedge the queue) or an
over-cap queue is surfaced in the session banner and by `--status`, not one stderr line nobody reads.
5xx and offline back off 10s → 5min and keep everything, in order. Unlike the OTel spooler there's no
HTTP listener at all — you control the writer, so the daemon is drain-only and nothing needs to be
running for a note to survive. `bin/test_vault_spooler.py` covers delivery, crash-replay idempotency,
offline-keeps-everything, 4xx-quarantine vs. 5xx-retry, and the no-eviction cap against a real HTTP
server. Point it at your own endpoint, or leave `VAULT_UPSTREAM` unset and the queue is simply a local
capture log.

---

## Secrets & versioning

A live `~/.claude` is full of secrets — credentials, chat history, transcripts, caches. So
`.gitignore` uses a **whitelist**: ignore everything, then re-include only the authored config. Two
things to keep honest: the top-level catch-all only ignores *new top-level* entries, so a file dropped
*inside* a re-included dir **is** tracked; and the re-includes name whole directories. The real secret
defense is a second layer of **pattern ignores** (`*.env`, `*.key`, `*.pem`, `*.crt`, `*.p12`,
`id_rsa*`, plus caches, `.credentials.json`, `history.jsonl`, `sessions/`, `projects/`) that hold
*even inside* a versioned dir. This same file, installed as your real `~/.claude/.gitignore`, keeps
your private state out of git while you version your config in place. The runtime state the hooks
produce is local by the same rule: `checkpoints/` and `vault-queue/` are machine-written, not
authored, so the top-level catch-all leaves them alone. They're also the two directories that grow on
their own, so each is bounded where it's written — checkpoints prune at 14 days, the vault queue
refuses new entries at its cap rather than evicting — because nothing here should fill a disk while
you're not looking. Spooler credentials live in `~/.config/*.env`, outside the tree entirely; only the
`.example` files are tracked.

---

## Credit

Distilled from a working private setup, and shared so others can fork a point of view rather than
start from an empty file. Take what's useful, delete what isn't, and make the modes your own. The
throughline worth keeping: **spend context deliberately, make the important things deterministic, keep
a human in the loop for anything hard to undo, and treat the configuration itself as a maintained,
coherent codebase.**

MIT licensed — see [LICENSE](LICENSE).
