"""S19/S21 — line-anchored source + the self-sufficient doc-page companion script.

Three concerns, no network:
  - render/markdown.py: every top-level block carries a data-src-line pointing at
    its ORIGINAL source line (frontmatter- and fence-aware), and _add_outline
    preserves that attribute while still injecting heading ids. Leading YAML
    frontmatter is stripped from the rendered body (a mid-doc --- hr survives).
  - render/page.py DOC_PAGE_SCRIPT (S21): the LIVE-served companion script is now
    self-sufficient — no SPA parent. It renders window.HUB_DOC's baked comments,
    hosts the "+" gutter composer (POST /_note), and edits in place (✎ Edit →
    /_doc-raw + /_edit-doc). It carries NO parent-frame postMessage.
Bundle self-containment (none of this leaks into a published bundle) is guarded
in test_bundle.py::test_no_spa_reader_keydown_forwarder.
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

    def test_leading_frontmatter_stripped_but_mid_doc_hr_kept(self):
        # A manifest opening with a YAML frontmatter fence: its keys must NOT
        # appear as visible body text (Hub already parses them for status/title).
        src = ("---\nstatus: ongoing\ntitle: X\n---\n"
               "# Heading\n\nbefore\n\n---\n\nafter\n")
        html = render._render_md(src)
        self.assertNotIn("status:", html)   # frontmatter not rendered as body
        self.assertNotIn("title: X", html)
        self.assertIn("<hr", html)           # the mid-document --- survives
        self.assertEqual(self._line_of(html, "h1"), 5)  # data-src-line still true


class TestDocPageScript(unittest.TestCase):
    def test_self_sufficient_comment_and_edit_machinery(self):
        s = _page.DOC_PAGE_SCRIPT
        # persistent "+" gutter lane → on-page composer (POST /_note)
        self.assertIn("hub-line-add", s)
        self.assertIn("hub-gutter-lane", s)
        self.assertIn("/_note", s)
        # inline comments render from the baked window.HUB_DOC — no parent frame
        self.assertIn("window.HUB_DOC", s)
        self.assertIn("data-src-line", s)
        self.assertNotIn("window.parent", s)
        # ✎ edit-in-place uses the same /_doc-raw + /_edit-doc endpoints (S18)
        self.assertIn("hubDocEdit", s)
        self.assertIn("/_doc-raw", s)
        self.assertIn("/_edit-doc", s)
        # ⌘C composer is guarded against a real text selection
        self.assertIn("getSelection", s)

    def test_edit_menu_item_and_config_baking(self):
        self.assertIn("hubDocEdit", _page.doc_edit_item())
        self.assertIn("✎", _page.doc_edit_item())
        cfg = _page.doc_config_script(
            {"repo": "r", "slug": "s", "target": "manifest.md",
             "notes": [{"body": "hi</script>x"}]})
        self.assertIn("window.HUB_DOC=", cfg)
        # a comment body can never close the <script> early
        self.assertNotIn("</script>x", cfg)


if __name__ == "__main__":
    unittest.main()
