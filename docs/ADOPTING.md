# Adopting this setup

A 10-minute path from a fresh install to a `~/.claude` that is yours. Read the
[README](../README.md) first for the *why*; this is the *how* of personalizing it. Installing,
prerequisites, and verification are [INSTALL.md](../INSTALL.md)'s job and are not repeated here.

## 1. Install

Run `install.sh` as [INSTALL.md](../INSTALL.md) describes — `git clone` the repo, then
`./install.sh`. It copies the authored config into `~/.claude`, backs up anything it replaces, leaves
runtime state alone, sets the exec bits, and seeds `rules/infra.md` and `rules/voice.md` from their
`.example` templates if you don't already have them. Then start a new Claude Code session and
confirm:

- the **status line** shows `host │ dir ⎇ branch │ model`, and
- a **session-start banner** names your host, directory, and git/docker state.

If neither appears, the hook paths in `settings.json` are the first thing to check: they use
`$HOME/.claude/...`, and a Claude Code build that doesn't expand `$HOME` in hook command strings
needs the absolute home path instead. The test suite and what it proves are under *Verify the hooks
work* in INSTALL.md.

## 2. Customize `CLAUDE.md` — keep only the modes you work in

`CLAUDE.md` is always loaded, so it's the most valuable context to keep lean. Edit it:

- Delete any of the three modes (infra / software / knowledge-work) you don't do.
- The "how I work", "never do these", secrets, and continuity sections are general — keep them, tune
  the wording to your taste.

## 3. Fill in the templates

Two rules ship as `.example` templates because they're inherently personal. `install.sh` seeded
working copies for you; if you installed by hand, copy them yourself:

```bash
cp -n ~/.claude/rules/voice.md.example ~/.claude/rules/voice.md
cp -n ~/.claude/rules/infra.md.example ~/.claude/rules/infra.md
```

- **`voice.md`** — your writing voice, so the `editor` agent drafts and critiques as *you*. The best
  way to fill it: point Claude at 10–20 things you've written and ask it to derive the profile
  (tone by medium, rhythm, diction, taboos), then edit what it gives you. The template explains this.
- **`infra.md`** — your host map. The safe-change protocol in it needs no changes; just fill in your
  hosts and topology. If you don't run infrastructure, delete both the file and the infra mode.

`rules/software.md` is an *example* stack doctrine (Python/`uv`/`ruff`/`mypy`). Replace the stack
details with yours, or delete it. Keep the shape: a short house style plus a hard quality gate.

## 4. Try each mechanism once

- **A command:** type `/whereami` — read-only, confirms host/git/docker.
- **The knowledge-work agents:** `/edit` a paragraph of your writing, or `/think` a decision you're
  weighing. (Fill in `voice.md` first for `/edit` to be useful.)
- **The guardrail:** in a scratch repo on `main` with at least one commit *you* authored, try
  `git push` — it should *ask* (pushing a human's mainline is the agency gate) and tell the agent to
  branch off instead. Then `git switch -c test` and note that `git commit` and a branch push sail
  through: everyday git is deliberately free. If the repo's ROOT commit is Claude's, the push won't
  ask at all — that's the origin exemption in `rules/software.md`, not a broken gate. `bin/repo-origin`
  says which way any repo reads, and records an override when the root commit gets it wrong.
- **A loop (software only):** `/improve-loop` against a measurable target sets up a checker-first,
  keep-or-rollback loop on a throwaway branch. Read `rules/loops.md` first.

## 5. Version your own config (optional)

The `.gitignore` uses a whitelist model: it tracks only the authored config and keeps all secrets,
history, and transcripts out — so you can safely `git init` your `~/.claude` and push it to a
**private** remote. Note that `rules/voice.md` and `rules/infra.md` are gitignored by default (they're
your personalized copies); delete those two lines from `.gitignore` if you want to version them in a
private repo.

## Turning things off

Anything here can be disabled in `settings.json` (remove a hook) or by starting Claude Code with
`--safe-mode`. The tools *suggest and review*; you decide what actually happens.

For a single session, every hook except the guardrail honours `CLAUDE_HOOKS_OFF` — the ids, the
matching rules, and why the guardrail is exempt are under *Turning a hook off* in the
[README](../README.md).
