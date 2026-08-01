#!/usr/bin/env python3
"""Tests for vault_curator.py — the Stop hook that hands vault capture to a
detached background agent.

The spawn itself can't be exercised in CI (it would invoke a real model), so the
seam is build_curator_argv(): the argv is a pure function of its inputs, and the
security-critical properties (no permission bypass, tools scoped to exactly the
digest + vault-write, recursion guard in the child env) are asserted against it.
Everything upstream of the spawn — the guards, the digest, the fallback — is
driven through main() with a stubbed transcript and a fake $HOME so no real
vault, checkpoint dir, or `claude` binary is touched.

Stdlib only, like the hook.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vault_curator as vc  # noqa: E402


def _msg(role, content):
    return {"message": {"role": role, "content": content}}


def _bash(cmd):
    return {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}


def _rows_working(n=10, infra=False):
    """A transcript with n mutating calls; infra-flavored if asked."""
    rows = [_msg("user", "please do the thing")]
    cmd = "ssh web-01 docker compose up -d" if infra else "uv run pytest tests/"
    for _ in range(n):
        rows.append(_msg("assistant", [{"type": "text", "text": "working"}, _bash(cmd)]))
    return rows


def _write_transcript(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


class ArgvContract(unittest.TestCase):
    """The security surface of the background agent lives entirely in the argv."""

    def setUp(self):
        self.digest = Path("/tmp/x/sess.digest.md")
        self.argv = vc.build_curator_argv(self.digest, "software", "/repo", "/usr/bin/claude")
        self.joined = " ".join(self.argv)

    def test_no_permission_bypass(self):
        for bad in ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
                    "bypassPermissions", "--permission-mode"):
            self.assertNotIn(bad, self.joined,
                             "curator must never run with a permission bypass")

    def test_tools_scoped_to_exactly_read_digest_and_vault_write(self):
        i = self.argv.index("--allowedTools")
        tools = self.argv[i + 1:i + 3]
        self.assertEqual(tools[0], "Read({})".format(self.digest))
        self.assertEqual(tools[1], "Bash({} *)".format(vc.VAULT_WRITE))
        # nothing broader than those two
        self.assertNotIn("Edit", self.joined)
        self.assertNotIn("Write(", self.joined)

    def test_cheap_model_and_hard_timeout(self):
        self.assertEqual(self.argv[0], "timeout")
        self.assertEqual(self.argv[1], str(vc.SPAWN_TIMEOUT_SECS))
        i = self.argv.index("--model")
        self.assertEqual(self.argv[i + 1], vc.MODEL)
        self.assertIn("haiku", vc.MODEL)


class StructuredOutput(unittest.TestCase):
    """The curator must ask for stream-json. Plain text mode is what let a run
    with denied tool calls read as a success."""

    def setUp(self):
        self.argv = vc.build_curator_argv(Path("/tmp/x/s.digest.md"), "software", "/repo", "/usr/bin/claude")

    def test_asks_for_stream_json_with_verbose(self):
        i = self.argv.index("--output-format")
        self.assertEqual(self.argv[i + 1], "stream-json")
        self.assertIn("--verbose", self.argv, "stream-json under -p requires --verbose")

    def test_runner_wraps_the_curator_without_changing_it(self):
        runner = vc.build_runner_argv(self.argv, python_bin="/usr/bin/python3")
        self.assertEqual(runner[0], "/usr/bin/python3")
        self.assertEqual(runner[1], os.path.abspath(vc.__file__))
        self.assertEqual(runner[2], vc.RUN_FLAG)
        self.assertEqual(runner[3], "--")
        self.assertEqual(runner[4:], self.argv, "the inner argv must pass through verbatim")

    def test_runner_preserves_the_security_contract(self):
        joined = " ".join(vc.build_runner_argv(self.argv))
        self.assertNotIn("--dangerously-skip-permissions", joined)
        self.assertNotIn("bypassPermissions", joined)
        self.assertIn("--allowedTools", joined)


class RenderEvent(unittest.TestCase):
    """A denial has to be legible in the log at a glance."""

    def test_tool_call_and_success_are_rendered(self):
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "/h/.claude/bin/vault-write --type note"}}]}}
        self.assertIn("CALL Bash: /h/.claude/bin/vault-write --type note", vc.render_event(call)[0])
        ok = {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "queued note-abc.md"}]}}
        self.assertEqual(vc.render_event(ok), ["  ok: queued note-abc.md"])

    def test_failed_tool_result_is_marked(self):
        row = {"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": "permission denied"}]}}
        self.assertEqual(vc.render_event(row), ["  FAILED: permission denied"])

    def test_assistant_prose_survives(self):
        row = {"type": "assistant", "message": {"content": [{"type": "text", "text": "Wrote three notes."}]}}
        self.assertEqual(vc.render_event(row), ["Wrote three notes."])

    def test_permission_denials_are_read_off_the_result_event(self):
        """Verbatim shape from a real `claude -p --output-format stream-json`
        denial (2026-07-31). Note subtype "success" and is_error False:
        the RUN succeeded, only the work did not. Anything keyed off is_error
        alone would call this a clean run."""
        row = {
            "type": "result", "subtype": "success", "is_error": False,
            "result": "I need permission to run that command.",
            "permission_denials": [{
                "tool_name": "Bash",
                "tool_use_id": "toolu_01V6RmiH4EquaeRMGcUSXKT3",
                "tool_input": {"command": "/home/user/.claude/bin/vault-write --type note --title probe",
                               "description": "Run vault-write command"},
            }],
        }
        self.assertEqual(len(vc._result_denials(row)), 1)
        rendered = vc.render_event(row)
        self.assertEqual(rendered, ["  DENIED: Bash /home/user/.claude/bin/vault-write --type note --title probe"])

    def test_result_without_denials_is_quiet(self):
        row = {"type": "result", "subtype": "success", "is_error": False, "result": "ok"}
        self.assertEqual(vc._result_denials(row), [])
        self.assertEqual(vc.render_event(row), [])

    def test_malformed_denials_do_not_raise(self):
        for bad in ("nope", ["str", 3], None, [{}]):
            row = {"type": "result", "permission_denials": bad}
            self.assertIsInstance(vc._result_denials(row), list)
            self.assertIsInstance(vc.render_event(row), list)

    def test_thinking_blocks_are_not_logged(self):
        """Real runs emit `thinking` blocks; they are noise and a place secrets
        could surface, so the log leaves them out."""
        row = {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "internal chain of thought"}]}}
        self.assertEqual(vc.render_event(row), [])

    def test_garbage_rows_do_not_raise(self):
        for row in ({}, {"type": "assistant"}, {"type": "user", "message": {"content": "nope"}},
                    {"type": "assistant", "message": {"content": [None, 7]}}):
            self.assertIsInstance(vc.render_event(row), list)

    def test_counts_only_vault_write_calls_as_attempts(self):
        read = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/d.md"}}]}}
        self.assertEqual(vc._event_counts(read), (0, 0))
        write = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "{} --type note".format(vc.VAULT_WRITE)}}]}}
        self.assertEqual(vc._event_counts(write), (1, 0))


class Reconciliation(unittest.TestCase):
    """The defect this fixes: the model says it wrote notes, nothing did, and
    no one compares the claim to the queue."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "sent").mkdir()
        self.p = mock.patch.object(vc, "QUEUE_DIR", self.tmp)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def _run(self, stream_rows, notes_written=0):
        """Fake `claude` as a python one-liner that prints the given stream rows
        and drops `notes_written` files into the queue, so the reconciliation is
        exercised against a real directory rather than a mock."""
        script = (
            "import json,sys,pathlib\n"
            "rows = json.loads(sys.argv[1])\n"
            "q = pathlib.Path(sys.argv[2])\n"
            "[print(json.dumps(r), flush=True) for r in rows]\n"
            "[ (q / ('n%d.md' % i)).write_text('x') for i in range(int(sys.argv[3])) ]\n"
        )
        argv = [sys.executable, "-c", script, json.dumps(stream_rows), str(self.tmp), str(notes_written)]
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            vc.run_curator(argv)
        return out.getvalue()

    def test_success_reports_the_actual_count(self):
        rows = [{"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "{} --type note".format(vc.VAULT_WRITE)}}]}}]
        out = self._run(rows, notes_written=2)
        self.assertIn("curator: OK - 2 note(s) reached the queue", out)

    def test_claimed_but_wrote_nothing_is_called_out(self):
        rows = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "{} --type note".format(vc.VAULT_WRITE)}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "permission denied"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Done. Three durable patterns enqueued to the vault."}]}},
        ]
        out = self._run(rows, notes_written=0)
        self.assertIn("WROTE NOTHING", out)
        self.assertIn("1 vault-write attempt(s)", out)
        self.assertIn("FAILED: permission denied", out,
                      "the denial itself must appear, not just the verdict")
        # the model's false claim is still logged -- but no longer the last word
        self.assertLess(out.index("Three durable patterns"), out.index("WROTE NOTHING"))

    def test_denial_is_named_as_the_cause(self):
        """The 2026-07-31 03:06 failure, replayed: three notes claimed, every
        call denied, queue untouched, run reports success."""
        rows = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "{} --type pattern".format(vc.VAULT_WRITE)}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": True, "content": "Permission to use Bash has been denied"}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Done. Three durable patterns enqueued to the vault."}]}},
            {"type": "result", "subtype": "success", "is_error": False, "result": "Done.",
             "permission_denials": [{"tool_name": "Bash",
                                     "tool_input": {"command": "{} --type pattern".format(vc.VAULT_WRITE)}}]},
        ]
        out = self._run(rows, notes_written=0)
        self.assertIn("WROTE NOTHING", out)
        self.assertIn("DENIED by the permission system", out)
        self.assertIn("DENIED: Bash", out)

    def test_honest_abstention_is_not_an_error(self):
        rows = [{"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Nothing durable here."}]}}]
        out = self._run(rows, notes_written=0)
        self.assertIn("nothing durable - no notes attempted", out)
        self.assertNotIn("WROTE NOTHING", out)

    def test_broken_invocation_is_distinguished_from_honest_abstention(self):
        """Both write zero notes; only the log can tell them apart, and that is
        what would catch a flag rename leaving the curator dead for weeks."""
        argv = [sys.executable, "-c", "import sys; sys.stderr.write('unknown option --output-format\\n'); sys.exit(2)"]
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            vc.run_curator(argv)
        self.assertIn("NO OUTPUT", out.getvalue())
        self.assertIn("exit 2", out.getvalue())
        self.assertNotIn("nothing durable", out.getvalue())

    def test_non_json_output_is_kept_not_dropped(self):
        argv = [sys.executable, "-c", "print('traceback: boom')"]
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            vc.run_curator(argv)
        self.assertIn("traceback: boom", out.getvalue())

    def test_unstartable_child_does_not_raise(self):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            vc.run_curator(["/nonexistent/binary-xyz"])
        self.assertIn("could not start", out.getvalue())


class Digest(unittest.TestCase):
    def test_carries_intent_and_actions_not_tool_results(self):
        rows = [
            _msg("user", "fix the flaky test"),
            _msg("assistant", [{"type": "text", "text": "root cause is a shared clock"},
                               _bash("uv run pytest -k flaky")]),
            # a tool_result turn with a huge blob must not land in the digest
            _msg("user", [{"type": "tool_result", "content": "SECRET_TOKEN=hunter2 " + "x" * 5000}]),
        ]
        d = vc.build_digest(rows)
        self.assertIn("USER: fix the flaky test", d)
        self.assertIn("root cause is a shared clock", d)
        self.assertIn("ACTION: $ uv run pytest -k flaky", d)
        self.assertNotIn("hunter2", d)
        self.assertNotIn("xxxxx", d)

    def test_bounded_size_keeps_head_and_tail(self):
        rows = [_msg("user", "ORIGINAL INTENT")]
        for i in range(4000):
            rows.append(_msg("assistant", [_bash("echo step %d" % i)]))
        rows.append(_msg("assistant", [{"type": "text", "text": "FINAL CONCLUSION"}]))
        d = vc.build_digest(rows)
        self.assertLessEqual(len(d.encode("utf-8")), vc.MAX_DIGEST_BYTES + 200)
        self.assertIn("ORIGINAL INTENT", d)      # head: the intent
        self.assertIn("FINAL CONCLUSION", d)      # tail: the payoff

    def test_empty_when_nothing_textual(self):
        self.assertEqual(vc.build_digest([{"noise": 1}]), "")


class MainFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        home = Path(self.tmp)
        (home / ".claude" / "bin").mkdir(parents=True)
        (home / ".claude" / "bin" / "vault-write").write_text("#!/bin/sh\n")
        self.home = home
        self.patchers = [
            mock.patch.object(vc, "HOME", home),
            mock.patch.object(vc, "VAULT_WRITE", home / ".claude" / "bin" / "vault-write"),
            mock.patch.object(vc, "STAMP_DIR", home / ".claude" / "checkpoints"),
            mock.patch.object(vc, "LOG_DIR", home / ".claude" / "vault-curator"),
        ]
        for p in self.patchers:
            p.start()
        self.spawned = []
        self.spawn_patch = mock.patch.object(vc, "_spawn_detached",
                                             lambda argv, sid: self.spawned.append(argv))
        self.spawn_patch.start()

    def tearDown(self):
        self.spawn_patch.stop()
        for p in self.patchers:
            p.stop()

    def _run(self, rows, session_id="s1", env=None):
        path = _write_transcript(rows)
        payload = json.dumps({"transcript_path": path, "session_id": session_id, "cwd": "/repo"})
        out = io.StringIO()
        environ = dict(os.environ)
        environ.pop(vc.GUARD_ENV, None)
        environ.pop(vc.ENABLE_ENV, None)
        if env:
            environ.update(env)
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), \
             mock.patch.object(sys, "stdout", out), \
             mock.patch.dict(os.environ, environ, clear=True), \
             mock.patch.object(vc.shutil, "which", return_value="/usr/bin/claude"):
            vc.main()
        return out.getvalue()

    def test_working_session_spawns_curator(self):
        out = self._run(_rows_working(10))
        self.assertEqual(len(self.spawned), 1, "a substantive session should spawn the curator")
        self.assertEqual(out, "", "spawning must be silent — no nudge, no wait")

    def test_spawns_the_reconciling_runner_not_the_bare_curator(self):
        self._run(_rows_working(10), session_id="runner")
        argv = self.spawned[0]
        self.assertEqual(argv[2], vc.RUN_FLAG,
                         "the hook must spawn the wrapper, or nothing reconciles the result")
        self.assertIn("--output-format", argv)
        self.assertIn("stream-json", argv)

    def test_infra_session_hints_infra_domain(self):
        self._run(_rows_working(10, infra=True))
        prompt = " ".join(self.spawned[0])
        self.assertIn("leaned infra", prompt)

    def test_quiet_session_does_nothing(self):
        out = self._run(_rows_working(2))
        self.assertEqual(self.spawned, [])
        self.assertEqual(out, "")

    def test_already_wrote_is_left_alone(self):
        rows = _rows_working(10)
        rows.append(_msg("assistant", [_bash("~/.claude/bin/vault-write --type note --domain software")]))
        self._run(rows)
        self.assertEqual(self.spawned, [], "don't double-capture what the session already recorded")

    def test_recursion_guard_blocks_child(self):
        out = self._run(_rows_working(10), env={vc.GUARD_ENV: "1"})
        self.assertEqual(self.spawned, [], "a curator child's own Stop must not spawn another")
        self.assertEqual(out, "")

    def test_once_per_session(self):
        self._run(_rows_working(10), session_id="dup")
        self._run(_rows_working(10), session_id="dup")
        self.assertEqual(len(self.spawned), 1, "Stop fires every turn; act at most once")

    def test_disabled_falls_back_to_nudge(self):
        out = self._run(_rows_working(10), env={vc.ENABLE_ENV: "0"})
        self.assertEqual(self.spawned, [])
        self.assertIn("systemMessage", out)
        self.assertIn("vault", out.lower())

    def test_prunes_stale_digests_but_keeps_fresh(self):
        vc.LOG_DIR.mkdir(parents=True, exist_ok=True)
        old = vc.LOG_DIR / "old.digest.md"
        new = vc.LOG_DIR / "new.digest.md"
        old.write_text("stale")
        new.write_text("fresh")
        stale = time.time() - 30 * 86400
        os.utime(old, (stale, stale))
        self._run(_rows_working(10), session_id="prune")
        self.assertFalse(old.exists(), "digests older than the window should be pruned")
        self.assertTrue(new.exists(), "recent digests must survive")

    def test_no_vault_installed_is_silent(self):
        (self.home / ".claude" / "bin" / "vault-write").unlink()
        out = self._run(_rows_working(10), session_id="novault")
        self.assertEqual(self.spawned, [])
        self.assertEqual(out, "")


class FailOpen(unittest.TestCase):
    def test_malformed_stdin(self):
        with mock.patch.object(sys, "stdin", io.StringIO("not json")):
            vc.main()  # must not raise

    def test_missing_transcript(self):
        payload = json.dumps({"transcript_path": "/nope/x.jsonl", "session_id": "s"})
        with mock.patch.object(sys, "stdin", io.StringIO(payload)):
            vc.main()  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
