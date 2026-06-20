"""Tests for pure helper functions in server.py."""
import csv
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import server


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(server._slugify("Hello World"), "hello-world")

    def test_punctuation_collapsed(self):
        self.assertEqual(server._slugify("Foo: Bar & Baz!"), "foo-bar-baz")

    def test_html_stripped(self):
        self.assertEqual(server._slugify("<strong>Title</strong>"), "title")

    def test_leading_trailing_trimmed(self):
        self.assertEqual(server._slugify("  hello  "), "hello")

    def test_numbers_kept(self):
        self.assertEqual(server._slugify("Step 2: Install"), "step-2-install")

    def test_empty_string(self):
        self.assertEqual(server._slugify(""), "")


class TestAddOutline(unittest.TestCase):
    def test_no_headings_returns_empty_outline(self):
        html = "<p>No headings here</p>"
        body, outline = server._add_outline(html)
        self.assertEqual(outline, "")
        self.assertEqual(body, html)

    def test_single_heading_returns_empty_outline(self):
        html = "<h2>Only One</h2><p>text</p>"
        body, outline = server._add_outline(html)
        self.assertEqual(outline, "")

    def test_two_headings_returns_outline(self):
        html = "<h2>First</h2><h2>Second</h2>"
        body, outline = server._add_outline(html)
        self.assertIn("First", outline)
        self.assertIn("Second", outline)
        self.assertIn('href="#first"', outline)

    def test_ids_injected_into_headings(self):
        html = "<h2>My Section</h2><h3>Sub</h3>"
        body, outline = server._add_outline(html)
        self.assertIn('id="my-section"', body)
        self.assertIn('id="sub"', body)

    def test_duplicate_heading_slugs_get_suffix(self):
        html = "<h2>Item</h2><h2>Item</h2>"
        body, outline = server._add_outline(html)
        self.assertIn('id="item"', body)
        self.assertIn('id="item-2"', body)

    def test_h1_through_h3_included(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3>"
        body, outline = server._add_outline(html)
        self.assertIn("Title", outline)
        self.assertIn("Section", outline)
        self.assertIn("Sub", outline)


class TestEscCell(unittest.TestCase):
    def test_ampersand(self):
        self.assertEqual(server._esc_cell("a&b"), "a&amp;b")

    def test_less_than(self):
        self.assertEqual(server._esc_cell("<script>"), "&lt;script&gt;")

    def test_quote(self):
        self.assertIn("&quot;", server._esc_cell('"hello"'))

    def test_plain_string_unchanged(self):
        self.assertEqual(server._esc_cell("hello"), "hello")

    def test_non_string_coerced(self):
        self.assertEqual(server._esc_cell(42), "42")


class TestRowsToTable(unittest.TestCase):
    def test_empty_returns_paragraph(self):
        result = server._rows_to_table([])
        self.assertIn("Empty", result)

    def test_header_row_in_thead(self):
        result = server._rows_to_table([["Name", "Age"], ["Alice", "30"]])
        self.assertIn("<thead>", result)
        self.assertIn("<th>Name</th>", result)

    def test_data_row_in_tbody(self):
        result = server._rows_to_table([["Name", "Age"], ["Alice", "30"]])
        self.assertIn("<tbody>", result)
        self.assertIn("<td>Alice</td>", result)

    def test_xss_escaped_in_cell(self):
        result = server._rows_to_table([["H"], ["<script>alert(1)</script>"]])
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_single_header_row(self):
        result = server._rows_to_table([["Col"]])
        self.assertIn("<th>Col</th>", result)
        self.assertIn("<tbody></tbody>", result)


class TestInjectIntoHtml(unittest.TestCase):
    def test_backlinks_css_added_to_head(self):
        src = "<html><head></head><body><h1>Title</h1></body></html>"
        result = server._inject_into_html(src, "<div>links</div>")
        self.assertIn("<style>", result)

    def test_lineage_injected_after_h1(self):
        src = "<html><head></head><body><h1>Title</h1><p>body</p></body></html>"
        marker = "INJECTED_MARKER_XYZ"
        result = server._inject_into_html(src, f"<div>{marker}</div>")
        h1_pos = result.find("</h1>")
        marker_pos = result.find(marker)
        self.assertGreater(marker_pos, h1_pos)

    def test_lineage_injected_at_body_if_no_h1(self):
        src = "<html><head></head><body><p>no heading</p></body></html>"
        result = server._inject_into_html(src, "<div>trace</div>")
        self.assertIn("trace", result)

    def test_favicon_link_added_when_provided(self):
        src = "<html><head></head><body></body></html>"
        result = server._inject_into_html(src, "", favicon="http://localhost:8787/favicon.svg")
        self.assertIn('rel="icon"', result)

    def test_print_button_injected(self):
        src = "<html><head></head><body></body></html>"
        result = server._inject_into_html(src, "")
        self.assertIn("doc-print", result)


class TestRenderMd(unittest.TestCase):
    def test_heading(self):
        result = server._render_md("# Hello")
        self.assertIn("<h1>", result)
        self.assertIn("Hello", result)

    def test_bold(self):
        result = server._render_md("**bold text**")
        self.assertIn("<strong>bold text</strong>", result)

    def test_italic(self):
        result = server._render_md("*italic*")
        self.assertIn("<em>italic</em>", result)

    def test_code_fence(self):
        result = server._render_md("```python\nprint('hi')\n```")
        self.assertIn("<pre>", result)
        self.assertIn("<code", result)

    def test_unordered_list(self):
        result = server._render_md("- item one\n- item two")
        self.assertIn("<ul>", result)
        self.assertIn("<li>", result)

    def test_ordered_list(self):
        result = server._render_md("1. first\n2. second")
        self.assertIn("<ol>", result)

    def test_link(self):
        result = server._render_md("[click](http://example.com)")
        self.assertIn('<a href="http://example.com">', result)

    def test_frontmatter_stripped(self):
        src = "---\ntitle: T\n---\n# Heading"
        result = server._render_md(src)
        self.assertNotIn("title:", result)
        self.assertIn("<h1>", result)

    def test_inline_code(self):
        result = server._render_md("use `foo()` here")
        self.assertIn("<code>foo()</code>", result)

    def test_table(self):
        src = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = server._render_md(src)
        self.assertIn("<table>", result)
        self.assertIn("<th>", result)

    def test_blockquote(self):
        result = server._render_md("> quoted text")
        self.assertIn("<blockquote>", result)


class TestRenderCsv(unittest.TestCase):
    def _write_csv(self, content, suffix=".csv"):
        tf = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        )
        tf.write(content)
        tf.close()
        return tf.name

    def test_csv_renders_table(self):
        name = self._write_csv("Name,Age\nAlice,30\nBob,25")
        try:
            result = server._render_csv(__import__("pathlib").Path(name))
            self.assertIn("<table>", result)
            self.assertIn("Alice", result)
            self.assertIn("Name", result)
        finally:
            os.unlink(name)

    def test_tsv_renders_table(self):
        name = self._write_csv("Name\tScore\nAlice\t100", suffix=".tsv")
        try:
            result = server._render_csv(__import__("pathlib").Path(name))
            self.assertIn("<table>", result)
            self.assertIn("Score", result)
        finally:
            os.unlink(name)

    def test_empty_csv(self):
        name = self._write_csv("")
        try:
            result = server._render_csv(__import__("pathlib").Path(name))
            self.assertIn("Empty", result)
        finally:
            os.unlink(name)

    def test_xss_in_csv(self):
        name = self._write_csv("Col\n<script>evil</script>")
        try:
            result = server._render_csv(__import__("pathlib").Path(name))
            self.assertNotIn("<script>", result)
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main()
