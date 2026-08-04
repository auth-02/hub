"""Integration tests for POST /_manifest-edit — the 1i inline-editing producer.

Asserts the endpoint rewrites ONLY the manifest's frontmatter `status:` line and
`## Plan` block (prose/decisions preserved), enforces the guards (bad slug /
unknown task), and — critically — honours the conflict rule: a stale base_mtime
is rejected with 409 and the file is left UNCHANGED (hub never wins a race
against your editor). Also checks a read-only manifest → 403.
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


def _post(port: int, path: str, body: bytes, timeout: float = 10.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


_MANIFEST = (
    "---\n"
    "status: ongoing\n"
    "title: Demo\n"
    "created: 2026-08-04\n"
    "---\n"
    "\n"
    "# Demo\n"
    "\n"
    "Prose that must survive byte-for-byte.\n"
    "\n"
    "## Plan\n"
    "- [ ] first thing\n"
    "- [ ] second thing\n"
    "\n"
    "## Decisions\n"
    "1. Keep it narrow.\n"
)


class TestManifestEditEndpoint(unittest.TestCase):
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

    def _manifest(self, slug: str = "demo") -> Path:
        return Path(self._scan_root) / "tasks" / slug / "manifest.md"

    def _seed(self, slug: str = "demo", text: str = _MANIFEST) -> Path:
        p = self._manifest(slug)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def _edit(self, **body):
        body.setdefault("repo", "(root)")
        body.setdefault("slug", "demo")
        return _post(self._port, "/_manifest-edit", json.dumps(body).encode("utf-8"))

    def test_edit_status_and_plan_rewrites_file(self):
        p = self._seed()
        base = p.stat().st_mtime
        status, body = self._edit(
            status="completed", base_mtime=base,
            plan=[{"text": "first thing", "done": True},
                  {"text": "second thing", "done": False},
                  {"text": "third thing", "done": False}],
        )
        self.assertEqual(status, 200, body)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        text = p.read_text(encoding="utf-8")
        self.assertIn("status: completed\n", text)
        self.assertIn("- [x] first thing\n- [ ] second thing\n- [ ] third thing\n", text)
        # Prose + decisions preserved byte-for-byte.
        self.assertIn("Prose that must survive byte-for-byte.", text)
        self.assertIn("## Decisions\n1. Keep it narrow.\n", text)

    def test_stale_mtime_conflict_leaves_file_unchanged(self):
        p = self._seed()
        before = p.read_text(encoding="utf-8")
        stale = p.stat().st_mtime - 500  # pretend the client read an older version
        status, body = self._edit(status="paused", base_mtime=stale)
        self.assertEqual(status, 409, body)
        out = json.loads(body)
        self.assertEqual(out["error"], "conflict")
        # File must be untouched — hub never wins the race.
        self.assertEqual(p.read_text(encoding="utf-8"), before)

    def test_rejects_bad_slug(self):
        status, body = self._edit(slug="../evil", status="paused")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_slug")

    def test_rejects_unknown_task(self):
        status, body = self._edit(slug="nope", status="paused")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid task")

    def test_rejects_invalid_status(self):
        self._seed()
        status, body = self._edit(status="bogus")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "invalid_status")

    def test_no_base_mtime_still_writes(self):
        # base_mtime is optional; without it we do not conflict-check.
        p = self._seed(slug="nobase")
        status, body = self._edit(slug="nobase", status="paused")
        self.assertEqual(status, 200, body)
        self.assertIn("status: paused\n", p.read_text(encoding="utf-8"))

    def test_readonly_manifest_refused(self):
        p = self._seed(slug="rotask")
        os.chmod(p, 0o444)
        os.chmod(p.parent, 0o555)
        try:
            status, body = self._edit(slug="rotask", status="paused",
                                      plan=[{"text": "x", "done": True}])
            self.assertEqual(status, 403, body)
            self.assertEqual(json.loads(body)["error"], "write_failed")
        finally:
            os.chmod(p.parent, 0o755)
            os.chmod(p, 0o644)

    def test_bad_json_rejected(self):
        status, _ = _post(self._port, "/_manifest-edit", b"not json")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
