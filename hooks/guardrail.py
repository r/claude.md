#!/usr/bin/env python3
"""PreToolUse guardrail — a small, data-driven safety net over destructive and
"agency" commands.

The specifics live in guardrail_rules.yaml (action + why + regexes). This file
is just the engine: for a Bash command it checks each command segment (leading
sudo/env stripped, so prose mentions don't trip it); for Write/Edit it scans the
content for secrets. FAIL-OPEN by design — any error allows the action, because
a bug here must never block every tool call across every session and host.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

RULES_FILE = Path(__file__).with_name("guardrail_rules.yaml")
WRAPPER = re.compile(r"^(?:\s*(?:\w+=\S+|sudo|nohup|time|env|command|exec)\s+)*")
SEGMENT = re.compile(r"[;&|\n]+")
Rule = dict[str, Any]


def load_rules() -> dict[str, list[Rule]]:
    import yaml  # deferred: a missing dep fails open via main()'s except

    rules: dict[str, list[Rule]] = yaml.safe_load(RULES_FILE.read_text())
    return rules


def _first_hit(rules: list[Rule], text: str) -> tuple[str, str] | None:
    for rule in rules:
        if all(re.search(pattern, text) for pattern in rule["all"]):
            return rule["action"], rule["why"]
    return None


def classify(
    tool: str, tool_input: Rule, rules: dict[str, list[Rule]]
) -> tuple[str, str] | None:
    """Return (action, why) for the first matching rule, else None. Pure — no I/O."""
    if tool == "Bash":
        command = tool_input.get("command", "") or ""
        for segment in SEGMENT.split(command):
            hit = _first_hit(rules.get("bash", []), WRAPPER.sub("", segment.strip()))
            if hit:
                return hit
        return None
    if tool in {"Write", "Edit", "MultiEdit"}:
        blob = " ".join(v for v in tool_input.values() if isinstance(v, str))
        blob += json.dumps(tool_input.get("edits", []))
        return _first_hit(rules.get("write", []), blob)
    return None


def emit(action: str, why: str) -> None:
    reason = {
        "deny": f"Guardrail blocked: {why}. Run it manually if truly intended, or edit guardrail_rules.yaml.",
        "ask": f"Safety check — {why}. Confirm the target and that you have a backup/rollback "
        "before proceeding.",
    }[action]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": action,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> None:
    data = json.load(sys.stdin)
    hit = classify(
        data.get("tool_name", ""), data.get("tool_input") or {}, load_rules()
    )
    if hit:
        emit(*hit)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block on our own error
    sys.exit(0)
