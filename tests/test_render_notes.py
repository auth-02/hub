"""S12 — the // NOTES section: notes_json is baked into the rendered page.

Comments are stored in an append-only JSONL per task; S12 bakes them into the
page as NOTES_DATA so the Trace overlay can render author/time/body cards. These
tests build a real index (via `python3 -m hubspace.cli.hub`) over a temp scan
root and assert the produced HTML carries the comment bodies — and that a task
with no comments still builds cleanly.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_index(scan_root: Path, state: Path) -> str:
    """Run a full index build over `scan_root`; return the produced HTML."""
    out = state / "docs-index.html"
    env = dict(os.environ)
    env.update({
        "HUB_SCAN_ROOT": str(scan_root),
        "HUB_OUTPUT": str(out),
        "HUB_DB": str(state / "hub.db"),
        "HUB_SERVER_PORT": "8787",
        # Ensure the subprocess can import the package from a source checkout.
        "PYTHONPATH": str(_REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", ""),
    })
    # No hub.toml in the temp root, so config falls back to env — a clean build.
    proc = subprocess.run(
        [sys.executable, "-m", "hubspace.cli.hub"],
        cwd=str(scan_root), env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"build failed:\n{proc.stdout}\n{proc.stderr}"
    return out.read_text(encoding="utf-8")


def _write_task(scan_root: Path, slug: str, *, notes: list[dict] | None) -> None:
    task = scan_root / "tasks" / slug
    task.mkdir(parents=True, exist_ok=True)
    (task / "manifest.md").write_text(
        f"---\nstatus: ongoing\ntitle: {slug}\n---\n\n# {slug}\n", encoding="utf-8")
    if notes is not None:
        (task / "comments").mkdir(parents=True, exist_ok=True)
        lines = "\n".join(json.dumps(n) for n in notes) + "\n"
        (task / "comments" / "notes.jsonl").write_text(lines, encoding="utf-8")


class TestNotesBaked(unittest.TestCase):
    def _extract_notes_data(self, html: str) -> dict:
        """Pull the NOTES_DATA={...}; JS global out of the built page."""
        marker = "const NOTES_DATA="
        i = html.index(marker) + len(marker)
        j = html.index(";", i)
        return json.loads(html[i:j])

    def test_comment_body_appears_in_notes_data(self):
        with tempfile.TemporaryDirectory() as sr, tempfile.TemporaryDirectory() as st:
            scan_root, state = Path(sr), Path(st)
            body = "the rotation window feels a little short here"
            _write_task(scan_root, "add-sso-login", notes=[
                {"id": "abc123", "target": "manifest.md", "author": "you",
                 "created": "2026-08-04T10:00:00", "body": body},
                {"id": "def456", "target": "artifacts/flow.html", "range": "L41-L48",
                 "author": "claude-agent", "created": "2026-08-04T11:00:00",
                 "body": "anchored note on the flow diagram"},
            ])
            html = _build_index(scan_root, state)

            self.assertIn("const NOTES_DATA=", html)
            data = self._extract_notes_data(html)
            # Key is "<repo>\t<slug>" (repo == scan-root dir name here). We wrote
            # exactly one task, so there is exactly one entry, ending in the slug.
            self.assertEqual(len(data), 1, data)
            (real_key, comments), = data.items()
            self.assertTrue(real_key.endswith("\tadd-sso-login"), real_key)
            self.assertEqual(len(comments), 2)
            bodies = [c["body"] for c in comments]
            self.assertIn(body, bodies)
            anchored = next(c for c in comments if c["target"] == "artifacts/flow.html")
            self.assertEqual(anchored["range"], "L41-L48")
            self.assertEqual(anchored["author"], "claude-agent")

    def test_task_without_notes_builds_and_is_omitted(self):
        with tempfile.TemporaryDirectory() as sr, tempfile.TemporaryDirectory() as st:
            scan_root, state = Path(sr), Path(st)
            _write_task(scan_root, "no-comments-task", notes=None)
            html = _build_index(scan_root, state)  # must not raise / must build
            self.assertIn("const NOTES_DATA=", html)
            data = self._extract_notes_data(html)
            self.assertEqual(data, {})  # a task with no comments is omitted


if __name__ == "__main__":
    unittest.main()
