#!/usr/bin/env bash
# PROTOTYPE — NOT WIRED INTO settings.json. See README.md in this dir.
#
# PreToolUse hook for WebFetch. If we have a cached body + validator for this URL,
# send a conditional request (If-None-Match / If-Modified-Since). ONLY on HTTP 304
# (origin confirms unchanged) do we short-circuit and serve the cached body — a hit
# is a fresh re-validation, not a stale read. Any other status (200, error, no
# validator, missing tools) => fall through and let the real WebFetch run.
#
# NOTE — the open question that keeps this a prototype: the exact PreToolUse
# contract for *substituting* a tool result in this Claude Code version. Exiting 2
# feeds stderr back to the model as a block reason (used here to hand over the
# cached body + a "revalidated via 304" note), but confirm that behavior before
# wiring — that's the validation step.
set +e

CACHE_DIR="${WEBFETCH_CACHE_DIR:-$HOME/.claude/cache/webfetch}"
command -v jq >/dev/null 2>&1     || exit 0
command -v curl >/dev/null 2>&1   || exit 0
command -v shasum >/dev/null 2>&1 || command -v sha256sum >/dev/null 2>&1 || exit 0

sha() { if command -v shasum >/dev/null 2>&1; then shasum -a 256 | cut -d' ' -f1; else sha256sum | cut -d' ' -f1; fi; }

payload=$(cat)
url=$(printf '%s' "$payload" | jq -r '.tool_input.url // empty' 2>/dev/null)
[ -z "$url" ] && exit 0

key=$(printf '%s' "$url" | sha)
entry="$CACHE_DIR/$key.json"
[ -f "$entry" ] || exit 0

etag=$(jq -r '.etag // empty' "$entry" 2>/dev/null)
lastmod=$(jq -r '.lastmod // empty' "$entry" 2>/dev/null)
[ -z "$etag" ] && [ -z "$lastmod" ] && exit 0

hdrs=()
[ -n "$etag" ]    && hdrs+=(-H "If-None-Match: $etag")
[ -n "$lastmod" ] && hdrs+=(-H "If-Modified-Since: $lastmod")
status=$(curl -s -o /dev/null -w '%{http_code}' -I --max-time 8 "${hdrs[@]}" "$url" 2>/dev/null)

if [ "$status" = "304" ]; then
  body=$(jq -r '.body // empty' "$entry" 2>/dev/null)
  if [ -n "$body" ]; then
    printf 'CACHE HIT (revalidated via HTTP 304 — content unchanged since last fetch of %s):\n\n%s\n' "$url" "$body" >&2
    exit 2
  fi
fi

exit 0
