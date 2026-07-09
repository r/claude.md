# OpenTelemetry — send Claude Code metrics to your own local backend

Claude Code can export **metrics** (cost, tokens, session count, active time) and **log events**
(prompts, tool decisions, api requests/errors) over OTLP. This guide points it at a backend **you
run**, with an optional local **spooler** so nothing is lost when that backend is offline (a laptop
on the road, or the host being down). Nothing here uploads anywhere you don't control.

This is entirely opt-in. If you don't set the env below, Claude Code exports nothing.

## 1. Point Claude Code at a collector

Put this in `~/.claude/settings.local.json` (machine-local, gitignored — never mirrored):

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative"
  }
}
```

Any OTLP/HTTP backend works — e.g. the all-in-one [`grafana/otel-lgtm`](https://github.com/grafana/docker-otel-lgtm)
container (OTel Collector + Prometheus + Loki + Grafana) is the lowest-friction local option.

### Two gotchas that will otherwise silently drop data
- **`OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=cumulative`** — Prometheus's OTLP receiver
  rejects *delta* temporality. Without this, metrics fail to export (logs are unaffected). It's in the
  template above; keep it.
- **Private-CA backends need `NODE_EXTRA_CA_CERTS`**, not `OTEL_EXPORTER_OTLP_CERTIFICATE` — Claude
  Code's exporter won't trust a private CA via the OTLP var alone. If your endpoint uses a private
  cert, add `"NODE_EXTRA_CA_CERTS": "/path/to/your-ca.pem"` to the env.
- **Auth:** Claude Code sends `OTEL_EXPORTER_OTLP_HEADERS` (e.g. `"Authorization=Bearer <token>"`) but
  does **not** present a client cert (no mTLS from the exporter). Gate a remote endpoint with a bearer
  token over TLS.

## 2. Optional: the offline spooler (`bin/otel-spooler.py`)

Claude Code's exporter has no disk buffer — if the backend is unreachable it drops the data, and it
can add latency retrying. The spooler is a ~140-line, dependency-free store-and-forward buffer:

```
Claude Code ──OTLP──▶ otel-spooler (localhost:4318) ──replays──▶ your real backend
                         │ writes raw bytes to a spool dir, returns 200 instantly
                         │ retries forever; drains automatically on reconnect
```

- **Never blocks Claude:** returns `200` immediately; if the spooler isn't running, the localhost
  export refuses instantly (telemetry skipped, Claude unaffected — fail fast).
- **Buffers offline, bulk-uploads on reconnect.** Bounded disk (`SPOOL_MAX_BYTES`, default 200 MB,
  oldest dropped). Dead-letters permanently-rejected (4xx) payloads so one bad batch can't wedge it.
- It never parses OTLP — replays exact bytes — so metrics, logs, and traces all work.

Point Claude at the spooler (`OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, as above — no token
or CA on the client side; the spooler holds those and talks to your backend).

Run it (env-configured):

```bash
export SPOOL_UPSTREAM=https://otlp.example.com   # your real backend
export SPOOL_TOKEN=your-bearer-token             # if your backend requires one
export SPOOL_CA=/path/to/your-ca.pem             # if it uses a private CA
python3 ~/.claude/bin/otel-spooler.py
```

As a **systemd user service** (Linux):

```ini
# ~/.config/systemd/user/otel-spooler.service   (put the SPOOL_* vars in ~/.config/otel-spooler.env)
[Unit]
Description=OTLP store-and-forward spooler
After=network-online.target
[Service]
Type=simple
EnvironmentFile=%h/.config/otel-spooler.env
ExecStart=/usr/bin/env python3 %h/.claude/bin/otel-spooler.py
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
```
```bash
systemctl --user daemon-reload && systemctl --user enable --now otel-spooler
```

On macOS use a `launchd` agent with the same `SPOOL_*` vars in its `EnvironmentVariables`.

All `SPOOL_*` options are documented at the top of `bin/otel-spooler.py`.

## What you get vs. what it can't tell you
Metrics + structured events give you cost/token/tool/error/latency dashboards. They are **not** a
verbatim transcript — for that, see the opt-in morph session trace capture in `INSTALL.md`. The two
are complementary: OTel = the *what/how-much*, morph = the *what-was-said*.

## Disable
Remove the `env` block from `settings.local.json` (and stop the spooler service). Off means off —
Claude Code exports nothing.
