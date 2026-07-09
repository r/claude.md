# Adopting this setup

A 10-minute path from clone to a working, personalized `~/.claude`. Read the
[README](../README.md) first for the *why*; this is the *how*.

## 1. Get the files into `~/.claude`

If you don't already have a `~/.claude` you care about:

```bash
git clone https://github.com/r/claude.md ~/.claude
```

If you already have a `~/.claude`, don't clobber it — clone elsewhere and copy in the pieces you want:

```bash
git clone https://github.com/r/claude.md /tmp/claude-setup
# then copy over the parts you want, e.g.:
cp -r /tmp/claude-setup/{rules,agents,commands,hooks,bin} ~/.claude/
cp /tmp/claude-setup/settings.json ~/.claude/settings.json   # review first if you have one
```

Make the hooks and scripts executable:

```bash
chmod +x ~/.claude/hooks/*.sh ~/.claude/hooks/guardrail.py ~/.claude/bin/*
```

## 2. Wire up `settings.json`

`settings.json` registers the hooks and the status line using `$HOME/.claude/...` paths. If your
Claude Code build doesn't expand `$HOME` in hook command strings, replace it with your absolute home
path. Then start a new Claude Code session and confirm:

- the **status line** shows `host │ dir ⎇ branch │ model`, and
- a **session-start banner** names your host, directory, and git/docker state.

The `guardrail.py` hook needs Python 3 with `pyyaml`. It **fails open** — if the dep is missing it
just allows actions rather than blocking you — but you want it working, so:

```bash
python3 -c "import yaml" || pip install pyyaml
python3 ~/.claude/hooks/test_guardrail.py    # should print: ok — N guardrail cases passed
```

## 3. Customize `CLAUDE.md` — keep only the modes you work in

`CLAUDE.md` is always loaded, so it's the most valuable context to keep lean. Edit it:

- Delete any of the three modes (infra / software / knowledge-work) you don't do.
- The "how I work", "never do these", secrets, and continuity sections are general — keep them, tune
  the wording to your taste.

## 4. Fill in the `.example` templates

Two rules ship as templates because they're inherently personal. Copy each and make it yours:

```bash
cp ~/.claude/rules/voice.md.example ~/.claude/rules/voice.md
cp ~/.claude/rules/infra.md.example ~/.claude/rules/infra.md
```

- **`voice.md`** — your writing voice, so the `editor` agent drafts and critiques as *you*. The best
  way to fill it: point Claude at 10–20 things you've written and ask it to derive the profile
  (tone by medium, rhythm, diction, taboos), then edit what it gives you. The template explains this.
- **`infra.md`** — your host map. The safe-change protocol in it needs no changes; just fill in your
  hosts and topology. If you don't run infrastructure, delete both the file and the infra mode.

`rules/software.md` is an *example* stack doctrine (Python/`uv`/`ruff`/`mypy`). Replace the stack
details with yours, or delete it. Keep the shape: a short house style plus a hard quality gate.

## 5. Try each mechanism once

- **A command:** type `/whereami` — read-only, confirms host/git/docker.
- **The knowledge-work agents:** `/edit` a paragraph of your writing, or `/think` a decision you're
  weighing. (Fill in `voice.md` first for `/edit` to be useful.)
- **The guardrail:** in a scratch repo on `main`, try `git push` — it should *ask* (pushing the
  mainline is the agency gate) and tell the agent to branch off instead. Then `git switch -c test`
  and note that `git commit` and a branch push sail through: everyday git is deliberately free.
- **A loop (software only):** `/improve-loop` against a measurable target sets up a checker-first,
  keep-or-rollback loop on a throwaway branch. Read `rules/loops.md` first.

## 6. Version your own config (optional)

The `.gitignore` uses a whitelist model: it tracks only the authored config and keeps all secrets,
history, and transcripts out — so you can safely `git init` your `~/.claude` and push it to a
**private** remote. Note that `rules/voice.md` and `rules/infra.md` are gitignored by default (they're
your personalized copies); delete those two lines from `.gitignore` if you want to version them in a
private repo.

## Turning things off

Anything here can be disabled in `settings.json` (remove a hook) or by starting Claude Code with
`--safe-mode`. The tools *suggest and review*; you decide what actually happens.
