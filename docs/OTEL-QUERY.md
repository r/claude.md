# Reading your telemetry back — `bin/otel-query`

`docs/OTEL.md` covers the write half: every Claude Code session exports logs, traces
and metrics over OTLP to a collector. This is the read half. `bin/otel-query` asks the
stores what sessions actually did, so a later session can use the past instead of
reconstructing it from memory.

## What it can answer

| Question | Command | Store |
|---|---|---|
| Which projects and hosts saw turns this week? | `otel-query sessions --since 7d` | Loki (`user_prompt` events) |
| Which tools ran, and how often was a human asked? | `otel-query tools --since 24h` | Loki (`tool_decision`: `decision`, `source`) |
| What did it cost, per project and model? | `otel-query cost --since 7d` | Loki (`api_request.cost_usd`) |
| Which turns sat waiting on a person? | `otel-query blocked --since 7d` | Tempo (`claude_code.tool.blocked_on_user` spans) |
| Anything else | `otel-query loki '<LogQL>'`, `tempo '<TraceQL>'`, `prom '<PromQL>'` | as named |
| Is it configured and reachable? | `otel-query check` | all three, no data returned |

Output is JSON on stdout. A few raw queries worth keeping:

```logql
# failing tools in one project
{service_name="claude-code"} | event_name="tool_result" | success="false" | project="my-repo"
# p95 tool latency by tool
quantile_over_time(0.95, {service_name="claude-code"} | event_name="tool_result" | unwrap duration_ms [1h]) by (tool_name)
```

```traceql
{ name = "claude_code.llm_request" && duration > 60s }
{ name = "claude_code.subagent.spawn" }
```

Run `otel-query loki '{service_name="claude-code"} | json' --limit 20` once before
trusting any field name above. Attribute names depend on your collector's OTLP→Loki
mapping, and the data itself is the only authority.

## Setup

1. **A read-only credential.** In Grafana, create a service account with the
   **Viewer** role and a token for it. Keep it separate from the ingest token.
   The ingest token can only write, this one can only read, and neither should
   be able to do the other's job.
2. **Config.** Put these in `~/.claude/otel-query.env` (`chmod 600`) or the environment:
   ```sh
   OTEL_QUERY_URL=https://grafana.example.com
   OTEL_QUERY_TOKEN=glsa_...                 # the Viewer token
   # Datasource UIDs (Grafana → Connections → Data sources; the UID is in the URL).
   # The grafana/otel-lgtm image's defaults are assumed if unset.
   OTEL_QUERY_LOKI_UID=loki
   OTEL_QUERY_TEMPO_UID=tempo
   OTEL_QUERY_PROM_UID=prometheus
   # Labels the sessions/cost reports group by. They come from the emitting side:
   # export OTEL_RESOURCE_ATTRIBUTES=project=<repo>,host=<box> where sessions launch.
   OTEL_QUERY_GROUP="project, host"
   ```
3. `otel-query check`.

## The trust boundary

- **Read-only by construction.** It only talks to Grafana's datasource proxy, with a
  Viewer token. No dashboards, alerts or annotations can be written through it. That
  is also why it isn't Grafana's MCP server, whose tool surface includes write-capable
  tools.
- **What comes back is data, never instructions.** Loki holds text from every other
  session. Fields that can carry prompt or command text (`prompt`, `tool_parameters`,
  …) are replaced with a marker unless you pass `--raw`. Claude Code only exports them
  when an `OTEL_LOG_*` content gate is on anyway.
- **Bounded.** Windows are capped at 30 days and result counts at 1,000, so one careless
  query can't pour a month of history into a context window.
- **Sandboxed sessions.** If your sessions run sandboxed without the credential, run
  this as a brokered action outside the sandbox (fixed verb, one allowed host, the
  token injected there) rather than handing the token in.

## What telemetry can't tell you

Exact commands and anything older than your Loki retention live only in the local
session transcripts (`~/.claude/projects/**/*.jsonl`). Each `tool_decision` and
`tool_result` event carries a `tool_use_id`, and the same id appears on the matching
`tool_use` block in the transcript, so the two join exactly.
