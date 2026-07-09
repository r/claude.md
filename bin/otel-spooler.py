#!/usr/bin/env python3
"""otel-spooler — a tiny, dependency-free store-and-forward buffer for OTLP/HTTP.

Point Claude Code (or any OTLP/HTTP client) at this on localhost. It accepts the
export, writes the RAW bytes to a spool dir, and returns 200 immediately — so the
client never blocks and never loses data when the real backend is unreachable
(host down, or laptop offline). A background thread replays spooled requests to the
real upstream (bearer token + TLS); on success it deletes them, on failure it keeps
them and retries. That's the "buffer while offline, bulk-upload on reconnect".

Content-agnostic: it never parses OTLP — it replays the exact bytes and content-type
to the same path, so it works for metrics, logs, and traces without knowing OTLP.

Stdlib only. Config via env (all optional except the upstream):

  SPOOL_LISTEN_HOST     default 127.0.0.1
  SPOOL_LISTEN_PORT     default 4318
  SPOOL_DIR             default ~/.claude/otel-spool
  SPOOL_UPSTREAM        e.g. https://otlp.example.com   (REQUIRED to forward)
  SPOOL_TOKEN           bearer token for the upstream (sent as "Authorization: Bearer <tok>")
  SPOOL_CA              path to CA bundle to verify the upstream's TLS cert (private CA)
  SPOOL_INSECURE        "1" to skip TLS verification (discouraged)
  SPOOL_FLUSH_INTERVAL  seconds between replay cycles (default 10)
  SPOOL_TIMEOUT         upstream request timeout seconds (default 10)
  SPOOL_MAX_BYTES       hard cap on spool size; oldest dropped past it (default 200_000_000)

If SPOOL_UPSTREAM is unset, it still accepts + spools (useful to prove capture),
but nothing drains — set it to forward.
"""
import json
import os
import ssl
import struct
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("SPOOL_LISTEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("SPOOL_LISTEN_PORT", "4318"))
SPOOL_DIR = Path(os.environ.get("SPOOL_DIR", str(Path.home() / ".claude" / "otel-spool")))
UPSTREAM = os.environ.get("SPOOL_UPSTREAM", "").rstrip("/")
TOKEN = os.environ.get("SPOOL_TOKEN", "")
CA = os.environ.get("SPOOL_CA", "")
INSECURE = os.environ.get("SPOOL_INSECURE", "") == "1"
FLUSH_INTERVAL = float(os.environ.get("SPOOL_FLUSH_INTERVAL", "10"))
TIMEOUT = float(os.environ.get("SPOOL_TIMEOUT", "10"))
MAX_BYTES = int(os.environ.get("SPOOL_MAX_BYTES", str(200_000_000)))

DEAD_DIR = SPOOL_DIR / "dead"
_seq_lock = threading.Lock()
_seq = 0


def log(msg):
    sys.stderr.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} otel-spooler: {msg}\n")
    sys.stderr.flush()


def _next_seq():
    global _seq
    with _seq_lock:
        _seq += 1
        return _seq


def _ssl_ctx():
    if UPSTREAM.startswith("https"):
        ctx = ssl.create_default_context(cafile=CA or None)
        if INSECURE:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def spool_bytes():
    total = 0
    for f in SPOOL_DIR.glob("*.spool"):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def enforce_cap():
    """Drop oldest spool files if over the size cap (bounded disk — never fill it)."""
    files = sorted(SPOOL_DIR.glob("*.spool"))
    total = spool_bytes()
    while total > MAX_BYTES and files:
        victim = files.pop(0)
        try:
            total -= victim.stat().st_size
            victim.unlink()
            log(f"spool over cap; dropped oldest {victim.name}")
        except OSError:
            pass


def write_spool(path, content_type, body):
    ts_ns = time.time_ns()
    name = f"{ts_ns:020d}-{_next_seq():06d}.spool"
    meta = json.dumps({"path": path, "content_type": content_type}).encode()
    tmp = SPOOL_DIR / (name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(struct.pack(">I", len(meta)))
        f.write(meta)
        f.write(body)
    tmp.rename(SPOOL_DIR / name)  # atomic; flusher only picks *.spool
    enforce_cap()


def read_spool(f):
    with open(f, "rb") as fh:
        (mlen,) = struct.unpack(">I", fh.read(4))
        meta = json.loads(fh.read(mlen))
        body = fh.read()
    return meta, body


def forward(meta, body):
    url = UPSTREAM + meta["path"]
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", meta.get("content_type") or "application/x-protobuf")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx())


def flusher():
    if not UPSTREAM:
        log("no SPOOL_UPSTREAM set — capturing only, not forwarding")
    while True:
        time.sleep(FLUSH_INTERVAL)
        if not UPSTREAM:
            continue
        files = sorted(SPOOL_DIR.glob("*.spool"))
        sent = 0
        for f in files:
            try:
                meta, body = read_spool(f)
            except (OSError, ValueError, struct.error):
                continue  # half-written / corrupt; skip this cycle
            try:
                forward(meta, body)
                f.unlink(missing_ok=True)
                sent += 1
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    DEAD_DIR.mkdir(parents=True, exist_ok=True)
                    f.rename(DEAD_DIR / f.name)  # poison payload; don't wedge the queue
                    log(f"upstream {e.code} on {f.name} -> moved to dead/")
                else:
                    break  # 5xx: transient, retry next cycle
            except (urllib.error.URLError, OSError, ssl.SSLError):
                break  # offline / host down: stop, keep everything, retry next cycle
        if sent:
            log(f"forwarded {sent} spooled request(s)")


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.startswith("/v1/"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        ctype = self.headers.get("Content-Type", "application/x-protobuf")
        try:
            write_spool(self.path, ctype, body)
        except OSError as e:
            log(f"spool write failed: {e}")
            self.send_response(500)
            self.end_headers()
            return
        # Empty 200 = OTLP success; client is unblocked regardless of upstream state.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # tiny health endpoint
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a):
        pass  # quiet; we log our own lines


def main():
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=flusher, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    log(f"listening on {HOST}:{PORT}, spool={SPOOL_DIR}, upstream={UPSTREAM or '(none)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
