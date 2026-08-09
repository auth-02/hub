"""Tests for the 1d Add-data feature — POST /_upload and the pure writer.

Covers the HTTP endpoint (writes into tasks/<slug>/data/, name preservation,
collision → -2, and the three server-side guards) plus direct unit tests of the
`tasks.accept_upload` / `tasks.safe_basename` helpers so the guard logic is
exercised without HTTP.
"""
import base64
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
from hubspace.core import tasks as _tasks


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


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# ── unit tests: the pure writer/guard helper (no HTTP) ──────────────────────

class TestAcceptUpload(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.data_dir = Path(self._dir) / "tasks" / "t" / "data"
        self.allowed = {".pdf", ".csv", ".txt"}

    def tearDown(self):
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_accepts_and_preserves_name(self):
        path, reason = _tasks.accept_upload(self.data_dir, "report.pdf", b"PDF", self.allowed)
        self.assertIsNone(reason)
        self.assertEqual(path.name, "report.pdf")
        self.assertEqual(path.read_bytes(), b"PDF")
        self.assertEqual(path.parent, self.data_dir)

    def test_collision_suffixes_dash2(self):
        _tasks.accept_upload(self.data_dir, "a.csv", b"1", self.allowed)
        p2, _ = _tasks.accept_upload(self.data_dir, "a.csv", b"2", self.allowed)
        p3, _ = _tasks.accept_upload(self.data_dir, "a.csv", b"3", self.allowed)
        self.assertEqual(p2.name, "a-2.csv")
        self.assertEqual(p3.name, "a-3.csv")
        self.assertEqual(p2.read_bytes(), b"2")

    def test_rejects_over_size(self):
        path, reason = _tasks.accept_upload(
            self.data_dir, "big.pdf", b"x" * 11, self.allowed, max_bytes=10)
        self.assertIsNone(path)
        self.assertEqual(reason, "over the 64 MB guard")
        self.assertFalse(self.data_dir.exists() and any(self.data_dir.iterdir()))

    def test_rejects_disallowed_ext(self):
        path, reason = _tasks.accept_upload(self.data_dir, "evil.exe", b"x", self.allowed)
        self.assertIsNone(path)
        self.assertIn("not in the allowlist", reason)

    def test_rejects_unsafe_names(self):
        for bad in ("../../etc/passwd", "a/b.pdf", "/abs.pdf", "..", ".", "sub\\x.pdf", ""):
            path, reason = _tasks.accept_upload(self.data_dir, bad, b"x", self.allowed)
            self.assertIsNone(path, bad)
            self.assertEqual(reason, "unsafe filename", bad)

    def test_safe_basename(self):
        self.assertEqual(_tasks.safe_basename("report.pdf"), "report.pdf")
        for bad in ("../x", "a/b", "/x", "\\x", "..", ".", "", "a\x00b"):
            self.assertIsNone(_tasks.safe_basename(bad), bad)


# ── integration tests: POST /_upload ────────────────────────────────────────

class TestUploadEndpoint(unittest.TestCase):
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

        # A pre-existing task the uploads attach to.
        (Path(cls._scan_root) / "tasks" / "demo").mkdir(parents=True)
        (Path(cls._scan_root) / "tasks" / "demo" / "manifest.md").write_text(
            "---\nstatus: ongoing\ntitle: Demo\n---\n# Demo\n", encoding="utf-8")

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

    def _upload(self, repo="(root)", slug="demo", files=None):
        body = json.dumps({"repo": repo, "slug": slug, "files": files or []})
        return _post(self._port, "/_upload", body.encode("utf-8"))

    @property
    def _data_dir(self) -> Path:
        return Path(self._scan_root) / "tasks" / "demo" / "data"

    def test_writes_accepted_file(self):
        status, body = self._upload(files=[{"name": "notes.txt", "dataBase64": _b64(b"hello data")}])
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertEqual(out["written"], 1)
        f = self._data_dir / "notes.txt"
        self.assertTrue(f.exists())
        self.assertEqual(f.read_bytes(), b"hello data")

    def test_name_collision_suffixes(self):
        self._upload(files=[{"name": "dup.csv", "dataBase64": _b64(b"a")}])
        self._upload(files=[{"name": "dup.csv", "dataBase64": _b64(b"b")}])
        self.assertTrue((self._data_dir / "dup.csv").exists())
        self.assertTrue((self._data_dir / "dup-2.csv").exists())
        self.assertEqual((self._data_dir / "dup-2.csv").read_bytes(), b"b")

    def test_rejects_over_64mb(self):
        # Just over 64 MB — rejected server-side, nothing written.
        big = b"x" * (64 * 1024 * 1024 + 1)
        status, body = self._upload(files=[{"name": "big.pdf", "dataBase64": _b64(big)}])
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertEqual(out["written"], 0)
        self.assertFalse((self._data_dir / "big.pdf").exists())
        self.assertEqual(out["results"][0]["reason"], "over the 64 MB guard")

    def test_rejects_disallowed_ext(self):
        status, body = self._upload(files=[{"name": "evil.exe", "dataBase64": _b64(b"x")}])
        out = json.loads(body)
        self.assertEqual(out["written"], 0)
        self.assertFalse((self._data_dir / "evil.exe").exists())
        self.assertIn("not in the allowlist", out["results"][0]["reason"])

    def test_rejects_path_escape_filename(self):
        for bad in ("../../escape.txt", "a/b.txt", "/tmp/abs.txt"):
            status, body = self._upload(files=[{"name": bad, "dataBase64": _b64(b"x")}])
            out = json.loads(body)
            self.assertEqual(out["written"], 0, bad)
            self.assertEqual(out["results"][0]["reason"], "unsafe filename", bad)
        # Nothing escaped the task's data/ dir.
        self.assertFalse((Path(self._scan_root) / "escape.txt").exists())
        self.assertFalse((Path(self._scan_root).parent / "escape.txt").exists())

    def test_rejects_invalid_slug(self):
        status, body = self._upload(slug="../evil", files=[{"name": "x.txt", "dataBase64": _b64(b"x")}])
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_slug")

    def test_rejects_unknown_task(self):
        status, body = self._upload(slug="does-not-exist",
                                    files=[{"name": "x.txt", "dataBase64": _b64(b"x")}])
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid task")

    def test_rejects_invalid_repo(self):
        status, body = self._upload(repo="../escape", slug="demo",
                                    files=[{"name": "x.txt", "dataBase64": _b64(b"x")}])
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid repo")

    def test_readonly_data_dir_refused(self):
        # A regular file named `data` in a task blocks mkdir → 403.
        ro = Path(self._scan_root) / "tasks" / "rotask"
        ro.mkdir(parents=True, exist_ok=True)
        (ro / "manifest.md").write_text("# ro\n", encoding="utf-8")
        (ro / "data").write_text("blocker", encoding="utf-8")
        status, body = self._upload(slug="rotask",
                                    files=[{"name": "x.txt", "dataBase64": _b64(b"x")}])
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["error"], "write_failed")

    def test_bad_json_rejected(self):
        status, _ = _post(self._port, "/_upload", b"not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
