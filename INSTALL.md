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

## Multi-machine install (`bin/claude-bootstrap`)

`install.sh` copies this template onto one machine. **`claude-bootstrap` is for the other case:** you
already run this config on one box, you keep it in a git repo, and you want a *second* machine — a
Mac, a laptop — to match it, including the parts that aren't in git.

```bash
./bin/claude-bootstrap --from you@home-host
```

Run it on the new machine while it can reach your home host. In one pass it attaches `~/.claude` to
your config repo, mints a **per-machine mTLS client cert**, installs the offline telemetry spooler as
a background service (launchd on macOS, systemd user unit on Linux), sources the telemetry env from
your shell rc, and then verifies all of it.

It reads every machine-specific value — repo URL, endpoints, tokens, CA paths — from a profile on the
home host (`~/.claude-bootstrap.profile`, `chmod 600`, format in `bootstrap.profile.example`). **The
script itself contains no hostnames and no secrets**, which is why it can ship here unmodified.

Three properties worth knowing, because they're the reason it exists:

- **Per-machine certs.** Each machine gets its own client cert (`CN=claude-<hostname>`). Lose the
  laptop and you revoke exactly one cert; every other machine keeps working. Copying one shared key
  around means a single loss forces you to re-issue everywhere.
- **It survives being off-network.** Claude Code's OTLP exporter has no disk buffer, so telemetry
  aimed straight at a backend is *dropped* whenever that backend is unreachable. Bootstrap points
  Claude at the local spooler instead, which buffers to bounded disk and replays on reconnect — so a
  laptop that's only sometimes on your network (or VPN) loses nothing.
- **Idempotent, and it backs up whatever it replaces.** Re-running is safe. `--dry-run` prints the
  full plan and changes nothing; `--no-otel` / `--no-zora` skip either half.

The secrets never touch an intermediate disk: they're pulled over SSH at install time, written `600`,
and the profile is `eval`'d in-process rather than copied down.

## Prerequisites

| Tool | Needed for | If missing |
|------|-----------|------------|
| **python3** | session banner, status line, doc-drift + vault nudges, guardrail | those hooks no-op — including the guardrail, which then **fails open**; install via Xcode CLT (`xcode-select --install`) or `brew install python` |
| **git** | the loop / commit / continuity workflow | core workflow features degrade |
| ruff *or* uv | Python auto-format on save | that hook no-ops (optional) |
| docker | container count in the session banner | banner omits it (optional) |
| `timeout` | bounding hook subprocesses | hooks run unbounded — harmless; macOS gets it via `brew install coreutils` (as `gtimeout`, which the hooks detect) |
| morph | the opt-in VCS mirror | `bin/morph-mirror` no-ops cleanly (optional) |

**No third-party Python packages.** Every hook, plus `bin/otel-spooler.py`, is stdlib-only on purpose:
there is no pip step, no venv, and nothing to install globally. The guardrail is the reason it's a rule
and not just a nicety — its rules used to be YAML, so on a machine without PyYAML it couldn't load them
and, being fail-open, silently allowed every destructive command. A safety control you can disarm by
*not* installing something is not a control, so the rules are now a plain Python dict literal
(`hooks/guardrail_rules.py`). The prerequisite that still changes *safety* rather than convenience is
therefore **python3** itself: without it the guardrail doesn't run at all.

## What's here

```
CLAUDE.md        Always-loaded global doctrine. EDIT THIS FIRST — make it yours.
settings.json    Wires the hooks + status line (paths use $HOME, so no editing needed).
rules/           software.md, loops.md, knowledge-work.md, prerelease.md, plus two templates you
                 personalize:
                 infra.md.example (host map + safe-change) and voice.md.example (your prose voice).
commands/        Slash commands: /whereami /safe-change /resume /improve-loop /ledger /doc-sweep
                 /edit /think.
agents/          doc-steward, infra-reviewer, editor, thought-partner.
hooks/           session_start, guardrail (+rules +tests), py_autoformat, statusline, doc_drift,
                 vault_nudge (+ its test), morph-global-{prompt,stop} (opt-in: record every
                 session — see below).
bin/             claude-bootstrap (set up a second machine — see above), morph-mirror (+ its test),
                 otel-spooler (offline OTLP buffer — see docs/OTEL.md) + its systemd unit.
bootstrap.profile.example
                 Template for the profile claude-bootstrap reads off your home host.
skills/          Where your own skills go (see its README).
docs/            ADOPTING.md — the 10-minute adoption walkthrough; OTEL.md — send Claude Code
                 metrics to your own local backend (opt-in).
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

## Optional: record every session (morph trace capture)

The `morph-global-{prompt,stop}` hooks can archive every Claude Code session — prompts, responses,
and tool calls — into a single local [morph](https://r.github.io/morph/) store, regardless of which
directory you're working in. It's **off by default and costs nothing until you opt in**: both hooks
bail in one line of bash if the store doesn't exist, so an un-opted machine never even starts Python.

To turn it on (needs the `morph` binary):

```bash
mkdir -p ~/.claude/morph-traces && cd ~/.claude/morph-traces && git init && morph init --git-init .
```

From then on, browse sessions with `morph session list` / `morph session show --with-trace <hash>`.
To turn it off, remove `~/.claude/morph-traces` (or the two hooks from `settings.json`). Everything
stays local — nothing is uploaded.

## Uninstall / roll back

Everything overwritten is in `~/.claude/.backup-<timestamp>/`. Move it back, or delete the installed
config files. Runtime state was never modified.

## Regenerating the downloadable zip (maintainers)

```bash
git archive --format=zip --prefix=claude-portable/ -o claude-config.zip HEAD
```

`.gitattributes` marks the blog notes as `export-ignore`, so the archive contains only the config.
