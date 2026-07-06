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
    ("Bash", {"command": ":(){ :|:& };:"}, "deny"),  # fork bomb (survives segment split)
    ("Bash", {"command": ": () { : | : & } ; :"}, "deny"),  # spaced variant
    ("Bash", {"command": "echo boom > /dev/sda"}, "deny"),  # redirect onto a disk device
    # ask — destructive but sometimes legitimate
    ("Bash", {"command": "zfs destroy pool/home"}, "ask"),
    ("Bash", {"command": "zpool destroy tank"}, "ask"),
    ("Bash", {"command": "docker volume rm data"}, "ask"),
    ("Bash", {"command": "docker volume prune"}, "ask"),
    ("Bash", {"command": "docker system prune -a"}, "ask"),
    ("Bash", {"command": "git push --force origin main"}, "ask"),
    # ask — agency / unattended (never on my behalf without a nod)
    ("Bash", {"command": "git commit -m 'fix parser'"}, "ask"),
    ("Bash", {"command": "git -C /srv/repo commit -am wip"}, "ask"),
    ("Bash", {"command": "git push origin main"}, "ask"),
    ("Bash", {"command": "git push --force-with-lease"}, "ask"),
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
    # allow — read-only / non-scheduling neighbors of the agency rules
    ("Bash", {"command": "git status"}, None),
    ("Bash", {"command": "git add -A"}, None),
    ("Bash", {"command": "git log --grep commit"}, None),
    ("Bash", {"command": "crontab -l"}, None),
    ("Bash", {"command": "atq"}, None),
    ("Bash", {"command": "systemctl status backup.timer"}, None),
    ("Bash", {"command": "systemctl restart nginx"}, None),
    # allow — prose that merely mentions dangerous words doesn't trip destructive rules
    ("Bash", {"command": 'echo "cleanup: rm -rf roots, mkfs, dd, zfs destroy"'}, None),
    # write — secrets
    ("Write", {"content": "-----BEGIN OPENSSH PRIVATE KEY-----\nx"}, "ask"),
    ("Write", {"content": "aws_secret_access_key = wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY"}, "ask"),
    ("Write", {"content": "just some config = value"}, None),
]


def check_case(tool: str, tool_input: dict[str, object], expected: str | None) -> None:
    hit = guardrail.classify(tool, tool_input, RULES)
    got = hit[0] if hit else None
    assert got == expected, f"{tool} {tool_input} -> {got!r}, expected {expected!r}"


def test_guardrail_cases() -> None:
    for tool, tool_input, expected in CASES:
        check_case(tool, tool_input, expected)


if __name__ == "__main__":
    for _tool, _input, _expected in CASES:
        check_case(_tool, _input, _expected)
    print(f"ok — {len(CASES)} guardrail cases passed")
