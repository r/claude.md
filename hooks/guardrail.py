#!/usr/bin/env python3
"""PreToolUse guardrail — a small, data-driven safety net over the ~/.claude
safe-change rules.

The specifics live in guardrail_rules.py (action + why + regexes). This file
is just the engine: for a Bash command it checks each command segment (leading
sudo/env stripped, so prose mentions don't trip it); for Write/Edit it scans the
content for secrets. FAIL-OPEN by design — any error allows the action, because
a bug here must never block every tool call across every session and host.

STDLIB ONLY — deliberately. Fail-open plus a third-party import is a trap: the
rules used to be YAML, so any machine without PyYAML installed had a guardrail
that silently allowed everything. A security control you can disarm by NOT
installing something is not a control. The rules are now a Python dict literal,
which every Python can read.
"""

from __future__ import annotations

import json
import re
import sys
# Callable from typing, NOT collections.abc: subscripting the collections.abc
# version (`Callable[[], ...]`) is PEP 585 and also needs 3.9. typing.Callable
# is subscriptable everywhere we run. Same reasoning as Rule/BranchFn below.
from typing import Any, Callable, Dict, Optional

WRAPPER = re.compile(r"^(?:\s*(?:\w+=\S+|sudo|nohup|time|env|command|exec)\s+)*")
SEGMENT = re.compile(r"[;&|\n]+")
DEFAULT_BRANCHES = {"main", "master"}
PUSH_REF_PREFIX = "refs/heads/"
# Dict[str, Any], NOT `dict[str, Any]` — same trap as BranchFn below, one
# version lower. This is a runtime assignment, so `from __future__ import
# annotations` does not defer it, and PEP 585 builtin subscripting needs 3.9.
# An Ubuntu 20.04 box running Python 3.8.10 raised TypeError here at
# import: the hook exited 1 with a traceback, PreToolUse treated that as a
# non-blocking error, and every dangerous command sailed straight through.
# The floor is the OLDEST python across the fleet (3.8), not the newest.
Rule = Dict[str, Any]
# Optional[str], NOT `str | None`. This line is a runtime assignment, not an
# annotation, so `from __future__ import annotations` does not defer it — and
# PEP 604 unions need Python 3.10. macOS ships 3.9, where `str | None` raises
# TypeError at import, the hook crashes, fail-open swallows it, and the guardrail
# is silently gone. Minimum supported Python here is 3.9; keep it that way.
BranchFn = Callable[[], Optional[str]]


def _unknown_branch() -> str | None:
    return None


def push_targets_default(segment: str, branch_of: BranchFn) -> bool:
    """True if this `git push` segment lands on main/master.

    Explicit refspecs are read from the command; a bare push (or a HEAD
    refspec) is resolved via branch_of(). Unknown branch => True — when we
    can't tell, the push might be the mainline, so we ask. Option values
    passed as separate tokens can be misparsed as refspecs; that only adds
    candidates, i.e. errs toward asking, never toward silence.
    """
    tokens = segment.split()
    if "push" not in tokens:
        return True  # regex matched but shape is odd — err toward asking
    rest = tokens[tokens.index("push") + 1 :]
    if any(t in {"--all", "--branches", "--mirror"} for t in rest):
        return True
    positional = [t for t in rest if not t.startswith("-")]
    refspecs = positional[1:]  # first positional is the remote
    if not refspecs:
        branch = branch_of()  # bare push: the current branch is the target
        return branch is None or branch in DEFAULT_BRANCHES
    for spec in refspecs:
        dst = spec.rsplit(":", 1)[-1].lstrip("+")
        # str.removeprefix() is 3.9+; this runs on 3.8. Failing here raised
        # AttributeError, which main()'s fail-open swallowed — so an explicit
        # `git push origin refs/heads/main` was silently ALLOWED.
        if dst.startswith(PUSH_REF_PREFIX):
            dst = dst[len(PUSH_REF_PREFIX) :]
        if dst == "HEAD":
            branch = branch_of()
            if branch is None or branch in DEFAULT_BRANCHES:
                return True
        elif dst in DEFAULT_BRANCHES:
            return True
    return False


def load_rules() -> dict[str, list[Rule]]:
    # Sibling module, stdlib import — no parser, no dependency, nothing to install.
    # This import cannot fail for a reason the user can't see, which is the point.
    from guardrail_rules import RULES

    return RULES


def _first_hit(
    rules: list[Rule], text: str, branch_of: BranchFn = _unknown_branch
) -> tuple[str, str, str | None] | None:
    for rule in rules:
        if not all(re.search(pattern, text) for pattern in rule["all"]):
            continue
        if rule.get("guard") == "default-branch-push" and not push_targets_default(
            text, branch_of
        ):
            continue
        return rule["action"], rule["why"], rule.get("hint")
    return None


def classify(
    tool: str,
    tool_input: Rule,
    rules: dict[str, list[Rule]],
    branch_of: BranchFn = _unknown_branch,
) -> tuple[str, str, str | None] | None:
    """Return (action, why, hint) for the first matching rule, else None.

    Pure given branch_of — the only I/O is the injected current-branch lookup,
    which defaults to "unknown" (conservative) so tests stay deterministic.
    """
    if tool == "Bash":
        command = tool_input.get("command", "") or ""
        for segment in SEGMENT.split(command):
            hit = _first_hit(
                rules.get("bash", []), WRAPPER.sub("", segment.strip()), branch_of
            )
            if hit:
                return hit
        return None
    if tool in {"Write", "Edit", "MultiEdit"}:
        blob = " ".join(v for v in tool_input.values() if isinstance(v, str))
        blob += json.dumps(tool_input.get("edits", []))
        return _first_hit(rules.get("write", []), blob)
    return None


def emit(action: str, why: str, hint: str | None = None) -> None:
    # A rule's `hint` replaces the generic boilerplate: it tells the agent how
    # to keep working (e.g. branch off) instead of just stopping it.
    reason = (
        hint
        or {
            "deny": f"Guardrail blocked: {why}. Run it manually if truly intended, or edit guardrail_rules.py.",
            "ask": f"Safety check — {why}. Confirm the target host and that you have a backup/rollback "
            "(safe-change protocol, ~/.claude/rules/homelab.md) before proceeding.",
        }[action]
    )
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


def _git_branch_resolver(cwd: str) -> BranchFn:
    """Lazy, memoized current-branch lookup for the session's cwd.

    Only ever invoked when a rule's guard needs it (i.e. a bare/HEAD push),
    so ordinary commands never pay the subprocess. Detached HEAD or any
    failure => None, which the guard treats as "could be main" (ask).
    """
    cache: list[str | None] = []

    def resolve() -> str | None:
        if not cache:
            import subprocess

            try:
                out = subprocess.run(
                    ["git", "-C", cwd or ".", "symbolic-ref", "--short", "-q", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                cache.append(out.stdout.strip() or None)
            except Exception:
                cache.append(None)
        return cache[0]

    return resolve


def main() -> None:
    data = json.load(sys.stdin)
    hit = classify(
        data.get("tool_name", ""),
        data.get("tool_input") or {},
        load_rules(),
        _git_branch_resolver(data.get("cwd") or "."),
    )
    if hit:
        emit(*hit)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail-open: never block on our own error
    sys.exit(0)
