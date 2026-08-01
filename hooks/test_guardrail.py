#!/usr/bin/env python3
"""Tests for the PreToolUse guardrail. Run directly (`python3 test_guardrail.py`)
or under pytest. Guards against regressions in guardrail_rules.py + the engine."""

from __future__ import annotations

import json
import os
import pathlib
import sys

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
    ("Bash", {"command": "rm -rf /mnt/docker-volumes/x/old"}, None),
    ("Bash", {"command": "docker rm -f my-app-tls"}, None),
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


def check_origin_case(command: str, origin: str | None, expected: str | None) -> None:
    hit = guardrail.classify(
        "Bash", {"command": command}, RULES, lambda: "main", lambda _seg: origin
    )
    got = hit[0] if hit else None
    assert got == expected, (
        f"{command!r} in a {origin!r}-origin repo -> {got!r}, expected {expected!r}"
    )


def test_origin_aware_mainline_push() -> None:
    """Whose mainline is it? Claude's own repo is exempt; everything else asks."""
    for command in ("git push", "git push origin main", "git push origin HEAD:master"):
        check_origin_case(command, "claude", None)
        check_origin_case(command, "human", "ask")
        check_origin_case(command, None, "ask")  # unclassifiable => human
    # Force-push carries no origin guard: gated even in a Claude-origin repo.
    check_origin_case("git push --force origin main", "claude", "ask")


def test_push_repo_dir_reads_the_target_not_the_cwd() -> None:
    assert guardrail.push_repo_dir("git -C /srv/app push origin main", "/srv/cwd") == "/srv/app"
    assert guardrail.push_repo_dir("git push origin main", "/srv/cwd") == "/srv/cwd"
    # A -C AFTER the subcommand isn't git's repo selector; don't be fooled by it.
    assert guardrail.push_repo_dir("git push -C /nope origin main", "/srv/cwd") == "/srv/cwd"


TRAILER = "\n\nCo-Authored-By: Claude Opus 5 <noreply@anthropic.com>"


def make_repo(path: str, *commits: str) -> str:
    import subprocess as _sp

    # No `git init -b <branch>`: that flag is git 2.28+, and the fleet floor is
    # older. These tests care about root commits, not about the branch name.
    _sp.run(["git", "init", "-q", path], check=True)
    for name, value in (("user.email", "t@example.com"), ("user.name", "t")):
        _sp.run(["git", "-C", path, "config", name, value], check=True)
    for message in commits:
        _sp.run(
            ["git", "-C", path, "commit", "-q", "--allow-empty", "-m", message], check=True
        )
    return path


def test_repo_origin_against_real_repos() -> None:
    """Who STARTED the repo, read off real git histories.

    The unit tests above inject the origin, so they say nothing about whether
    the root-commit read works at all. It is easy to get subtly wrong — the
    obvious `--format=…%(trailers:…valueonly)` appends a newline per commit, so
    a Claude commit also emits a BLANK line and naive line-counting scores a
    whole-Claude history as entirely human. Assert against real commits.

    Note what is deliberately NOT tested, because it is not the rule: later
    commits. A repo Claude scaffolded stays Claude's after a person edits it —
    the gate protects a human's mainline, and this repo never had one.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ[guardrail.ORIGIN_DB_ENV] = f"{tmp}/overlay.json"  # never the real one
        try:
            agent = make_repo(f"{tmp}/agent", "scaffold" + TRAILER, "more" + TRAILER)
            assert guardrail._repo_origin(agent) == "claude"

            # A human commit ON TOP does not change who started it.
            import subprocess as _sp

            _sp.run(
                ["git", "-C", agent, "commit", "-q", "--allow-empty", "-m", "by hand"],
                check=True,
            )
            assert guardrail._repo_origin(agent) == "claude", "root commit decides, not the tip"

            # A repo a person started stays theirs however much Claude writes in it.
            mine = make_repo(f"{tmp}/mine", "initial", "claude wrote this" + TRAILER)
            assert guardrail._repo_origin(mine) == "human"

            # Fail-closed paths: no repo at all, and a repo with no commits yet.
            assert guardrail._repo_origin(f"{tmp}/nope") is None
            assert guardrail._repo_origin(make_repo(f"{tmp}/empty")) is None
        finally:
            del os.environ[guardrail.ORIGIN_DB_ENV]


def test_overlay_overrides_the_root_commit_both_ways() -> None:
    """The override lives OUTSIDE the repo, keyed by root SHA — so it survives a
    clone to a new path, which a committed marker file would too but only by
    riding along in the tree we are trying to keep clean."""
    import subprocess as _sp
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        overlay = f"{tmp}/overlay.json"
        os.environ[guardrail.ORIGIN_DB_ENV] = overlay
        try:
            agent = make_repo(f"{tmp}/agent", "scaffold" + TRAILER)
            mine = make_repo(f"{tmp}/mine", "initial")
            root_of = lambda p: _sp.run(  # noqa: E731
                ["git", "-C", p, "rev-list", "--max-parents=0", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.split()[-1]

            pathlib.Path(overlay).write_text(json.dumps({"repos": {
                root_of(agent): {"origin": "human", "note": "handing this one off"},
                root_of(mine): {"origin": "claude"},
            }}))
            assert guardrail._repo_origin(agent) == "human", "override re-imposes the gate"
            assert guardrail._repo_origin(mine) == "claude", "override lifts it"

            # Follows a clone: same root SHA, different path, no file in the tree.
            clone = f"{tmp}/cloned"
            _sp.run(["git", "clone", "-q", mine, clone], check=True)
            assert guardrail._repo_origin(clone) == "claude"
            assert not (pathlib.Path(clone) / ".claude").exists(), "nothing written into the repo"

            # A malformed or absent overlay falls back to the root commit.
            pathlib.Path(overlay).write_text("{ not json")
            assert guardrail._repo_origin(agent) == "claude"
            assert guardrail._repo_origin(mine) == "human"
            assert guardrail.load_origin_db(overlay) == {}
        finally:
            del os.environ[guardrail.ORIGIN_DB_ENV]


def test_repo_origin_helper_cli() -> None:
    """bin/repo-origin — the thing that makes the overlay usable by hand."""
    import subprocess as _sp
    import tempfile

    tool = pathlib.Path(__file__).resolve().parent.parent / "bin" / "repo-origin"
    if not tool.exists():  # the hooks ship without bin/ in some layouts
        return

    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, CLAUDE_REPO_ORIGINS=f"{tmp}/overlay.json")

        def run(*args: str) -> str:
            out = _sp.run(
                [sys.executable, str(tool)] + list(args),
                capture_output=True, text=True, env=env, timeout=30,
            )
            assert out.returncode == 0, f"{args} failed: {out.stderr}"
            return out.stdout

        agent = make_repo(f"{tmp}/agent", "scaffold" + TRAILER)
        assert "claude" in run(agent), "reads the root commit with no overlay at all"

        run(agent, "--set", "human", "--note", "handing off")
        assert "human" in run(agent) and "override" in run(agent)
        assert "handing off" in run("--list")

        run(agent, "--unset")
        assert "claude" in run(agent), "unset falls back to the root commit"
        # The repo itself is never touched.
        assert not (pathlib.Path(agent) / ".claude").exists()


def test_end_to_end_under_system_python() -> None:
    """Run the hook the way the HARNESS runs it: as a subprocess, over stdin.

    The tests above `import guardrail`, so they exercise the rules but say
    nothing about whether the file loads under the interpreter that `#!/usr/bin/env
    python3` actually resolves to on this machine. That gap has now bitten four
    times — `str | None` (3.10), `dict[str, Any]` (3.9), `collections.abc.Callable[…]`
    (3.9), `str.removeprefix` (3.9) — and each time the failure was invisible:
    the hook died at import, PreToolUse read the non-zero exit as a non-blocking
    error, and every destructive command was allowed. The oldest box in the fleet
    runs Ubuntu 20.04 / Python 3.8.10, so the runtime floor is 3.8, not 3.9.

    A guardrail that silently allows everything is worse than no guardrail,
    because you think you have one. Assert the observable output.
    """
    import json as _json
    import subprocess as _sp

    hook = pathlib.Path(__file__).resolve().parent / "guardrail.py"

    def decide(command: str) -> str | None:
        proc = _sp.run(
            [str(hook)],
            input=_json.dumps({
                "tool_name": "Bash",
                "tool_input": {"command": command},
                "cwd": "/tmp",
            }),
            text=True, capture_output=True, timeout=30,
        )
        assert proc.returncode == 0, (
            f"hook exited {proc.returncode} for {command!r} — it probably failed to "
            f"load under {sys.version.split()[0]}. stderr:\n{proc.stderr}"
        )
        if not proc.stdout.strip():
            return None  # no opinion == allow
        payload = _json.loads(proc.stdout)
        section = payload.get("hookSpecificOutput", payload)
        decision: str | None = section.get("permissionDecision")
        return decision

    assert decide("rm -rf /") == "deny", "catastrophic command was not denied"
    assert decide("mkfs.ext4 /dev/sda1") == "deny"
    assert decide("git push --force origin main") == "ask"
    assert decide("ls -la") is None, "ordinary command should pass silently"
    # The refspec path specifically — this is where removeprefix() used to blow up.
    assert decide("git push origin refs/heads/main") == "ask"


if __name__ == "__main__":
    for _tool, _input, _expected in CASES:
        check_case(_tool, _input, _expected)
    for _cmd, _branch, _exp in BRANCH_CASES:
        check_branch_case(_cmd, _branch, _exp)
    test_mainline_push_hint_survives_to_emit_reason()
    test_origin_aware_mainline_push()
    test_push_repo_dir_reads_the_target_not_the_cwd()
    test_repo_origin_against_real_repos()
    test_overlay_overrides_the_root_commit_both_ways()
    test_repo_origin_helper_cli()
    test_end_to_end_under_system_python()
    print(
        f"ok — {len(CASES) + len(BRANCH_CASES) + 7} guardrail cases passed "
        f"(python {sys.version.split()[0]})"
    )
