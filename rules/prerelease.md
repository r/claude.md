# Pre-release mode — live infra mutation when nobody's using it

Load this when a task wants to **mutate cloud infrastructure for a project I'm building** (AWS,
Terraform/CDK/Pulumi, a managed DB, a deploy target) and the default gates in `CLAUDE.md` are about
to stop the work. It's a scoped, declared exception to those gates — not a general softening.

The reason it exists: the "Never do these" list is calibrated for **changes people feel**. A stack
nobody has ever used has no one to disturb, and stopping to ask about it — especially in auto mode —
is pure friction protecting nothing. So the gate stops asking *"is this hard to reverse?"* and starts
asking the question that actually matters:

> **Who feels it if this goes wrong right now?**
> Nobody → go to town. Somebody, or you can't tell → the normal gates apply, unchanged.

This is a **cloud-project rule only.** Self-hosted / homelab infra is never pre-release: real people
depend on it, rollback there isn't `terraform destroy`, and it stays on `/safe-change`. See
`infra.md`.

## Declaring it

Pre-release is a **declared state, never an inferred one.** A dev-looking account name, a `-staging`
suffix, or a stack that "looks new" is not a declaration — mislabeled environments are exactly how a
silent prod mutation happens.

The declaration lives in the project at **`.claude/stage.json`**:

```json
{
  "stage": "pre-release",
  "users": "none — not launched, no external traffic",
  "blast_radius": "dedicated AWS acct 1234; no shared VPC, DNS zone, or org IAM",
  "cost_ceiling": "$200/mo",
  "declared": "2026-07-20",
  "expires": "2026-10-20"
}
```

Every field is load-bearing. `users` and `blast_radius` are the two I'm actually asserting; the rest
bound it.

**If the file is absent, ask once — then write it.** At the first gated infra action in a session:
ask whether anything is live on this, what the blast radius is, and offer to write the marker. One
question, once, and the answer persists across sessions and into auto mode. Don't re-ask per action.

**If the file is absent in auto mode, it is not pre-release.** No marker means the normal gate: skip
the item, append to the approvals queue, keep going. Never infer a declaration in order to unblock
yourself — that's the one failure mode this whole rule has to avoid.

**Expiry tightens, never loosens.** Past `expires`, the project is no longer pre-release and the
normal gates resume until I re-declare. This looks like the "no unattended behavior flip" rule being
broken but is its mirror image: the timer only ever restores caution, and a forgotten marker fails
closed. A pre-release marker with no `expires` is treated as expired.

## What pre-release actually unlocks

Inside a declared project's own scope, on the resources it owns:

- Create, replace, resize, and **destroy** infra without asking — including stateful resources.
- Apply a plan straight through rather than propose-then-confirm.
- Iterate hot in auto mode: apply, observe, roll forward. No approvals-queue detour.
- Skip the observe-only staging step for behavior changes. Nobody's behavior is being changed.

Autonomy slider (`loops.md`): a declared pre-release cloud project moves from **coldest** up to the
**software-with-a-real-gate** setting — as long as its checker is real (a plan diff read, a smoke
test, a health check), the loop's rollback is `terraform apply` back, and it stays on a branch.
No checker, no loop, still.

## What stays gated regardless

Pre-release lifts the "who does this disturb" gate. It does not lift these:

- **Real money.** Cost-bearing resources beyond the declared `cost_ceiling`, or anything that bills
  whether or not it's used. Pre-release means no users, not no invoice. A NAT gateway left running
  costs the same on an app nobody has launched.
- **Shared blast radius.** Anything reaching outside the project's own account/VPC/stack — a shared
  DNS zone, org-level IAM, a peered VPC, a registry or bucket someone else reads. *"Nobody uses my
  app"* is not *"nobody uses this account."* If the marker's `blast_radius` doesn't clearly cover the
  target, it's out of scope.
- **Unbacked data deletion.** Deleting or overwriting state with no snapshot. Snapshots are cheap and
  this is the one mistake pre-release doesn't excuse — "it was only test data" is what people say
  right before discovering it wasn't.
- **Secrets and credentials.** Unchanged in every mode. See `security.md`.

These three go to the approvals queue in auto mode exactly as they do today.

## When pre-release ends

Launch, first external user, or anything pointed at a real domain ends it. **Delete or flip the
marker at that moment** — a stale `stage: pre-release` on a live system is strictly worse than never
having declared one, because it converts a deliberate exception into a silent one. If I mention that
something went live and the marker is still there, say so and offer to clear it.
