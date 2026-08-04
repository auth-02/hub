"""Tests for the 2b graph-order layout + graph→Excalidraw converter (core/graph.py)
and the `hub draw` CLI verb."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import graph
from hubspace.cli import hub as hub_cli


# A fixed node/edge set (the 2b star: a task manifest + three children).
NODES = [
    {"id": "n1", "kind": "task", "path": "tasks/t/manifest.md", "at": "2026-07-01"},
    {"id": "n2", "kind": "run", "path": "tasks/t/runs/2026-07-02/r.md", "at": "2026-07-02"},
    {"id": "n3", "kind": "artifact", "path": "tasks/t/artifacts/a.md", "at": "2026-07-03"},
    {"id": "n4", "kind": "run", "path": "tasks/t/runs/2026-07-01/early.md", "at": "2026-07-01"},
]
EDGES = [
    {"from": "n1", "to": "n2", "rel": "task_has_run", "external": False},
    {"from": "n1", "to": "n3", "rel": "task_has_artifact", "external": False},
    {"from": "n1", "to": "n4", "rel": "task_has_run", "external": False},
]


class TestLayout(unittest.TestCase):
    def test_deterministic(self):
        self.assertEqual(graph.layout(NODES), graph.layout(NODES))

    def test_task_left_of_children(self):
        pos = graph.layout(NODES, EDGES)
        self.assertLess(pos["n1"]["x"], pos["n2"]["x"])
        self.assertLess(pos["n1"]["x"], pos["n3"]["x"])

    def test_kind_columns(self):
        # runs share a column, distinct from artifacts.
        pos = graph.layout(NODES)
        self.assertEqual(pos["n2"]["x"], pos["n4"]["x"])       # both runs
        self.assertNotEqual(pos["n2"]["x"], pos["n3"]["x"])    # run vs artifact

    def test_date_order_within_column(self):
        # Within the run column, the earlier date sits above the later one.
        pos = graph.layout(NODES)
        self.assertLess(pos["n4"]["y"], pos["n2"]["y"])

    def test_every_node_placed(self):
        pos = graph.layout(NODES)
        self.assertEqual(set(pos), {"n1", "n2", "n3", "n4"})


class TestToExcalidraw(unittest.TestCase):
    def setUp(self):
        self.scene = graph.to_excalidraw(NODES, EDGES)

    def test_scene_shape(self):
        self.assertEqual(self.scene["type"], "excalidraw")
        self.assertIsInstance(self.scene["elements"], list)
        self.assertIn("appState", self.scene)
        self.assertIn("files", self.scene)

    def test_paper_ground_not_white(self):
        self.assertEqual(self.scene["appState"]["viewBackgroundColor"], graph.PAPER_BG)
        self.assertNotEqual(self.scene["appState"]["viewBackgroundColor"].lower(), "#ffffff")

    def test_each_node_a_rect_and_text(self):
        rects = [e for e in self.scene["elements"] if e["type"] == "rectangle"]
        texts = [e for e in self.scene["elements"] if e["type"] == "text"]
        self.assertEqual(len(rects), len(NODES))
        self.assertEqual(len(texts), len(NODES))

    def test_each_edge_an_arrow_bound(self):
        arrows = [e for e in self.scene["elements"] if e["type"] == "arrow"]
        self.assertEqual(len(arrows), len(EDGES))
        for a in arrows:
            self.assertIn("startBinding", a)
            self.assertIn("endBinding", a)
            self.assertTrue(a["startBinding"]["elementId"].startswith("rect-"))
            self.assertTrue(a["endBinding"]["elementId"].startswith("rect-"))

    def test_kind_coloured(self):
        rects = {e["id"]: e for e in self.scene["elements"] if e["type"] == "rectangle"}
        self.assertEqual(rects["rect-n1"]["strokeColor"], graph.KIND_COLOR["task"])

    def test_deterministic(self):
        self.assertEqual(graph.to_excalidraw(NODES, EDGES),
                         graph.to_excalidraw(NODES, EDGES))

    def test_json_serialisable(self):
        import json
        json.dumps(self.scene)  # must not raise

    def test_uses_supplied_positions(self):
        pos = {"n1": {"x": 5, "y": 6}}
        scene = graph.to_excalidraw([NODES[0]], [], positions=pos)
        rect = [e for e in scene["elements"] if e["type"] == "rectangle"][0]
        self.assertEqual((rect["x"], rect["y"]), (5, 6))


class TestBlankScene(unittest.TestCase):
    def test_blank(self):
        s = graph.blank_scene()
        self.assertEqual(s["type"], "excalidraw")
        self.assertEqual(s["elements"], [])
        self.assertEqual(s["appState"]["viewBackgroundColor"], graph.PAPER_BG)


class TestDrawVerb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def _run(self, name=None, task=None, repo=None):
        buf = io.StringIO()
        with patch.object(hub_cli, "ROOT", self.root), redirect_stdout(buf):
            hub_cli._cmd_draw(name, task, repo)
        return buf.getvalue()

    def test_top_level_draw(self):
        self._run(name="sketch")
        self.assertTrue((self.root / "sketch.excalidraw").exists())

    def test_task_draw_lands_in_draws(self):
        (self.root / "tasks" / "t").mkdir(parents=True)
        (self.root / "tasks" / "t" / "manifest.md").write_text("# t\n")
        self._run(name="timeline", task="t")
        target = self.root / "tasks" / "t" / "draws" / "timeline.excalidraw"
        self.assertTrue(target.exists())
        import json
        self.assertEqual(json.loads(target.read_text())["type"], "excalidraw")

    def test_collision_suffixes(self):
        self._run(name="d")
        self._run(name="d")
        self.assertTrue((self.root / "d.excalidraw").exists())
        self.assertTrue((self.root / "d-2.excalidraw").exists())

    def test_bad_task_slug_exits(self):
        with self.assertRaises(SystemExit):
            self._run(name="x", task="Bad Slug")

    def test_not_a_task_exits(self):
        (self.root / "tasks" / "real").mkdir(parents=True)
        (self.root / "tasks" / "real" / "manifest.md").write_text("# r\n")
        with self.assertRaises(SystemExit):
            self._run(name="x", task="ghost")  # no manifest → not a task

    def test_bad_repo_exits(self):
        with self.assertRaises(SystemExit):
            self._run(name="x", repo="../evil")


if __name__ == "__main__":
    unittest.main()
