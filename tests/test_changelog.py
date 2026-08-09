"""S6 (2a) — the /changelog skill ships, and Hub renders the provenance line
it stamps. Hub gains no model/network/key: it only reads front matter and
(client-side) copies a string.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.render import page, _inject_into_html
from hubspace.core import metadata

_PLUGIN = (
    Path(__file__).resolve().parent.parent
    / "hubspace" / "plugin" / "hub-agent" / "skills" / "changelog"
)


class TestRenderProvenance(unittest.TestCase):
    def test_renders_line_when_present(self):
        prov = {
            "generated_by": "claude ▸ skill:changelog",
            "commit_range": "abc..def",
            "written_at": "2026-08-05T10:00:00Z",
        }
        html = page.render_provenance(prov)
        self.assertIn("written by claude ▸ skill:changelog", html)
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
    def test_skill_md_exists(self):
        self.assertTrue((_PLUGIN / "SKILL.md").is_file())

    def test_template_exists(self):
        self.assertTrue((_PLUGIN / "templates" / "changelog.html").is_file())

    def test_template_carries_provenance_frontmatter(self):
        text = (_PLUGIN / "templates" / "changelog.html").read_text()
        self.assertIn("generated_by:", text)
        self.assertIn("commit_range:", text)
        self.assertIn("Hub did not generate this file.", text)

    def test_template_is_self_contained(self):
        # No external hosts — fully offline / publishable as-is.
        text = (_PLUGIN / "templates" / "changelog.html").read_text()
        for needle in ("http://", "https://", "//cdn", "src=\"//", "@import"):
            self.assertNotIn(needle, text, f"template must not reference {needle!r}")

    def test_skill_documents_the_command(self):
        text = (_PLUGIN / "SKILL.md").read_text()
        self.assertIn("/changelog", text)
        self.assertIn("--canvas", text)


if __name__ == "__main__":
    unittest.main()
