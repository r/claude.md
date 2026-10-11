# Containment — when a session runs inside a sandbox

Load this when you are **inside a contained session** and something fails with "Operation not
permitted", "Read-only file system", or "No such file" for a path that exists outside; when
git or ssh is refused; or when a task needs a secret the sandbox withholds (a signing key, a
token). The sandbox this is written for is [corral](https://github.com/r/corral), which sets
`ZNUC_CONTAINED` inside; another sandbox with the same shape (a writable project, a gateway
for the outside, policy on the machine) reads the same way.

corral's own `docs/agent-guide.md` is the authoritative page; this is the summary that travels
with the Claude config.

## What is true

- **Writable:** the project, and a private scratch (`TMPDIR`). Nothing else. The rest of home is
  hidden or read-only, secrets with it. A write anywhere else fails. That is the sandbox, not a
  broken machine.
- **git, ssh and signing go through a gateway outside.** git reaches only the project's own
  remotes (no force-push, no branch deletion); ssh only the hosts the project was granted; signing
  runs outside on the project's own archive. Keys never come in.
- **The policy is on the machine, not in the project**, and you cannot read or change it.
  `corral grants` shows what this session may do.
- **Grants are fixed at session start** for the ones the sandbox is built from (`contain`,
  `xcode`, `egress`, `trace`, a profile); ssh hosts, actions and release count at once. Every
  refusal says which.

## First session in a project — ask once, up front

1. `corral grants`.
2. Work out what the task will need that you do not have: a deploy host, a token, a key, a build
   tool.
3. Ask for all of it in **one** message, with `corral request KEY=VALUE --why "..."` per grant, so
   the owner answers once (`corral grant`) rather than once per refusal.
4. Carry on with everything that does not need them.

## When a task needs a withheld secret — write an action

Don't look for the secret and don't route around the wall. A stock action may already exist
(`corral list`, `corral help`). Otherwise write `.corral/actions/NAME`: an executable whose
header names the secrets, tools, inputs, outputs and network it needs. `corral run NAME` runs it
outside with exactly those, once the owner has approved its exact content; the first run's
refusal prints the command the owner runs. Any edit needs approving again.

## How to diagnose — evidence first

Read the refusal: every gateway refusal names its fix. The sandbox's own refusals (a hidden path)
name nothing; a hidden file is simply not there. Do not theorise about the record you cannot
read; ask the owner for `corral log` output if you need it.

## How to fix — narrowest first

1. Redirect into scratch with the tool's own setting (`TMPDIR`, a cache flag, `-derivedDataPath`).
2. Ask for the one grant (`corral request`).
3. For a secret, an action.

**Never:** copy a key in, add a remote, open a tunnel, write a policy marker into the project, or
make a shared cache writable that processes outside trust later.
