#!/usr/bin/env python3
"""Tests for otel-query. Runs on Python 3.8 (the fleet floor), stdlib only.

Small tests for the pure helpers, and one medium test that runs the script as a
process against a fake Grafana on localhost — the way a session actually calls
it — to prove the URL, the auth header and the redaction end to end.

Usage: python3 test_otel_query.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "otel-query"

_spec = importlib.util.spec_from_loader(
    "otel_query", importlib.machinery.SourceFileLoader("otel_query", str(SCRIPT))
)
assert _spec is not None and _spec.loader is not None
oq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oq)

FAILURES: List[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  ok   {}".format(name))
    else:
        print("  FAIL {} {}".format(name, detail))
        FAILURES.append(name)


def test_parse_duration() -> None:
    check("7d is a week of seconds", oq.parse_duration("7d") == 7 * 86400)
    check("90s", oq.parse_duration("90s") == 90)
    try:
        oq.parse_duration("7 days")
        check("garbage duration rejected", False)
    except oq.QueryError:
        check("garbage duration rejected", True)


def test_window_is_capped() -> None:
    start, end, capped = oq.window("90d", now=1_000_000_000)
    check("90d capped to 30d", end - start == 30 * 86400 and capped)
    start, end, capped = oq.window("24h", now=1_000_000_000)
    check("24h not capped", end - start == 86400 and not capped)


def test_limit_clamped() -> None:
    check("limit ceiling", oq.clamp_limit(10**6) == oq.MAX_LIMIT)
    check("limit floor", oq.clamp_limit(0) == 1)


def test_redact_nested() -> None:
    data = {"a": [{"prompt": "my password is x", "tool_name": "Bash"}], "tool_parameters": "rm"}
    out = oq.redact(data)
    check("nested prompt redacted", out["a"][0]["prompt"] == oq.REDACTED)
    check("top-level tool_parameters redacted", out["tool_parameters"] == oq.REDACTED)
    check("ordinary field kept", out["a"][0]["tool_name"] == "Bash")
    check("--raw keeps everything", oq.redact(data, raw=True) == data)


def test_config_env_wins_over_file() -> None:
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "otel-query.env"
        f.write_text("# comment\nexport OTEL_QUERY_URL='https://file'\nOTEL_QUERY_TOKEN=t1\n")
        cfg = oq.load_config({"OTEL_QUERY_TOKEN": "t2", "HOME": "/x"}, f)
        check("file value read, quotes stripped", cfg["OTEL_QUERY_URL"] == "https://file")
        check("env overrides file", cfg["OTEL_QUERY_TOKEN"] == "t2")
        check("unrelated env ignored", "HOME" not in cfg)


def test_proxy_url_shape() -> None:
    cfg = {"OTEL_QUERY_URL": "https://g.example/", "OTEL_QUERY_LOKI_UID": "abc"}
    url = oq.proxy_url(cfg, "loki", "/loki/api/v1/labels", {"x": 1, "skip": None})
    check(
        "datasource proxy url",
        url == "https://g.example/api/datasources/proxy/uid/abc/loki/api/v1/labels?x=1",
        url,
    )
    url = oq.proxy_url({"OTEL_QUERY_URL": "https://g"}, "prom", "/p", {})
    check("default uid for prom", "/uid/prometheus/p" in url, url)


def test_canned_queries() -> None:
    store, q = oq.canned("sessions", {"OTEL_QUERY_GROUP": "rp, rh"}, "7d")
    check("sessions → loki, grouped, windowed", store == "loki" and "by (rp, rh)" in q and "[7d]" in q, q)
    store, q = oq.canned("blocked", {}, "7d")
    check("blocked → tempo span name", store == "tempo" and "tool.blocked_on_user" in q, q)
    check("metric logql detected", oq.is_metric_logql("sum by (a) (count_over_time({x=\"y\"}[1h]))"))
    check("log-line logql detected", not oq.is_metric_logql('{service_name="claude-code"} | json'))


class _FakeGrafana(BaseHTTPRequestHandler):
    seen: List[Dict[str, Any]] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        u = urlparse(self.path)
        _FakeGrafana.seen.append(
            {"path": u.path, "qs": parse_qs(u.query), "auth": self.headers.get("Authorization")}
        )
        body = {"status": "success", "data": {"result": [{"stream": {"prompt": "secret", "tool_name": "Bash"}}]}}
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: Any) -> None:
        pass


def test_end_to_end_against_fake_grafana() -> None:
    srv = HTTPServer(("127.0.0.1", 0), _FakeGrafana)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ)
            env.update(
                {
                    "HOME": home,  # no stray ~/.claude/otel-query.env leaks in
                    "OTEL_QUERY_URL": "http://127.0.0.1:{}".format(srv.server_port),
                    "OTEL_QUERY_TOKEN": "viewer-token",
                }
            )
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "loki", '{service_name="claude-code"}', "--since", "1h"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            check("exit 0", r.returncode == 0, r.stderr.decode())
            out = json.loads(r.stdout.decode() or "{}")
            stream = out.get("data", {}).get("result", [{}])[0].get("stream", {})
            check("prompt redacted in output", stream.get("prompt") == oq.REDACTED, str(stream))
            req = _FakeGrafana.seen[-1]
            check("hit loki via datasource proxy", req["path"] == "/api/datasources/proxy/uid/loki/loki/api/v1/query_range", req["path"])
            check("bearer token sent", req["auth"] == "Bearer viewer-token")
            check("log query carries a limit", req["qs"].get("limit") == ["200"], str(req["qs"]))

            env.pop("OTEL_QUERY_TOKEN")
            r = subprocess.run(
                [sys.executable, str(SCRIPT), "tools"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            check("missing token: exit 1, one clear line", r.returncode == 1 and b"OTEL_QUERY_TOKEN" in r.stderr, r.stderr.decode())
    finally:
        srv.shutdown()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print("\n{} failed: {}".format(len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("\nall green")
