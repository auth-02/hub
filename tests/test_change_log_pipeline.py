"""S32 draw→save→HTML pipeline: the change-log is edited as a draw, and Saving
it (when it lives under `change-log/`) renders the interactive HTML sibling.

Covers the round-trip (to_scene embeds the model in customData; scene_to_graph
rebuilds it, edited labels + positions winning) and the server `/draw/save`
hook that renders the HTML, plus the standalone-serve bypass.
"""
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import changelog, changemap
from hubspace.cli import server
from hubspace.core import db as _db

_NODES = [
    {"id": "ep", "kind": "task", "title": "Delete a comment", "verb": "new",
     "summary": "Remove one comment by id.",
     "files": [{"path": "hubspace/cli/server.py", "change": "+handler"}],
     "functions": [{"symbol": "_note_delete()", "note": "guards"}],
     "tests": ["TestNoteDeleteEndpoint"], "note": "mirrors /_note"},
    {"id": "st", "kind": "script", "title": "Notes store", "verb": "new",
     "summary": "byte-preserving removal",
     "files": [{"path": "hubspace/core/tasks.py", "change": "+delete_note"}],
     "functions": [{"symbol": "delete_note()", "note": "idempotent"}],
     "tests": ["TestDeleteNote"], "note": ""},
]
_EDGES = [{"from": "ep", "to": "st", "rel": "calls"}]
_META = {"generated_by": "claude ▸ skill:change-log",
         "commit_range": "abc..def", "slug": "demo"}


def _scene():
    return changelog.to_scene(_NODES, _EDGES, title="CL — delete", subtitle="2 changes",
                              meta=_META, interactive_href="/tasks/demo/change-log/map.html")


class TestSceneRoundTrip(unittest.TestCase):
    def test_customData_roles_embedded(self):
        scene = _scene()
        roles = {(e.get("customData") or {}).get("cl", {}).get("role")
                 for e in scene["elements"]}
        self.assertTrue({"node", "edge", "title", "meta"} <= roles)

    def test_link_pill_points_at_html(self):
        links = [e.get("link") for e in _scene()["elements"] if e.get("link")]
        self.assertIn("/tasks/demo/change-log/map.html", links)

    def test_scene_to_graph_recovers_everything(self):
        g = changelog.scene_to_graph(_scene())
        self.assertEqual([n["title"] for n in g["nodes"]], ["Delete a comment", "Notes store"])
        self.assertEqual(g["edges"], [{"from": "ep", "to": "st", "rel": "calls"}])
        self.assertEqual(g["meta"].get("slug"), "demo")
        self.assertEqual(set(g["positions"]), {"ep", "st"})
        ep = next(n for n in g["nodes"] if n["id"] == "ep")
        self.assertEqual(ep["functions"], [{"symbol": "_note_delete()", "note": "guards"}])

    def test_edited_card_label_wins(self):
        scene = _scene()
        for el in scene["elements"]:
            cl = (el.get("customData") or {}).get("cl", {})
            if cl.get("role") == "title" and cl.get("id") == "ep":
                el["text"] = "Delete a comment (edited)"
        g = changelog.scene_to_graph(scene)
        self.assertEqual(next(n for n in g["nodes"] if n["id"] == "ep")["title"],
                         "Delete a comment (edited)")

    def test_untagged_elements_ignored(self):
        scene = _scene()
        scene["elements"].append({"id": "doodle", "type": "rectangle", "x": 0, "y": 0})
        g = changelog.scene_to_graph(scene)
        self.assertEqual(len(g["nodes"]), 2)  # the free-hand shape is not a node

    def test_render_uses_supplied_positions(self):
        g = changelog.scene_to_graph(_scene())
        html = changemap.render_html(g["meta"], g["nodes"], g["edges"],
                                     positions=g["positions"])
        self.assertIn("_note_delete()", html)
        self.assertIn('name="hub:standalone"', html)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port, path, body):
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://localhost:{port}{path}", timeout=10) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


class TestSaveHookRendersHtml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        cls._port = _free_port()
        cls._root = tempfile.mkdtemp()
        cls._state = tempfile.mkdtemp()
        cls._patchers = [
            patch.object(server, "_SIDECAR", Path(cls._state) / ".scan_root"),
            patch.object(server, "_DB_PATH", Path(cls._state) / "hub.db"),
            patch.object(_db, "_STATUS_SIDECAR", Path(cls._state) / "task-status.json"),
        ]
        for p in cls._patchers:
            p.start()
        cls._env = {"HUB_DB": str(Path(cls._state) / "hub.db"),
                    "HUB_OUTPUT": str(Path(cls._state) / "docs-index.html")}
        cls._env_saved = {k: os.environ.get(k) for k in cls._env}
        os.environ.update(cls._env)
        # Save globals we mutate so later test modules aren't polluted.
        cls._saved_globals = (server._active_root, server.SCAN_ROOT,
                              server.HubHandler.server_port)
        server._active_root = Path(cls._root)
        server.SCAN_ROOT = Path(cls._root)
        server.HubHandler.server_port = cls._port
        (Path(cls._root) / "tasks" / "demo" / "change-log").mkdir(parents=True)
        (Path(cls._root) / "tasks" / "demo" / "manifest.md").write_text("# Demo\n", encoding="utf-8")
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
        server._active_root, server.SCAN_ROOT, server.HubHandler.server_port = cls._saved_globals
        import shutil
        shutil.rmtree(cls._root, ignore_errors=True)
        shutil.rmtree(cls._state, ignore_errors=True)

    def _save(self, rel, scene):
        return _post(self._port, "/draw/save",
                     json.dumps({"rel": rel, "scene": scene}).encode())

    def test_change_log_save_renders_html_sibling(self):
        status, body = self._save("tasks/demo/change-log/map.excalidraw", _scene())
        self.assertEqual(status, 200)
        out = json.loads(body)
        self.assertEqual(out["change_log_html"], "tasks/demo/change-log/map.html")
        html_path = Path(self._root) / "tasks" / "demo" / "change-log" / "map.html"
        self.assertTrue(html_path.is_file())
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("_note_delete()", html)          # deep-dive baked
        self.assertIn('name="hub:standalone"', html)    # opts out of doc chrome
        # View-first: the HTML carries an Edit button pointing at the draw canvas.
        self.assertIn('class="editbtn"', html)
        self.assertIn('href="/tasks/demo/change-log/map.excalidraw"', html)

    def test_served_html_is_not_wrapped_in_doc_chrome(self):
        self._save("tasks/demo/change-log/map.excalidraw", _scene())
        status, html, headers = _get(self._port, "/tasks/demo/change-log/map.html")
        self.assertEqual(status, 200)
        # Hub's doc-page injections must be absent (they'd collide with the app).
        self.assertNotIn("doc-menu", html)
        self.assertNotIn("backlinks", html)
        self.assertNotIn("DOC_PAGE", html)
        # …and it's served no-cache so a refresh always shows the fresh render.
        self.assertIn("no-store", headers.get("Cache-Control", ""))

    def test_plain_draw_outside_change_log_gets_no_html(self):
        (Path(self._root) / "tasks" / "demo" / "draws").mkdir(exist_ok=True)
        status, body = self._save("tasks/demo/draws/plain.excalidraw", _scene())
        self.assertEqual(status, 200)
        self.assertNotIn("change_log_html", json.loads(body))
        self.assertFalse((Path(self._root) / "tasks" / "demo" / "draws" / "plain.html").exists())

    def test_change_log_draw_without_model_skips_render(self):
        blank = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}}
        status, body = self._save("tasks/demo/change-log/blank.excalidraw", blank)
        self.assertEqual(status, 200)
        self.assertNotIn("change_log_html", json.loads(body))


if __name__ == "__main__":
    unittest.main()
