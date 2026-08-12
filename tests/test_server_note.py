"""Integration tests for POST /_note — the 1e/S7 Comments producer.

Asserts the endpoint APPENDS exactly one JSON line to the task's append-only
`comments/notes.jsonl` (target/range/author/created/body), never rewrites prior
lines, and enforces the guards: bad slug, unknown task, target escaping the
task, empty body, and a read-only root → 403.
"""
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import server
from hubspace.core import db as _db


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port: int, path: str, body: bytes, timeout: float = 10.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class TestNoteEndpoint(unittest.TestCase):
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

        (Path(cls._scan_root) / "tasks" / "demo" / "artifacts").mkdir(parents=True)
        (Path(cls._scan_root) / "tasks" / "demo" / "manifest.md").write_text(
            "---\nstatus: ongoing\ntitle: Demo\n---\n# Demo\n", encoding="utf-8")
        (Path(cls._scan_root) / "tasks" / "demo" / "artifacts" / "flow.html").write_text(
            "<p>flow</p>", encoding="utf-8")

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

    def _note(self, **body):
        body.setdefault("repo", "(root)")
        body.setdefault("slug", "demo")
        return _post(self._port, "/_note", json.dumps(body).encode("utf-8"))

    @property
    def _jsonl(self) -> Path:
        return Path(self._scan_root) / "tasks" / "demo" / "comments" / "notes.jsonl"

    def _lines(self):
        if not self._jsonl.exists():
            return []
        return [ln for ln in self._jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def test_appends_one_json_line(self):
        before = len(self._lines())
        status, body = self._note(
            target="artifacts/flow.html", range="L41-L48",
            author="atharva", body="rotation window feels short please fix")
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertTrue(out["id"])
        self.assertEqual(out["rel"], self._jsonl.relative_to(Path(self._scan_root)).as_posix())
        # exactly ONE new line appended by this single POST
        lines = self._lines()
        self.assertEqual(len(lines), before + 1)
        obj = json.loads(lines[-1])
        self.assertEqual(obj["target"], "artifacts/flow.html")
        self.assertEqual(obj["range"], "L41-L48")
        self.assertEqual(obj["author"], "atharva")
        self.assertIn(date.today().isoformat(), obj["created"])
        self.assertIn("rotation window feels short", obj["body"])
        self.assertEqual(obj["id"], out["id"])

    def test_second_post_appends_leaving_prior_lines_intact(self):
        self._note(target="manifest.md", body="append-only comment one")
        first = self._jsonl.read_bytes()
        self._note(target="manifest.md", body="append-only comment two")
        after = self._jsonl.read_bytes()
        # prior line(s) are the exact prefix — nothing rewritten/reordered
        self.assertTrue(after.startswith(first))
        bodies = [json.loads(ln)["body"] for ln in self._lines()]
        self.assertIn("append-only comment one", bodies)
        self.assertIn("append-only comment two", bodies)

    def test_rejects_bad_slug(self):
        status, body = self._note(slug="../evil", target="manifest.md", body="x")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_slug")

    def test_rejects_unknown_task(self):
        status, body = self._note(slug="nope", target="manifest.md", body="x")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid task")

    def test_rejects_target_escape(self):
        for bad in ("../../escape.md", "/etc/passwd"):
            status, body = self._note(target=bad, body="x")
            self.assertEqual(status, 400, bad)
            self.assertEqual(json.loads(body)["error"], "invalid_target", bad)
        self.assertFalse((Path(self._scan_root) / "escape.md").exists())

    def test_rejects_empty_body(self):
        status, body = self._note(target="manifest.md", body="   ")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "body required")

    def test_readonly_comments_refused(self):
        ro = Path(self._scan_root) / "tasks" / "rotask"
        ro.mkdir(parents=True, exist_ok=True)
        (ro / "manifest.md").write_text("# ro\n", encoding="utf-8")
        (ro / "comments").write_text("blocker", encoding="utf-8")
        status, body = self._note(slug="rotask", target="manifest.md", body="hi")
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "write_failed")

    def test_bad_json_rejected(self):
        status, _ = _post(self._port, "/_note", b"not json")
        self.assertEqual(status, 400)


class TestNoteDeleteEndpoint(unittest.TestCase):
    """POST /_note-delete — the S30 inverse of /_note (remove one comment by id)."""

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

        (Path(cls._scan_root) / "tasks" / "demo").mkdir(parents=True)
        (Path(cls._scan_root) / "tasks" / "demo" / "manifest.md").write_text(
            "# Demo\n", encoding="utf-8")

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

    @property
    def _jsonl(self) -> Path:
        return Path(self._scan_root) / "tasks" / "demo" / "comments" / "notes.jsonl"

    def _lines(self):
        if not self._jsonl.exists():
            return []
        return [ln for ln in self._jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _add(self, body_text):
        status, body = _post(self._port, "/_note", json.dumps(
            {"repo": "(root)", "slug": "demo", "target": "manifest.md",
             "body": body_text}).encode("utf-8"))
        self.assertEqual(status, 200)
        return json.loads(body)["id"]

    def _delete(self, **body):
        body.setdefault("repo", "(root)")
        body.setdefault("slug", "demo")
        return _post(self._port, "/_note-delete", json.dumps(body).encode("utf-8"))

    def test_deletes_by_id_and_leaves_others(self):
        keep = self._add("keep this one")
        drop = self._add("remove this one")
        status, body = self._delete(id=drop)
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertTrue(out["removed"])
        bodies = [json.loads(ln)["body"] for ln in self._lines()]
        self.assertIn("keep this one", bodies)
        self.assertNotIn("remove this one", bodies)
        # the kept comment's id is unaffected
        self.assertIn(keep, [json.loads(ln)["id"] for ln in self._lines()])

    def test_unknown_id_is_idempotent(self):
        self._add("still here")
        before = len(self._lines())
        status, body = self._delete(id="deadbeef")
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertFalse(out["removed"])
        self.assertEqual(len(self._lines()), before)

    def test_rejects_bad_slug(self):
        status, body = self._delete(slug="../evil", id="x")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_slug")

    def test_rejects_unknown_task(self):
        status, body = self._delete(slug="nope", id="x")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid task")

    def test_rejects_missing_id(self):
        status, body = self._delete(id="   ")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "id required")

    def test_bad_json_rejected(self):
        status, _ = _post(self._port, "/_note-delete", b"not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
