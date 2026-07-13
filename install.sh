#!/usr/bin/env bash
# install.sh — install this portable Claude Code config into ~/.claude.
#
# Safe by design:
#   * Only writes the AUTHORED config (CLAUDE.md, settings.json, rules/, commands/,
#     agents/, hooks/, bin/, README/INSTALL, .gitignore).
#   * NEVER touches runtime state — projects/, sessions/, history.jsonl, caches,
#     credentials — if a ~/.claude already exists.
#   * Backs up anything it would overwrite into ~/.claude/.backup-<timestamp>/.
# Works on macOS (bash 3.2, BSD userland) and Linux.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DEST/.backup-$TS"

ITEMS="CLAUDE.md settings.json .gitignore README.md INSTALL.md LICENSE rules commands agents hooks bin skills docs"

echo "Installing portable Claude Code config"
echo "  from: $SRC"
echo "  into: $DEST"
echo

mkdir -p "$DEST"

# Back up + copy each authored item; leave everything else in $DEST untouched.
backed_up=0
for item in $ITEMS; do
  [ -e "$SRC/$item" ] || continue
  if [ -e "$DEST/$item" ]; then
    mkdir -p "$BACKUP"
    cp -R "$DEST/$item" "$BACKUP/"
    rm -rf "$DEST/$item"
    backed_up=1
  fi
  cp -R "$SRC/$item" "$DEST/$item"
done

# Ensure executables are executable regardless of how the zip was unpacked.
chmod +x "$DEST"/hooks/*.sh "$DEST"/hooks/*.py "$DEST"/bin/* 2>/dev/null || true

[ "$backed_up" -eq 1 ] && echo "Existing config backed up to: $BACKUP" && echo
echo "Config installed."
echo

# --- preflight: report what's present, install nothing without your say-so ---
echo "Preflight checks:"
have() { command -v "$1" >/dev/null 2>&1; }

if have python3; then
  echo "  ✓ python3 (all hooks are stdlib-only — nothing to pip install)"
else
  echo "  ✗ python3 MISSING — session_start, statusline, doc_drift and the guardrail need it."
  echo "      macOS:  install the Xcode Command Line Tools ('xcode-select --install') or 'brew install python'"
fi

have git    && echo "  ✓ git"    || echo "  ✗ git MISSING — required for the loop/commit/doc-drift workflow."
have ruff || have uv && echo "  ✓ ruff/uv (Python auto-format hook active)" || echo "  · ruff/uv not found — Python auto-format hook will no-op (optional)."
have docker && echo "  ✓ docker (session banner will show container count)" || echo "  · docker not found — session banner just omits it (optional)."
have timeout || have gtimeout && echo "  ✓ timeout available" || echo "  · no 'timeout' — hooks run unbounded, which is fine (macOS: 'brew install coreutils' adds gtimeout)."
have morph  && echo "  ✓ morph (VCS mirror active)" || echo "  · morph not found — bin/morph-mirror no-ops cleanly (optional)."

echo
echo "Done. Open a new Claude Code session; the status line and session banner confirm it's live."
echo "First thing to do: read ~/.claude/CLAUDE.md and edit it to match how YOU work."
