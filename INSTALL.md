# Installing this Claude Code config

A portable, de-personalized [Claude Code](https://code.claude.com) global setup. Works on **macOS**
and **Linux**. See `README.md` for what each piece does and *why*; `docs/ADOPTING.md` is the
step-by-step guide to making it yours.

## Quick install

```bash
unzip claude-config.zip
cd claude-portable
./install.sh
```

(Or clone the repo and run `./install.sh` from its root — the zip is just `git archive` of the repo.)

`install.sh` copies the authored config into `~/.claude`, backing up anything it would overwrite into
`~/.claude/.backup-<timestamp>/`. It **never** touches runtime state (`projects/`, `sessions/`,
`history.jsonl`, caches, credentials) if a `~/.claude` already exists. It ends with a preflight report
of which optional tools are present.

Install somewhere other than `~/.claude`:

```bash
./install.sh /path/to/target/.claude
```

## Prerequisites

| Tool | Needed for | If missing |
|------|-----------|------------|
| **python3** | session banner, status line, doc-drift nudge, guardrail | those hooks no-op; install via Xcode CLT (`xcode-select --install`) or `brew install python` |
| **PyYAML** | the guardrail reads its rules from YAML | **guardrail fails OPEN (allows everything)** — `python3 -m pip install pyyaml` |
| **git** | the loop / commit / continuity workflow | core workflow features degrade |
| ruff *or* uv | Python auto-format on save | that hook no-ops (optional) |
| docker | container count in the session banner | banner omits it (optional) |
| `timeout` | bounding hook subprocesses | hooks run unbounded — harmless; macOS gets it via `brew install coreutils` (as `gtimeout`, which the hooks detect) |
| morph | the opt-in VCS mirror | `bin/morph-mirror` no-ops cleanly (optional) |

The only prerequisite that changes *safety* rather than *convenience* is **PyYAML** — without it the
destructive-command guardrail can't load its rules and fails open. Install it.

## What's here

```
CLAUDE.md        Always-loaded global doctrine. EDIT THIS FIRST — make it yours.
settings.json    Wires the hooks + status line (paths use $HOME, so no editing needed).
rules/           software.md, loops.md, knowledge-work.md, plus two templates you personalize:
                 infra.md.example (host map + safe-change) and voice.md.example (your prose voice).
commands/        Slash commands: /whereami /safe-change /resume /improve-loop /ledger /doc-sweep
                 /edit /think.
agents/          doc-steward, infra-reviewer, editor, thought-partner.
hooks/           session_start, guardrail (+rules +tests), py_autoformat, statusline, doc_drift.
bin/             morph-mirror (+ its test).
skills/          Where your own skills go (see its README).
docs/            ADOPTING.md — the 10-minute adoption walkthrough.
```

## After installing

1. **Edit `~/.claude/CLAUDE.md`** — it's written in a neutral voice but encodes one person's
   preferences. Make it match how you work.
2. **Copy the templates you'll use:** `rules/infra.md.example → rules/infra.md` (fill in your host
   map) if you do infra/ops work; `rules/voice.md.example → rules/voice.md` (codify your writing
   voice) if you'll use `/edit`. Delete what you don't need.
3. Open a new Claude Code session. The status line (`host │ dir ⎇ branch │ model`) and the
   session-start banner confirm the hooks are live.
4. To version your `~/.claude`, the included `.gitignore` uses a whitelist model that tracks only the
   authored config and excludes all secrets, history, and session state: `cd ~/.claude && git init`.

## Verify the hooks work

```bash
# guardrail unit tests (should print "ok — N guardrail cases passed")
python3 ~/.claude/hooks/test_guardrail.py

# morph-mirror tests (should print "ok — all morph-mirror cases passed")
bash ~/.claude/bin/test_morph_mirror.sh
```

A quick feel for the agency gate: in a scratch repo on `main`, `git push` *asks* (and tells the agent
to branch off instead of stalling); `git commit` and feature-branch pushes sail through freely.

## Uninstall / roll back

Everything overwritten is in `~/.claude/.backup-<timestamp>/`. Move it back, or delete the installed
config files. Runtime state was never modified.

## Regenerating the downloadable zip (maintainers)

```bash
git archive --format=zip --prefix=claude-portable/ -o claude-config.zip HEAD
```

`.gitattributes` marks the blog notes as `export-ignore`, so the archive contains only the config.
