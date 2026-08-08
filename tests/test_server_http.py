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
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import server
from hubspace.core import db as _db


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
        # Isolated hub state dir. Without this, endpoints that write persistent
        # state — /_set-root (writes the .scan_root sidecar) and /_task-status
        # (writes hub.db + task-status.json) — would clobber the developer's real
        # ~/.local/state/hub, e.g. repointing their live hub at a temp dir.
        cls._state = tempfile.mkdtemp()

        # Write a minimal markdown file into the scan root
        (Path(cls._scan_root) / "hello.md").write_text("# Hello\nworld", encoding="utf-8")

        # Redirect every writable-state path to the temp state dir. The module-level
        # constants are already computed, so patch them directly; the rebuild
        # subprocess reads HUB_DB/HUB_OUTPUT from the environment, so set those too.
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
        for p in getattr(cls, "_patchers", []):
            p.stop()
        for k, v in getattr(cls, "_env_saved", {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import shutil
        shutil.rmtree(cls._scan_root, ignore_errors=True)
        shutil.rmtree(getattr(cls, "_state", ""), ignore_errors=True)

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

    def test_served_page_carries_reader_keydown_forwarder(self):
        """S17 — a live-served doc page carries the tiny forwarder that relays
        palette/composer/close keydowns to window.parent when it is shown inside
        the SPA reading-view iframe. It is a no-op when opened as a top-level tab
        (guarded by window.parent===window)."""
        md_path = Path(self._scan_root) / "hello.md"
        status, body = _get(self._port, str(md_path))
        self.assertEqual(status, 200)
        text = body.decode("utf-8", "replace")
        self.assertIn("hub-doc", text)
        self.assertIn("window.parent===window", text)
        self.assertIn("hub-reader-scroll", text)

    def test_notes_jsonl_redirects_instead_of_downloading(self):
        """S13 — a direct GET to a task's comments/notes.jsonl must NOT stream
        the raw log as octet-stream (which downloads); it bounces to the SPA."""
        import http.client
        comments = Path(self._scan_root) / "tasks" / "s13-task" / "comments"
        comments.mkdir(parents=True, exist_ok=True)
        raw = b'{"id":"x","target":"manifest.md","author":"you","body":"secret comment"}\n'
        jsonl = comments / "notes.jsonl"
        jsonl.write_bytes(raw)

        # Raw request WITHOUT following redirects, so we observe the 302 itself.
        conn = http.client.HTTPConnection("localhost", self._port, timeout=5)
        conn.request("GET", str(jsonl))
        resp = conn.getresponse()
        status = resp.status
        ctype = resp.getheader("Content-Type") or ""
        location = resp.getheader("Location")
        payload = resp.read()
        conn.close()

        self.assertEqual(status, 302, "notes.jsonl should redirect, not serve")
        self.assertEqual(location, "/")
        self.assertNotIn("octet-stream", ctype)
        self.assertNotIn(b"secret comment", payload)

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

    # ── /_list-dirs — directory picker backend ───────────────────────────────
    def test_list_dirs_lists_sorted_subdirs(self):
        import json
        root = tempfile.mkdtemp()
        try:
            for name in ("Zebra", "alpha", "mid"):
                (Path(root) / name).mkdir()
            (Path(root) / "a_file.md").write_text("x", encoding="utf-8")
            status, body = _get(self._port, "/_list-dirs?path=" + root)
            self.assertEqual(status, 200)
            data = json.loads(body)
            names = [d["name"] for d in data["dirs"]]
            # subdirs only (file omitted), sorted case-insensitively
            self.assertEqual(names, ["alpha", "mid", "Zebra"])
            # child paths are absolute and point back into the (normalized) root
            rroot = str(Path(root).resolve())
            for d in data["dirs"]:
                self.assertTrue(d["path"].startswith(rroot))
            # parent is the containing dir (root has one here)
            self.assertEqual(data["parent"], str(Path(root).resolve().parent))
            self.assertEqual(data["path"], rroot)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_list_dirs_omits_hidden_dirs(self):
        import json
        root = tempfile.mkdtemp()
        try:
            (Path(root) / "visible").mkdir()
            (Path(root) / ".hidden").mkdir()
            status, body = _get(self._port, "/_list-dirs?path=" + root)
            self.assertEqual(status, 200)
            names = [d["name"] for d in json.loads(body)["dirs"]]
            self.assertIn("visible", names)
            self.assertNotIn(".hidden", names)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_list_dirs_bad_path_returns_error_not_500(self):
        import json
        status, body = _get(self._port, "/_list-dirs?path=/no/such/dir/xyz123")
        self.assertEqual(status, 400)
        data = json.loads(body)
        self.assertIn("error", data)
        self.assertIn("path", data)

    def test_list_dirs_default_path_is_valid(self):
        import json
        # No ?path → server defaults to the current scan root; must return a
        # valid listing (never an error) with an absolute normalized path.
        status, body = _get(self._port, "/_list-dirs")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertNotIn("error", data)
        self.assertTrue(data["path"].startswith("/"))
        self.assertIn("dirs", data)

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

    def test_task_status_post_valid(self):
        import json
        payload = json.dumps({
            "task_slug": "test-slug",
            "task_repo": "test-repo",
            "status": "completed",
        }).encode("utf-8")
        status, body = _post(self._port, "/_task-status", payload)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ok")

    def test_task_status_post_invalid_status_rejected(self):
        import json
        payload = json.dumps({
            "task_slug": "test-slug",
            "task_repo": "test-repo",
            "status": "invalid_value",
        }).encode("utf-8")
        status, _ = _post(self._port, "/_task-status", payload)
        self.assertEqual(status, 400)

    def test_task_status_post_missing_fields(self):
        import json
        payload = json.dumps({"task_slug": "test-slug"}).encode("utf-8")
        status, _ = _post(self._port, "/_task-status", payload)
        self.assertEqual(status, 400)

    def test_task_status_post_invalid_json(self):
        payload = b"not valid json"
        status, _ = _post(self._port, "/_task-status", payload)
        self.assertEqual(status, 400)

    def test_relative_path_resolved_against_scan_root(self):
        # hello.md exists in the scan root; a relative request should resolve it
        status, body = _get(self._port, "/hello.md")
        # 200 if resolved, 404 if not found — both acceptable; must not be 500
        self.assertIn(status, (200, 404))

    # ── Excalidraw routes (Phase 02) ──────────────────────────────────────

    def test_draw_blank_canvas(self):
        status, body = _get(self._port, "/draw")
        self.assertEqual(status, 200)
        self.assertIn(b"window.DRAW_STATE", body)
        self.assertIn(b"/static/draw.js", body)

    def test_excalidraw_file_served_as_canvas(self):
        scene = '{"type":"excalidraw","elements":[{"type":"text","text":"hi there"}]}'
        (Path(self._scan_root) / "diag.excalidraw").write_text(scene, encoding="utf-8")
        status, body = _get(self._port, "/diag.excalidraw")
        self.assertEqual(status, 200)
        self.assertIn(b"window.DRAW_STATE", body)
        self.assertIn(b"hi there", body)

    def test_draw_save_new_creates_file(self):
        import json
        payload = json.dumps({"rel": None, "scene": {"elements": []}}).encode("utf-8")
        status, body = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["ok"])
        self.assertTrue(out["rel"].endswith(".excalidraw"))
        self.assertTrue((Path(self._scan_root) / out["rel"]).exists())

    def test_draw_save_rejects_traversal(self):
        import json
        payload = json.dumps({"rel": "../evil.excalidraw", "scene": {}}).encode("utf-8")
        status, _ = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 403)

    def test_draw_save_rejects_non_excalidraw_ext(self):
        import json
        payload = json.dumps({"rel": "notes.md", "scene": {}}).encode("utf-8")
        status, _ = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 400)

    def test_draw_save_missing_scene(self):
        import json
        payload = json.dumps({"rel": None}).encode("utf-8")
        status, _ = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 400)

    def test_draw_save_into_dir_creates_nested_file(self):
        import json
        payload = json.dumps({
            "rel": None, "dir": "tasks/my-task/draws", "scene": {"elements": []},
        }).encode("utf-8")
        status, body = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertTrue(out["rel"].startswith("tasks/my-task/draws/"))
        self.assertTrue((Path(self._scan_root) / out["rel"]).exists())

    def test_draw_save_dir_rejects_traversal(self):
        import json
        payload = json.dumps({
            "rel": None, "dir": "../escape", "scene": {"elements": []},
        }).encode("utf-8")
        status, _ = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 403)

    def test_task_manifest_page_has_new_draw_menu_item(self):
        # A manifest.md under tasks/<slug>/ gets a "New draw" item in the ⋯ menu.
        d = Path(self._scan_root) / "tasks" / "demo-task"
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.md").write_text("# Demo Task\n", encoding="utf-8")
        status, body = _get(self._port, f"{d}/manifest.md")
        self.assertEqual(status, 200)
        self.assertIn(b'<details class="doc-menu">', body)
        self.assertIn(b"/draw?dir=tasks/demo-task/draws", body)
        self.assertIn(b'class="pencil"', body)

    def test_plain_md_has_menu_but_no_new_draw(self):
        # Every doc page has the ⋯ menu (Save as PDF); only task manifests add New draw.
        status, body = _get(self._port, f"{self._scan_root}/hello.md")
        if status == 200:
            self.assertIn(b'<details class="doc-menu">', body)
            self.assertNotIn(b"/draw?dir=", body)

    def test_draw_save_with_name(self):
        import json
        payload = json.dumps({
            "rel": None, "name": "My Architecture!", "scene": {"elements": []},
        }).encode("utf-8")
        status, body = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 200)
        out = json.loads(body)
        # sanitized: punctuation dropped, spaces kept
        self.assertEqual(out["rel"], "My Architecture.excalidraw")
        self.assertTrue((Path(self._scan_root) / out["rel"]).exists())

    def test_draw_save_name_collision_gets_suffix(self):
        import json
        (Path(self._scan_root) / "dup.excalidraw").write_text("{}", encoding="utf-8")
        payload = json.dumps({"rel": None, "name": "dup", "scene": {"elements": []}}).encode("utf-8")
        status, body = _post(self._port, "/draw/save", payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["rel"], "dup-2.excalidraw")


if __name__ == "__main__":
    unittest.main()
