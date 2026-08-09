"""Integration tests for POST /_new-task — the palette's one write surface.

Asserts the endpoint writes exactly `manifest.md` (no extra dirs), signals slug
collisions, rejects path-escape slugs, and refuses a read-only root.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import server
from hubspace.core import db as _db


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port: int, path: str, body: bytes, timeout: float = 8.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class TestNewTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._port = _free_port()
        cls._scan_root = tempfile.mkdtemp()
        cls._state = tempfile.mkdtemp()
        cls._patchers = [
            patch.object(server, "_SIDECAR", Path(cls._state) / ".scan_root"),
            patch.object(server, "_DB_PATH", Path(cls._state) / "hub.db"),
            patch.object(_db, "_STATUS_SIDECAR", Path(cls._state) / "task-status.json"),
        ]
        for p in cls._patchers:
            p.start()
        cls._env = {
            "HUB_DB": str(Path(cls._state) / "hub.db"),
            "HUB_OUTPUT": str(Path(cls._state) / "docs-index.html"),
        }
        cls._env_saved = {k: os.environ.get(k) for k in cls._env}
        os.environ.update(cls._env)

        server._active_root = Path(cls._scan_root)
        server.SCAN_ROOT = Path(cls._scan_root)
        server.HubHandler.server_port = cls._port

        cls._server = server._HubServer(("::", cls._port), server.HubHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", cls._port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        for p in cls._patchers:
            p.stop()
        for k, v in cls._env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import shutil
        shutil.rmtree(cls._scan_root, ignore_errors=True)
        shutil.rmtree(cls._state, ignore_errors=True)

    def _new(self, **fields):
        return _post(self._port, "/_new-task", json.dumps(fields).encode("utf-8"))

    def test_writes_exactly_manifest(self):
        status, body = self._new(title="MCP retrieval adapter")
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertEqual(out["slug"], "mcp-retrieval-adapter")
        task_dir = Path(self._scan_root) / "tasks" / "mcp-retrieval-adapter"
        self.assertEqual([c.name for c in task_dir.iterdir()], ["manifest.md"])
        text = (task_dir / "manifest.md").read_text(encoding="utf-8")
        # S22: no frontmatter — the manifest is just the `# Title` H1.
        self.assertNotIn("---", text)
        self.assertNotIn("status:", text)
        self.assertNotIn("created:", text)
        self.assertTrue(text.startswith("# MCP retrieval adapter"))

    def test_status_round_trips_via_db_not_file(self):
        # A non-default status is persisted to the DB/sidecar, never the file.
        status, body = self._new(title="Paused task", status="paused")
        self.assertEqual(status, 200, body)
        task_repo = Path(self._scan_root).name
        text = (Path(self._scan_root) / "tasks" / "paused-task" / "manifest.md").read_text()
        self.assertNotIn("status:", text)  # not in the file
        conn = _db.open_db(Path(self._state) / "hub.db")
        statuses = json.loads(_db.get_statuses_json(conn))
        conn.close()
        self.assertEqual(statuses.get(f"{task_repo}:paused-task"), "paused")

    def test_writes_into_repo_with_plan(self):
        (Path(self._scan_root) / "cortex").mkdir(exist_ok=True)
        status, body = self._new(repo="cortex", title="Add SSO", plan=["design", "ship"])
        self.assertEqual(status, 200)
        text = (Path(self._scan_root) / "cortex" / "tasks" / "add-sso" / "manifest.md").read_text()
        self.assertIn("## Plan", text)
        self.assertIn("- [ ] design", text)
        self.assertIn("- [ ] ship", text)

    def test_collision_returns_409_with_suggestion(self):
        self._new(title="dupe task")
        status, body = self._new(title="dupe task")
        self.assertEqual(status, 409)
        out = json.loads(body)
        self.assertEqual(out["error"], "exists")
        self.assertEqual(out["suggestion"], "dupe-task-2")

    def test_path_escape_slugs_rejected(self):
        for bad in ("../evil", "a/b", "/abs", ".."):
            status, body = self._new(title="x", slug=bad)
            self.assertEqual(status, 400, bad)
            self.assertEqual(json.loads(body)["error"], "invalid_slug")
        # the manifest must never land outside tasks/
        self.assertFalse((Path(self._scan_root) / "evil").exists())

    def test_missing_title_rejected(self):
        status, body = self._new(slug="no-title")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "title required")

    def test_invalid_repo_rejected(self):
        status, body = self._new(repo="../escape", title="X")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid repo")

    def test_readonly_root_refused(self):
        # A regular file named `tasks` in a repo makes the write fail → 403.
        repo = Path(self._scan_root) / "roproj"
        repo.mkdir(exist_ok=True)
        (repo / "tasks").write_text("blocker", encoding="utf-8")
        status, body = self._new(repo="roproj", title="Blocked")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "write_failed")

    def test_invalid_json_rejected(self):
        status, _ = _post(self._port, "/_new-task", b"not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
