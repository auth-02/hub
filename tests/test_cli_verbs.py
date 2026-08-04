"""Tests for the read CLI verbs `hub trace` / `hub timeline` and their arg parsing.

Also a guard that core/query.py and cli/mcp.py import nothing outside the stdlib
(+ hubspace.* itself) — the zero-runtime-dependency invariant.
"""
import ast
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import hub as hub_cli
from hubspace.core import db, query

_TS = time.mktime((2026, 7, 22, 12, 0, 0, 0, 0, -1))


def _seed():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = db.open_db(Path(tf.name))
    base = {"repo": "cortex", "ext": "md", "task_slug": "t", "task_repo": "cortex",
            "mtime": _TS, "skill_slug": None, "skill_repo": None}
    db.upsert(conn, {**base, "abs": "/r/cortex/tasks/t/manifest.md",
                     "rel": "tasks/t/manifest.md", "kind": "task"}, "T", "body")
    db.upsert(conn, {**base, "abs": "/r/cortex/tasks/t/runs/2026-07-22/r.md",
                     "rel": "tasks/t/runs/2026-07-22/r.md", "kind": "run"}, "R", "body")
    conn.commit()
    db.build_lineage(conn)
    conn.close()
    return tf.name


class TestArgParsing(unittest.TestCase):
    """The subparsers must accept the documented shapes without SystemExit."""

    def _parse(self, argv):
        # Rebuild the parser the same way main() does, but only through the
        # subparser definitions — invoke main() with stubbed handlers.
        captured = {}
        with patch.object(hub_cli, "_cmd_trace", lambda *a: captured.update(trace=a)), \
             patch.object(hub_cli, "_cmd_timeline", lambda *a: captured.update(timeline=a)), \
             patch.object(sys, "argv", ["hub", *argv]):
            hub_cli.main()
        return captured

    def test_trace_args(self):
        cap = self._parse(["trace", "some/path.md", "--json"])
        self.assertEqual(cap["trace"], ("some/path.md", True))

    def test_trace_default_not_json(self):
        cap = self._parse(["trace", "p.md"])
        self.assertEqual(cap["trace"], ("p.md", False))

    def test_timeline_args(self):
        cap = self._parse(["timeline", "my-task", "--json", "--repo", "cortex"])
        self.assertEqual(cap["timeline"], ("my-task", True, "cortex"))


class TestCmdOutput(unittest.TestCase):
    def setUp(self):
        self.name = _seed()

    def tearDown(self):
        os.unlink(self.name)

    def _run(self, fn, *args):
        buf = io.StringIO()
        with patch.object(query, "default_db_path", lambda: Path(self.name)), \
             redirect_stdout(buf):
            fn(*args)
        return buf.getvalue()

    def test_trace_json(self):
        out = self._run(hub_cli._cmd_trace, "tasks/t/manifest.md", True)
        data = json.loads(out)
        self.assertEqual(data["kind"], "task")
        self.assertTrue(data["down"])

    def test_trace_human(self):
        out = self._run(hub_cli._cmd_trace, "tasks/t/manifest.md", False)
        self.assertIn("[task]", out)
        self.assertIn("task_has_run", out)

    def test_timeline_json_contract(self):
        out = self._run(hub_cli._cmd_timeline, "t", True, None)
        data = json.loads(out)
        self.assertEqual(set(data), {"task", "nodes", "edges"})
        self.assertEqual(len(data["nodes"]), 2)

    def test_timeline_human(self):
        out = self._run(hub_cli._cmd_timeline, "t", False, None)
        self.assertIn("timeline: t", out)
        self.assertIn("2026-07-22", out)


class TestStdlibOnly(unittest.TestCase):
    """core/query.py and cli/mcp.py must import only stdlib + hubspace.*"""

    _STDLIB = {
        "__future__", "json", "sqlite3", "re", "sys", "io", "os", "time",
        "pathlib", "datetime", "typing", "contextlib", "ast",
    }

    def _top_level_imports(self, rel_path):
        root = Path(__file__).resolve().parent.parent
        tree = ast.parse((root / rel_path).read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative import: hubspace.* — allowed
                if node.module:
                    mods.add(node.module.split(".")[0])
        return mods

    def _assert_stdlib(self, rel_path):
        for mod in self._top_level_imports(rel_path):
            if mod == "hubspace":
                continue
            self.assertIn(mod, self._STDLIB,
                          f"{rel_path} imports non-stdlib module {mod!r}")

    def test_query_stdlib_only(self):
        self._assert_stdlib("hubspace/core/query.py")

    def test_mcp_stdlib_only(self):
        self._assert_stdlib("hubspace/cli/mcp.py")


if __name__ == "__main__":
    unittest.main()
