# Keeping a private `~/.claude` and this public mirror in step

This repo is a **sanitized mirror** of a working `~/.claude`, not its source. The
private copy is where changes are made; this one is where they are published
with the personal parts taken out. That asymmetry is the whole of the procedure,
and everything below follows from it.

You only need this if you run the same split — a private harness you actually
use, and a public copy you share. If you just adopted this repo, read
[ADOPTING.md](ADOPTING.md) instead.

## The rule

**Private is committed first, and the public mirror is never ahead of it.**

Not for tidiness. The sanitizing only ever removes — hostnames, real paths,
the name of a personal agent, anything that names a machine or a person. A
change that lands here first has, by definition, not been through that pass, and
the cheapest moment to notice something should not be public is *before* it is.

## The steps

1. **Commit in the private repo first.** The change is finished there, gate
   green, before the mirror is touched at all.

2. **Apply the same change here — re-apply it, do not copy the file.** Both
   repos have the same shape (`hooks/`, `bin/`, `agents/`, `commands/`,
   `settings.json`, docs), so a straight copy looks right and quietly drags a
   private path or a machine name across with it. Make the same edit, in this
   repo's own wording.

3. **Check for drift.** Compare the two copies of anything that exists in both
   — `bin/`, `hooks/`, `settings.json` — and confirm the only differences are
   the sanitized ones you intended. A file present in both is the thing that
   drifts; a file present in only one cannot.

4. **Scan for leaks before pushing.** Both repos run pre-commit hooks that grep
   for credential shapes. Beyond secrets, the recurring leaks in a mirror like
   this one are duller and easier to miss: absolute home paths, internal
   hostnames, an internal domain, the name of a service only you run.

5. **Push private, then public.** In that order, for the same reason as step 1.

## What actually goes wrong

**The mirror silently falls behind on a shared file.** This is the common one,
and it does not announce itself: you fix something in the private copy, push it,
move on, and the public copy of the same script keeps its old behaviour for
weeks. It is worth re-checking the shared files periodically rather than trusting
that every past change remembered step 2. (Written after doing exactly this: a
`bin/vault-write` fix landed privately and the mirror kept the old code until a
later sweep noticed.)

**A file that only makes sense privately gets mirrored anyway.** Some things are
about one person's machines — a network map, a host inventory, notes naming
rooms in a house. Those are not "sanitize and publish", they are "do not
publish". Deciding that per file, once, is easier than sanitizing the same file
repeatedly and hoping.

**A shared or network filesystem delays the change on other machines.** If
`~/.claude` lives on a network home mounted by several machines, a newly
*created* file can be invisible to the others for as long as the attribute cache
holds — replacing an existing file usually propagates promptly, which is what
makes a new one the surprising case. After adding a file, verify on the other
machine before concluding the change did not work.

## Worked example

A hook kill-switch (`CLAUDE_HOOKS_OFF`) was added privately. Both the private
README and this repo's `ADOPTING.md` needed the same paragraph, in the same
words, and both were committed and pushed together as one change across the two
repos — private first.
