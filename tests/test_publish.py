"""Tests for roadmap 1f — publish one asset.

Two layers, no network anywhere:
  - core/publish.py: the pure redaction scanner + redactor (table-driven scan,
    clean-text negatives, byte-identical redaction, source never modified).
  - cli/hub.py `hub publish`: the privacy gate (findings block publish without a
    gate flag; --i-have-reviewed / --redact proceed to a dak handoff; a private
    workspace refuses). dak is stubbed to a missing path so nothing is executed.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import publish
from hubspace.core import config
from hubspace.cli import hub as hub_cli


# ── core: the scanner ─────────────────────────────────────────────────────────

class TestScan(unittest.TestCase):
    def test_finds_each_kind(self):
        cases = [
            ("path",  "see /Users/atharva/secrets/key.pem for details"),
            ("path",  "cloned into /home/deploy/app right now"),
            ("host",  "curl http://db-primary.internal/health"),
            ("host",  "ssh box.local worked"),
            ("host",  "ping mail.corp today"),
            ("email", "reach me at atharva.shinde@tifinrm.com please"),
            ("ip",    "bind 10.0.0.5 to the pool"),
            ("ip",    "gateway is 192.168.1.1 here"),
            ("ip",    "internal 172.16.30.9 route"),
            ("ip",    "loopback 127.0.0.1 only"),
        ]
        for kind, text in cases:
            with self.subTest(kind=kind, text=text):
                found = publish.scan(text)
                self.assertTrue(found, f"expected a finding in {text!r}")
                self.assertIn(kind, {f["kind"] for f in found})

    def test_no_false_positive_on_clean_text(self):
        clean = (
            "# Design notes\n"
            "The rotation window is 30 minutes. We serve on port 8787.\n"
            "Public host is example.com and the ratio is 172.5 percent.\n"
            "A relative path like docs/spec.md and version 10.2 are fine.\n"
            "Contact the team via the shared channel.\n"
        )
        self.assertEqual(publish.scan(clean), [])

    def test_public_ip_not_flagged(self):
        # 8.8.8.8 is public; 172.200.x is outside the private 16-31 range.
        self.assertEqual(publish.scan("dns 8.8.8.8 and 172.200.1.1"), [])

    def test_findings_have_line_and_span(self):
        text = "line one\ncall bob@x.com\n/Users/me/f"
        found = publish.scan(text)
        by_kind = {f["kind"]: f for f in found}
        self.assertEqual(by_kind["email"]["line"], 2)
        self.assertEqual(by_kind["path"]["line"], 3)
        for f in found:
            s, e = f["span"]
            self.assertEqual(text[s:e], f["text"])

    def test_email_wins_over_host_on_overlap(self):
        # bob@srv.internal is ONE email finding, not email + host.
        found = publish.scan("bob@srv.internal")
        self.assertEqual([f["kind"] for f in found], ["email"])


# ── core: the redactor ────────────────────────────────────────────────────────

class TestRedact(unittest.TestCase):
    def test_replaces_findings_with_placeholders(self):
        text = "path /Users/me/x and ip 10.0.0.1 done"
        out = publish.redact(text, publish.scan(text))
        self.assertIn("‹redacted:path›", out)
        self.assertIn("‹redacted:ip›", out)
        self.assertNotIn("/Users/me/x", out)
        self.assertNotIn("10.0.0.1", out)

    def test_rest_is_byte_identical(self):
        text = "before 10.0.0.1 after"
        out = publish.redact(text, publish.scan(text))
        self.assertEqual(out, "before ‹redacted:ip› after")

    def test_empty_findings_returns_text_unchanged(self):
        text = "nothing to see here"
        self.assertEqual(publish.redact(text, []), text)

    def test_subset_of_findings_only(self):
        text = "a@b.com and 10.0.0.1"
        found = publish.scan(text)
        email = [f for f in found if f["kind"] == "email"]
        out = publish.redact(text, email)
        self.assertIn("‹redacted:email›", out)
        self.assertIn("10.0.0.1", out)  # the un-selected finding is left alone


# ── cli: the privacy gate ─────────────────────────────────────────────────────

class TestPublishCLI(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.state = Path(self._dir) / "state"
        self.state.mkdir()
        self.file = Path(self._dir) / "report.md"
        self.file.write_text("host db.internal and /Users/me/x\n", encoding="utf-8")
        self._sd = patch.object(config, "state_dir", lambda: self.state)
        self._sd.start()

    def tearDown(self):
        self._sd.stop()
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def _run(self, **kw):
        kw.setdefault("reviewed", False)
        kw.setdefault("do_redact", False)
        kw.setdefault("dry_run", True)
        kw.setdefault("title", None)
        kw.setdefault("mode", None)
        kw.setdefault("slug", None)
        buf = io.StringIO()
        code = None
        with redirect_stdout(buf):
            try:
                hub_cli._cmd_publish(str(self.file), **kw)
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()

    def test_findings_block_without_gate_flag(self):
        with patch.object(hub_cli, "CONFIG", {}):
            code, out = self._run()
        self.assertEqual(code, 1)
        self.assertIn("finding", out)

    def test_private_refuses_entirely(self):
        with patch.object(hub_cli, "CONFIG", {"private": True}):
            code, out = self._run(reviewed=True)
        self.assertEqual(code, 2)
        self.assertIn("private", out)

    def test_reviewed_proceeds_to_handoff(self):
        # dak stubbed missing → prints the command (no execution, no network).
        fake = Path(self._dir) / "nope" / "dak.py"
        with patch.object(hub_cli, "CONFIG", {}), \
             patch.object(hub_cli, "_dak_script", lambda: fake):
            code, out = self._run(reviewed=True)
        self.assertIn("--dry-run", out)
        self.assertIn("report", out)

    def test_redact_writes_copy_and_leaves_original(self):
        original = self.file.read_text(encoding="utf-8")
        fake = Path(self._dir) / "nope" / "dak.py"
        with patch.object(hub_cli, "CONFIG", {}), \
             patch.object(hub_cli, "_dak_script", lambda: fake):
            code, out = self._run(do_redact=True)
        # original untouched
        self.assertEqual(self.file.read_text(encoding="utf-8"), original)
        # a sanitized copy was written under state_dir()/publish
        copy = self.state / "publish" / "report.redacted.md"
        self.assertTrue(copy.exists())
        self.assertNotIn("db.internal", copy.read_text(encoding="utf-8"))
        self.assertIn("redacted copy", out)


# ── config.is_private ─────────────────────────────────────────────────────────

class TestIsPrivate(unittest.TestCase):
    def test_bool_true(self):
        self.assertTrue(config.is_private({"private": True}))

    def test_string_truthy(self):
        self.assertTrue(config.is_private({"private": "yes"}))

    def test_absent_or_falsy(self):
        self.assertFalse(config.is_private({}))
        self.assertFalse(config.is_private({"private": False}))
        self.assertFalse(config.is_private({"private": "no"}))


if __name__ == "__main__":
    unittest.main()
