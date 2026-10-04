# Installing this Claude Code config

A portable, de-personalized [Claude Code](https://code.claude.com) global setup. Works on **macOS**
and **Linux**. See `README.md` for what each piece does and *why*; `docs/ADOPTING.md` is the
step-by-step guide to making it yours.

## Install

```bash
git clone https://github.com/r/claude.md claude-setup
./claude-setup/install.sh
```

That is the only install path. `install.sh` copies the authored config into `~/.claude`, backing up
anything it would overwrite into `~/.claude/.backup-<timestamp>/`. It **never** touches runtime state
(`projects/`, `sessions/`, `history.jsonl`, caches, credentials) if a `~/.claude` already exists, and
it never overwrites a `rules/infra.md` or `rules/voice.md` you have already personalized — it only
seeds them from the `.example` templates when they are absent. Re-running it is safe. It ends with a
preflight report of which optional tools are present.

What gets installed, and what each piece is for, is the inventory in [README.md](README.md).

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
  full plan and changes nothing; `--no-otel` / `--no-agent` skip either half (the second half is the
  mTLS client cert and `agent.env` for a personal agent you run yourself; most people have no such
  thing and skip it).

The secrets never touch an intermediate disk: they're pulled over SSH at install time, written `600`,
and the profile is `eval`'d in-process rather than copied down.

## Prerequisites

| Tool | Needed for | If missing |
|------|-----------|------------|
| **python3** | session banner, status line, doc-drift + vault curator/nudge, guardrail | those hooks no-op — including the guardrail, which then **fails open**; install via Xcode CLT (`xcode-select --install`) or `brew install python` |
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

## After installing

1. **Edit `~/.claude/CLAUDE.md`** — it's written in a neutral voice but encodes one person's
   preferences. Make it match how you work.
2. **Fill in the seeded templates:** `rules/infra.md` (your host map) if you do infra/ops work;
   `rules/voice.md` (your writing voice) if you'll use `/edit`. Delete what you don't need.
3. Open a new Claude Code session. The status line (`host │ dir ⎇ branch │ model`) and the
   session-start banner confirm the hooks are live.
4. To version your `~/.claude`, the included `.gitignore` uses a whitelist model that tracks only the
   authored config and excludes all secrets, history, and session state: `cd ~/.claude && git init`.

The full personalization walkthrough is [docs/ADOPTING.md](docs/ADOPTING.md).

## Verify the hooks work

```bash
# every test in the config — offline, scratch dirs only, nothing live is touched
~/.claude/bin/run-tests

# add the linters too, if you have ruff and/or shellcheck (both optional)
~/.claude/bin/run-tests --lint
```

That should end on `ok — N/N passed`. Run it after any edit to a hook: the whole point of a hook is
that it's a guarantee rather than a request, and a guarantee nobody checks is a request again.
Individual files still run on their own (`python3 ~/.claude/hooks/test_guardrail.py`) when you want
one in isolation.

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

## Optional: run the vault spooler as a background service

`bin/vault-spooler.py` drains `~/.claude/vault-queue/` (notes captured offline) to your vault
endpoint; see the README for what it is and `bin/vault-spooler.env.example` for its config. Running it
by hand works, but a queue that nothing drains is the failure mode to avoid, so both platforms ship a
service definition:

- **Linux (systemd user unit):** `bin/vault-spooler.service` — its header is the install recipe.
- **macOS (launchd user agent):** `bin/vault-spooler.plist.example` plus `bin/vault-spooler-run.sh`.
  launchd cannot read an `EnvironmentFile`, so the plist calls the wrapper script, which sources
  `~/.config/vault-spooler.env` (`chmod 600`) and execs the spooler — credentials never land in the
  plist. Install:

  ```bash
  sed "s|__HOME__|$HOME|g" ~/.claude/bin/vault-spooler.plist.example \
    > ~/Library/LaunchAgents/local.vault-spooler.plist
  launchctl load -w ~/Library/LaunchAgents/local.vault-spooler.plist
  bash ~/.claude/bin/vault-spooler-run.sh --status      # health check
  ```

  The plist's header explains how to read its exit status (a nonzero last-exit while off-network is
  "retained, will retry", not breakage) and the one-line rollback.

## Uninstall / roll back

Everything overwritten is in `~/.claude/.backup-<timestamp>/`. Move it back, or delete the installed
config files. Runtime state was never modified.
