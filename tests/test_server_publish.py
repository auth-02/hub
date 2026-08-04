"""Tests for the 1f publish endpoints — POST /_publish-scan and POST /_publish.

/_publish-scan runs the SAME core.publish scanner the CLI uses and guards the
path (must resolve inside the active scan root). /_publish prepares the local
publish (writes a sanitized copy for the redacted subset, original untouched)
and returns the dak command string — Hub never makes a network call here.
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


def _post(port: int, path: str, obj, timeout: float = 10.0):
    body = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


class TestPublishEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._port = _free_port()
        cls._scan_root = tempfile.mkdtemp()
        cls._state = tempfile.mkdtemp()
        cls._patchers = [
            patch.object(server, "_SIDECAR", Path(cls._state) / ".scan_root"),
            patch.object(server, "_DB_PATH", Path(cls._state) / "hub.db"),
            patch.object(server.config, "state_dir", lambda: Path(cls._state)),
        ]
        for p in cls._patchers:
            p.start()

        server._active_root = Path(cls._scan_root)
        server.SCAN_ROOT = Path(cls._scan_root)
        server.HubHandler.server_port = cls._port

        cls.asset = Path(cls._scan_root) / "report.md"
        cls.asset.write_text(
            "contact bob@corp.internal at 10.0.0.9\nnothing else\n", encoding="utf-8")

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
        cls._server.server_close()
        for p in cls._patchers:
            p.stop()
        import shutil
        shutil.rmtree(cls._scan_root, ignore_errors=True)
        shutil.rmtree(cls._state, ignore_errors=True)

    def test_scan_returns_findings(self):
        status, d = _post(self._port, "/_publish-scan", {"path": str(self.asset)})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        kinds = {f["kind"] for f in d["findings"]}
        self.assertIn("email", kinds)
        self.assertIn("ip", kinds)

    def test_scan_relative_path(self):
        status, d = _post(self._port, "/_publish-scan", {"path": "report.md"})
        self.assertEqual(status, 200)
        self.assertTrue(d["findings"])

    def test_scan_guards_path_escape(self):
        status, d = _post(self._port, "/_publish-scan", {"path": "/etc/passwd"})
        self.assertEqual(status, 403)
        self.assertFalse(d.get("ok", False))

    def test_scan_missing_path(self):
        status, d = _post(self._port, "/_publish-scan", {})
        self.assertEqual(status, 400)

    def test_publish_returns_dak_command_and_writes_copy(self):
        status, d = _post(self._port, "/_publish",
                          {"path": "report.md", "redact_indices": [0, 1],
                           "title": "My Report"})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertIn("dak.py", d["command"])
        self.assertIn("--title", d["command"])
        # original file is never modified
        self.assertIn("bob@corp.internal", self.asset.read_text(encoding="utf-8"))
        # a sanitized copy was written and is what dak would receive
        self.assertTrue(d["copy"])
        copy_text = Path(d["copy"]).read_text(encoding="utf-8")
        self.assertNotIn("bob@corp.internal", copy_text)

    def test_publish_private_refuses(self):
        with patch.object(server.config, "load_config", lambda *a, **k: {"private": True}):
            status, d = _post(self._port, "/_publish", {"path": "report.md"})
        self.assertEqual(status, 403)
        self.assertEqual(d.get("error"), "private")


if __name__ == "__main__":
    unittest.main()
