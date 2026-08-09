"""Integration tests for GET /_doc-raw + POST /_edit-doc — the S18 general editor.

The reading view lets a user edit ANY hub text document inline and save to disk.
Unlike /_manifest-edit (surgical status/plan edit), this is a whole-file replace
for markdown/text docs. These tests assert the write happens, the S3c conflict
rule holds (stale base_mtime → 409, file untouched), and — critically — that no
write ever escapes the scan root or lands on an internal / HTML file.
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
import urllib.parse
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


def _post(port: int, path: str, body: bytes, timeout: float = 10.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(port: int, path: str, timeout: float = 10.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class TestEditDocEndpoint(unittest.TestCase):
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

    def _seed(self, rel: str, text: str) -> Path:
        p = Path(self._scan_root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def _edit(self, **body):
        return _post(self._port, "/_edit-doc", json.dumps(body).encode("utf-8"))

    # ── happy path ───────────────────────────────────────────────────────────
    def test_edit_md_writes_new_content_and_returns_mtime(self):
        p = self._seed("notes/hello.md", "# Old\n\nold body\n")
        base = p.stat().st_mtime
        status, body = self._edit(
            path="notes/hello.md", content="# New\n\nfresh body\n", base_mtime=base)
        self.assertEqual(status, 200, body)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertEqual(p.read_bytes(), b"# New\n\nfresh body\n")
        # A fresh mtime is returned so the client can update its base.
        self.assertIn("mtime", out)
        self.assertEqual(out["rel"], "notes/hello.md")

    def test_edit_script_ext_allowed(self):
        p = self._seed("tasks/t1/probe.py", "print(1)\n")
        base = p.stat().st_mtime
        status, body = self._edit(path="tasks/t1/probe.py",
                                  content="print(2)\n", base_mtime=base)
        self.assertEqual(status, 200, body)
        self.assertEqual(p.read_text(), "print(2)\n")

    def test_absolute_path_accepted(self):
        p = self._seed("abs.md", "a\n")
        status, body = self._edit(path=str(p), content="b\n", base_mtime=p.stat().st_mtime)
        self.assertEqual(status, 200, body)
        self.assertEqual(p.read_text(), "b\n")

    # ── conflict rule (hub never wins a race against your editor) ─────────────
    def test_stale_mtime_conflict_leaves_file_unchanged(self):
        p = self._seed("race.md", "keep me\n")
        before = p.read_bytes()
        stale = p.stat().st_mtime - 500
        status, body = self._edit(path="race.md", content="clobbered\n", base_mtime=stale)
        self.assertEqual(status, 409, body)
        self.assertEqual(json.loads(body)["error"], "conflict")
        self.assertEqual(p.read_bytes(), before)  # untouched

    def test_no_base_mtime_still_writes(self):
        p = self._seed("nobase.md", "x\n")
        status, body = self._edit(path="nobase.md", content="y\n")
        self.assertEqual(status, 200, body)
        self.assertEqual(p.read_text(), "y\n")

    # ── rejections: never write outside the scan root or to internal/HTML ─────
    def test_rejects_html(self):
        self._seed("page.html", "<h1>hi</h1>\n")
        status, body = self._edit(path="page.html", content="<h1>x</h1>", base_mtime=None)
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["error"], "html_unsupported")

    def test_rejects_path_escaping_scan_root(self):
        # A ../ path must never resolve outside the active scan root.
        outside = Path(self._scan_root).parent / "escape.md"
        outside.write_text("secret\n", encoding="utf-8")
        try:
            status, body = self._edit(path="../escape.md", content="pwned\n")
            self.assertEqual(status, 403, body)
            self.assertEqual(json.loads(body)["error"], "forbidden")
            self.assertEqual(outside.read_text(), "secret\n")  # untouched
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_internal_comments_log(self):
        self._seed("tasks/t1/comments/notes.jsonl", '{"id":"a"}\n')
        status, body = self._edit(path="tasks/t1/comments/notes.jsonl",
                                  content="tampered\n")
        self.assertEqual(status, 400, body)
        self.assertIn(json.loads(body)["error"], ("internal", "unsupported"))

    def test_rejects_nonexistent_file(self):
        status, body = self._edit(path="ghost.md", content="x\n")
        self.assertEqual(status, 404, body)

    def test_readonly_file_refused(self):
        p = self._seed("ro/locked.md", "locked\n")
        base = p.stat().st_mtime
        os.chmod(p, 0o444)
        os.chmod(p.parent, 0o555)
        try:
            status, body = self._edit(path="ro/locked.md", content="new\n", base_mtime=base)
            self.assertEqual(status, 403, body)
            self.assertEqual(json.loads(body)["error"], "write_failed")
        finally:
            os.chmod(p.parent, 0o755)
            os.chmod(p, 0o644)

    def test_bad_json_rejected(self):
        status, _ = _post(self._port, "/_edit-doc", b"not json")
        self.assertEqual(status, 400)

    def test_missing_content_rejected(self):
        self._seed("needc.md", "a\n")
        status, body = self._edit(path="needc.md")
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["error"], "content required")

    # ── GET /_doc-raw ──────────────────────────────────────────────────────
    def test_doc_raw_returns_text_and_mtime_header(self):
        p = self._seed("raw/read.md", "# raw\n\nsource\n")
        status, body, headers = _get(
            self._port, "/_doc-raw?path=" + urllib.parse.quote("raw/read.md"))
        self.assertEqual(status, 200, body)
        self.assertEqual(body.decode("utf-8"), "# raw\n\nsource\n")
        self.assertIn("X-Doc-Mtime", headers)

    def test_doc_raw_containment_guarded(self):
        outside = Path(self._scan_root).parent / "raw-escape.md"
        outside.write_text("secret\n", encoding="utf-8")
        try:
            status, body, _ = _get(
                self._port, "/_doc-raw?path=" + urllib.parse.quote("../raw-escape.md"))
            self.assertEqual(status, 403, body)
        finally:
            outside.unlink(missing_ok=True)

    def test_doc_raw_rejects_html(self):
        self._seed("raw/page.html", "<h1>x</h1>\n")
        status, body, _ = _get(
            self._port, "/_doc-raw?path=" + urllib.parse.quote("raw/page.html"))
        self.assertEqual(status, 400, body)


if __name__ == "__main__":
    unittest.main()
