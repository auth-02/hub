"""S19 — reader v2: line-anchored source, DOC_EMBED_SCRIPT gutter/inline comments.

Three concerns, no network:
  - render/markdown.py: every top-level block carries a data-src-line pointing at
    its ORIGINAL source line (frontmatter- and fence-aware), and _add_outline
    preserves that attribute while still injecting heading ids.
  - render/page.py DOC_EMBED_SCRIPT: the LIVE-served companion script carries the
    hover "+" gutter, the hub-comment-line hand-off, and inline-comment rendering.
Bundle self-containment (none of this script leaks into a published bundle) is
guarded in test_bundle.py::test_no_spa_reader_keydown_forwarder.
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace import render
from hubspace.render import page as _page


class TestSrcLineAnnotation(unittest.TestCase):
    def _line_of(self, html, tag):
        m = re.search(rf'<{tag}[^>]*\bdata-src-line="(\d+)"', html)
        return int(m.group(1)) if m else None

    def test_heading_line_after_frontmatter(self):
        # Frontmatter occupies lines 1-4; the h1 is on original source line 5.
        src = "---\ntitle: x\nkind: y\n---\n# Heading One\n\nBody paragraph.\n"
        html = render._render_md(src)
        self.assertEqual(self._line_of(html, "h1"), 5)
        self.assertEqual(self._line_of(html, "p"), 7)

    def test_blocks_survive_multiline_code_fence(self):
        # A fenced block must not collapse the line count of blocks AFTER it.
        src = ("# Top\n\n"          # h1 on line 1
               "```python\n"        # fence opens on line 3
               "a = 1\n"
               "b = 2\n"
               "```\n\n"
               "## After\n")        # heading after code on line 8
        html = render._render_md(src)
        self.assertEqual(self._line_of(html, "h1"), 1)
        self.assertEqual(self._line_of(html, "pre"), 3)
        self.assertEqual(self._line_of(html, "h2"), 8)

    def test_list_items_carry_their_own_line(self):
        src = "intro\n\n- alpha\n- beta\n- gamma\n"
        html = render._render_md(src)
        lis = re.findall(r'<li data-src-line="(\d+)"', html)
        self.assertEqual(lis, ["3", "4", "5"])

    def test_outline_preserves_src_line_and_adds_id(self):
        src = "# One\n\ntext\n\n## Two\n\nmore\n"
        html = render._render_md(src)
        body, outline = render._add_outline(html)
        self.assertIn("outline", outline)
        # id injected AND data-src-line kept on the same heading.
        self.assertRegex(body, r'<h1 data-src-line="1" id="one">')
        self.assertRegex(body, r'<h2 data-src-line="5" id="two">')


class TestDocEmbedScript(unittest.TestCase):
    def test_has_gutter_and_inline_comment_machinery(self):
        s = _page.DOC_EMBED_SCRIPT
        # hover "+" gutter → parent hand-off with the clicked line
        self.assertIn("hub-line-add", s)
        self.assertIn("hub-comment-line", s)
        # inline anchored/general comment rendering fed from the parent
        self.assertIn("hub-doc-notes", s)
        self.assertIn("data-src-line", s)
        # S17 keydown forwarding must stay intact
        self.assertIn("hub-key", s)
        # only meaningful when embedded (never on a top-level tab)
        self.assertIn("window.parent===window", s)


if __name__ == "__main__":
    unittest.main()
