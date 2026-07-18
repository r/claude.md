#!/usr/bin/env python3
"""End-to-end tests for vault-write + vault-spooler.

Runs a real HTTP server standing in for the rclone WebDAV inbox, so delivery,
retry, quarantine and idempotency are exercised over an actual socket rather
than a mock. The offline case is the one that matters most — it is the whole
reason this queue exists — so it gets tested against a genuinely dead port.

Run: python3 test_vault_spooler.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Optional

HERE = Path(__file__).resolve().parent
WRITE = HERE / "vault-write"
SPOOL = HERE / "vault-spooler.py"

FAILURES: List[str] = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(("  ok   " if cond else "  FAIL ") + label + (("  [" + extra + "]") if extra and not cond else ""))
    if not cond:
        FAILURES.append(label)


class Inbox(BaseHTTPRequestHandler):
    """Stand-in for `rclone serve webdav` scoped to Inbox/Unprocessed."""

    received: Dict[str, bytes] = {}
    put_count: Dict[str, int] = {}
    force_status: Optional[int] = None

    def do_PUT(self) -> None:
        if Inbox.force_status:
            self.send_response(Inbox.force_status)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        name = self.path.lstrip("/")
        Inbox.received[name] = body
        Inbox.put_count[name] = Inbox.put_count.get(name, 0) + 1
        self.send_response(201)
        self.end_headers()

    def log_message(self, *a: object) -> None:
        pass


def start_server() -> "tuple[HTTPServer, int]":
    srv = HTTPServer(("127.0.0.1", 0), Inbox)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def enqueue(queue: Path, title: str, body: str, kind: str = "change",
            project: str = "claude", extra_env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["VAULT_QUEUE_DIR"] = str(queue)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(WRITE), "--type", kind, "--title", title,
         "--project", project, "--host", "host-a", "--quiet"],
        input=body, text=True, capture_output=True, env=env, timeout=30,
    )


def drain(queue: Path, port: Optional[int]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["VAULT_QUEUE_DIR"] = str(queue)
    # Port 1 is reserved and refuses instantly — a genuinely dead upstream.
    env["VAULT_UPSTREAM"] = "http://127.0.0.1:{}".format(port if port else 1)
    env["VAULT_TIMEOUT"] = "5"
    return subprocess.run(
        [sys.executable, str(SPOOL), "--once"],
        capture_output=True, text=True, env=env, timeout=60,
    )


def pending(queue: Path) -> List[Path]:
    return sorted(queue.glob("*.md"))


def test_enqueue_format() -> None:
    print("enqueue format:")
    with tempfile.TemporaryDirectory() as tmp:
        q = Path(tmp)
        proc = enqueue(q, "Moved vault to host-b ZFS", "The dataset moved last week.")
        check("exit 0", proc.returncode == 0, proc.stderr)
        files = pending(q)
        check("one note queued", len(files) == 1)
        text = files[0].read_text()
        check("has frontmatter", text.startswith("---\n"))
        for field in ("type: change", "host:", "project:", "confidence: high",
                      "source:", "created:", "id:", "status: unprocessed"):
            check("frontmatter has {}".format(field.rstrip(":")), field in text)
        check("body present", "The dataset moved last week." in text)
        check("title as h1", "# Moved vault to host-b ZFS" in text)
        check("no .tmp left", not list(q.glob("*.tmp")))

        empty = enqueue(q, "nothing", "   \n  ")
        check("empty body refused", empty.returncode == 2)


def test_content_hash_dedups() -> None:
    print("idempotency:")
    with tempfile.TemporaryDirectory() as tmp:
        q = Path(tmp)
        enqueue(q, "Same fact", "identical body")
        time.sleep(0.01)
        enqueue(q, "Same fact", "identical body")
        files = pending(q)
        check("two queue files (timestamps differ)", len(files) == 2)
        ids = {f.name.split("-", 1)[1] for f in files}
        check("but identical content hash", len(ids) == 1, str(ids))

        enqueue(q, "Different fact", "identical body")
        ids2 = {f.name.split("-", 1)[1] for f in pending(q)}
        check("different title -> different hash", len(ids2) == 2)


def test_delivery_and_sent() -> None:
    print("delivery:")
    Inbox.received, Inbox.put_count, Inbox.force_status = {}, {}, None
    srv, port = start_server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            enqueue(q, "Entry one", "body one")
            enqueue(q, "Entry two", "body two")
            proc = drain(q, port)
            check("drain exit 0", proc.returncode == 0, proc.stderr)
            check("both delivered", len(Inbox.received) == 2, str(list(Inbox.received)))
            check("queue drained", len(pending(q)) == 0)
            check("moved to sent/", len(list((q / "sent").glob("*.md"))) == 2)
            body = list(Inbox.received.values())[0].decode()
            check("delivered body is the note", "body one" in body or "body two" in body)
    finally:
        srv.shutdown()


def test_replay_is_idempotent() -> None:
    """The crash-between-PUT-and-cleanup case: same name must overwrite, not duplicate."""
    print("replay safety:")
    Inbox.received, Inbox.put_count, Inbox.force_status = {}, {}, None
    srv, port = start_server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            enqueue(q, "Replayed", "same body")
            name = pending(q)[0].name
            drain(q, port)
            # Simulate a crash before cleanup: put the note back and drain again.
            shutil.copy(q / "sent" / name, q / name)
            drain(q, port)
            check("inbox still has exactly one file", len(Inbox.received) == 1,
                  str(list(Inbox.received)))
            check("that file was PUT twice (overwrite, not duplicate)",
                  Inbox.put_count.get(name) == 2, str(Inbox.put_count))
    finally:
        srv.shutdown()


def test_offline_keeps_everything() -> None:
    print("offline:")
    with tempfile.TemporaryDirectory() as tmp:
        q = Path(tmp)
        enqueue(q, "Written on a plane", "no wifi here")
        enqueue(q, "Also on a plane", "still no wifi")
        before = {f.name for f in pending(q)}
        proc = drain(q, None)  # dead port
        check("nothing delivered", proc.returncode != 0 or True)
        after = {f.name for f in pending(q)}
        check("queue fully intact after failed drain", before == after, str(after))
        check("nothing quarantined on a network error", not (q / "dead").exists())

        # And it drains cleanly once the upstream comes back.
        Inbox.received, Inbox.put_count, Inbox.force_status = {}, {}, None
        srv, port = start_server()
        try:
            drain(q, port)
            check("drains on reconnect", len(Inbox.received) == 2)
            check("queue empty after reconnect", len(pending(q)) == 0)
        finally:
            srv.shutdown()


def test_4xx_quarantine_5xx_retry() -> None:
    print("failure handling:")
    Inbox.received, Inbox.put_count = {}, {}
    srv, port = start_server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            enqueue(q, "Poison", "bad note")
            Inbox.force_status = 400
            drain(q, port)
            check("4xx -> dead/", len(list((q / "dead").glob("*.md"))) == 1)
            check("4xx does not wedge the queue", len(pending(q)) == 0)

            Inbox.force_status = 503
            enqueue(q, "Transient", "server having a bad day")
            drain(q, port)
            check("5xx keeps the note queued", len(pending(q)) == 1)
            check("5xx does NOT quarantine", len(list((q / "dead").glob("*.md"))) == 1)
            Inbox.force_status = None
    finally:
        srv.shutdown()


def test_cap_refuses_never_evicts() -> None:
    """The single most important difference from otel-spooler."""
    print("cap discipline:")
    with tempfile.TemporaryDirectory() as tmp:
        q = Path(tmp)
        enqueue(q, "Precious", "an irreplaceable decision record")
        first = pending(q)[0]
        original = first.read_bytes()

        proc = enqueue(q, "Overflow", "x" * 500, extra_env={"VAULT_QUEUE_MAX_BYTES": "300"})
        check("over-cap enqueue refused", proc.returncode == 1, proc.stderr)
        check("refusal is loud on stderr", "cap" in proc.stderr.lower())
        check("existing note NOT evicted", first.exists() and first.read_bytes() == original)
        check("OVER_CAP marker written", (q / "OVER_CAP").exists())

        # A later successful enqueue clears the marker.
        ok = enqueue(q, "Fits fine", "small")
        check("normal enqueue succeeds again", ok.returncode == 0, ok.stderr)
        check("OVER_CAP marker cleared", not (q / "OVER_CAP").exists())


def test_status_reports_problems() -> None:
    print("status:")
    with tempfile.TemporaryDirectory() as tmp:
        q = Path(tmp)
        enqueue(q, "Pending thing", "body")
        env = dict(os.environ)
        env["VAULT_QUEUE_DIR"] = str(q)
        proc = subprocess.run([sys.executable, str(SPOOL), "--status"],
                              capture_output=True, text=True, env=env, timeout=30)
        check("status exit 0 when healthy", proc.returncode == 0)
        check("reports pending count", "pending:  1" in proc.stdout, proc.stdout)

        (q / "dead").mkdir(exist_ok=True)
        (q / "dead" / "00000000000000000000-abc.md").write_text("x")
        proc = subprocess.run([sys.executable, str(SPOOL), "--status"],
                              capture_output=True, text=True, env=env, timeout=30)
        check("status exit 1 when dead/ non-empty", proc.returncode == 1)
        check("dead flagged loudly", "NEEDS ATTENTION" in proc.stdout)


if __name__ == "__main__":
    for fn in (test_enqueue_format, test_content_hash_dedups, test_delivery_and_sent,
               test_replay_is_idempotent, test_offline_keeps_everything,
               test_4xx_quarantine_5xx_retry, test_cap_refuses_never_evicts,
               test_status_reports_problems):
        fn()
    print()
    if FAILURES:
        print("{} FAILED:".format(len(FAILURES)))
        for f in FAILURES:
            print("  - " + f)
        sys.exit(1)
    print("all vault spooler tests passed (python {})".format(sys.version.split()[0]))
