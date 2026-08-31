#!/usr/bin/env python3
"""vault-spooler — drain the local vault queue to the vault's inbox when reachable.

Companion to bin/vault-write. That tool enqueues notes into ~/.claude/vault-queue
as plain files; this one PUTs them, in order, to a WebDAV endpoint scoped to the
vault's Inbox/Unprocessed/ and nothing else. the vault agent normalizes them from there into
the typed folders, so she remains the sole writer of canonical vault files and no
two-way merge ever has to exist.

Forked from bin/otel-spooler.py, which is already a correct store-and-forward
implementation. Kept: the order-preserving break-on-offline drain, the 4xx
quarantine, the bounded-disk discipline, the systemd-user-unit shape, stdlib-only.

Deliberately changed, because knowledge is not telemetry:

  1. NO EVICTION. otel-spooler's enforce_cap() unlinks the OLDEST spool file to
     stay under its cap — a lossy ring buffer. Correct for metrics, data loss for
     a decision record. Here, over-cap is a loud refusal at enqueue time and
     nothing already queued is ever deleted to make room.
  2. IDEMPOTENT DELIVERY. otel-spooler is at-least-once with no dedup: a crash
     between forward() and unlink() replays the request. Here the filename carries
     a content hash and delivery is a PUT to that name, so a replay overwrites the
     same inbox file instead of duplicating the note. Sent files move to sent/
     rather than being unlinked, so a failed cleanup can't resurrect them either.
  3. VISIBLE FAILURE. A non-empty dead/ is reported by --status and surfaced in
     the session banner, instead of one line on stderr nobody reads.

Also: backoff 10s -> 5min while offline, because a laptop idle for days should not
wake up every ten seconds.

There is no HTTP listener here, unlike otel-spooler: capture is a plain file write
done by vault-write, so an entry is safely on disk whether or not this is running.
This process only moves already-durable files.

Config via env (see ~/.config/vault-spooler.env):
  VAULT_QUEUE_DIR       default ~/.claude/vault-queue
  VAULT_UPSTREAM        e.g. https://vault-inbox.example.com  (REQUIRED to forward)
  VAULT_LOCAL_INBOX     path to the vault's Inbox/Unprocessed. When set, notes are
                        written straight there and HTTP is skipped entirely — for a
                        host where the vault is a local directory. Takes precedence
                        over VAULT_UPSTREAM. Leave unset on a laptop.
  VAULT_USER            basic-auth user (rclone htpasswd)
  VAULT_PASS            basic-auth password
  VAULT_CA              CA bundle for a private-CA upstream
  VAULT_INSECURE        "1" to skip TLS verification (discouraged)
  VAULT_FLUSH_INTERVAL  seconds between drain cycles when healthy (default 10)
  VAULT_MAX_INTERVAL    backoff ceiling while offline (default 300)
  VAULT_TIMEOUT         per-request timeout (default 15)
  VAULT_SENT_RETAIN_DAYS  how long delivered notes linger in sent/ (default 7)
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

QUEUE = Path(os.environ.get("VAULT_QUEUE_DIR") or (Path.home() / ".claude" / "vault-queue"))
UPSTREAM = os.environ.get("VAULT_UPSTREAM", "").rstrip("/")
# Local delivery. Set to the vault's Inbox/Unprocessed to skip HTTP entirely on a
# host where the vault is a local directory. Empty = HTTP, which is the default and
# the only option on a laptop. Opt-in on purpose: see local_put().
LOCAL_INBOX = os.environ.get("VAULT_LOCAL_INBOX", "")
USER = os.environ.get("VAULT_USER", "")
PASS = os.environ.get("VAULT_PASS", "")
CA = os.environ.get("VAULT_CA", "")
INSECURE = os.environ.get("VAULT_INSECURE", "") == "1"
FLUSH_INTERVAL = float(os.environ.get("VAULT_FLUSH_INTERVAL", "10"))
MAX_INTERVAL = float(os.environ.get("VAULT_MAX_INTERVAL", "300"))
TIMEOUT = float(os.environ.get("VAULT_TIMEOUT", "15"))
SENT_RETAIN_DAYS = float(os.environ.get("VAULT_SENT_RETAIN_DAYS", "7"))

DEAD_DIR = QUEUE / "dead"
SENT_DIR = QUEUE / "sent"


def log(msg: str) -> None:
    sys.stderr.write("{} vault-spooler: {}\n".format(
        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg))
    sys.stderr.flush()


def ssl_ctx() -> Optional[ssl.SSLContext]:
    if not UPSTREAM.startswith("https"):
        return None
    ctx = ssl.create_default_context(cafile=CA or None)
    if INSECURE:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def put(name: str, body: bytes) -> None:
    """PUT the note to <upstream>/<name>. The name carries a content hash, so a
    redelivery lands on the same path and overwrites rather than duplicating."""
    req = urllib.request.Request(UPSTREAM + "/" + name, data=body, method="PUT")
    req.add_header("Content-Type", "text/markdown; charset=utf-8")
    if USER:
        token = base64.b64encode("{}:{}".format(USER, PASS).encode()).decode()
        req.add_header("Authorization", "Basic " + token)
    urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl_ctx())


# The filename contract, duplicated from the reverse proxy on purpose — and this
# duplication is the whole cost of the local path, so it is worth naming. When
# delivery goes over HTTP, the proxy owns three rules: this regex, PUT-only, and a
# 10m body cap. Writing straight to the directory bypasses all three, so they are
# re-enforced here. If the vhost's regex or cap ever changes, THIS MUST CHANGE
# WITH IT.
FNAME_RE = re.compile(r"^\d{20}-[0-9a-f]{12}\.md$")
MAX_NOTE_BYTES = 10 * 1024 * 1024   # mirrors client_max_body_size 10m


def local_put(name: str, body: bytes) -> None:
    """Write the note straight into the vault inbox, skipping HTTP.

    Only safe where the vault is a local directory. The containment the reverse
    proxy and a container mount namespace provide for a REMOTE credential does not
    apply here and is not needed: a local process that can write this directory
    could do anything else on the box anyway. What we do still owe is the three
    rules the proxy enforced, because the vault agent's processor trusts them.

    Atomicity matters more than it looks. That processor polls, its scan reads the
    file, and its validate step parses frontmatter — a half-written file fails to
    parse and gets quarantined for review with an alarm. So: write a temp, then
    rename. The temp MUST NOT end in .md, because the scan skips non-.md files and
    would otherwise pick the partial one up mid-write.
    """
    if not FNAME_RE.match(name):
        raise ValueError("refusing to write {!r}: violates the inbox filename contract".format(name))
    if len(body) > MAX_NOTE_BYTES:
        raise ValueError("refusing to write {}: {} bytes exceeds the {} cap".format(
            name, len(body), MAX_NOTE_BYTES))

    inbox = Path(LOCAL_INBOX).resolve()
    dest = (inbox / name).resolve()
    # Belt and braces: the regex already forbids a separator, but assert the
    # resolved parent anyway so no future loosening of the regex turns into a
    # traversal. The proxy got this from the mount namespace; we have to check.
    if dest.parent != inbox:
        raise ValueError("refusing to write outside the inbox: {}".format(dest))

    tmp = inbox / (".{}.tmp".format(name))
    with open(tmp, "wb") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, dest)   # atomic, and overwrites a replay exactly as PUT did


def deliver(name: str, body: bytes) -> None:
    """Local write when configured, HTTP otherwise."""
    if LOCAL_INBOX:
        local_put(name, body)
    else:
        put(name, body)


def prune_sent(now: float) -> None:
    cutoff = now - SENT_RETAIN_DAYS * 86400
    try:
        for f in SENT_DIR.glob("*.md"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
    except OSError:
        pass


def drain_once() -> Tuple[int, bool]:
    """Returns (delivered, healthy). healthy=False means the upstream looked down,
    so the caller should back off rather than hammer it."""
    if not UPSTREAM and not LOCAL_INBOX:
        return 0, False
    files = sorted(QUEUE.glob("*.md"))
    delivered = 0
    healthy = True
    for f in files:
        try:
            body = f.read_bytes()
        except OSError:
            continue  # mid-write; the .tmp -> rename makes this rare, skip the cycle
        try:
            deliver(f.name, body)
        except ValueError as exc:
            # Local-path contract violation (bad filename, oversized). This is the
            # same class as an upstream 4xx — the note will never be accepted, so
            # quarantine it rather than let one bad entry wedge the queue forever.
            DEAD_DIR.mkdir(parents=True, exist_ok=True)
            try:
                f.rename(DEAD_DIR / f.name)
            except OSError:
                pass
            log("{} -> dead/ ({})".format(f.name, exc))
            continue
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                # Poison entry: quarantine so one bad note can't wedge the queue.
                DEAD_DIR.mkdir(parents=True, exist_ok=True)
                try:
                    f.rename(DEAD_DIR / f.name)
                except OSError:
                    pass
                log("upstream {} on {} -> dead/ (needs a look)".format(exc.code, f.name))
                continue
            healthy = False
            break  # 5xx: transient. Keep everything, preserve order, retry later.
        except (urllib.error.URLError, OSError, ssl.SSLError):
            healthy = False
            break  # offline. This is the normal laptop case, not an error.
        # Two-phase: move rather than unlink, so a crash here cannot resurrect
        # the note on the next pass and re-PUT it.
        SENT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            f.rename(SENT_DIR / f.name)
        except OSError:
            try:
                f.unlink()
            except OSError:
                pass
        delivered += 1
    return delivered, healthy


def status() -> int:
    pending = sorted(QUEUE.glob("*.md"))
    dead = sorted(DEAD_DIR.glob("*.md")) if DEAD_DIR.exists() else []
    sent = sorted(SENT_DIR.glob("*.md")) if SENT_DIR.exists() else []
    over = (QUEUE / "OVER_CAP").exists()

    print("queue:    {}".format(QUEUE))
    if LOCAL_INBOX:
        writable = os.access(LOCAL_INBOX, os.W_OK)
        print("delivery: LOCAL -> {}{}".format(
            LOCAL_INBOX, "" if writable else "  <-- NOT WRITABLE, nothing will drain"))
    else:
        print("upstream: {}".format(UPSTREAM or "(unset — capturing only, not forwarding)"))
    print("pending:  {} note(s)".format(len(pending)))
    print("sent:     {} note(s) awaiting prune".format(len(sent)))
    print("dead:     {} note(s){}".format(len(dead), "  <-- NEEDS ATTENTION" if dead else ""))
    if over:
        print("OVER CAP: queue hit its size limit; nothing was dropped, but new "
              "entries are being refused.")
    for f in pending[:5]:
        print("  pending: {}".format(f.name))
    for f in dead[:5]:
        print("  dead:    {}".format(f.name))
    return 1 if (dead or over) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="drain once and exit")
    ap.add_argument("--status", action="store_true", help="report queue health and exit")
    args = ap.parse_args()

    QUEUE.mkdir(parents=True, exist_ok=True)

    if args.status:
        return status()

    if args.once:
        delivered, healthy = drain_once()
        prune_sent(time.time())
        log("delivered {} note(s); upstream {}".format(
            delivered, "ok" if healthy else "unreachable"))
        return 0 if healthy or delivered else 1

    if not UPSTREAM:
        log("no VAULT_UPSTREAM set — nothing to drain to; exiting")
        return 0

    log("draining {} -> {}".format(QUEUE, UPSTREAM))
    interval = FLUSH_INTERVAL
    while True:
        time.sleep(interval)
        delivered, healthy = drain_once()
        if delivered:
            log("delivered {} note(s)".format(delivered))
        if healthy:
            interval = FLUSH_INTERVAL
            prune_sent(time.time())
        else:
            # Exponential backoff to the ceiling: a laptop offline for a week
            # should not spin every 10s for a week.
            interval = min(interval * 2, MAX_INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
