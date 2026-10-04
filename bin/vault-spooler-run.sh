#!/bin/bash
# Run the vault spooler with its config loaded.
#
# WHY THIS EXISTS, AND ONLY ON MACS. Linux machines run vault-spooler.service,
# and systemd's EnvironmentFile= is what puts ~/.config/vault-spooler.env into
# the process. launchd has no equivalent, so on macOS the env file is inert
# unless something sources it -- which is how a Mac can sit for weeks with a
# queue that captured dozens of notes and forwarded none. The config was not
# wrong; nothing was reading it, and nothing was running.
#
# Secrets stay in the 0600 env file and are never written into a plist, which is
# the other reason not to let launchd carry them directly.
#
#   bash ~/.claude/bin/vault-spooler-run.sh --once     # one drain, then exit
#   bash ~/.claude/bin/vault-spooler-run.sh --status   # health, no delivery
#   bash ~/.claude/bin/vault-spooler-run.sh            # stay up and drain
#
# Offline is not an error here: the drainer retains and retries, so running this
# on a network that cannot reach the endpoint is a no-op, not a loss.

set -u

ENV_FILE="${VAULT_SPOOLER_ENV:-$HOME/.config/vault-spooler.env}"
SPOOLER="$HOME/.claude/bin/vault-spooler.py"

[ -r "$SPOOLER" ] || { echo "$0: cannot read $SPOOLER" >&2; exit 1; }

if [ -r "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
else
    # Not fatal: --status is still useful, and capture never depended on this.
    echo "$0: no $ENV_FILE -- capturing only, nothing will be forwarded." >&2
fi

exec /usr/bin/env python3 "$SPOOLER" "$@"
