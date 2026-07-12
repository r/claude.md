# WebFetch revalidation cache (PROTOTYPE — inert)

An adaptation of addyosmani/agent-skills' `sdd-cache` hook. It caches WebFetch results keyed by
`sha256(url)` and serves from cache **only on an HTTP 304** — i.e. a cache hit is a fresh
re-validation against the origin, never a stale memory read. That property is what makes it safe for
`deep-research` / `verify`, whose whole value is "checked against the live source."

**Status: NOT wired into `settings.json`.** These scripts do nothing until you add a `PreToolUse` +
`PostToolUse` matcher for `WebFetch`. Left inert on purpose — it changes runtime fetch behavior, and
per the working agreement no behavior flip lands unattended.

## How it works
- `…-post.sh` (PostToolUse) — after a fetch, HEADs the URL for `ETag`/`Last-Modified`; if a validator
  exists, stores `{url, etag, lastmod, body}` under `cache/webfetch/<key>.json`. No validator → nothing
  cached.
- `…-pre.sh` (PreToolUse) — on a repeat fetch, sends a conditional HEAD; on `304` it hands the cached
  body back and short-circuits. Any other status → falls through to a real fetch.
- Graceful degradation throughout: missing `jq`/`curl`/`shasum`, no validator, or any error → no-op,
  let the fetch run. Never fails the tool call.

## Before wiring — the validation step
1. **Confirm the PreToolUse result-substitution contract** for this Claude Code version. The pre-hook
   uses `exit 2` (stderr → model) to deliver the cached body; verify that's how you want a hit
   surfaced, vs. a `hookSpecificOutput` JSON form if this version supports returning a tool result.
2. Note the **cost**: one extra HEAD per fetch (Claude Code doesn't expose WebFetch's own response
   headers to the hook).
3. Note the **shape caveat**: the cached body is prompt-shaped (a prior read against a prior prompt);
   the hit message says so. Fine for stable reference docs, less so for prompt-specific extraction.

To wire (once validated), add to `settings.json` `hooks`:
```json
"PreToolUse":  [{ "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "…/experimental/webfetch-revalidate-pre.sh" }] }],
"PostToolUse": [{ "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "…/experimental/webfetch-revalidate-post.sh" }] }]
```
