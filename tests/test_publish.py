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

# ── S26 — deterministic dak worker slugs (live-mode, suffix-free, idempotent) ──
class TestWorkerSlug(unittest.TestCase):
    def test_task_slug_real_repo(self):
        # real repo → slug(<repo>-<slug>)
        self.assertEqual(publish.task_worker_slug("acme-api", "hello"),
                         "acme-api-hello")

    def test_task_slug_root_pseudo_repo(self):
        # the (root) pseudo-repo → bare slug(<slug>)
        self.assertEqual(publish.task_worker_slug("(root)", "hello"), "hello")
        self.assertEqual(publish.task_worker_slug(None, "hello"), "hello")
        self.assertEqual(publish.task_worker_slug("", "hello"), "hello")

    def test_task_slug_is_dns_safe_and_deterministic(self):
        s1 = publish.task_worker_slug("Acme_API!!", "Hello World")
        s2 = publish.task_worker_slug("Acme_API!!", "Hello World")
        self.assertEqual(s1, s2)                 # idempotent — same string twice
        self.assertEqual(s1, "acme-api-hello-world")
        self.assertTrue(all(c.isalnum() or c == "-" for c in s1))

    def test_task_slug_capped_at_63(self):
        s = publish.task_worker_slug("r" * 40, "s" * 40)
        self.assertLessEqual(len(s), 63)

    def test_file_slug_under_task(self):
        # under a task → slug(<repo>-<taskslug>-<fileStem>)
        self.assertEqual(
            publish.file_worker_slug("acme-api", "tasks/hello/artifacts/report",
                                     task_slug="hello", file_stem="report"),
            "acme-api-hello-report")

    def test_file_slug_under_task_root(self):
        self.assertEqual(
            publish.file_worker_slug("(root)", "report",
                                     task_slug="hello", file_stem="report"),
            "hello-report")

    def test_file_slug_loose_doc(self):
        # not under a task → slug(<repo>-<relpathNoExt>)
        self.assertEqual(
            publish.file_worker_slug("acme-api", "docs/guide"),
            "acme-api-docs-guide")

    def test_file_slug_loose_doc_root(self):
        self.assertEqual(publish.file_worker_slug("(root)", "report"), "report")

    def test_worker_from_url(self):
        self.assertEqual(
            publish.worker_from_url("https://acme-api-hello.sub.workers.dev"),
            "acme-api-hello")
        self.assertEqual(
            publish.worker_from_url("https://report-abc123.atharva-dak.workers.dev"),
            "report-abc123")
        self.assertIsNone(publish.worker_from_url(""))
        self.assertIsNone(publish.worker_from_url("https://example.com/x"))

    def test_record_stores_worker_field(self):
        import tempfile as _tf
        sidecar = Path(_tf.mkdtemp()) / "published.json"
        publish.record_published("acme", "hello", "https://x", mode="live",
                                 path=sidecar, worker="acme-hello")
        data = publish.load_published(sidecar)
        self.assertEqual(data[publish.published_key("acme", "hello")]["worker"],
                         "acme-hello")
        self.assertEqual(data[publish.published_key("acme", "hello")]["mode"], "live")


class TestIsPrivate(unittest.TestCase):
    def test_bool_true(self):
        self.assertTrue(config.is_private({"private": True}))

    def test_string_truthy(self):
        self.assertTrue(config.is_private({"private": "yes"}))

    def test_absent_or_falsy(self):
        self.assertFalse(config.is_private({}))
        self.assertFalse(config.is_private({"private": False}))
        self.assertFalse(config.is_private({"private": "no"}))


# ── single-file published-state under a symlinked scan root (S20 regression) ──
# The files index stores each abs UNRESOLVED (scan._meta: str(path)); the UI's
# data-abs and PUBLISHED_DATA["asset\t"+abs] lookup use that exact string. But
# record_published_asset stores the RESOLVED abs. Under a symlinked root the two
# differ, so before the fix the baked PUBLISHED_DATA key never matched any row's
# data-abs → no PUBLISHED marker. These pin the realpath reconciliation.

class TestAssetKeyRealpath(unittest.TestCase):
    def test_find_asset_key_matches_across_symlink(self):
        base = tempfile.mkdtemp()
        try:
            real = Path(base) / "realroot"; real.mkdir()
            link = Path(base) / "linkroot"; os.symlink(real, link)
            (real / "report.md").write_text("hi\n", encoding="utf-8")
            resolved = str((real / "report.md"))
            unresolved = str(link / "report.md")
            self.assertNotEqual(resolved, unresolved)  # symlink really differs
            data = {f"asset\t{resolved}": {"url": "u"}}
            # lookup by the UNRESOLVED (files-index) abs still finds the entry
            self.assertEqual(publish.find_asset_key(data, unresolved),
                             f"asset\t{resolved}")
            self.assertIsNone(publish.find_asset_key(data, str(link / "other.md")))
        finally:
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_realign_rekeys_to_unresolved_files_index_abs(self):
        base = tempfile.mkdtemp()
        try:
            real = Path(base) / "realroot"; real.mkdir()
            link = Path(base) / "linkroot"; os.symlink(real, link)
            (real / "report.md").write_text("hi\n", encoding="utf-8")
            resolved = str(real / "report.md")
            unresolved = str(link / "report.md")   # what scan._meta would record
            data = {
                f"asset\t{resolved}": {"url": "u"},
                "myrepo\tmy-task": {"url": "t"},           # task key: untouched
                "asset\t/gone/missing.md": {"url": "x"},   # no such file: untouched
            }
            out = publish.realign_asset_keys(data, [unresolved])
            self.assertIn(f"asset\t{unresolved}", out)          # re-keyed to UI abs
            self.assertNotIn(f"asset\t{resolved}", out)
            self.assertEqual(out[f"asset\t{unresolved}"]["url"], "u")
            self.assertIn("myrepo\tmy-task", out)               # passthrough
            self.assertIn("asset\t/gone/missing.md", out)       # passthrough
        finally:
            import shutil; shutil.rmtree(base, ignore_errors=True)

    def test_revoke_matches_across_symlink(self):
        base = tempfile.mkdtemp()
        try:
            real = Path(base) / "realroot"; real.mkdir()
            link = Path(base) / "linkroot"; os.symlink(real, link)
            (real / "report.md").write_text("hi\n", encoding="utf-8")
            import json as _json
            sidecar = Path(base) / "published.json"
            # Stored under the UNRESOLVED abs (the files-index form)…
            unresolved = str(link / "report.md")
            resolved = os.path.realpath(unresolved)
            self.assertNotEqual(unresolved, resolved)  # symlink really differs
            sidecar.write_text(_json.dumps({f"asset\t{unresolved}": {"url": "u"}}),
                               encoding="utf-8")
            # …revoke by the RESOLVED abs (server form) still removes it.
            self.assertTrue(
                publish.revoke_published_asset(resolved, sidecar=sidecar))
            self.assertEqual(publish.load_published(sidecar), {})
        finally:
            import shutil; shutil.rmtree(base, ignore_errors=True)


class TestBakedPublishedStateSymlinkedRoot(unittest.TestCase):
    """End-to-end: build the real index under a symlinked scan root and assert
    the baked PUBLISHED_DATA carries a key under the SAME abs string a file row
    uses for data-abs — so publishedForFile(dataAbs) would hit."""

    def test_marker_key_matches_row_data_abs(self):
        import json as _json
        import re as _re
        import shutil
        import subprocess
        base = tempfile.mkdtemp()
        try:
            real = Path(base) / "realroot"; real.mkdir()
            link = Path(base) / "linkroot"; os.symlink(real, link)
            state = Path(base) / "state" / "hub"; state.mkdir(parents=True)
            (real / "report.md").write_text("# Report\nhello\n", encoding="utf-8")

            # Record via the helper the SAME way /_publish does — it resolve()s,
            # so the stored key is the /private/... (resolved) abs.
            sidecar = state / "published.json"
            walked_abs = str(link / "report.md")   # how os.walk yields it under the root
            publish.record_published_asset(walked_abs, "https://x.example/r",
                                           sidecar=sidecar)
            stored = _json.loads(sidecar.read_text())
            self.assertIn(f"asset\t{os.path.realpath(walked_abs)}", stored)

            out_html = Path(base) / "docs-index.html"
            repo_root = os.path.dirname(os.path.dirname(__file__))
            env = {
                **os.environ,
                "PYTHONPATH": repo_root,
                "XDG_STATE_HOME": str(Path(base) / "state"),
                "HUB_SCAN_ROOT": str(link),
                "HUB_OUTPUT": str(out_html),
                "HUB_DB": str(Path(base) / "hub.db"),
            }
            r = subprocess.run(
                [sys.executable, "-m", "hubspace.cli.hub"],
                env=env, cwd=base, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

            html = out_html.read_text(encoding="utf-8")
            m = _re.search(r"const PUBLISHED_DATA=(\{.*?\});", html)
            self.assertIsNotNone(m, "PUBLISHED_DATA not found in baked index")
            pub = _json.loads(m.group(1))
            # The key the UI computes from a row's data-abs (unresolved) hits.
            self.assertIn(f"asset\t{walked_abs}", pub,
                          "PUBLISHED_DATA missing the files-index abs key")
            self.assertEqual(pub[f"asset\t{walked_abs}"]["url"],
                             "https://x.example/r")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
