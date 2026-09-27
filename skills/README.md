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

## A second pattern: capture to a queue, deliver when reachable

The other shape worth stealing runs the opposite direction — a skill that needs to *write* somewhere
durable. `bin/vault-write` and `bin/vault-spooler.py` in this repo are a working instance (the README
covers their mechanics); the skill on top is only the judgment layer deciding what's worth recording.
The shape itself:

- **Capture is a plain file write.** Enqueuing touches the local disk and nothing else — no daemon,
  no network, not even a localhost port — so it succeeds identically on a server and on a laptop with
  no wifi. That matters more than it sounds: if capture can fail, the agent learns to skip it, and the
  entries you lose are the ones written in the middle of something hard.
- **Delivery is a separate, drain-only process.** Something moves already-durable files to the
  configured endpoint when it's reachable, and backs off when it isn't. Nothing has to be running for
  an entry to survive; the failure mode is a queue that grows, not data that vanishes.
- **One writer of the canonical files.** The queue delivers into a single inbox, and exactly one thing
  on the far side files entries into their final home. That's what buys you never needing a merge
  algorithm, which is the expensive part of every sync design.

The generic lesson: **queue locally, deliver when reachable, and keep exactly one writer of the
canonical files so you never need a merge algorithm.** A skill's bundled script is a natural place for
the enqueue side, precisely because it can't fail in a way that costs you the thought.

Three things this shape teaches once you actually run it, all of which cost more to learn later:

- **An identifier that changes with the content can't correlate anything.** A content hash tells you
  *this is the same text*; it cannot tell you *this is a newer version of that note*, because editing
  the text changes the hash. If entries are ever revised, carry a second, stable key naming what the
  entry is *about* — and let the hash do nothing but deduplicate redeliveries. Conflating the two
  means every revision files itself as a brand-new record.
- **Don't let one entry be both an event and a state.** "What happened" is immutable and correct
  forever; "what's currently true" needs revising. Put them in one entry and the live fact gets
  frozen inside an append-only record that nobody will ever update. Split them, and let a shared key
  tie the pair together.
- **Check whether your server can actually scope a credential before you consolidate.** It's
  tempting to serve reads and writes from one process. Many file servers — `rclone serve webdav`
  among them — authenticate many users but give all of them the same view, with read-only set
  process-wide. Where that's true, the *only* thing separating a writer from your canonical files is
  what you mounted into its process. Verify against the server's own docs rather than assuming a
  per-user permission model exists, and prove the boundary with a negative test: attempt the
  traversal, then check the filesystem rather than trusting the status code.

## A third pattern: one shared browser for an app with no API

Some tools you want an agent to drive only exist as a web app. The author's setup has a skill
that runs a design-to-build loop against one: the build agent writes a brief, the design app
iterates, the agent pulls the result and keeps building. The skill is private, because it
names machines. The shape underneath it is not:

- **One broker, not one browser per session.** An MCP server over stdio starts once per agent
  session, so a browser-backed one starts a browser per session. Run a single long-lived broker
  instead, over streamable HTTP behind a bearer token. It holds the one logged-in session, and
  every agent on the network shares it.
- **Tabs are a cache, not state.** Everything durable lives on the app's servers, and a tab
  reopens in a couple of seconds. The only moment a tab holds something you cannot get back is
  while the app's own agent is working in it. So you never need a "done with this tab" signal.
  Close freely outside a turn, never during one, and make the unit of work the project, not
  the session.
- **Read the turn off the app's own traffic, not the page.** DOM heuristics guess; the app's
  network calls know. Here, a turn opens with a streaming Chat request and closes with the
  page's own `ReleaseTurn`. Watch the gap between the two, because a retry or a verify phase
  looks idle and is exactly when an eager cleanup kills a live run. Then add a silence
  failsafe, so one lost event cannot pin a tab busy forever.
- **Headless Chrome is caught by what it says, not what it lacks.** Stock headless sat on a
  Cloudflare challenge indefinitely. The same browser passed once it sent headed Chrome's
  user-agent, rewrote the one tell-tale client-hint brand on every target (cross-origin
  iframes and workers included, via auto-attach), and set its screen size browser-wide. A
  per-session screen override was undone the moment a second debugger attached. Headless
  also used about 220 MB less than headed Chrome plus a virtual display. (Measured September
  2026, Chrome 154, one tab on the same page.) Keep a switch back to headed: the detector
  gets a vote too.
- **Tell the agent, not a phone.** When the session dies, no push notification. Every tool
  that needs the session goes through one gate, and the error it returns is written for the
  agent: a human must log in, here are the exact steps, do not retry. The agent in front of
  the human is the notification. Gate even the tools that never call the app's API: the
  one that types into the page kept failing 30 seconds later as "selector missing", which
  sent the agent after a UI change that never happened.
- **Keep the token out of the MCP config.** Claude Code's `headersHelper` runs a command on
  each connect and uses the headers it prints. The token stays in one file with the broker,
  not in `.claude.json`.

One trap to know before you wire any of this in: **register MCP servers from a plain shell,
not from inside a Claude Code session.** A `claude mcp add` run by a session is answered by
that live session. It reports "added", `claude mcp get` shows it connected, and nothing is
written to disk.

The caveat: an app with no API has not promised you anything. This works by driving
its internal endpoints, so it breaks when they change, and it is only for your own account,
within the app's terms.
