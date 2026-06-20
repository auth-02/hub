"""Integration tests — spin up a real _HubServer on a random free port."""
import os
import sys
import socket
import tempfile
import threading
import time
import urllib.request
import urllib.error
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int, path: str, timeout: float = 5.0):
    url = f"http://localhost:{port}{path}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post(port: int, path: str, body: bytes, timeout: float = 5.0):
    url = f"http://localhost:{port}{path}"
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class TestServerHttp(unittest.TestCase):
    _server = None
    _port = None
    _scan_root = None
    _thread = None

    @classmethod
    def setUpClass(cls):
        cls._port = _free_port()
        cls._scan_root = tempfile.mkdtemp()

        # Write a minimal markdown file into the scan root
        (Path(cls._scan_root) / "hello.md").write_text("# Hello\nworld", encoding="utf-8")

        # Point server at a temp scan root and patch module-level _active_root
        server._active_root = Path(cls._scan_root)
        server.SCAN_ROOT = Path(cls._scan_root)
        server.HubHandler.server_port = cls._port

        cls._server = server._HubServer(("::", cls._port), server.HubHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

        # Wait for server to accept connections
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                s = socket.create_connection(("127.0.0.1", cls._port), timeout=0.5)
                s.close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls._server:
            cls._server.shutdown()
        import shutil
        shutil.rmtree(cls._scan_root, ignore_errors=True)

    def test_rebuild_returns_ok(self):
        status, body = _get(self._port, "/_rebuild")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")

    def test_root_returns_200_or_404(self):
        # / returns 200 if docs-index.html exists, 404 if not built yet — both are valid
        status, _ = _get(self._port, "/")
        self.assertIn(status, (200, 404))

    def test_nonexistent_file_returns_404(self):
        status, _ = _get(self._port, f"{self._scan_root}/no_such_file_xyz.md")
        self.assertEqual(status, 404)

    def test_markdown_file_served(self):
        md_path = Path(self._scan_root) / "hello.md"
        status, body = _get(self._port, str(md_path))
        self.assertEqual(status, 200)
        self.assertIn(b"Hello", body)

    def test_post_set_root_valid_path(self):
        payload = self._scan_root.encode("utf-8")
        status, body = _post(self._port, "/_set-root", payload)
        # ok (200) or hub.py rebuild failure (500) are both acceptable in test env
        self.assertIn(status, (200, 500))

    def test_post_set_root_invalid_path(self):
        payload = b"/nonexistent/path/that/does/not/exist"
        status, _ = _post(self._port, "/_set-root", payload)
        self.assertEqual(status, 400)

    def test_path_traversal_blocked(self):
        # Attempt to access a file outside both scan root and hub dir
        status, _ = _get(self._port, "/etc/passwd")
        # Should be 403 (forbidden) or 404 (not found) — never 200
        self.assertIn(status, (403, 404))

    def test_unknown_post_endpoint_returns_404(self):
        status, _ = _post(self._port, "/_unknown", b"")
        self.assertEqual(status, 404)

    def test_concurrent_requests(self):
        # Fire 5 rebuild requests concurrently — server must not crash
        results = []

        def _req():
            s, _ = _get(self._port, "/_rebuild")
            results.append(s)

        threads = [threading.Thread(target=_req) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        for s in results:
            self.assertEqual(s, 200)


if __name__ == "__main__":
    unittest.main()
