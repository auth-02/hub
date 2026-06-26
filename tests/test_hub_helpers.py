"""Tests for pure helper functions in hub.py."""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import hub


class TestClassify(unittest.TestCase):
    def test_claude_stem(self):
        p = Path("/repo/CLAUDE.md")
        self.assertEqual(hub._classify(p, "CLAUDE.md"), "claude")

    def test_readme_stem(self):
        p = Path("/repo/README.md")
        self.assertEqual(hub._classify(p, "README.md"), "readme")

    def test_inside_tasks_dir(self):
        p = Path("/repo/tasks/my-task/manifest.md")
        self.assertEqual(hub._classify(p, "tasks/my-task/manifest.md"), "task")

    def test_inside_runs_dir(self):
        p = Path("/repo/tasks/slug/runs/2024-01-01/out.md")
        self.assertEqual(hub._classify(p, "tasks/slug/runs/2024-01-01/out.md"), "run")

    def test_inside_artifacts_dir(self):
        p = Path("/repo/tasks/slug/artifacts/note.md")
        self.assertEqual(hub._classify(p, "tasks/slug/artifacts/note.md"), "artifact")

    def test_inside_data_dir(self):
        p = Path("/repo/tasks/slug/data/input.csv")
        self.assertEqual(hub._classify(p, "tasks/slug/data/input.csv"), "data")

    def test_inside_prompts_dir_at_repo_root_returns_none(self):
        # Top-level prompts/ is not in the spec; only tasks/<slug>/prompts/** → prompt
        p = Path("/repo/prompts/system.txt")
        self.assertIsNone(hub._classify(p, "prompts/system.txt"))

    def test_prompts_inside_tasks_dir(self):
        # Bug-fix: tasks/<slug>/prompts/ must classify as prompt, not task
        p = Path("/repo/tasks/slug/prompts/system.txt")
        self.assertEqual(hub._classify(p, "tasks/slug/prompts/system.txt"), "prompt")

    def test_non_manifest_in_tasks_returns_none(self):
        # Only manifest.md at tasks/<slug>/manifest.md gets kind=task
        p = Path("/repo/tasks/my-task/notes.md")
        self.assertIsNone(hub._classify(p, "tasks/my-task/notes.md"))

    def test_skill_md_classified_as_skill(self):
        p = Path("/repo/app/skills/rate_limiting/SKILL.md")
        self.assertEqual(hub._classify(p, "app/skills/rate_limiting/SKILL.md"), "skill")

    def test_skill_reference_returns_none(self):
        p = Path("/repo/app/skills/rate_limiting/references/algorithms.md")
        self.assertIsNone(hub._classify(p, "app/skills/rate_limiting/references/algorithms.md"))

    def test_inside_docs_dir(self):
        p = Path("/repo/docs/guide.md")
        self.assertEqual(hub._classify(p, "docs/guide.md"), "doc")

    def test_plain_file_returns_none(self):
        p = Path("/repo/src/app.md")
        self.assertIsNone(hub._classify(p, "src/app.md"))


class TestTaskSlug(unittest.TestCase):
    def test_path_inside_tasks(self):
        p = Path("/repo/tasks/add-oauth/manifest.md")
        self.assertEqual(hub._task_slug(p), "add-oauth")

    def test_path_deep_inside_task(self):
        p = Path("/repo/tasks/my-slug/runs/2024-01-01/out.md")
        self.assertEqual(hub._task_slug(p), "my-slug")

    def test_path_outside_tasks_returns_none(self):
        p = Path("/repo/docs/guide.md")
        self.assertIsNone(hub._task_slug(p))

    def test_tasks_dir_at_root(self):
        p = Path("/tasks/some-task/manifest.md")
        self.assertEqual(hub._task_slug(p), "some-task")


class TestTaskRepo(unittest.TestCase):
    def test_standard_layout(self):
        p = Path("/root/cortex/tasks/slug/manifest.md")
        repo_root = Path("/root/cortex")
        self.assertEqual(hub._task_repo(p, repo_root), "cortex")

    def test_nested_scan_root(self):
        p = Path("/tifin/cortex/tasks/slug/manifest.md")
        repo_root = Path("/tifin/cortex")
        self.assertEqual(hub._task_repo(p, repo_root), "cortex")

    def test_fallback_to_repo_root_name(self):
        # Path with no tasks/ segment → falls back to repo_root.name
        p = Path("/tifin/cortex/docs/guide.md")
        repo_root = Path("/tifin/cortex")
        self.assertEqual(hub._task_repo(p, repo_root), "cortex")


class TestAgo(unittest.TestCase):
    def test_zero_mtime_returns_dash(self):
        self.assertEqual(hub._ago(0), "—")

    def test_just_now(self):
        self.assertEqual(hub._ago(time.time()), "just now")

    def test_just_now_boundary(self):
        self.assertEqual(hub._ago(time.time() - 89), "just now")

    def test_minutes(self):
        result = hub._ago(time.time() - 120)
        self.assertTrue(result.endswith("m ago"), f"unexpected: {result}")
        self.assertEqual(result, "2m ago")

    def test_hours(self):
        result = hub._ago(time.time() - 7200)
        self.assertEqual(result, "2h ago")

    def test_days(self):
        result = hub._ago(time.time() - 3 * 86400)
        self.assertEqual(result, "3d ago")


class TestIncluded(unittest.TestCase):
    def test_markdown_file(self):
        self.assertTrue(hub._included(Path("/repo/README.md")))

    def test_html_file(self):
        self.assertTrue(hub._included(Path("/repo/docs/page.html")))

    def test_txt_in_prompts_dir(self):
        self.assertTrue(hub._included(Path("/repo/prompts/system.txt")))

    def test_txt_outside_prompts_dir_excluded(self):
        self.assertFalse(hub._included(Path("/repo/notes.txt")))

    def test_csv_in_data_dir(self):
        self.assertTrue(hub._included(Path("/repo/tasks/slug/data/input.csv")))

    def test_csv_outside_data_dir_excluded(self):
        self.assertFalse(hub._included(Path("/repo/input.csv")))

    def test_python_file_excluded(self):
        self.assertFalse(hub._included(Path("/repo/app.py")))

    def test_pdf_in_data_dir(self):
        self.assertTrue(hub._included(Path("/repo/tasks/slug/data/report.pdf")))

    def test_xlsx_in_data_dir(self):
        self.assertTrue(hub._included(Path("/repo/tasks/slug/data/report.xlsx")))


class TestHref(unittest.TestCase):
    def test_file_link_without_port(self):
        with patch.dict(os.environ, {}, clear=False):
            # Force module-level _SERVER_PORT to empty by patching the module attribute
            with patch.object(hub, "_SERVER_PORT", ""):
                result = hub._href("/Users/user/doc.md")
                self.assertTrue(result.startswith("file://"))

    def test_http_link_with_port(self):
        with patch.object(hub, "_SERVER_PORT", "8787"):
            result = hub._href("/Users/user/doc.md")
            self.assertTrue(result.startswith("http://localhost:8787"))
            self.assertIn("doc.md", result)


if __name__ == "__main__":
    unittest.main()
