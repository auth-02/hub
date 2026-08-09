"""Tests for pure helper functions in hub.py."""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import hub
from hubspace.core import scan
from hubspace.utils.text import relative_time


class TestClassify(unittest.TestCase):
    def test_claude_stem(self):
        p = Path("/repo/CLAUDE.md")
        self.assertEqual(scan._classify(p, "CLAUDE.md"), "claude")

    def test_readme_stem(self):
        p = Path("/repo/README.md")
        self.assertEqual(scan._classify(p, "README.md"), "readme")

    def test_inside_tasks_dir(self):
        p = Path("/repo/tasks/my-task/manifest.md")
        self.assertEqual(scan._classify(p, "tasks/my-task/manifest.md"), "task")

    def test_inside_runs_dir(self):
        p = Path("/repo/tasks/slug/runs/2024-01-01/out.md")
        self.assertEqual(scan._classify(p, "tasks/slug/runs/2024-01-01/out.md"), "run")

    def test_inside_artifacts_dir(self):
        p = Path("/repo/tasks/slug/artifacts/note.md")
        self.assertEqual(scan._classify(p, "tasks/slug/artifacts/note.md"), "artifact")

    def test_inside_data_dir(self):
        p = Path("/repo/tasks/slug/data/input.csv")
        self.assertEqual(scan._classify(p, "tasks/slug/data/input.csv"), "data")

    def test_comments_notes_jsonl_returns_note(self):
        # S7 — the append-only comment log classifies as kind:note.
        p = Path("/repo/tasks/slug/comments/notes.jsonl")
        self.assertEqual(
            scan._classify(p, "tasks/slug/comments/notes.jsonl"), "note")

    def test_inside_prompts_dir_at_repo_root_returns_none(self):
        # Top-level prompts/ is not in the spec; only tasks/<slug>/prompts/** → prompt
        p = Path("/repo/prompts/system.txt")
        self.assertIsNone(scan._classify(p, "prompts/system.txt"))

    def test_prompts_inside_tasks_dir(self):
        # Bug-fix: tasks/<slug>/prompts/ must classify as prompt, not task
        p = Path("/repo/tasks/slug/prompts/system.txt")
        self.assertEqual(scan._classify(p, "tasks/slug/prompts/system.txt"), "prompt")

    def test_script_py_in_task_root_is_script(self):
        # S16 — a loose .py in the task root classifies as script.
        p = Path("/repo/tasks/slug/probe.py")
        self.assertEqual(scan._classify(p, "tasks/slug/probe.py"), "script")

    def test_script_sh_in_scripts_dir_is_script(self):
        p = Path("/repo/tasks/slug/scripts/run.sh")
        self.assertEqual(scan._classify(p, "tasks/slug/scripts/run.sh"), "script")

    def test_script_wins_over_artifacts(self):
        # S16 — a probe .py in artifacts/ is a script, not an artifact.
        p = Path("/repo/tasks/slug/artifacts/probe.py")
        self.assertEqual(scan._classify(p, "tasks/slug/artifacts/probe.py"), "script")

    def test_md_in_artifacts_still_artifact(self):
        # Non-script exts under artifacts/ keep their kind (regression).
        p = Path("/repo/tasks/slug/artifacts/note.md")
        self.assertEqual(scan._classify(p, "tasks/slug/artifacts/note.md"), "artifact")

    def test_script_does_not_override_prompts(self):
        # A .txt in prompts/ stays a PROMPT, not a script.
        p = Path("/repo/tasks/slug/prompts/system.txt")
        self.assertEqual(scan._classify(p, "tasks/slug/prompts/system.txt"), "prompt")

    def test_script_does_not_override_data(self):
        # A .json in data/ stays DATA, not a script.
        p = Path("/repo/tasks/slug/data/blob.json")
        self.assertEqual(scan._classify(p, "tasks/slug/data/blob.json"), "data")

    def test_py_outside_task_not_classified_as_script(self):
        # Out-of-task code never becomes a script (and _included keeps it out).
        p = Path("/repo/src/app.py")
        self.assertIsNone(scan._classify(p, "src/app.py"))

    def test_non_manifest_in_tasks_gets_md_catch_all(self):
        # Only manifest.md gets kind=task; other .md in tasks root get MD catch-all
        p = Path("/repo/tasks/my-task/notes.md")
        self.assertEqual(scan._classify(p, "tasks/my-task/notes.md"), "md")

    def test_skill_md_classified_as_skill(self):
        p = Path("/repo/app/skills/rate_limiting/SKILL.md")
        self.assertEqual(scan._classify(p, "app/skills/rate_limiting/SKILL.md"), "skill")

    def test_skill_reference_gets_md_catch_all(self):
        # Non-SKILL.md files inside skills/ get MD catch-all (they're searchable docs)
        p = Path("/repo/app/skills/rate_limiting/references/algorithms.md")
        self.assertEqual(scan._classify(p, "app/skills/rate_limiting/references/algorithms.md"), "md")

    def test_inside_docs_dir(self):
        p = Path("/repo/docs/guide.md")
        self.assertEqual(scan._classify(p, "docs/guide.md"), "doc")

    def test_plain_md_returns_md_kind(self):
        # Loose .md not matching any structural pattern → MD catch-all
        p = Path("/repo/src/app.md")
        self.assertEqual(scan._classify(p, "src/app.md"), "md")

    def test_html_in_docs_returns_doc(self):
        p = Path("/repo/docs/page.html")
        self.assertEqual(scan._classify(p, "docs/page.html"), "doc")

    def test_html_outside_docs_returns_md_kind(self):
        p = Path("/repo/views/index.html")
        self.assertEqual(scan._classify(p, "views/index.html"), "md")

    def test_htm_extension_returns_md_kind(self):
        p = Path("/repo/page.htm")
        self.assertEqual(scan._classify(p, "page.htm"), "md")

    def test_classify_manifest_in_tasks_repo(self):
        # When the repo dir itself is named "tasks", repo_name="tasks" shifts rel
        p = Path("/scan/tasks/my-feature/manifest.md")
        self.assertEqual(scan._classify(p, "my-feature/manifest.md", repo_name="tasks"), "task")

    def test_classify_run_in_tasks_repo(self):
        p = Path("/scan/tasks/my-feature/runs/2024-01-01/out.md")
        self.assertEqual(
            scan._classify(p, "my-feature/runs/2024-01-01/out.md", repo_name="tasks"), "run"
        )

    def test_classify_artifact_in_tasks_repo(self):
        p = Path("/scan/tasks/slug/artifacts/note.md")
        self.assertEqual(
            scan._classify(p, "slug/artifacts/note.md", repo_name="tasks"), "artifact"
        )

    def test_classify_prompt_in_tasks_repo(self):
        p = Path("/scan/tasks/slug/prompts/system.txt")
        self.assertEqual(
            scan._classify(p, "slug/prompts/system.txt", repo_name="tasks"), "prompt"
        )

    def test_classify_data_in_tasks_repo(self):
        p = Path("/scan/tasks/slug/data/input.csv")
        self.assertEqual(
            scan._classify(p, "slug/data/input.csv", repo_name="tasks"), "data"
        )

    def test_nested_docs_subdir_returns_doc(self):
        p = Path("/repo/docs/api/reference.md")
        self.assertEqual(scan._classify(p, "docs/api/reference.md"), "doc")

    def test_excalidraw_returns_draw(self):
        p = Path("/repo/diagram.excalidraw")
        self.assertEqual(scan._classify(p, "diagram.excalidraw"), "draw")

    def test_excalidraw_anywhere_returns_draw(self):
        # kind:draw regardless of location — even inside docs/ or tasks/
        p = Path("/repo/docs/arch.excalidraw")
        self.assertEqual(scan._classify(p, "docs/arch.excalidraw"), "draw")
        p2 = Path("/repo/tasks/slug/flow.excalidraw")
        self.assertEqual(scan._classify(p2, "tasks/slug/flow.excalidraw"), "draw")

    def test_excalidraw_named_readme_still_draw(self):
        # Extension wins over stem-based rules
        p = Path("/repo/README.excalidraw")
        self.assertEqual(scan._classify(p, "README.excalidraw"), "draw")


class TestTaskSlug(unittest.TestCase):
    def test_path_inside_tasks(self):
        p = Path("/repo/tasks/add-oauth/manifest.md")
        self.assertEqual(scan._task_slug(p), "add-oauth")

    def test_path_deep_inside_task(self):
        p = Path("/repo/tasks/my-slug/runs/2024-01-01/out.md")
        self.assertEqual(scan._task_slug(p), "my-slug")

    def test_path_outside_tasks_returns_none(self):
        p = Path("/repo/docs/guide.md")
        self.assertIsNone(scan._task_slug(p))

    def test_tasks_dir_at_root(self):
        p = Path("/tasks/some-task/manifest.md")
        self.assertEqual(scan._task_slug(p), "some-task")


class TestTaskRepo(unittest.TestCase):
    def test_standard_layout(self):
        p = Path("/root/cortex/tasks/slug/manifest.md")
        repo_root = Path("/root/cortex")
        self.assertEqual(scan._task_repo(p, repo_root), "cortex")

    def test_nested_scan_root(self):
        p = Path("/tifin/cortex/tasks/slug/manifest.md")
        repo_root = Path("/tifin/cortex")
        self.assertEqual(scan._task_repo(p, repo_root), "cortex")

    def test_fallback_to_repo_root_name(self):
        # Path with no tasks/ segment → falls back to repo_root.name
        p = Path("/tifin/cortex/docs/guide.md")
        repo_root = Path("/tifin/cortex")
        self.assertEqual(scan._task_repo(p, repo_root), "cortex")


class TestAgo(unittest.TestCase):
    def test_zero_mtime_returns_dash(self):
        self.assertEqual(relative_time(0), "—")

    def test_just_now(self):
        self.assertEqual(relative_time(time.time()), "just now")

    def test_just_now_boundary(self):
        self.assertEqual(relative_time(time.time() - 89), "just now")

    def test_minutes(self):
        result = relative_time(time.time() - 120)
        self.assertTrue(result.endswith("m ago"), f"unexpected: {result}")
        self.assertEqual(result, "2m ago")

    def test_hours(self):
        result = relative_time(time.time() - 7200)
        self.assertEqual(result, "2h ago")

    def test_days(self):
        result = relative_time(time.time() - 3 * 86400)
        self.assertEqual(result, "3d ago")


class TestIncluded(unittest.TestCase):
    def test_markdown_file(self):
        self.assertTrue(scan._included(Path("/repo/README.md")))

    def test_html_file(self):
        self.assertTrue(scan._included(Path("/repo/docs/page.html")))

    def test_txt_in_prompts_dir(self):
        self.assertTrue(scan._included(Path("/repo/prompts/system.txt")))

    def test_txt_outside_prompts_dir_excluded(self):
        self.assertFalse(scan._included(Path("/repo/notes.txt")))

    def test_csv_in_data_dir(self):
        self.assertTrue(scan._included(Path("/repo/tasks/slug/data/input.csv")))

    def test_csv_outside_data_dir_excluded(self):
        self.assertFalse(scan._included(Path("/repo/input.csv")))

    def test_python_file_excluded(self):
        self.assertFalse(scan._included(Path("/repo/app.py")))

    def test_pdf_in_data_dir(self):
        self.assertTrue(scan._included(Path("/repo/tasks/slug/data/report.pdf")))

    def test_xlsx_in_data_dir(self):
        self.assertTrue(scan._included(Path("/repo/tasks/slug/data/report.xlsx")))

    def test_excalidraw_included_anywhere(self):
        self.assertTrue(scan._included(Path("/repo/diagram.excalidraw")))
        self.assertTrue(scan._included(Path("/repo/deep/nested/flow.excalidraw")))

    def test_jsonl_in_comments_dir_included(self):
        # S7 — the comment log is swept in only under a comments/ dir.
        self.assertTrue(scan._included(Path("/repo/tasks/slug/comments/notes.jsonl")))

    def test_jsonl_outside_comments_dir_excluded(self):
        # A stray .jsonl anywhere else is NOT indexed.
        self.assertFalse(scan._included(Path("/repo/data/events.jsonl")))
        self.assertFalse(scan._included(Path("/repo/notes.jsonl")))

    def test_script_in_task_subtree_included(self):
        # S16 — code/probe files inside a task subtree are indexed for lineage.
        self.assertTrue(scan._included(Path("/repo/tasks/slug/artifacts/probe.py")))
        self.assertTrue(scan._included(Path("/repo/tasks/slug/scripts/run.sh")))
        self.assertTrue(scan._included(Path("/repo/tasks/slug/query.sql")))
        self.assertTrue(scan._included(Path("/repo/tasks/slug/probes/out.txt")))

    def test_script_outside_task_subtree_excluded(self):
        # S16 — scripts are NOT swept vault-wide; only inside tasks/<slug>/**.
        self.assertFalse(scan._included(Path("/repo/app.py")))
        self.assertFalse(scan._included(Path("/repo/src/lib/util.py")))
        self.assertFalse(scan._included(Path("/repo/scripts/deploy.sh")))


class TestSkillSlug(unittest.TestCase):
    def test_skill_md_returns_parent_dir_as_slug(self):
        p = Path("/repo/app/skills/rate_limiting/SKILL.md")
        self.assertEqual(scan._skill_slug(p), "rate_limiting")

    def test_non_skill_stem_inside_skills_dir_returns_slug(self):
        # _skill_slug returns the dir name one level inside skills/, not just SKILL.md
        p = Path("/repo/app/skills/rate_limiting/notes.md")
        self.assertEqual(scan._skill_slug(p), "rate_limiting")

    def test_no_skills_dir_returns_none(self):
        p = Path("/repo/README.md")
        self.assertIsNone(scan._skill_slug(p))

    def test_skill_dir_at_root_returns_slug(self):
        p = Path("/repo/skills/auth/SKILL.md")
        self.assertEqual(scan._skill_slug(p), "auth")


class TestSkillRepo(unittest.TestCase):
    def test_returns_parent_of_skills_dir(self):
        p = Path("/root/cortex/app/skills/rate_limiting/SKILL.md")
        self.assertEqual(scan._skill_repo(p, Path("/root/cortex")), "app")

    def test_fallback_to_repo_root_name_when_no_skills_in_path(self):
        p = Path("/root/cortex/docs/guide.md")
        self.assertEqual(scan._skill_repo(p, Path("/root/cortex")), "cortex")


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


class TestResolveWithDirs(unittest.TestCase):
    def test_none_is_empty(self):
        self.assertEqual(hub._resolve_with_dirs(None), [])

    def test_empty_is_empty(self):
        self.assertEqual(hub._resolve_with_dirs([]), [])

    def test_all_expands_to_canonical_order(self):
        self.assertEqual(hub._resolve_with_dirs(["all"]), ["runs", "artifacts", "data"])

    def test_all_wins_over_others(self):
        self.assertEqual(
            hub._resolve_with_dirs(["all", "runs"]), ["runs", "artifacts", "data"]
        )

    def test_subset_in_canonical_order(self):
        # input order doesn't matter — output follows _TASK_SUBDIRS
        self.assertEqual(hub._resolve_with_dirs(["data", "runs"]), ["runs", "data"])

    def test_dedups(self):
        self.assertEqual(hub._resolve_with_dirs(["runs", "runs"]), ["runs"])

    def test_prompts_never_included(self):
        self.assertNotIn("prompts", hub._resolve_with_dirs(["all"]))


class TestCmdNewTask(unittest.TestCase):
    def _run(self, slug, with_dirs=None):
        import tempfile
        target = Path(tempfile.mkdtemp())
        hub._cmd_new_task(slug, target, with_dirs)
        return target / "tasks" / slug

    def test_default_creates_only_manifest(self):
        d = self._run("feat-default")
        self.assertTrue((d / "manifest.md").exists())
        for sub in ("runs", "artifacts", "data", "prompts"):
            self.assertFalse((d / sub).exists(), f"{sub} should not be created")

    def test_with_all_creates_three_subdirs(self):
        d = self._run("feat-all", ["all"])
        for sub in ("runs", "artifacts", "data"):
            self.assertTrue((d / sub).is_dir())
        self.assertFalse((d / "prompts").exists())

    def test_with_subset(self):
        d = self._run("feat-sub", ["runs"])
        self.assertTrue((d / "runs").is_dir())
        self.assertFalse((d / "artifacts").exists())
        self.assertFalse((d / "data").exists())

    def test_rerun_adds_dirs_later(self):
        import tempfile
        target = Path(tempfile.mkdtemp())
        hub._cmd_new_task("feat-late", target)            # bare task
        d = target / "tasks" / "feat-late"
        self.assertFalse((d / "data").exists())
        hub._cmd_new_task("feat-late", target, ["data"])  # add later
        self.assertTrue((d / "data").is_dir())
        # manifest untouched on the second run
        self.assertTrue((d / "manifest.md").exists())


class TestRenderTemplate(unittest.TestCase):
    """S4a — render() fills the template (incl. the task_timeline placeholder)
    with no str.format KeyError, and bakes the per-task timeline into the page."""

    def test_render_fills_all_placeholders(self):
        # No missing/extra placeholder blows up str.format(); empty groups render.
        out = hub.render({})
        self.assertIn("<!DOCTYPE html>", out)
        self.assertIn("TASK_TIMELINE_DATA", out)

    def test_task_timeline_placeholder_is_baked(self):
        payload = ('{"cortex\\tauth-refactor":'
                   '[{"id":"n1","kind":"task","path":"tasks/auth-refactor/manifest.md",'
                   '"at":"2026-07-22"}]}')
        out = hub.render({}, task_timeline_json=payload)
        self.assertIn("const TASK_TIMELINE_DATA=" + payload, out)

    def test_drawer_chrome_is_gone(self):
        # The timeline drawer (tl-tab / tl-drawer / feed-drawer) was retired; the
        # global timeline now mounts at the head of Work.
        out = hub.render({})
        for gone in ('id="tl-tab"', 'id="tl-drawer"', 'feed-drawer'):
            self.assertNotIn(gone, out)
        self.assertIn('id="tl-panel"', out)
        self.assertIn('id="hub-timeline"', out)


if __name__ == "__main__":
    unittest.main()
