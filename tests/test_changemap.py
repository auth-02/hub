"""hubspace.core.changemap — the interactive HTML change-map (S32).

The change-log skill's primary deliverable: a self-contained, offline page whose
nodes are *functional changes* (not files) and where clicking a node deep-dives
into its file / function / test detail. These tests pin: self-containment (no
external hosts), the change-oriented content, the baked deep-dive payload +
inspector, provenance front matter, no grid, and determinism.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import changemap

_META = {
    "title": "Change-log — delete a comment", "slug": "hub-evolution",
    "subtitle": "abc..def · 2 changes",
    "generated_by": "claude ▸ skill:change-log",
    "commit_range": "abc..def", "written_at": "2026-08-11T10:00:00",
}
_NODES = [
    {"id": "endpoint", "kind": "task", "title": "Delete-comment endpoint",
     "verb": "new", "summary": "Remove one comment by id.",
     "files": [{"path": "hubspace/cli/server.py", "change": "+handler"}],
     "functions": [{"symbol": "_note_delete()", "note": "guards + rebuild"}],
     "tests": ["TestNoteDeleteEndpoint"], "note": "mirrors /_note"},
    {"id": "store", "kind": "script", "title": "Notes store",
     "verb": "new", "summary": "Byte-preserving line removal.",
     "files": [{"path": "hubspace/core/tasks.py", "change": "+delete_note"}],
     "functions": [{"symbol": "delete_note()", "note": "idempotent"}],
     "tests": ["TestDeleteNote"], "note": ""},
]
_EDGES = [{"from": "endpoint", "to": "store", "rel": "calls"}]


class TestChangeMap(unittest.TestCase):
    def setUp(self):
        self.html = changemap.render_html(_META, _NODES, _EDGES)

    def test_self_contained_offline(self):
        # No external hosts / CDNs / remote fonts — publishable as-is.
        for needle in ("http://", "https://", "//cdn", 'src="//', "@import"):
            self.assertNotIn(needle, self.html, f"must not reference {needle!r}")

    def test_is_one_html_document(self):
        self.assertIn("<!DOCTYPE html>", self.html)
        self.assertIn("<style>", self.html)
        self.assertIn("<script>", self.html)

    def test_change_oriented_titles_render(self):
        # Nodes are named by the CHANGE, and shown as cards.
        self.assertIn("Delete-comment endpoint", self.html)
        self.assertIn("Notes store", self.html)
        self.assertIn('class="node"', self.html)

    def test_no_grid_background(self):
        # The checks/grid are gone — clean paper ground only.
        self.assertNotIn("background-size:22px", self.html)
        self.assertNotIn("radial-gradient", self.html)

    def test_deep_dive_payload_and_inspector_present(self):
        # Every node's file/function/test detail is baked for the inspector,
        # and the inspector + click wiring ship in the page.
        self.assertIn('id="insp"', self.html)
        self.assertIn("window.CMAP", self.html)
        for needle in ("_note_delete()", "delete_note()", "TestNoteDeleteEndpoint",
                       "hubspace/cli/server.py", "guards + rebuild"):
            self.assertIn(needle, self.html)
        self.assertIn(".onclick", self.html)  # nodes are clickable

    def test_edge_label_rendered(self):
        self.assertIn("calls", self.html)

    def test_provenance_frontmatter_when_generated_by(self):
        self.assertTrue(self.html.lstrip().startswith("<!--"))
        self.assertIn('generated_by: "claude ▸ skill:change-log"', self.html)
        self.assertIn("commit_range: \"abc..def\"", self.html)

    def test_no_provenance_when_absent(self):
        html = changemap.render_html({"title": "X"}, _NODES, _EDGES)
        self.assertTrue(html.lstrip().startswith("<!DOCTYPE"))

    def test_left_to_right_flow(self):
        # endpoint depends on store (endpoint→store), so store sits to its right.
        pos = changemap._positions(_NODES, _EDGES)
        self.assertLess(pos["endpoint"][0], pos["store"][0])

    def test_deterministic(self):
        self.assertEqual(self.html, changemap.render_html(_META, _NODES, _EDGES))

    def test_script_close_tags_escaped(self):
        # A node note containing </script> must not break out of the payload.
        nodes = [dict(_NODES[0], note="danger </script> x")]
        html = changemap.render_html(_META, nodes, [])
        self.assertNotIn("</script> x", html)
        self.assertIn("<\\/script> x", html)


if __name__ == "__main__":
    unittest.main()
