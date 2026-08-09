"""Unit tests for the shared task manifest writer (hubspace.core.tasks)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import tasks


class TestSlug(unittest.TestCase):
    def test_valid_slugs(self):
        for s in ("a", "add-sso", "mcp-retrieval-adapter", "v2-thing"):
            self.assertTrue(tasks.valid_slug(s), s)

    def test_invalid_slugs(self):
        # path-escape guard: no separators, no traversal, no absolute, no caps
        for s in ("", "../x", "a/b", "/abs", "..", "-lead", "Caps", "a b", "a.b"):
            self.assertFalse(tasks.valid_slug(s), s)


class TestRenderManifest(unittest.TestCase):
    def test_minimal_matches_cli_historical_shape(self):
        # No created, no plan → the exact string `hub new task` always wrote.
        out = tasks.render_manifest("My Task")
        self.assertEqual(out, "---\nstatus: ongoing\ntitle: My Task\n---\n\n# My Task\n")

    def test_with_created_and_plan(self):
        out = tasks.render_manifest("T", status="paused", created="2026-08-04",
                                    plan=["draft", "wire"])
        self.assertEqual(
            out,
            "---\nstatus: paused\ntitle: T\ncreated: 2026-08-04\n---\n\n"
            "# T\n\n## Plan\n- [ ] draft\n- [ ] wire\n",
        )

    def test_mcp_example_body(self):
        # The exact manifest for the roadmap's example title (no plan).
        out = tasks.render_manifest("MCP retrieval adapter", created="2026-08-04")
        self.assertEqual(
            out,
            "---\nstatus: ongoing\ntitle: MCP retrieval adapter\n"
            "created: 2026-08-04\n---\n\n# MCP retrieval adapter\n",
        )


class TestWriteManifest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_writes_only_manifest_no_subdirs(self):
        p = tasks.write_manifest(self.root, "mcp-retrieval-adapter",
                                 "MCP retrieval adapter", created="2026-08-04")
        self.assertTrue(p.exists())
        self.assertEqual(p.name, "manifest.md")
        # exactly one child in the task dir — no runs/artifacts/data folders
        self.assertEqual([c.name for c in p.parent.iterdir()], ["manifest.md"])

    def test_invalid_slug_raises(self):
        for bad in ("../evil", "a/b", "/abs", "Caps"):
            with self.assertRaises(tasks.SlugError):
                tasks.write_manifest(self.root, bad, "T")

    def test_collision_raises_with_suggestion(self):
        tasks.write_manifest(self.root, "dup", "Dup")
        with self.assertRaises(tasks.TaskExists) as ctx:
            tasks.write_manifest(self.root, "dup", "Dup again")
        self.assertEqual(ctx.exception.suggestion, "dup-2")
        # original untouched (never overwritten/merged)
        self.assertIn("Dup", tasks.manifest_path(self.root, "dup").read_text())

    def test_readonly_root_raises_oserror(self):
        # A regular file named `tasks` makes the mkdir fail deterministically.
        (self.root / "tasks").write_text("not a dir", encoding="utf-8")
        with self.assertRaises(OSError):
            tasks.write_manifest(self.root, "x", "X")


if __name__ == "__main__":
    unittest.main()
