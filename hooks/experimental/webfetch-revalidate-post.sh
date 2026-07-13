#!/usr/bin/env bash
# PROTOTYPE — NOT WIRED INTO settings.json. See README.md in this dir.
#
# PostToolUse hook for WebFetch. After a successful fetch, cache the (prompt-shaped)
# result body keyed by sha256(url), alongside the origin's ETag / Last-Modified
# validators obtained via a HEAD request. The pre-hook uses those validators to
# serve from cache ONLY on an HTTP 304 — so a cache hit is a fresh re-validation
# against the origin, never a stale memory read. That's the whole point: it keeps
# deep-research / verify honest ("checked against live docs") while cutting the
# cost of re-downloading unchanged pages.
#
# Design rules: graceful degradation everywhere (missing jq/curl/shasum => no-op,
# let the fetch proceed), never fail the tool call, never cache without a validator.
set +e

CACHE_DIR="${WEBFETCH_CACHE_DIR:-$HOME/.claude/cache/webfetch}"
command -v jq >/dev/null 2>&1     || exit 0
command -v curl >/dev/null 2>&1   || exit 0
command -v shasum >/dev/null 2>&1 || { command -v sha256sum >/dev/null 2>&1 || exit 0; }

sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 | cut -d' ' -f1; else sha256sum | cut -d' ' -f1; fi; }

payload=$(cat)
url=$(printf '%s' "$payload" | jq -r '.tool_input.url // empty' 2>/dev/null)
[ -z "$url" ] && exit 0

# The result body shape varies; prefer .tool_response.result, fall back defensively.
body=$(printf '%s' "$payload" | jq -r '.tool_response.result // .tool_response // .result // empty' 2>/dev/null)
[ -z "$body" ] && exit 0

# Only cache when the origin gives us a validator — no validator, no honest revalidation.
headers=$(curl -sI --max-time 8 "$url" 2>/dev/null)
etag=$(printf '%s' "$headers" | tr -d '\r' | awk -F': ' 'tolower($1)=="etag"{print $2; exit}')
lastmod=$(printf '%s' "$headers" | tr -d '\r' | awk -F': ' 'tolower($1)=="last-modified"{print $2; exit}')
[ -z "$etag" ] && [ -z "$lastmod" ] && exit 0

key=$(printf '%s' "$url" | sha)
mkdir -p "$CACHE_DIR" 2>/dev/null || exit 0
jq -cn --arg url "$url" --arg etag "$etag" --arg lastmod "$lastmod" --arg body "$body" \
  '{url:$url, etag:$etag, lastmod:$lastmod, body:$body}' > "$CACHE_DIR/$key.json" 2>/dev/null

exit 0
