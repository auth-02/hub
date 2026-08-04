"""Tests for core/query.py — the read-only query layer (search/get_task/trace/timeline)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import db, query

# A fixed timestamp so `at` dates are deterministic: 2026-07-22 (local).
_TS = time.mktime((2026, 7, 22, 12, 0, 0, 0, 0, -1))


def _meta(abs_path, rel, kind, task_slug="auth-refactor", task_repo="cortex",
          ext="md", mtime=_TS):
    return {
        "abs": abs_path, "repo": task_repo, "rel": rel, "ext": ext, "kind": kind,
        "mtime": mtime, "task_slug": task_slug, "task_repo": task_repo,
        "skill_slug": None, "skill_repo": None,
    }


class _Base(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.conn = db.open_db(Path(self.tf.name))
        # A real on-disk manifest so plan/notes extraction (which reads the file)
        # has something to parse; the abs paths point into this temp tree.
        self.root = Path(tempfile.mkdtemp())
        man = self.root / "cortex/tasks/auth-refactor/manifest.md"
        man.parent.mkdir(parents=True)
        man.write_text(
            "---\nstatus: ongoing\ntitle: Auth Refactor\n---\n"
            "Plan the auth work.\n- [x] design tokens\n- [ ] ship it\n\n"
            "## Decisions\n1. Use JWT\n2. Rotate keys\n", encoding="utf-8")
        os.utime(man, (_TS, _TS))

        db.upsert(self.conn,
                  _meta(str(man), "tasks/auth-refactor/manifest.md", "task"),
                  "Auth Refactor", "Plan the auth work.")
        db.upsert(self.conn,
                  _meta("/r/cortex/tasks/auth-refactor/runs/2026-07-22/exp.md",
                        "tasks/auth-refactor/runs/2026-07-22/exp.md", "run"),
                  "Run exp", "benchmark output")
        db.upsert(self.conn,
                  _meta("/r/cortex/tasks/auth-refactor/artifacts/report.md",
                        "tasks/auth-refactor/artifacts/report.md", "artifact"),
                  "Report", "final report artifact")
        self.conn.commit()
        db.build_lineage(self.conn)

    def tearDown(self):
        import shutil
        self.conn.close()
        os.unlink(self.tf.name)
        shutil.rmtree(self.root, ignore_errors=True)


class TestSearch(_Base):
    def test_returns_shape(self):
        rows = query.search(self.conn, "benchmark")
        self.assertTrue(rows)
        r = rows[0]
        self.assertEqual(set(r), {"path", "repo", "kind", "title", "snippet"})
        self.assertEqual(r["kind"], "run")

    def test_kind_filter(self):
        rows = query.search(self.conn, "auth OR report OR benchmark", kind="artifact")
        self.assertTrue(all(r["kind"] == "artifact" for r in rows))
        self.assertTrue(rows)

    def test_blank_and_bad_query_degrade(self):
        self.assertEqual(query.search(self.conn, ""), [])
        # An unbalanced FTS query must not raise.
        self.assertEqual(query.search(self.conn, '"'), [])

    def test_none_conn(self):
        self.assertEqual(query.search(None, "anything"), [])


class TestGetTask(_Base):
    def test_shape_and_children(self):
        t = query.get_task(self.conn, "auth-refactor")
        self.assertIsNotNone(t)
        self.assertEqual(t["slug"], "auth-refactor")
        self.assertEqual(t["repo"], "cortex")
        self.assertEqual(t["title"], "Auth Refactor")
        # plan parsed from the manifest body
        self.assertEqual(t["plan"], [{"text": "design tokens", "done": True},
                                     {"text": "ship it", "done": False}])
        self.assertIn("Use JWT", t["notes"])
        self.assertEqual(len(t["runs"]), 1)
        self.assertEqual(len(t["artifacts"]), 1)

    def test_missing_returns_none(self):
        self.assertIsNone(query.get_task(self.conn, "no-such-task"))

    def test_none_conn(self):
        self.assertIsNone(query.get_task(None, "auth-refactor"))


class TestTrace(_Base):
    def test_manifest_down_edges(self):
        t = query.trace(self.conn, "tasks/auth-refactor/manifest.md")
        self.assertEqual(t["kind"], "task")
        self.assertEqual(t["task"], "auth-refactor")
        kinds = {e["kind"] for e in t["down"]}
        self.assertIn("run", kinds)
        self.assertIn("artifact", kinds)

    def test_relative_path_resolves(self):
        t = query.trace(self.conn, "tasks/auth-refactor/runs/2026-07-22/exp.md")
        self.assertEqual(t["kind"], "run")
        # a run links UP to its manifest and ACROSS to siblings
        self.assertTrue(any(e["kind"] == "task" for e in t["up"]))
        self.assertTrue(t["siblings"])

    def test_unknown_path_empty(self):
        t = query.trace(self.conn, "/nope.md")
        self.assertEqual(t["kind"], None)
        self.assertEqual(t["down"], [])

    def test_none_conn(self):
        self.assertEqual(query.trace(None, "/x")["down"], [])


class TestTimeline(_Base):
    def test_2b_contract(self):
        tl = query.timeline(self.conn, "auth-refactor")
        self.assertEqual(set(tl), {"task", "nodes", "edges"})
        self.assertEqual(tl["task"], "auth-refactor")
        # 3 nodes: manifest + run + artifact
        self.assertEqual(len(tl["nodes"]), 3)
        # manifest is always n1 (task first)
        self.assertEqual(tl["nodes"][0]["id"], "n1")
        self.assertEqual(tl["nodes"][0]["kind"], "task")
        for n in tl["nodes"]:
            self.assertEqual(set(n), {"id", "kind", "path", "at"})
        # 2 edges from the manifest (task_has_run, task_has_artifact)
        self.assertEqual(len(tl["edges"]), 2)
        for e in tl["edges"]:
            self.assertEqual(set(e), {"from", "to", "rel", "external"})
            self.assertFalse(e["external"])
            self.assertEqual(e["from"], "n1")

    def test_at_dates(self):
        tl = query.timeline(self.conn, "auth-refactor")
        by_kind = {n["kind"]: n["at"] for n in tl["nodes"]}
        # run's `at` comes from its runs/<YYYY-MM-DD>/ dir
        self.assertEqual(by_kind["run"], "2026-07-22")
        # manifest's `at` is the mtime ISO date
        self.assertEqual(by_kind["task"], "2026-07-22")

    def test_missing_task(self):
        tl = query.timeline(self.conn, "ghost")
        self.assertEqual(tl["nodes"], [])
        self.assertEqual(tl["edges"], [])

    def test_none_conn(self):
        self.assertEqual(query.timeline(None, "auth-refactor")["nodes"], [])


class TestConnect(unittest.TestCase):
    def test_missing_db_returns_none(self):
        self.assertIsNone(query.connect("/no/such/hub.db"))


if __name__ == "__main__":
    unittest.main()
