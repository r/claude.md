# Security & hardening

Load this whenever the work touches a **trust boundary**: auth, input handling, secrets, third-party
data, file/URL fetches, or an **agent's permissions and tool surface**. It's a cross-cutting rule
like `loops.md` — the same "how do we know we're right?" posture, aimed at "how would someone misuse
this?" The spirit matches the rest of the setup: reversible, least-privilege, provenance on every
input.

## Threat-model before you harden
- **If you can't name the trust boundaries, you're not ready to secure it.** Sketch where data
  crosses from less-trusted to more-trusted (user → server, third-party API → your code, model
  output → an action) before writing a mitigation.
- **Abuse cases next to use cases.** For each feature ask "how would I misuse this?" — that question
  is the first test to write, not an afterthought.
- **Validate at the boundary, trust internal code.** Untrusted input gets validated once, at the
  edge; don't re-validate everywhere (that hides where the real boundary is). Third-party API
  responses are untrusted data, not gospel.

## The boundary tiers (mirror of CLAUDE.md's "Never do these")
- **Always** — parameterize queries, escape output, authorize every request server-side, hash
  passwords, TLS in transit.
- **Ask first** — anything that widens the attack surface: a new external dependency, a new
  inbound port, relaxing CORS/CSP, storing a new class of PII.
- **Never** — roll your own crypto, log secrets, trust the client for authorization, `--force` past
  a dependency-audit finding.

## Patterns worth having written down
- **SSRF is a TOCTOU trap.** Validating a URL then fetching it leaves a gap where DNS can rebind
  between check and fetch — resolve the host, pin the IP, and fetch *that*; block internal ranges on
  the pinned address, not the hostname.
- **Secrets: rotate, don't delete.** If a secret ever lands in a commit, history, or a log, it's
  compromised — rotate it. Removing the line is not remediation. (A `pre-commit` secret grep is
  cheaper than the rotation.)
- **Dependencies:** one upgrade per PR, read the changelog not just the semver, review the lockfile
  diff, and treat install/postinstall scripts as a supply-chain surface — a passed audit does **not**
  mean a dependency is safe to run at install time. Never `npm audit fix --force` / blind auto-fix.

## Agents are a trust boundary too (the part most guides miss)
This is where the real power — and the real risk — lives (the Harbor / harness-permissions frame).
- **The system prompt is not a security boundary.** Instructions in a prompt can be overridden by
  injected content. Enforce permissions **in code / in the harness**, not by asking the model nicely.
- **Model output is untrusted input.** Anything an LLM emits — a command, a URL, a file path, a tool
  call — is attacker-influencable if any of its context was. Validate it like user input before it
  drives an action.
- **Least agency.** Scope each tool/credential an agent holds to exactly the task; prefer read-only
  and allow-lists; a capability the agent doesn't need is a capability an injection can borrow.
- **Bound consumption.** Unbounded tool loops / fetches are a denial-of-wallet and denial-of-service
  surface — cap iterations, budgets, and fan-out (this is also why `loops.md` demands a stop
  condition).

## Red flags
Concatenating user input into a query/command/prompt; authorization checked in the client or the
system prompt; a secret in a diff or a log line; an agent handed a broad token "to be safe"; a fetch
that trusts a hostname it validated a moment ago; a dependency bump that skipped the changelog.
