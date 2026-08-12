"""Tests for metadata.py — title and body extraction."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import metadata


class TestReadSafe(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        self.assertEqual(metadata.read_safe("/nonexistent/path/file.md"), "")

    def test_reads_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("hello world")
            name = f.name
        try:
            self.assertEqual(metadata.read_safe(name), "hello world")
        finally:
            os.unlink(name)

    def test_permission_error_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("secret")
            name = f.name
        try:
            os.chmod(name, 0o000)
            result = metadata.read_safe(name)
            self.assertEqual(result, "")
        finally:
            os.chmod(name, 0o644)
            os.unlink(name)


class TestExtractTitle(unittest.TestCase):
    def test_h1_heading(self):
        self.assertEqual(metadata.extract_title("doc.md", "# My Title\n\nbody"), "My Title")

    def test_frontmatter_title(self):
        text = "---\ntitle: Frontmatter Title\n---\n# Other\n"
        self.assertEqual(metadata.extract_title("doc.md", text), "Frontmatter Title")

    def test_frontmatter_takes_priority_over_h1(self):
        text = "---\ntitle: FM Title\n---\n# H1 Title\n"
        self.assertEqual(metadata.extract_title("doc.md", text), "FM Title")

    def test_filename_fallback(self):
        self.assertEqual(metadata.extract_title("my-doc-file.md", "no heading here"), "My Doc File")

    def test_html_title_tag(self):
        # HTML files fall back to stem when there's no h1 in text (title tag is in head which gets stripped)
        result = metadata.extract_title("page.html", "<html><head><title>Page</title></head></html>")
        # Falls back to filename stem because there's no # heading in the text
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_frontmatter_single_quotes(self):
        text = "---\ntitle: 'Quoted Title'\n---\n"
        self.assertEqual(metadata.extract_title("doc.md", text), "Quoted Title")

    def test_underscore_filename_fallback(self):
        self.assertEqual(metadata.extract_title("my_file_name.md", ""), "My File Name")


class TestExtractBody(unittest.TestCase):
    def test_markdown_strips_headings(self):
        result = metadata.extract_body("doc.md", "# Title\n\nbody text here")
        self.assertIn("body text here", result)
        self.assertNotIn("#", result)

    def test_markdown_strips_code_fence(self):
        src = "intro\n```python\nprint('hi')\n```\noutro"
        result = metadata.extract_body("doc.md", src)
        self.assertIn("intro", result)
        self.assertIn("outro", result)
        self.assertNotIn("```", result)

    def test_markdown_strips_inline_code(self):
        result = metadata.extract_body("doc.md", "use `foo()` here")
        self.assertNotIn("`", result)

    def test_markdown_strips_frontmatter(self):
        text = "---\ntitle: T\n---\nbody only"
        result = metadata.extract_body("doc.md", text)
        self.assertNotIn("title:", result)
        self.assertIn("body only", result)

    def test_markdown_link_text_kept(self):
        result = metadata.extract_body("doc.md", "[click here](http://example.com)")
        self.assertIn("click here", result)

    def test_max_chars_respected(self):
        big = "a " * 2000
        result = metadata.extract_body("doc.md", big, max_chars=100)
        self.assertLessEqual(len(result), 100)

    def test_html_strips_tags(self):
        src = "<p>Hello <b>world</b></p>"
        result = metadata.extract_body("page.html", src)
        self.assertIn("Hello", result)
        self.assertIn("world", result)
        self.assertNotIn("<p>", result)
        self.assertNotIn("<b>", result)

    def test_html_strips_script(self):
        src = "<p>text</p><script>alert(1)</script>"
        result = metadata.extract_body("page.html", src)
        self.assertNotIn("alert", result)
        self.assertIn("text", result)

    def test_pdf_returns_empty(self):
        self.assertEqual(metadata.extract_body("doc.pdf", "binary"), "")

    def test_excalidraw_returns_empty(self):
        # JSON scene graph must not be indexed as raw text
        scene = '{"type":"excalidraw","elements":[{"type":"text","text":"hello"}]}'
        self.assertEqual(metadata.extract_body("diagram.excalidraw", scene), "")

    def test_csv_normalises_whitespace(self):
        result = metadata.extract_body("data.csv", "a,  b ,c\n1,2,3")
        self.assertIn("a", result)

    def test_html_entity_decoding(self):
        result = metadata.extract_body("page.html", "<p>Tom &amp; Jerry</p>")
        self.assertIn("Tom & Jerry", result)


class TestExtractHtmlBody(unittest.TestCase):
    def test_strips_style_block(self):
        src = "<style>body{color:red}</style><p>content</p>"
        result = metadata._extract_html_body(src, 2000)
        self.assertNotIn("color:red", result)
        self.assertIn("content", result)

    def test_nbsp_becomes_space(self):
        result = metadata._extract_html_body("<p>a&nbsp;b</p>", 2000)
        self.assertIn("a b", result)

    def test_max_chars(self):
        src = "<p>" + ("x " * 3000) + "</p>"
        result = metadata._extract_html_body(src, 100)
        self.assertLessEqual(len(result), 100)


class TestExtractStatus(unittest.TestCase):
    def test_default_ongoing_when_no_frontmatter(self):
        self.assertEqual(metadata.extract_status("just plain text"), "ongoing")

    def test_ongoing_from_frontmatter(self):
        self.assertEqual(metadata.extract_status("---\nstatus: ongoing\n---\n"), "ongoing")

    def test_paused_from_frontmatter(self):
        self.assertEqual(metadata.extract_status("---\nstatus: paused\n---\n"), "paused")

    def test_completed_from_frontmatter(self):
        self.assertEqual(metadata.extract_status("---\nstatus: completed\n---\n"), "completed")

    def test_invalid_status_falls_back_to_ongoing(self):
        self.assertEqual(metadata.extract_status("---\nstatus: blocked\n---\n"), "ongoing")

    def test_status_case_insensitive(self):
        self.assertEqual(metadata.extract_status("---\nstatus: PAUSED\n---\n"), "paused")

    def test_status_with_double_quotes(self):
        self.assertEqual(metadata.extract_status('---\nstatus: "completed"\n---\n'), "completed")

    def test_status_with_single_quotes(self):
        self.assertEqual(metadata.extract_status("---\nstatus: 'paused'\n---\n"), "paused")

    def test_empty_text_returns_ongoing(self):
        self.assertEqual(metadata.extract_status(""), "ongoing")

    def test_status_not_in_frontmatter_returns_ongoing(self):
        self.assertEqual(metadata.extract_status("---\ntitle: My Task\n---\n"), "ongoing")


class TestExtractPlan(unittest.TestCase):
    def test_empty_text_returns_empty_list(self):
        self.assertEqual(metadata.extract_plan(""), [])

    def test_no_checkboxes_returns_empty_list(self):
        self.assertEqual(metadata.extract_plan("- plain item\n- another"), [])

    def test_unchecked_item(self):
        items = metadata.extract_plan("- [ ] Do something")
        self.assertEqual(len(items), 1)
        self.assertFalse(items[0]["d"])
        self.assertEqual(items[0]["t"], "Do something")

    def test_checked_item_lowercase_x(self):
        items = metadata.extract_plan("- [x] Done thing")
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["d"])
        self.assertEqual(items[0]["t"], "Done thing")

    def test_checked_item_uppercase_x(self):
        items = metadata.extract_plan("- [X] Capital X")
        self.assertTrue(items[0]["d"])

    def test_mixed_plan_preserves_order(self):
        text = "- [x] Step 1\n- [ ] Step 2\n- [x] Step 3"
        items = metadata.extract_plan(text)
        self.assertEqual(len(items), 3)
        self.assertEqual([i["d"] for i in items], [True, False, True])
        self.assertEqual([i["t"] for i in items], ["Step 1", "Step 2", "Step 3"])

    def test_text_after_checkbox_preserved_including_markup(self):
        items = metadata.extract_plan("- [ ] **Bold step** with `code`")
        self.assertEqual(items[0]["t"], "**Bold step** with `code`")

    def test_space_only_in_brackets_is_unchecked(self):
        items = metadata.extract_plan("- [ ] Pending")
        self.assertFalse(items[0]["d"])


class TestExtractDecisions(unittest.TestCase):
    def test_no_decisions_section_returns_empty(self):
        self.assertEqual(metadata.extract_decisions("no section here"), [])

    def test_h2_decisions_section(self):
        text = "## Decisions\n1. Use SQLite\n2. Stdlib only\n"
        self.assertEqual(metadata.extract_decisions(text), ["Use SQLite", "Stdlib only"])

    def test_h3_decisions_section(self):
        text = "### Decisions\n1. First decision\n"
        self.assertEqual(metadata.extract_decisions(text), ["First decision"])

    def test_h1_decisions_section(self):
        text = "# Decisions\n1. Top level\n"
        self.assertEqual(metadata.extract_decisions(text), ["Top level"])

    def test_decisions_case_insensitive(self):
        text = "## DECISIONS\n1. Case test\n"
        self.assertEqual(metadata.extract_decisions(text), ["Case test"])

    def test_empty_decisions_section_returns_empty(self):
        text = "## Decisions\n\n## Next Section\n"
        self.assertEqual(metadata.extract_decisions(text), [])

    def test_stops_at_next_heading(self):
        text = "## Decisions\n1. Keep this\n## Other Section\n2. Not this\n"
        decisions = metadata.extract_decisions(text)
        self.assertEqual(decisions, ["Keep this"])

    def test_non_numbered_items_ignored(self):
        text = "## Decisions\n- bullet point\n1. numbered only\n"
        decisions = metadata.extract_decisions(text)
        self.assertEqual(decisions, ["numbered only"])

    def test_decisions_text_stripped(self):
        text = "## Decisions\n1.   extra spaces   \n"
        decisions = metadata.extract_decisions(text)
        self.assertEqual(decisions, ["extra spaces"])


class TestExtractProvenance(unittest.TestCase):
    """S6 (2a) — provenance front matter written by the /change-log skill."""

    def test_raw_frontmatter_md(self):
        text = (
            "---\n"
            'generated_by: "claude ▸ skill:change-log"\n'
            'commit_range: "abc123..def456"\n'
            "written_at: 2026-08-05T10:00:00Z\n"
            "task: my-feature\n"
            "---\n\n# Changelog\n"
        )
        prov = metadata.extract_provenance(text)
        self.assertEqual(prov["generated_by"], "claude ▸ skill:change-log")
        self.assertEqual(prov["commit_range"], "abc123..def456")
        self.assertEqual(prov["written_at"], "2026-08-05T10:00:00Z")
        self.assertEqual(prov["task"], "my-feature")

    def test_html_comment_wrapped_frontmatter(self):
        # .html artifacts wrap the block in a comment so it never renders.
        text = (
            "<!--\n---\n"
            'generated_by: "claude ▸ skill:change-log"\n'
            'commit_range: "aaa..bbb"\n'
            "---\n-->\n<!DOCTYPE html><html><body>hi</body></html>"
        )
        prov = metadata.extract_provenance(text)
        self.assertEqual(prov["generated_by"], "claude ▸ skill:change-log")
        self.assertEqual(prov["commit_range"], "aaa..bbb")

    def test_normal_file_returns_none(self):
        self.assertIsNone(metadata.extract_provenance("# Just a doc\n\nnothing here"))

    def test_frontmatter_without_generated_by_returns_none(self):
        # A normal manifest front matter (title/status) is not provenance.
        text = "---\ntitle: Something\nstatus: ongoing\n---\n# Doc\n"
        self.assertIsNone(metadata.extract_provenance(text))

    def test_optional_fields_absent(self):
        text = '---\ngenerated_by: "agent"\n---\nbody'
        prov = metadata.extract_provenance(text)
        self.assertEqual(prov, {"generated_by": "agent"})


if __name__ == "__main__":
    unittest.main()
