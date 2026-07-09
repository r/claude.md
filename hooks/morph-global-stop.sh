#!/usr/bin/env bash
# GLOBAL Claude Code hook: Stop.
#
# Pairs with morph-global-prompt.sh. When a session ends, assembles a Trace+Run
# from the session transcript (or the pending prompts as a fallback) and imports
# it into the silent central morph store (~/.claude/morph-traces), tagged with
# the real working directory. Records EVERY session regardless of cwd and
# regardless of whether cwd was ever `morph init`'d.
#
# NEVER fails or stalls a Claude session: every error path exits 0. A lost trace
# is acceptable; a broken Stop hook is not.
#
# Companion: morph-global-prompt.sh
set -u

MORPH_STORE="${MORPH_TRACES_STORE:-$HOME/.claude/morph-traces}"

# Fast bail before python startup: no central store → not opted in → do nothing.
# Keeps this near-zero-cost for public-config users who don't use trace capture.
[ -d "$MORPH_STORE/.morph" ] || exit 0

# Resolve the morph binary: explicit install first, then PATH.
MORPH_BIN="$HOME/.local/bin/morph"
[ -x "$MORPH_BIN" ] || MORPH_BIN="$(command -v morph 2>/dev/null || true)"

exec 3<&0  # preserve original stdin before the heredoc replaces it
python3 - "$MORPH_STORE" "$MORPH_BIN" << 'PY' || true
import json, os, subprocess, sys
from pathlib import Path
from datetime import datetime

store = Path(sys.argv[1])
morph_bin = sys.argv[2]
morph_dir = store / ".morph"
if not morph_dir.is_dir() or not morph_bin:
    sys.exit(0)

try:
    raw = os.fdopen(3).read().strip()
except Exception:
    sys.exit(0)
if not raw:
    sys.exit(0)
try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    sys.exit(0)

cwd = payload.get("cwd") or "."
session_id = payload.get("session_id") or "unknown"
response_text = payload.get("last_assistant_message") or ""
model_name = payload.get("model") or os.environ.get("ANTHROPIC_MODEL") or ""
transcript_path_str = payload.get("transcript_path") or ""
conversation = payload.get("conversation") or []

MAX_CONTENT_LEN = 2000
now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def truncate(s, limit=MAX_CONTENT_LEN):
    if s and len(s) > limit:
        return s[:limit] + "... [truncated]"
    return s

def log(name, msg):
    try:
        d = morph_dir / "hooks" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / name, "a") as f:
            f.write(f"{now} {msg}\n")
    except Exception:
        pass

log("global-invoke.log", f"Stop session_id={session_id} cwd={cwd}")

pending = morph_dir / "hooks" / f"pending-{session_id}.jsonl"
if not pending.exists():
    sys.exit(0)
try:
    with open(pending) as f:
        lines = [ln.strip() for ln in f if ln.strip()]
except Exception:
    sys.exit(0)
if not lines:
    pending.unlink(missing_ok=True)
    sys.exit(0)

FILE_READ_TOOLS = {"Read", "Grep", "Glob", "SemanticSearch"}
FILE_EDIT_TOOLS = {"StrReplace", "Write", "EditNotebook", "Delete", "Edit", "MultiEdit"}

def tool_use_to_event(seq, tool_name, tool_input, ts):
    inp = tool_input or {}
    if tool_name in FILE_READ_TOOLS:
        kind = "file_read"
        path = inp.get("path") or inp.get("file_path") or inp.get("glob_pattern") or inp.get("pattern") or ""
        ev = {"text": truncate(json.dumps(inp)), "name": tool_name, "path": path}
    elif tool_name in FILE_EDIT_TOOLS:
        kind = "file_edit"
        path = inp.get("path") or inp.get("file_path") or inp.get("target_notebook") or ""
        ev = {"text": truncate(json.dumps(inp)), "name": tool_name, "path": path}
    elif tool_name in ("Shell", "Bash"):
        kind = "tool_call"
        ev = {"text": truncate(inp.get("command") or ""), "name": tool_name, "input": truncate(json.dumps(inp))}
    elif tool_name in ("Task", "Agent"):
        kind = "tool_call"
        ev = {"text": truncate(inp.get("description") or inp.get("prompt") or ""), "name": tool_name, "input": truncate(json.dumps(inp))}
    else:
        kind = "tool_call"
        ev = {"text": truncate(json.dumps(inp)), "name": tool_name}
        if inp:
            ev["input"] = truncate(json.dumps(inp))
    return {"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": kind, "payload": ev}

def parse_transcript(tp, ts):
    events, seq = [], 0
    try:
        with open(tp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = entry.get("role") or "unknown"
                message = entry.get("message") or {}
                parts = message.get("content") or []
                if isinstance(parts, str):
                    parts = [{"type": "text", "text": parts}]
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type") or "text"
                    if ptype == "text":
                        kind = "user" if role in ("user", "human") else "assistant"
                        events.append({"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": kind,
                                       "payload": {"text": truncate(part.get("text") or "")}})
                        seq += 1
                    elif ptype == "tool_use":
                        events.append(tool_use_to_event(seq, part.get("name") or "unknown_tool", part.get("input") or {}, ts))
                        seq += 1
                    elif ptype == "tool_result":
                        out = part.get("content") or part.get("output") or ""
                        if isinstance(out, list):
                            out = " ".join(str(o.get("text", "")) if isinstance(o, dict) else str(o) for o in out)
                        events.append({"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": "tool_result",
                                       "payload": {"text": truncate(str(out))}})
                        seq += 1
    except (IOError, OSError):
        return None
    return events or None

def parse_conversation(conv, ts):
    events, seq = [], 0
    for msg in conv:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role") or "unknown"
        content = msg.get("content")
        if isinstance(content, str):
            kind = "user" if role in ("user", "human") else "assistant"
            events.append({"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": kind,
                           "payload": {"text": truncate(content)}})
            seq += 1
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type") or "text"
                if ptype == "text":
                    kind = "user" if role in ("user", "human") else "assistant"
                    events.append({"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": kind,
                                   "payload": {"text": truncate(part.get("text", ""))}})
                    seq += 1
                elif ptype == "tool_use":
                    events.append(tool_use_to_event(seq, part.get("name", ""), part.get("input", {}), ts))
                    seq += 1
                elif ptype == "tool_result":
                    out = part.get("content") or part.get("output") or ""
                    if isinstance(out, list):
                        out = " ".join(str(o.get("text", "")) if isinstance(o, dict) else str(o) for o in out)
                    events.append({"id": f"evt_{seq}", "seq": seq, "ts": ts, "kind": "tool_result",
                                   "payload": {"text": truncate(str(out))}})
                    seq += 1
    return events or None

# Prefer the richest available source.
events = None
if transcript_path_str:
    tp = Path(transcript_path_str)
    if tp.exists():
        events = parse_transcript(tp, now)
if not events and conversation:
    events = parse_conversation(conversation, now)
if not events:
    events = []
    for seq, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append({"id": f"evt_prompt_{seq}", "seq": seq, "ts": row.get("ts", now),
                       "kind": "user", "payload": {"text": truncate(row.get("prompt", ""))}})
    events.append({"id": "evt_response", "seq": len(events), "ts": now,
                   "kind": "assistant", "payload": {"text": truncate(response_text)}})

# Prepend a marker event so the real workspace is visible inside the trace.
marker = {"id": "evt_workspace", "seq": -1, "ts": now, "kind": "note",
          "payload": {"text": f"workspace cwd={cwd} session={session_id}", "cwd": cwd}}
for i, e in enumerate(events):
    e["seq"] = i
marker["seq"] = 0
for e in events:
    e["seq"] += 1
events = [marker] + events

trace_obj = {"type": "trace", "events": events}
runs_dir = morph_dir / "runs"
runs_dir.mkdir(parents=True, exist_ok=True)
stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
trace_path = runs_dir / f"session-{session_id[:8]}-{stamp}.trace.json"
run_path = runs_dir / f"session-{session_id[:8]}-{stamp}.run.json"
try:
    with open(trace_path, "w") as f:
        json.dump(trace_obj, f, indent=2)
except Exception as e:
    log("global-record.log", f"ERR write trace: {e}")
    sys.exit(0)

def run_morph(args):
    return subprocess.run([morph_bin, *args], cwd=str(store), capture_output=True, text=True)

r = run_morph(["hash-object", str(trace_path)])
if r.returncode != 0:
    log("global-record.log", f"ERR hash-object: {r.stderr.strip()}")
    sys.exit(0)
trace_hash = r.stdout.strip()

r = run_morph(["pipeline", "identity-hash"])
if r.returncode != 0:
    log("global-record.log", f"ERR pipeline: {r.stderr.strip()}")
    sys.exit(0)
pipeline_hash = r.stdout.strip()

resolved_model = model_name
if not resolved_model:
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("model"):
            resolved_model = row["model"]
            break
resolved_model = resolved_model or "unknown"

params = {"cwd": cwd, "session_id": session_id}
for key in ("input_tokens", "output_tokens", "total_tokens"):
    val = payload.get(key)
    if val is not None:
        params[key] = val

run_obj = {
    "type": "run",
    "pipeline": pipeline_hash,
    "commit": None,
    "environment": {"model": resolved_model, "version": "1.0", "parameters": params, "toolchain": {}},
    "input_state_hash": "0" * 64,
    "output_artifacts": [],
    "metrics": {},
    "trace": trace_hash,
    "agent": {"id": "claude-code-global", "version": "1.0", "policy": None},
}
try:
    with open(run_path, "w") as f:
        json.dump(run_obj, f, indent=2)
except Exception as e:
    log("global-record.log", f"ERR write run: {e}")
    sys.exit(0)

r = run_morph(["session", "import", str(run_path), "--trace", str(trace_path)])
if r.returncode != 0:
    log("global-record.log", f"ERR session import: {r.stderr.strip()}")
    sys.exit(0)
run_hash = r.stdout.strip()
log("global-record.log", f"OK session_id={session_id} cwd={cwd} run={run_hash}")
pending.unlink(missing_ok=True)
PY
exit 0
