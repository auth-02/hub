"""Tests for db.py — SQLite layer."""
import os
import sys
import tempfile
import time
import json
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import db


def _make_conn():
    """Open an in-memory DB with the full hub schema."""
    conn = db.open_db(Path(":memory:"))
    return conn


def _fake_meta(abs_path, repo="repo", rel="tasks/slug/manifest.md",
               ext="md", kind="task", mtime=None,
               task_slug="slug", task_repo="repo",
               skill_slug=None, skill_repo=None):
    return {
        "abs": abs_path,
        "repo": repo,
        "rel": rel,
        "ext": ext,
        "kind": kind,
        "mtime": mtime or time.time(),
        "task_slug": task_slug,
        "task_repo": task_repo,
        "skill_slug": skill_slug,
        "skill_repo": skill_repo,
    }


class TestOpenDb(unittest.TestCase):
    def test_creates_all_tables(self):
        # Use a real temp file because :memory: returns a new db per connect
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            name = f.name
        try:
            conn = db.open_db(Path(name))
            tables = {r[0] for r in
                      conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for expected in ("files", "lineage", "task_status", "activity_log"):
                self.assertIn(expected, tables)
            conn.close()
        finally:
            os.unlink(name)

    def test_fts_virtual_table_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            name = f.name
        try:
            conn = db.open_db(Path(name))
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fts'"
            ).fetchall()
            self.assertTrue(len(rows) > 0)
            conn.close()
        finally:
            os.unlink(name)


class TestIsCurrent(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tf.name)

    def test_unknown_path_returns_false(self):
        self.assertFalse(db.is_current(self.conn, "/no/such/file.md", 1234.0))

    def test_matching_mtime_returns_true(self):
        mtime = time.time()
        meta = _fake_meta("/a/b.md", mtime=mtime)
        db.upsert(self.conn, meta, "Title", "body")
        self.conn.commit()
        self.assertTrue(db.is_current(self.conn, "/a/b.md", mtime))

    def test_stale_mtime_returns_false(self):
        mtime = time.time()
        meta = _fake_meta("/a/c.md", mtime=mtime)
        db.upsert(self.conn, meta, "Title", "body")
        self.conn.commit()
        self.assertFalse(db.is_current(self.conn, "/a/c.md", mtime + 10))


class TestUpsert(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tf.name)

    def test_inserts_row(self):
        meta = _fake_meta("/proj/readme.md")
        db.upsert(self.conn, meta, "Readme", "content")
        self.conn.commit()
        row = self.conn.execute("SELECT title FROM files WHERE abs='/proj/readme.md'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Readme")

    def test_updates_existing_row(self):
        meta = _fake_meta("/proj/readme.md")
        db.upsert(self.conn, meta, "Old Title", "old body")
        self.conn.commit()
        db.upsert(self.conn, meta, "New Title", "new body")
        self.conn.commit()
        rows = self.conn.execute("SELECT title FROM files WHERE abs='/proj/readme.md'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "New Title")

    def test_fts_entry_synced_on_insert(self):
        meta = _fake_meta("/proj/guide.md")
        db.upsert(self.conn, meta, "Guide Title", "searchable content")
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT rowid FROM fts WHERE fts MATCH 'searchable'"
        ).fetchall()
        self.assertTrue(len(rows) > 0)

    def test_fts_entry_updated_on_update(self):
        meta = _fake_meta("/proj/guide2.md")
        db.upsert(self.conn, meta, "Guide", "old content")
        self.conn.commit()
        db.upsert(self.conn, meta, "Guide", "new content")
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT rowid FROM fts WHERE fts MATCH 'new'").fetchall()
        self.assertTrue(len(rows) > 0)


class TestPrune(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tf.name)

    def test_removes_gone_paths(self):
        db.upsert(self.conn, _fake_meta("/a/file1.md"), "T1", "b1")
        db.upsert(self.conn, _fake_meta("/a/file2.md"), "T2", "b2")
        self.conn.commit()
        db.prune(self.conn, {"/a/file1.md"})
        self.conn.commit()
        remaining = {r[0] for r in self.conn.execute("SELECT abs FROM files").fetchall()}
        self.assertIn("/a/file1.md", remaining)
        self.assertNotIn("/a/file2.md", remaining)

    def test_empty_live_set_removes_all(self):
        db.upsert(self.conn, _fake_meta("/a/x.md"), "X", "body")
        self.conn.commit()
        db.prune(self.conn, set())
        self.conn.commit()
        count = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        self.assertEqual(count, 0)

    def test_prune_does_not_remove_live_paths(self):
        db.upsert(self.conn, _fake_meta("/a/keep.md"), "K", "b")
        self.conn.commit()
        db.prune(self.conn, {"/a/keep.md"})
        self.conn.commit()
        count = self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        self.assertEqual(count, 1)


class TestBuildLineage(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tf.name)

    def test_task_to_run_edge_created(self):
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/manifest.md", kind="task", task_slug="slug"),
                  "Manifest", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/runs/2024-01-01/out.md", kind="run", task_slug="slug"),
                  "Run", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        rows = self.conn.execute("SELECT rel_type FROM lineage").fetchall()
        rel_types = {r[0] for r in rows}
        self.assertIn("task_has_run", rel_types)
        self.assertIn("belongs_to_task", rel_types)

    def test_task_to_draw_edge_created(self):
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/manifest.md", kind="task", task_slug="slug"),
                  "Manifest", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/draws/flow.excalidraw", kind="draw", task_slug="slug"),
                  "Flow", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        rel_types = {r[0] for r in self.conn.execute("SELECT rel_type FROM lineage").fetchall()}
        self.assertIn("task_has_draw", rel_types)
        self.assertIn("belongs_to_task", rel_types)
        # A draw under a task must NOT be mislabeled as a doc
        self.assertNotIn("task_has_doc", rel_types)

    def test_task_to_script_edge_created(self):
        # S16 — a .py and a .sh under a task build task_has_script edges.
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/manifest.md", kind="task", task_slug="slug"),
                  "Manifest", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/artifacts/probe.py",
                             rel="tasks/slug/artifacts/probe.py",
                             ext="py", kind="script", task_slug="slug"),
                  "Probe", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/scripts/run.sh",
                             rel="tasks/slug/scripts/run.sh",
                             ext="sh", kind="script", task_slug="slug"),
                  "Run", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        rel_types = {r[0] for r in self.conn.execute("SELECT rel_type FROM lineage").fetchall()}
        self.assertIn("task_has_script", rel_types)
        self.assertIn("belongs_to_task", rel_types)
        # Two scripts → two task_has_script edges.
        n = self.conn.execute(
            "SELECT COUNT(*) FROM lineage WHERE rel_type='task_has_script'"
        ).fetchone()[0]
        self.assertEqual(n, 2)
        # A script under a task must NOT be mislabeled as a doc.
        self.assertNotIn("task_has_doc", rel_types)

    def test_task_to_note_edge_created(self):
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/manifest.md", kind="task", task_slug="slug"),
                  "Manifest", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/slug/comments/notes.jsonl",
                             rel="tasks/slug/comments/notes.jsonl",
                             kind="note", task_slug="slug"),
                  "1 comment", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        rel_types = {r[0] for r in self.conn.execute("SELECT rel_type FROM lineage").fetchall()}
        self.assertIn("task_has_note", rel_types)
        self.assertIn("belongs_to_task", rel_types)
        # A note under a task must NOT be mislabeled as a doc
        self.assertNotIn("task_has_doc", rel_types)

    def test_lineage_cleared_on_rebuild(self):
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/s/manifest.md", kind="task", task_slug="s"),
                  "M", "")
        db.upsert(self.conn,
                  _fake_meta("/r/tasks/s/runs/d/out.md", kind="run", task_slug="s"),
                  "R", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        first_count = self.conn.execute("SELECT COUNT(*) FROM lineage").fetchone()[0]
        db.build_lineage(self.conn)
        second_count = self.conn.execute("SELECT COUNT(*) FROM lineage").fetchone()[0]
        self.assertEqual(first_count, second_count)


class TestSetStatusGetStatuses(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        # Patch sidecar path to a temp location so tests don't pollute real state
        self.sidecar_tf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._patcher = patch.object(db, "_STATUS_SIDECAR", Path(self.sidecar_tf.name))
        self._patcher.start()
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self._patcher.stop()
        self.conn.close()
        os.unlink(self.tf.name)
        os.unlink(self.sidecar_tf.name)

    def test_set_and_get_roundtrip(self):
        db.set_status(self.conn, "my-task", "my-repo", "done")
        result = json.loads(db.get_statuses_json(self.conn))
        self.assertEqual(result.get("my-repo:my-task"), "done")

    def test_update_status(self):
        db.set_status(self.conn, "t", "r", "ongoing")
        db.set_status(self.conn, "t", "r", "done")
        result = json.loads(db.get_statuses_json(self.conn))
        self.assertEqual(result.get("r:t"), "done")

    def test_multiple_tasks(self):
        db.set_status(self.conn, "task-a", "repo1", "ongoing")
        db.set_status(self.conn, "task-b", "repo1", "done")
        result = json.loads(db.get_statuses_json(self.conn))
        self.assertEqual(result["repo1:task-a"], "ongoing")
        self.assertEqual(result["repo1:task-b"], "done")


class TestExportHtmlData(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))

    def tearDown(self):
        self.conn.close()
        os.unlink(self.tf.name)

    def test_empty_db_returns_valid_json(self):
        fts_json, lineage_json = db.export_html_data(self.conn)
        self.assertEqual(json.loads(fts_json), [])
        self.assertEqual(json.loads(lineage_json), {})

    def test_upserted_file_appears_in_fts_json(self):
        db.upsert(self.conn, _fake_meta("/x/doc.md"), "Doc Title", "doc body")
        self.conn.commit()
        fts_json, _ = db.export_html_data(self.conn)
        items = json.loads(fts_json)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["t"], "Doc Title")

    def test_lineage_json_populated_after_build_lineage(self):
        db.upsert(self.conn,
                  _fake_meta("/p/tasks/s/manifest.md", kind="task", task_slug="s"),
                  "M", "")
        db.upsert(self.conn,
                  _fake_meta("/p/tasks/s/artifacts/note.md", kind="artifact", task_slug="s"),
                  "A", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        _, lineage_json = db.export_html_data(self.conn)
        lineage = json.loads(lineage_json)
        self.assertTrue(len(lineage) > 0)

    def test_script_appears_in_trace_lineage_data(self):
        # S16 — a task-subtree script surfaces in the exported trace lineage,
        # keyed by the manifest abs with rel_type task_has_script.
        db.upsert(self.conn,
                  _fake_meta("/p/tasks/s/manifest.md", kind="task", task_slug="s"),
                  "M", "")
        db.upsert(self.conn,
                  _fake_meta("/p/tasks/s/artifacts/probe.py",
                             rel="tasks/s/artifacts/probe.py",
                             ext="py", kind="script", task_slug="s"),
                  "Probe", "")
        self.conn.commit()
        db.build_lineage(self.conn)
        _, lineage_json = db.export_html_data(self.conn)
        lineage = json.loads(lineage_json)
        links = lineage["/p/tasks/s/manifest.md"]
        script_links = [l for l in links if l["r"] == "task_has_script"]
        self.assertEqual(len(script_links), 1)
        self.assertEqual(script_links[0]["k"], "script")
        self.assertTrue(script_links[0]["p"].endswith("probe.py"))


if __name__ == "__main__":
    unittest.main()
