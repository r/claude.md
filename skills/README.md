# skills/

Skills are model-invoked procedures with bundled files — a reusable playbook Claude auto-loads when
it's relevant, optionally with scripts attached. Each skill is a directory with a `SKILL.md`
(name + description + instructions) and any helper files it needs.

This template ships **no personal skills** — they're where your private integrations live, so they're
yours to add. Drop a directory here (e.g. `skills/my-thing/SKILL.md`) and Claude will pick it up.

## A pattern worth stealing: A2A over MCP for personal data

One skill in the author's real setup is worth describing because the *shape* is reusable. Instead of
giving Claude direct MCP access to email and calendar, Claude talks to a **separate personal agent**
over an agent-to-agent bridge. That agent holds the tools and decides what to share or refuse; Claude
only ever asks.

Why do it this way:

- **A gatekeeper, not raw keys.** The personal agent mediates every request. Claude never holds the
  credentials or touches the plaintext data — it sends a natural-language ask and relays the answer.
- **Defense in depth on the wire.** The bridge can be mutually authenticated (a client cert from your
  own CA) plus a bearer token, with the sensitive API never leaving its host.
- **Relay, don't route around.** If the gatekeeper declines or asks for clarification, that response
  is relayed verbatim — the skill's instructions forbid Claude from answering it another way.

If you want personal data in reach without handing over the keys, delegation-with-a-gatekeeper beats
a direct integration. The bundled-script part of a skill is exactly where a small client for that
bridge lives.
