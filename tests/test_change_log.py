"""S6 (2a) / S32 — the /change-log skill ships (now diagram-first: it draws the
change as a connected wireframe on the draw canvas), and Hub renders the
provenance line the `--doc` companion stamps. Hub gains no model/network/key: it
only lays out a graph the agent hands it, reads front matter, and (client-side)
copies a string.
"""
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.render import page, _inject_into_html
from hubspace.core import metadata

_PLUGIN = (
    Path(__file__).resolve().parent.parent
    / "hubspace" / "plugin" / "hub-agent" / "skills" / "change-log"
)


class TestRenderProvenance(unittest.TestCase):
    def test_renders_line_when_present(self):
        prov = {
            "generated_by": "claude ▸ skill:change-log",
            "commit_range": "abc..def",
            "written_at": "2026-08-05T10:00:00Z",
        }
        html = page.render_provenance(prov)
        self.assertIn("written by claude ▸ skill:change-log", html)
        self.assertIn("abc..def", html)
        self.assertIn("2026-08-05T10:00:00Z", html)
        self.assertIn("Hub did not generate this file.", html)

    def test_empty_when_absent(self):
        self.assertEqual(page.render_provenance(None), "")
        self.assertEqual(page.render_provenance({}), "")

    def test_escapes_html(self):
        html = page.render_provenance({"generated_by": "<script>x</script>"})
        self.assertNotIn("<script>", html)

    def test_inject_adds_provenance_to_html_doc(self):
        src = "<html><head></head><body><h1>Title</h1><p>body</p></body></html>"
        prov_html = page.render_provenance({"generated_by": "agent"})
        out = _inject_into_html(src, "", "", prov_html)
        self.assertIn("Hub did not generate this file.", out)
        # Injected right after the h1.
        self.assertLess(out.index("Title</h1>"), out.index("Hub did not generate"))

    def test_inject_omits_provenance_for_normal_doc(self):
        src = "<html><head></head><body><h1>Title</h1></body></html>"
        out = _inject_into_html(src, "", "", "")
        self.assertNotIn("Hub did not generate", out)


class TestSkillShips(unittest.TestCase):
    def test_skill_md_exists_and_is_named_change_log(self):
        self.assertTrue((_PLUGIN / "SKILL.md").is_file())
        text = (_PLUGIN / "SKILL.md").read_text()
        self.assertIn("name: change-log", text)

    def test_doc_template_exists_and_is_renamed(self):
        self.assertTrue((_PLUGIN / "templates" / "change-log.html").is_file())
        # The old name is gone (rename is complete, not additive).
        self.assertFalse((_PLUGIN / "templates" / "changelog.html").exists())

    def test_doc_template_carries_provenance_frontmatter(self):
        text = (_PLUGIN / "templates" / "change-log.html").read_text()
        self.assertIn("generated_by:", text)
        self.assertIn("skill:change-log", text)
        self.assertIn("commit_range:", text)
        self.assertIn("Hub did not generate this file.", text)

    def test_doc_template_is_self_contained(self):
        # No external hosts — fully offline / publishable as-is.
        text = (_PLUGIN / "templates" / "change-log.html").read_text()
        for needle in ("http://", "https://", "//cdn", "src=\"//", "@import"):
            self.assertNotIn(needle, text, f"template must not reference {needle!r}")

    def test_skill_documents_draw_first_flow(self):
        text = (_PLUGIN / "SKILL.md").read_text()
        self.assertIn("/change-log", text)
        # Draw-first: agent writes the editable .excalidraw into change-log/…
        self.assertIn("change-log/", text)
        self.assertIn("changelog.to_scene", text)
        self.assertIn("interactive_href", text)
        # …and Save renders the interactive HTML via the round-trip + renderer.
        self.assertIn("scene_to_graph", text)
        self.assertIn("changemap.render_html", text)
        self.assertIn("deep-dive", text)
        self.assertIn("--doc", text)


# The worked example the starter template + SKILL.md recipe are built from.
_EX_NODES = [
    {"id": "n1", "kind": "task", "path": "delete-comment endpoint", "at": "new", "note": "POST /_note-delete"},
    {"id": "n2", "kind": "script", "path": "notes store · delete_note", "at": "new", "note": "byte-preserving remove"},
    {"id": "n3", "kind": "artifact", "path": "trace + doc-page ✕ UI", "at": "changed", "note": "two-click confirm"},
]
_EX_EDGES = [{"from": "n1", "to": "n2", "rel": "calls"}, {"from": "n3", "to": "n1", "rel": "posts to"}]
_EX_KW = dict(title="Change-log — delete a comment",
              subtitle="<short-since>..<short-head> · 3 change-units")


class TestDiagramTemplateIsAValidScene(unittest.TestCase):
    """The starter `.excalidraw` must be a scene Hub's draw canvas can open."""

    def _scene(self):
        p = _PLUGIN / "templates" / "change-log.excalidraw"
        self.assertTrue(p.is_file(), "diagram starter template is missing")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_is_a_clean_paper_excalidraw_scene(self):
        scene = self._scene()
        self.assertEqual(scene.get("type"), "excalidraw")
        self.assertIsInstance(scene.get("elements"), list)
        self.assertTrue(scene["elements"], "scene has no elements")
        app = scene.get("appState", {})
        self.assertIn("viewBackgroundColor", app)
        self.assertIsNone(app.get("gridSize"))  # no grid — clean paper ground

    def test_has_change_nodes_and_dependency_arrows(self):
        scene = self._scene()
        types = [el.get("type") for el in scene["elements"]]
        self.assertIn("rectangle", types)  # cards + accent bars
        self.assertIn("arrow", types)      # dependencies
        self.assertIn("text", types)       # labels

    def test_matches_the_changelog_emitter(self):
        # The template is Hub's own deterministic emitter output — regenerating
        # the documented worked example must reproduce it byte-for-byte, so the
        # skill's `changelog.to_scene(...)` recipe is provably correct.
        from hubspace.core import changelog
        regenerated = changelog.to_scene(_EX_NODES, _EX_EDGES, **_EX_KW)
        self.assertEqual(regenerated, self._scene())


class TestChangelogEmitter(unittest.TestCase):
    """hubspace.core.changelog.to_scene — the polished change-map renderer."""

    def setUp(self):
        from hubspace.core import changelog
        self.changelog = changelog
        self.scene = changelog.to_scene(_EX_NODES, _EX_EDGES, **_EX_KW)
        self.texts = [e["text"] for e in self.scene["elements"] if e.get("type") == "text"]

    def test_title_and_subtitle_rendered(self):
        self.assertIn("Change-log — delete a comment", self.texts)
        self.assertTrue(any("3 change-units" in t for t in self.texts))

    def test_numbered_cards(self):
        self.assertIn("01", self.texts)
        self.assertIn("02", self.texts)
        self.assertIn("03", self.texts)

    def test_each_node_has_an_accent_bar_in_its_kind_colour(self):
        # A bar rectangle whose stroke == the kind accent (color_for) exists.
        bars = [e for e in self.scene["elements"]
                if e.get("type") == "rectangle" and e["id"].startswith("bar-")]
        self.assertEqual(len(bars), len(_EX_NODES))
        self.assertIn(self.changelog.color_for("task"),
                      [b["strokeColor"] for b in bars])

    def test_edge_labels_drawn(self):
        self.assertIn("calls", self.texts)
        self.assertIn("posts to", self.texts)

    def test_legend_lists_only_present_kinds(self):
        self.assertIn("KINDS", self.texts)
        for k in ("task", "script", "artifact"):
            self.assertIn(k, self.texts)
        self.assertNotIn("run", self.texts)   # not used by the example

    def test_left_to_right_dependency_flow(self):
        # n1 depends on n2 (n1→n2), so n2 (a dependency) sits to n1's right.
        pos = self.changelog._positions(_EX_NODES, _EX_EDGES)
        self.assertLess(pos["n1"]["x"], pos["n2"]["x"])

    def test_deterministic(self):
        again = self.changelog.to_scene(_EX_NODES, _EX_EDGES, **_EX_KW)
        self.assertEqual(again, self.scene)


if __name__ == "__main__":
    unittest.main()
