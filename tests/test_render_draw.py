"""Tests for the Excalidraw host page (render/draw.py)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.render import draw


class TestDrawPageHtml(unittest.TestCase):
    def test_blank_canvas(self):
        html = draw.draw_page_html(None, None, 8787)
        self.assertIn('<div id="app">', html)
        self.assertIn('src="/static/draw.js"', html)
        self.assertIn('href="/static/draw.css"', html)
        self.assertIn("window.DRAW_STATE", html)
        self.assertIn("<title>Draw</title>", html)
        # rel + data are null for a fresh diagram
        self.assertIn('"rel": null', html)
        self.assertIn('"data": null', html)

    def test_title_from_rel_stem(self):
        html = draw.draw_page_html("docs/architecture.excalidraw", None, 8787)
        self.assertIn("<title>architecture</title>", html)

    def test_scene_embedded_in_state(self):
        scene = {"type": "excalidraw", "elements": [{"type": "text", "text": "hi"}]}
        html = draw.draw_page_html("d.excalidraw", json.dumps(scene), 8787)
        # The scene object is present inside window.DRAW_STATE
        self.assertIn('"type"', html)
        self.assertIn("hi", html)

    def test_malformed_scene_falls_back_to_blank(self):
        html = draw.draw_page_html("bad.excalidraw", "{not valid json", 8787)
        # Must not raise; data should be null
        self.assertIn("window.DRAW_STATE", html)
        self.assertIn('"data": null', html)

    def test_script_breakout_is_escaped(self):
        # A text element literally containing </script> must not close the tag.
        scene = {"elements": [{"type": "text", "text": "</script><script>alert(1)"}]}
        html = draw.draw_page_html("x.excalidraw", json.dumps(scene), 8787)
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertIn("<\\/script>", html)

    def test_parse_scene_helpers(self):
        self.assertIsNone(draw._parse_scene(None))
        self.assertIsNone(draw._parse_scene("   "))
        self.assertIsNone(draw._parse_scene("nope"))
        self.assertEqual(draw._parse_scene('{"a":1}'), {"a": 1})


if __name__ == "__main__":
    unittest.main()
