"""Safety rules for the PreToolUse guardrail (hooks/guardrail.py).

This is DATA, not logic — a plain Python literal so the guardrail needs nothing
but the standard library. That is deliberate and load-bearing:

  A security control that fails open when a dependency is missing is not a
  security control. The rules used to live in YAML, which meant a machine
  without PyYAML installed silently allowed every destructive command. Python
  ships a dict literal parser; it does not ship a YAML one. So we use a dict.

Raw strings (r'...') also mean the regexes read exactly as you'd type them into
`grep` — no backslash doubling, which is why this isn't JSON either.

Each rule has:
    action: "deny" | "ask"
    why:    short human explanation
    all:    list of regexes that must ALL match for the rule to fire
    guard:  (optional) extra engine-evaluated condition; currently only
            "default-branch-push" — fires only when a `git push` lands on
            main/master (resolves the current branch for bare/HEAD pushes)
    hint:   (optional) replaces the generic ask/deny boilerplate — use it to
            tell the agent how to KEEP WORKING (e.g. branch off), not just stop

`bash` rules are matched against each command SEGMENT (split on ; & | newline)
after leading sudo/env/wrappers are stripped, so a `^` anchors to the start of
an actual command — prose mentions of dangerous words (e.g. in a commit
message) don't trip it. `write` rules scan Write/Edit/MultiEdit content.

To tune the guardrail, edit THIS file — no changes to guardrail.py needed.
Run `python3 test_guardrail.py` afterwards; it covers every rule below.
"""

from __future__ import annotations

from typing import Any

RULES: dict[str, list[dict[str, Any]]] = {
    "bash": [
        # --- deny: catastrophic, essentially never legitimate via Claude ---
        {
            "action": "deny",
            "why": "recursive force-rm of a system root",
            "all": [
                r"^rm\b",
                r"-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r|(?:--recursive\b.*--force|--force\b.*--recursive)",
                r"(?:^|\s)(?:/|/\*|~|~/\*|\$HOME|\$\{HOME\}|/home|/mnt|/etc|/var|/usr|/bin|/lib|/boot|/root|/opt|/sys|/proc)(?:/\*)?(?:\s|$)",
            ],
        },
        {
            "action": "deny",
            "why": "mkfs would format a filesystem",
            "all": [r"^mkfs(?:\.\w+)?\s+\S"],
        },
        {
            "action": "deny",
            "why": "dd writing directly to a disk device",
            "all": [r"^dd\s+\S", r"\bof=/dev/(?:sd|nvme|vd|mmcblk|disk)"],
        },
        {
            "action": "deny",
            "why": "recursive chmod 777 on /",
            "all": [r"^chmod\s+-R\s+0*777\s+/(?:\s|$)"],
        },
        {
            # The classic bomb `:(){ :|:& };:` contains ; & | — which are exactly
            # the command-segment separators guardrail.py splits on — so a
            # full-string pattern can never match a post-split segment. Match
            # instead on the colon-function *definition* `:(){`, which lands
            # intact in the first segment and is essentially never legitimate.
            "action": "deny",
            "why": "fork bomb (colon-function definition)",
            "all": [r"^:\s*\(\s*\)\s*\{"],
        },
        {
            "action": "deny",
            "why": "redirecting output onto a disk device",
            "all": [r">\s*/dev/(?:sd|nvme|vd|mmcblk|disk)"],
        },
        # --- ask: destructive but sometimes legitimate (force a confirmation) ---
        {
            "action": "ask",
            "why": "zfs destroy removes a dataset/snapshot",
            "all": [r"^zfs\s+destroy\s+\S"],
        },
        {
            "action": "ask",
            "why": "zpool destroy removes an entire pool",
            "all": [r"^zpool\s+destroy\s+\S"],
        },
        {
            "action": "ask",
            "why": "docker system prune -a removes all unused images",
            "all": [r"^docker\s+system\s+prune\b.*(?:-a|--all)"],
        },
        {
            # `docker volume prune` needs no argument (it prunes ALL unused
            # volumes), so require an arg only for `rm`; bare `prune` is the
            # dangerous form to catch.
            "action": "ask",
            "why": "removing docker volumes can delete stateful data",
            "all": [r"^docker\s+volume\s+(?:prune\b|rm\s+\S)"],
        },
        {
            "action": "ask",
            "why": "git push --force can overwrite remote history",
            "all": [r"^git\b.*\bpush\b.*--force(?!-with-lease)"],
        },
        # --- ask: agency — only the outward-facing edge, not everyday git.
        # Commits and feature-branch pushes are FREE: they're local/recoverable
        # (git reset; re-push a branch) and the loop doctrine's "keep = commit"
        # depends on them not halting auto mode. What still stops for a nod is
        # publishing to the MAINLINE: any push that targets main/master —
        # explicit refspec, HEAD/bare push while on main (the engine resolves the
        # current branch), --all/--mirror — plus force-pushes (rule above) and
        # the unattended-scheduling rules below. Anchored to the git SUBCOMMAND
        # so `git log --grep push` doesn't trip.
        {
            "action": "ask",
            "why": "this push lands on main/master — the mainline is the outward edge (feature-branch pushes don't ask)",
            "all": [r"^git\s+(?:-C\s+\S+\s+|-c\s+\S+\s+)*push\b"],
            "guard": "default-branch-push",
            "hint": (
                "This push lands on main/master, which needs the user's explicit ok. Don't "
                "stall the work: keep going on a feature branch instead — `git switch -c "
                "<topic>` (move your commits there if you're sitting on main), push THAT "
                "branch (feature-branch pushes are free), and append the staged mainline "
                "push/merge to NEEDS-APPROVAL.md per the auto-mode skip-and-log rule. "
                "Only push main directly when the user has said yes in this session."
            ),
        },
        {
            "action": "ask",
            "why": "crontab -e/-r or install schedules an unattended job (crontab -l is read-only)",
            "all": [r"^crontab\b(?!.*\s-l(?:\s|$))"],
        },
        {
            "action": "ask",
            "why": "`at` schedules a command to run later, unattended",
            "all": [r"^at\s"],
        },
        {
            "action": "ask",
            "why": "enabling or starting a systemd timer arms an unattended job",
            "all": [r"^systemctl\b", r"\b(?:enable|start)\b", r"\.timer(?:\s|$)"],
        },
        {
            "action": "ask",
            "why": "systemd-run --on-* schedules a transient unattended job",
            "all": [r"^systemd-run\b", r"--on-"],
        },
    ],
    "write": [
        {
            "action": "ask",
            "why": "a private key",
            "all": [r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |PGP )?PRIVATE KEY-----"],
        },
        {
            "action": "ask",
            "why": "an AWS secret access key",
            "all": [r"aws_secret_access_key\s*=\s*[A-Za-z0-9/+]{30,}"],
        },
    ],
}
