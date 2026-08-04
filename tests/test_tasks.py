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


class TestWriteNote(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "tasks" / "demo").mkdir(parents=True)
        (self.root / "tasks" / "demo" / "manifest.md").write_text(
            "# Demo\n", encoding="utf-8")

    def test_writes_one_note_with_frontmatter(self):
        p = tasks.write_note(
            self.root, "demo", "artifacts/token-flow.html",
            "The rotation window feels short — can we make it configurable?",
            author="atharva", range_="L41-L48", created="2026-08-04")
        self.assertTrue(p.exists())
        self.assertEqual(p.parent.name, "comments")
        self.assertTrue(p.name.startswith("2026-08-04-"))
        self.assertTrue(p.name.endswith(".md"))
        text = p.read_text(encoding="utf-8")
        self.assertIn("target: artifacts/token-flow.html", text)
        self.assertIn("range: L41-L48", text)
        self.assertIn("author: atharva", text)
        self.assertIn("created: 2026-08-04", text)
        self.assertIn("rotation window feels short", text)
        # comments/ is created lazily inside the existing task dir
        self.assertEqual(os.path.realpath(p.parent),
                         os.path.realpath(self.root / "tasks" / "demo" / "comments"))

    def test_optional_fields_omitted(self):
        p = tasks.write_note(self.root, "demo", "manifest.md", "Looks good.",
                             created="2026-08-04")
        text = p.read_text(encoding="utf-8")
        self.assertNotIn("range:", text)
        self.assertNotIn("author:", text)
        self.assertIn("target: manifest.md", text)

    def test_collision_suffixes_dashN(self):
        a = tasks.write_note(self.root, "demo", "manifest.md", "same words here",
                             created="2026-08-04")
        b = tasks.write_note(self.root, "demo", "manifest.md", "same words here",
                             created="2026-08-04")
        self.assertNotEqual(a.name, b.name)
        self.assertRegex(b.name, r"-2\.md$")
        # first note untouched
        self.assertIn("same words here", a.read_text())

    def test_invalid_slug_raises(self):
        with self.assertRaises(tasks.SlugError):
            tasks.write_note(self.root, "../evil", "manifest.md", "x")

    def test_target_escaping_task_raises(self):
        for bad in ("../../etc/passwd", "/etc/passwd", "../other/x.md"):
            with self.assertRaises(tasks.SlugError):
                tasks.write_note(self.root, "demo", bad, "x")

    def test_empty_target_or_body_raises(self):
        with self.assertRaises(ValueError):
            tasks.write_note(self.root, "demo", "", "body")
        with self.assertRaises(ValueError):
            tasks.write_note(self.root, "demo", "manifest.md", "  ")

    def test_readonly_task_raises_oserror(self):
        # A regular file named `comments` blocks the mkdir → OSError.
        (self.root / "tasks" / "demo" / "comments").write_text("x", encoding="utf-8")
        with self.assertRaises(OSError):
            tasks.write_note(self.root, "demo", "manifest.md", "hi")


class TestFindTaskFor(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_finds_owning_task(self):
        f = self.root / "cortex" / "tasks" / "auth" / "artifacts" / "flow.html"
        f.parent.mkdir(parents=True)
        f.write_text("<p>x</p>", encoding="utf-8")
        ctx = tasks.find_task_for(f)
        self.assertIsNotNone(ctx)
        repo_root, slug, target_rel = ctx
        self.assertEqual(slug, "auth")
        self.assertEqual(repo_root.name, "cortex")
        self.assertEqual(os.path.realpath(repo_root),
                         os.path.realpath(self.root / "cortex"))
        self.assertEqual(target_rel, "artifacts/flow.html")

    def test_returns_none_when_not_under_task(self):
        f = self.root / "docs" / "loose.md"
        f.parent.mkdir(parents=True)
        f.write_text("x", encoding="utf-8")
        self.assertIsNone(tasks.find_task_for(f))


class TestNoteStem(unittest.TestCase):
    def test_from_body(self):
        self.assertEqual(
            tasks.note_stem("The rotation window feels short", "manifest.md"),
            "the-rotation-window-feels-short")

    def test_falls_back_to_target(self):
        self.assertEqual(tasks.note_stem("!!!", "artifacts/token-flow.html"),
                         "token-flow")

    def test_ultimate_fallback(self):
        self.assertEqual(tasks.note_stem("", ""), "note")


if __name__ == "__main__":
    unittest.main()
