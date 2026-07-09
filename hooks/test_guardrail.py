#!/usr/bin/env python3
"""Tests for the PreToolUse guardrail. Run directly (`python3 test_guardrail.py`)
or under pytest. Guards against regressions in guardrail_rules.yaml + the engine."""

from __future__ import annotations

import guardrail

RULES = guardrail.load_rules()

# (tool, tool_input, expected_action_or_None)
CASES: list[tuple[str, dict[str, object], str | None]] = [
    # deny — catastrophic
    ("Bash", {"command": "rm -rf /"}, "deny"),
    ("Bash", {"command": "rm -rf /mnt"}, "deny"),
    ("Bash", {"command": "sudo rm -fr /home/*"}, "deny"),
    ("Bash", {"command": "mkfs.ext4 /dev/sda1"}, "deny"),
    ("Bash", {"command": "sudo mkfs -t ext4 /dev/sdb"}, "deny"),
    ("Bash", {"command": "dd if=img of=/dev/nvme0n1"}, "deny"),
    ("Bash", {"command": "chmod -R 777 /"}, "deny"),
    (
        "Bash",
        {"command": ":(){ :|:& };:"},
        "deny",
    ),  # fork bomb (survives segment split)
    ("Bash", {"command": ": () { : | : & } ; :"}, "deny"),  # spaced variant
    (
        "Bash",
        {"command": "echo boom > /dev/sda"},
        "deny",
    ),  # redirect onto a disk device
    # ask — destructive but sometimes legitimate
    ("Bash", {"command": "zfs destroy pool/home"}, "ask"),
    ("Bash", {"command": "zpool destroy tank"}, "ask"),
    ("Bash", {"command": "docker volume rm data"}, "ask"),
    ("Bash", {"command": "docker volume prune"}, "ask"),
    ("Bash", {"command": "docker system prune -a"}, "ask"),
    ("Bash", {"command": "git push --force origin main"}, "ask"),
    (
        "Bash",
        {"command": "git push --force origin feature/x"},
        "ask",
    ),  # force = rewrite, any branch
    # ask — agency: only pushes that land on the mainline
    ("Bash", {"command": "git push origin main"}, "ask"),
    ("Bash", {"command": "git push origin master"}, "ask"),
    ("Bash", {"command": "git push -u origin HEAD:main"}, "ask"),
    ("Bash", {"command": "git push origin fix:refs/heads/main"}, "ask"),
    ("Bash", {"command": "git push --all origin"}, "ask"),  # includes main
    ("Bash", {"command": "git push --mirror backup"}, "ask"),
    (
        "Bash",
        {"command": "git push"},
        "ask",
    ),  # bare push, branch unknown here => could be main
    ("Bash", {"command": "crontab -e"}, "ask"),
    ("Bash", {"command": "crontab /etc/cron.d/mine"}, "ask"),
    ("Bash", {"command": "at 09:00"}, "ask"),
    ("Bash", {"command": "systemctl enable --now backup.timer"}, "ask"),
    ("Bash", {"command": "systemctl start backup.timer"}, "ask"),
    ("Bash", {"command": "systemd-run --on-active=30m /usr/bin/foo"}, "ask"),
    # allow — safe / scoped
    ("Bash", {"command": "rm -rf ./build"}, None),
    ("Bash", {"command": "rm -rf /mnt/data/project/old"}, None),
    ("Bash", {"command": "docker rm -f my-container"}, None),
    ("Bash", {"command": "chmod -R 777 ./tmp"}, None),  # 777 not on /
    ("Bash", {"command": "docker system prune"}, None),  # prune without -a is fine
    # allow — everyday git is free: commits and feature-branch pushes
    ("Bash", {"command": "git commit -m 'fix parser'"}, None),
    ("Bash", {"command": "git -C /srv/repo commit -am wip"}, None),
    ("Bash", {"command": "git push origin feature/parser"}, None),
    ("Bash", {"command": "git push -u origin fix/gate"}, None),
    ("Bash", {"command": "git push --force-with-lease origin fix/gate"}, None),
    ("Bash", {"command": "git push origin v1.2.3"}, None),  # tag push
    ("Bash", {"command": "git push origin --delete stale-branch"}, None),
    # allow — read-only / non-scheduling neighbors of the agency rules
    ("Bash", {"command": "git status"}, None),
    ("Bash", {"command": "git add -A"}, None),
    ("Bash", {"command": "git log --grep commit"}, None),
    ("Bash", {"command": "git log --grep push"}, None),
    ("Bash", {"command": "crontab -l"}, None),
    ("Bash", {"command": "atq"}, None),
    ("Bash", {"command": "systemctl status backup.timer"}, None),
    ("Bash", {"command": "systemctl restart nginx"}, None),
    # allow — prose that merely mentions dangerous words doesn't trip destructive rules
    ("Bash", {"command": 'echo "cleanup: rm -rf roots, mkfs, dd, zfs destroy"'}, None),
    # write — secrets
    ("Write", {"content": "-----BEGIN OPENSSH PRIVATE KEY-----\nx"}, "ask"),
    (
        "Write",
        {"content": "aws_secret_access_key = wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"},
        "ask",
    ),
    ("Write", {"content": "just some config = value"}, None),
]


# (command, current_branch_or_None, expected) — branch-aware push guard
BRANCH_CASES: list[tuple[str, str | None, str | None]] = [
    ("git push", "fix/gate", None),  # bare push from a feature branch: free
    ("git push origin", "fix/gate", None),
    ("git push", "main", "ask"),  # bare push while sitting on main
    ("git push", "master", "ask"),
    ("git push", None, "ask"),  # detached / unknown: could be main
    ("git push origin HEAD", "fix/gate", None),
    ("git push origin HEAD", "main", "ask"),
    ("git push -u origin HEAD:main", "fix/gate", "ask"),  # explicit target wins
    (
        "git push origin fix/gate",
        "main",
        None,
    ),  # explicit branch target, even from main
]


def check_case(tool: str, tool_input: dict[str, object], expected: str | None) -> None:
    hit = guardrail.classify(tool, tool_input, RULES)
    got = hit[0] if hit else None
    assert got == expected, f"{tool} {tool_input} -> {got!r}, expected {expected!r}"


def check_branch_case(command: str, branch: str | None, expected: str | None) -> None:
    hit = guardrail.classify("Bash", {"command": command}, RULES, lambda: branch)
    got = hit[0] if hit else None
    assert got == expected, (
        f"{command!r} on {branch!r} -> {got!r}, expected {expected!r}"
    )


def test_guardrail_cases() -> None:
    for tool, tool_input, expected in CASES:
        check_case(tool, tool_input, expected)


def test_branch_aware_push() -> None:
    for command, branch, expected in BRANCH_CASES:
        check_branch_case(command, branch, expected)


def test_mainline_push_hint_survives_to_emit_reason() -> None:
    hit = guardrail.classify("Bash", {"command": "git push origin main"}, RULES)
    assert hit is not None and hit[2] is not None
    assert "feature branch" in hit[2] and "NEEDS-APPROVAL" in hit[2]


if __name__ == "__main__":
    for _tool, _input, _expected in CASES:
        check_case(_tool, _input, _expected)
    for _cmd, _branch, _exp in BRANCH_CASES:
        check_branch_case(_cmd, _branch, _exp)
    test_mainline_push_hint_survives_to_emit_reason()
    print(f"ok — {len(CASES) + len(BRANCH_CASES) + 1} guardrail cases passed")
