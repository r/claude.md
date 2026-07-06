---
description: Report the current host / git / docker context so we don't act on the wrong machine
---

Report the operating context so we never act on the wrong machine. Run only read-only checks, then summarize. Do not change anything.

1. Current host: `hostname`; note whether we're local, inside an SSH session, or inside a `docker exec`.
2. Primary IPs (`ip -br addr` or `hostname -I`) and map them to the host table in `~/.claude/rules/infra.md` if you keep one.
3. Working directory; if it's a git repo, its branch and short status.
4. Docker context if present: `docker ps --format 'table {{.Names}}\t{{.Status}}'`.

End with one line: **"You are on `<host>` (`<ip>`), in `<dir>`, `<git/docker summary>`."**
