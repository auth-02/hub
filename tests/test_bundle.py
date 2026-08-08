"""Tests for roadmap 1g — publish a task with lineage.

Three layers, no network anywhere:
  - render/bundle.py: freeze a task subtree to ONE self-contained HTML string —
    manifest + every child inlined, lineage baked STATIC (not a live DB call),
    and no external http(s) host. Plus the external-ref include/exclude choice.
  - core/publish.py published-state sidecar: record/load/revoke round-trip.
  - cli/hub.py `hub publish --task`: renders under state_dir()/publish (never the
    scan root), applies the SAME S5a gate, and refuses when private.
"""
import io
import os
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import db, query, publish, config
from hubspace.render import bundle
from hubspace.cli import hub as hub_cli

_TS = time.mktime((2026, 7, 22, 12, 0, 0, 0, 0, -1))


def _meta(abs_path, rel, kind, task_slug="auth-refactor", task_repo="cortex",
          ext="md", mtime=_TS):
    return {
        "abs": abs_path, "repo": task_repo, "rel": rel, "ext": ext, "kind": kind,
        "mtime": mtime, "task_slug": task_slug, "task_repo": task_repo,
        "skill_slug": None, "skill_repo": None,
    }


class _Base(unittest.TestCase):
    """A real on-disk task tree (manifest + run + artifact + note) indexed in a
    temp DB, so the bundle renderer has files to read and lineage to bake."""

    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))
        self.root = Path(tempfile.mkdtemp())

        def _write(rel, text):
            p = self.root / "cortex" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            os.utime(p, (_TS, _TS))
            return p

        man = _write("tasks/auth-refactor/manifest.md",
                     "---\nstatus: ongoing\ntitle: Auth Refactor\n---\n"
                     "The manifest prose SENTINEL_MANIFEST.\n"
                     "- [x] design tokens\n- [ ] ship it\n")
        run = _write("tasks/auth-refactor/runs/2026-07-22/exp.md",
                     "# Run\nbenchmark SENTINEL_RUN output\n")
        art = _write("tasks/auth-refactor/artifacts/report.md",
                     "# Report\nfinal SENTINEL_ARTIFACT report\n")
        note = _write(
            "tasks/auth-refactor/comments/notes.jsonl",
            '{"id":"n1","target":"manifest.md","author":"you",'
            '"created":"2026-07-22T09:00:00","body":"a SENTINEL_NOTE thought"}\n')

        db.upsert(self.conn, _meta(str(man), "tasks/auth-refactor/manifest.md",
                                   "task"), "Auth Refactor", "prose")
        db.upsert(self.conn, _meta(str(run),
                  "tasks/auth-refactor/runs/2026-07-22/exp.md", "run"),
                  "Run exp", "benchmark")
        db.upsert(self.conn, _meta(str(art),
                  "tasks/auth-refactor/artifacts/report.md", "artifact"),
                  "Report", "report")
        db.upsert(self.conn, _meta(str(note),
                  "tasks/auth-refactor/comments/notes.jsonl", "note"),
                  "1 comment", "a SENTINEL_NOTE thought")
        self.conn.commit()
        db.build_lineage(self.conn)

    def tearDown(self):
        import shutil
        self.conn.close()
        os.unlink(self.tf.name)
        shutil.rmtree(self.root, ignore_errors=True)


# ── render/bundle.py ───────────────────────────────────────────────────────────
class TestRenderBundle(_Base):
    def test_returns_one_self_contained_document(self):
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        self.assertTrue(html.strip().startswith("<!DOCTYPE"))
        self.assertEqual(html.count("<!DOCTYPE"), 1)  # ONE document, not nested
        self.assertIn("<style>", html)               # CSS embedded, not linked

    def test_contains_manifest_and_every_child(self):
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        for sentinel in ("SENTINEL_MANIFEST", "SENTINEL_RUN",
                         "SENTINEL_ARTIFACT", "SENTINEL_NOTE"):
            self.assertIn(sentinel, html, sentinel)

    def test_lineage_baked_static_not_live_placeholder(self):
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        self.assertIn("bundle-trace", html)
        self.assertIn("frozen from lineage", html)
        # the frozen trace names the actual child paths (baked, not a fetch stub)
        self.assertIn("runs/2026-07-22/exp.md", html)
        # no live-DB / server placeholder leaked in
        self.assertNotIn("{lineage_json}", html)
        self.assertNotIn("/_publish", html)

    def test_no_external_host(self):
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        hosts = re.findall(r'https?://[^\s"\')]+', html)
        self.assertEqual([h for h in hosts if "localhost" not in h], [])
        self.assertNotIn("localhost", html)

    def test_favicon_is_data_uri(self):
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        self.assertIn("data:image/svg+xml", html)

    def test_no_spa_reader_keydown_forwarder(self):
        """S17 — the parent-messaging keydown forwarder is for LIVE-served pages
        shown inside the SPA reader only. A published bundle must stay fully
        self-contained: it must NOT carry the parent postMessage script."""
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor")
        self.assertNotIn("hub-doc", html)
        self.assertNotIn("window.parent.postMessage", html)
        # S19 — the reader companion (hover "+" gutter, inline-comment renderer,
        # line-click hand-off) is LIVE-served only; it must never reach a bundle.
        self.assertNotIn("hub-comment-line", html)
        self.assertNotIn("hub-line-add", html)

    def test_missing_task_raises(self):
        with self.assertRaises(ValueError):
            bundle.render_task_bundle(self.conn, "cortex", "no-such-task")

    def test_none_conn_raises(self):
        with self.assertRaises(ValueError):
            bundle.render_task_bundle(None, "cortex", "auth-refactor")


class TestExternalRefs(_Base):
    """A lineage edge to a file OUTSIDE the task is either inlined (include) or
    marked excluded (default) — never a dead link."""

    def _add_external_edge(self):
        # An indexed file that does NOT belong to the task, plus a hand-written
        # lineage edge from the manifest to it (the cross-task case).
        ext = self.root / "cortex" / "docs" / "external-SENTINEL_EXT.md"
        ext.parent.mkdir(parents=True, exist_ok=True)
        ext.write_text("# External\nSENTINEL_EXT body\n", encoding="utf-8")
        os.utime(ext, (_TS, _TS))
        m = _meta(str(ext), "docs/external-SENTINEL_EXT.md", "doc",
                  task_slug=None)
        m["task_repo"] = "cortex"
        db.upsert(self.conn, m, "External", "body")
        self.conn.commit()
        man_id = self.conn.execute(
            "SELECT id FROM files WHERE kind='task'").fetchone()[0]
        ext_id = self.conn.execute(
            "SELECT id FROM files WHERE rel=?",
            ("docs/external-SENTINEL_EXT.md",)).fetchone()[0]
        self.conn.execute(
            "INSERT INTO lineage(src_id, dst_id, rel_type) VALUES (?,?,?)",
            (man_id, ext_id, "task_has_doc"))
        self.conn.commit()
        return ext_id

    def test_external_marked_excluded_by_default(self):
        self._add_external_edge()
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor",
                                         include_external=False)
        self.assertIn("external", html.lower())
        self.assertIn("excluded", html.lower())
        # excluded → the body is NOT inlined
        self.assertNotIn("SENTINEL_EXT body", html)

    def test_external_inlined_when_requested(self):
        self._add_external_edge()
        html = bundle.render_task_bundle(self.conn, "cortex", "auth-refactor",
                                         include_external=True)
        self.assertIn("SENTINEL_EXT body", html)


# ── published-state sidecar (core/publish.py) ──────────────────────────────────
class TestPublishedSidecar(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.sidecar = Path(self._dir) / "published.json"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_missing_file_is_empty(self):
        self.assertEqual(publish.load_published(self.sidecar), {})

    def test_record_and_load_round_trip(self):
        publish.record_published("cortex", "auth-refactor",
                                 "https://x.example/abc", mode="snapshot",
                                 path=self.sidecar)
        data = publish.load_published(self.sidecar)
        entry = data["cortex\tauth-refactor"]
        self.assertEqual(entry["url"], "https://x.example/abc")
        self.assertEqual(entry["mode"], "snapshot")
        self.assertIn("at", entry)

    def test_key_shape(self):
        self.assertEqual(publish.published_key("cortex", "t"), "cortex\tt")
        self.assertEqual(publish.published_key(None, "t"), "(root)\tt")

    def test_revoke_removes_entry(self):
        publish.record_published("cortex", "t", "https://x", path=self.sidecar)
        self.assertTrue(publish.revoke_published("cortex", "t", path=self.sidecar))
        self.assertEqual(publish.load_published(self.sidecar), {})
        # revoking again is a no-op returning False
        self.assertFalse(publish.revoke_published("cortex", "t", path=self.sidecar))

    # ── S20: single-file asset entries in the SAME sidecar ─────────────────────
    def test_asset_record_and_load_round_trip(self):
        asset = Path(self._dir) / "report.md"
        asset.write_text("hi\n", encoding="utf-8")
        publish.record_published_asset(asset, "https://a.example/xyz",
                                       mode="snapshot", sidecar=self.sidecar)
        data = publish.load_published(self.sidecar)
        key = publish.published_asset_key(asset)
        self.assertEqual(data[key]["url"], "https://a.example/xyz")
        self.assertEqual(data[key]["mode"], "snapshot")
        self.assertIn("at", data[key])
        # asset key can never collide with a "<repo>\t<slug>" task key
        self.assertTrue(key.startswith("asset\t"))

    def test_asset_revoke_by_path(self):
        asset = Path(self._dir) / "report.md"
        asset.write_text("hi\n", encoding="utf-8")
        publish.record_published_asset(asset, "https://a", sidecar=self.sidecar)
        self.assertTrue(publish.revoke_published_asset(asset, sidecar=self.sidecar))
        self.assertEqual(publish.load_published(self.sidecar), {})
        # revoking again is a no-op returning False
        self.assertFalse(publish.revoke_published_asset(asset, sidecar=self.sidecar))

    def test_asset_revoke_leaves_task_entries(self):
        asset = Path(self._dir) / "report.md"
        asset.write_text("hi\n", encoding="utf-8")
        publish.record_published("cortex", "t", "https://task", path=self.sidecar)
        publish.record_published_asset(asset, "https://asset", sidecar=self.sidecar)
        self.assertTrue(publish.revoke_published_asset(asset, sidecar=self.sidecar))
        data = publish.load_published(self.sidecar)
        self.assertEqual(list(data), ["cortex\tt"])  # task entry untouched


# ── S20: a recorded asset entry is baked into the generated index ───────────────
class TestAssetPublishedBaked(unittest.TestCase):
    """End-to-end: record_published_asset + load_published round-trip an asset
    entry that the generated index BAKES into PUBLISHED_DATA. Builds the index in
    a subprocess (XDG_STATE_HOME → temp) so load_published reads our seeded
    sidecar; no network anywhere."""

    def test_generated_index_carries_asset_url(self):
        import subprocess
        root = tempfile.mkdtemp()
        state = tempfile.mkdtemp()
        try:
            asset = Path(root) / "report.md"
            asset.write_text("# Report\nnothing secret\n", encoding="utf-8")
            url = "https://baked-asset.example/xyz"
            sidecar = Path(state) / "hub" / "published.json"
            publish.record_published_asset(asset, url, sidecar=sidecar)

            out = Path(state) / "docs-index.html"
            env = dict(os.environ)
            env.update({
                "XDG_STATE_HOME": state,       # → state_dir() = <state>/hub
                "HUB_SCAN_ROOT": root,
                "HUB_OUTPUT": str(out),
                "HUB_DB": str(Path(state) / "hub.db"),
                "PYTHONPATH": os.path.dirname(os.path.dirname(__file__)),
            })
            r = subprocess.run([sys.executable, "-m", "hubspace.cli.hub"],
                               env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            page = out.read_text(encoding="utf-8")
            self.assertIn(url, page)                        # asset URL baked
            # S20 fix: the entry is baked under the FILES-INDEX abs (unresolved
            # str(path) — what the row uses for data-abs), so publishedForFile()
            # hits. Under a symlinked temp root this differs from the resolved abs
            # record_published_asset stored under; the resolved form must NOT be
            # the baked key (else the marker would never render).
            self.assertIn(f'data-abs="{asset}"', page)      # row abs (unresolved)
            self.assertIn(f'asset\\t{asset}"', page)         # PUBLISHED_DATA keyed to match
            if str(asset) != str(asset.resolve()):
                self.assertNotIn(f'asset\\t{asset.resolve()}"', page)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)
            shutil.rmtree(state, ignore_errors=True)


# ── cli: hub publish --task ─────────────────────────────────────────────────────
class TestPublishTaskCLI(_Base):
    def setUp(self):
        super().setUp()
        self.state = Path(tempfile.mkdtemp())
        self._sd = patch.object(config, "state_dir", lambda: self.state)
        self._sd.start()
        # point the read layer at our fixture DB
        self._cn = patch.object(query, "connect", lambda *a, **k: self.conn)
        self._cn.start()

    def tearDown(self):
        self._cn.stop()
        self._sd.stop()
        import shutil
        shutil.rmtree(self.state, ignore_errors=True)
        super().tearDown()

    def _run(self, **kw):
        kw.setdefault("repo", "cortex")
        kw.setdefault("include_external", False)
        kw.setdefault("out", None)
        kw.setdefault("reviewed", False)
        kw.setdefault("do_redact", False)
        kw.setdefault("dry_run", True)
        kw.setdefault("title", None)
        kw.setdefault("mode", None)
        buf = io.StringIO()
        code = None
        with redirect_stdout(buf):
            try:
                hub_cli._cmd_publish_task("auth-refactor", **kw)
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()

    def test_writes_bundle_under_state_publish_not_scan_root(self):
        with patch.object(hub_cli, "CONFIG", {}):
            code, out = self._run()
        produced = self.state / "publish" / "cortex-auth-refactor.html"
        self.assertTrue(produced.exists())
        # nothing written into the scan root
        self.assertFalse((self.root / "publish").exists())
        html = produced.read_text(encoding="utf-8")
        self.assertIn("SENTINEL_MANIFEST", html)

    def test_clean_bundle_scan_only_exits_zero(self):
        # our fixture has no redaction findings → scan-only exits 0
        with patch.object(hub_cli, "CONFIG", {}):
            code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("scan clean", out)

    def test_private_refuses(self):
        with patch.object(hub_cli, "CONFIG", {"private": True}):
            code, out = self._run(reviewed=True)
        self.assertEqual(code, 2)
        self.assertIn("private", out)

    def test_redact_dry_run_proceeds_to_handoff(self):
        # inject a finding into the manifest so --redact has something to do
        man = self.root / "cortex/tasks/auth-refactor/manifest.md"
        man.write_text(man.read_text(encoding="utf-8") +
                       "\ncontact bob@corp.internal\n", encoding="utf-8")
        fake = Path(self.state) / "nope" / "dak.py"
        with patch.object(hub_cli, "CONFIG", {}), \
             patch.object(hub_cli, "_dak_script", lambda: fake):
            code, out = self._run(do_redact=True)
        self.assertIn("--dry-run", out)
        self.assertIn("redacted copy", out)
        redacted = self.state / "publish" / "cortex-auth-refactor.redacted.html"
        self.assertTrue(redacted.exists())


if __name__ == "__main__":
    unittest.main()
