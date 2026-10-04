#!/usr/bin/env bash
# install.sh — install this portable Claude Code config into ~/.claude.
#
# Safe by design:
#   * Only writes the AUTHORED config (CLAUDE.md, settings.json, rules/, commands/,
#     agents/, hooks/, bin/, README/INSTALL, .gitignore, the *.example templates).
#   * NEVER touches runtime state — projects/, sessions/, history.jsonl, caches,
#     credentials — if a ~/.claude already exists.
#   * Backs up anything it would overwrite into ~/.claude/.backup-<timestamp>/.
#   * Seeds rules/infra.md and rules/voice.md from their .example templates ONLY
#     when the target does not exist — a personalized copy is never overwritten.
#   * Idempotent: re-running produces the same result.
# Works on macOS (bash 3.2, BSD userland) and Linux.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DEST/.backup-$TS"

ITEMS="CLAUDE.md settings.json .gitignore README.md INSTALL.md LICENSE otel.env.example bootstrap.profile.example rules commands agents hooks bin skills docs"

# Templates seeded into a personalized copy on first install. "src dest" pairs,
# both relative to the config root.
SEEDS="rules/infra.md.example:rules/infra.md rules/voice.md.example:rules/voice.md"

echo "Installing portable Claude Code config"
echo "  from: $SRC"
echo "  into: $DEST"
echo

mkdir -p "$DEST"

# Back up + copy each authored item; leave everything else in $DEST untouched.
# rules/ is copied as a whole, so a personalized rules/infra.md or rules/voice.md
# living inside it is first preserved and put back afterwards (never overwritten,
# never lost — and it is in the backup too).
backed_up=0
preserved="$DEST/.install-preserve-$TS"
for pair in $SEEDS; do
  target="${pair#*:}"
  if [ -f "$DEST/$target" ]; then
    mkdir -p "$preserved/$(dirname "$target")"
    cp -p "$DEST/$target" "$preserved/$target"
  fi
done

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

# Seed the personal templates: restore a preserved copy, else create one from the
# .example. Either way the .example itself stays alongside as the reference.
for pair in $SEEDS; do
  example="${pair%%:*}"
  target="${pair#*:}"
  if [ -f "$preserved/$target" ]; then
    cp -p "$preserved/$target" "$DEST/$target"
    echo "Kept your existing $target (not overwritten)."
  elif [ -f "$DEST/$example" ] && [ ! -e "$DEST/$target" ]; then
    cp "$DEST/$example" "$DEST/$target"
    echo "Seeded $target from $example — fill it in."
  fi
done
rm -rf "$preserved"

# Ensure executables are executable regardless of how the tree was obtained
# (a clone on a core.fileMode=false filesystem, a copied directory, an archive).
chmod +x "$DEST"/hooks/*.sh "$DEST"/hooks/*.py "$DEST"/bin/* 2>/dev/null || true

if [ "$backed_up" -eq 1 ]; then
  echo "Existing config backed up to: $BACKUP"
  echo
fi
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

if have git; then
  echo "  ✓ git"
else
  echo "  ✗ git MISSING — required for the loop/commit/doc-drift workflow."
fi

if have ruff; then
  echo "  ✓ ruff (Python auto-format hook active)"
elif have uv; then
  echo "  ✓ uv (Python auto-format hook active via 'uv run ruff')"
else
  echo "  · ruff/uv not found — Python auto-format hook will no-op (optional)."
fi

if have docker; then
  echo "  ✓ docker (session banner will show container count)"
else
  echo "  · docker not found — session banner just omits it (optional)."
fi

if have timeout; then
  echo "  ✓ timeout available"
elif have gtimeout; then
  echo "  ✓ gtimeout available (the hooks detect it)"
else
  echo "  · no 'timeout' — hooks run unbounded, which is fine (macOS: 'brew install coreutils' adds gtimeout)."
fi

if have morph; then
  echo "  ✓ morph (VCS mirror active)"
else
  echo "  · morph not found — bin/morph-mirror no-ops cleanly (optional)."
fi

echo
echo "Done. Open a new Claude Code session; the status line and session banner confirm it's live."
echo "First thing to do: read ~/.claude/CLAUDE.md and edit it to match how YOU work."
