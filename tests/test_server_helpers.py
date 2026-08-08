"""Tests for render/utils helper functions."""
import csv
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace import render
from hubspace.utils.paths import is_within
from hubspace.utils.text import esc_html, slugify


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_collapsed(self):
        self.assertEqual(slugify("Foo: Bar & Baz!"), "foo-bar-baz")

    def test_html_stripped(self):
        self.assertEqual(slugify("<strong>Title</strong>"), "title")

    def test_leading_trailing_trimmed(self):
        self.assertEqual(slugify("  hello  "), "hello")

    def test_numbers_kept(self):
        self.assertEqual(slugify("Step 2: Install"), "step-2-install")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")


class TestAddOutline(unittest.TestCase):
    def test_no_headings_returns_empty_outline(self):
        html = "<p>No headings here</p>"
        body, outline = render._add_outline(html)
        self.assertEqual(outline, "")
        self.assertEqual(body, html)

    def test_single_heading_returns_empty_outline(self):
        html = "<h2>Only One</h2><p>text</p>"
        body, outline = render._add_outline(html)
        self.assertEqual(outline, "")

    def test_two_headings_returns_outline(self):
        html = "<h2>First</h2><h2>Second</h2>"
        body, outline = render._add_outline(html)
        self.assertIn("First", outline)
        self.assertIn("Second", outline)
        self.assertIn('href="#first"', outline)

    def test_ids_injected_into_headings(self):
        html = "<h2>My Section</h2><h3>Sub</h3>"
        body, outline = render._add_outline(html)
        self.assertIn('id="my-section"', body)
        self.assertIn('id="sub"', body)

    def test_duplicate_heading_slugs_get_suffix(self):
        html = "<h2>Item</h2><h2>Item</h2>"
        body, outline = render._add_outline(html)
        self.assertIn('id="item"', body)
        self.assertIn('id="item-2"', body)

    def test_h1_through_h3_included(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3>"
        body, outline = render._add_outline(html)
        self.assertIn("Title", outline)
        self.assertIn("Section", outline)
        self.assertIn("Sub", outline)


class TestEscCell(unittest.TestCase):
    def test_ampersand(self):
        self.assertEqual(esc_html("a&b"), "a&amp;b")

    def test_less_than(self):
        self.assertEqual(esc_html("<script>"), "&lt;script&gt;")

    def test_quote(self):
        self.assertIn("&quot;", esc_html('"hello"'))

    def test_plain_string_unchanged(self):
        self.assertEqual(esc_html("hello"), "hello")

    def test_non_string_coerced(self):
        self.assertEqual(esc_html(42), "42")


class TestRowsToTable(unittest.TestCase):
    def test_empty_returns_paragraph(self):
        result = render._rows_to_table([])
        self.assertIn("Empty", result)

    def test_header_row_in_thead(self):
        result = render._rows_to_table([["Name", "Age"], ["Alice", "30"]])
        self.assertIn("<thead>", result)
        self.assertIn("<th>Name</th>", result)

    def test_data_row_in_tbody(self):
        result = render._rows_to_table([["Name", "Age"], ["Alice", "30"]])
        self.assertIn("<tbody>", result)
        self.assertIn("<td>Alice</td>", result)

    def test_xss_escaped_in_cell(self):
        result = render._rows_to_table([["H"], ["<script>alert(1)</script>"]])
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_single_header_row(self):
        result = render._rows_to_table([["Col"]])
        self.assertIn("<th>Col</th>", result)
        self.assertIn("<tbody></tbody>", result)


class TestInjectIntoHtml(unittest.TestCase):
    def test_backlinks_css_added_to_head(self):
        src = "<html><head></head><body><h1>Title</h1></body></html>"
        result = render._inject_into_html(src, "<div>links</div>")
        self.assertIn("<style>", result)

    def test_lineage_injected_after_h1(self):
        src = "<html><head></head><body><h1>Title</h1><p>body</p></body></html>"
        marker = "INJECTED_MARKER_XYZ"
        result = render._inject_into_html(src, f"<div>{marker}</div>")
        h1_pos = result.find("</h1>")
        marker_pos = result.find(marker)
        self.assertGreater(marker_pos, h1_pos)

    def test_lineage_injected_at_body_if_no_h1(self):
        src = "<html><head></head><body><p>no heading</p></body></html>"
        result = render._inject_into_html(src, "<div>trace</div>")
        self.assertIn("trace", result)

    def test_favicon_link_added_when_provided(self):
        src = "<html><head></head><body></body></html>"
        result = render._inject_into_html(src, "", favicon="http://localhost:8787/favicon.svg")
        self.assertIn('rel="icon"', result)

    def test_reader_keydown_forwarder_injected_into_html(self):
        # S17 — injected HTML docs served live also carry the reader forwarder.
        src = "<html><head></head><body><h1>T</h1></body></html>"
        result = render._inject_into_html(src, "")
        self.assertIn("hub-doc", result)
        self.assertIn("window.parent===window", result)

    def test_print_button_injected(self):
        src = "<html><head></head><body></body></html>"
        result = render._inject_into_html(src, "")
        # HTML docs get the ⋯ menu with a Save-as-PDF item.
        self.assertIn("doc-menu", result)
        self.assertIn("window.print()", result)

    def test_publish_item_injected_with_path(self):
        # S14 / #5 — an HTML doc served with a pub_path gets the ↗ Publish menu
        # item (path baked in) + the tiny publisher script.
        src = "<html><head></head><body><h1>Doc</h1></body></html>"
        result = render._inject_into_html(src, "", pub_path="docs/spec.html")
        self.assertIn("↗ Publish", result)
        self.assertIn('data-pub-path="docs/spec.html"', result)
        self.assertIn("hubPublish", result)
        self.assertIn("/_publish", result)

    def test_no_publish_item_without_path(self):
        # No pub_path → the plain print-only menu, no publish affordance.
        src = "<html><head></head><body></body></html>"
        result = render._inject_into_html(src, "")
        self.assertNotIn("↗ Publish", result)
        self.assertNotIn("hubPublish", result)


class TestDocPublishItem(unittest.TestCase):
    def test_item_bakes_path_and_targets_publish(self):
        from hubspace.render import doc_publish_item
        item = doc_publish_item("tasks/x/manifest.md")
        self.assertIn('data-pub-path="tasks/x/manifest.md"', item)
        self.assertIn("hubPublish(this)", item)
        self.assertIn("↗ Publish", item)

    def test_item_escapes_attribute(self):
        from hubspace.render import doc_publish_item
        item = doc_publish_item('a"b.md')
        self.assertNotIn('a"b.md"', item)      # raw quote would break the attr
        self.assertIn("&quot;", item)


class TestRenderMd(unittest.TestCase):
    def test_heading(self):
        result = render._render_md("# Hello")
        self.assertIn("<h1>", result)
        self.assertIn("Hello", result)

    def test_bold(self):
        result = render._render_md("**bold text**")
        self.assertIn("<strong>bold text</strong>", result)

    def test_italic(self):
        result = render._render_md("*italic*")
        self.assertIn("<em>italic</em>", result)

    def test_code_fence(self):
        result = render._render_md("```python\nprint('hi')\n```")
        self.assertIn("<pre>", result)
        self.assertIn("<code", result)

    def test_unordered_list(self):
        result = render._render_md("- item one\n- item two")
        self.assertIn("<ul>", result)
        self.assertIn("<li>", result)

    def test_ordered_list(self):
        result = render._render_md("1. first\n2. second")
        self.assertIn("<ol>", result)

    def test_link(self):
        result = render._render_md("[click](http://example.com)")
        self.assertIn('<a href="http://example.com">', result)

    def test_frontmatter_stripped(self):
        src = "---\ntitle: T\n---\n# Heading"
        result = render._render_md(src)
        self.assertNotIn("title:", result)
        self.assertIn("<h1>", result)

    def test_inline_code(self):
        result = render._render_md("use `foo()` here")
        self.assertIn("<code>foo()</code>", result)

    def test_table(self):
        src = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = render._render_md(src)
        self.assertIn("<table>", result)
        self.assertIn("<th ", result)  # class attribute added by typed-column renderer

    def test_blockquote(self):
        result = render._render_md("> quoted text")
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
            result = render._render_csv(__import__("pathlib").Path(name))
            self.assertIn("<table>", result)
            self.assertIn("Alice", result)
            self.assertIn("Name", result)
        finally:
            os.unlink(name)

    def test_tsv_renders_table(self):
        name = self._write_csv("Name\tScore\nAlice\t100", suffix=".tsv")
        try:
            result = render._render_csv(__import__("pathlib").Path(name))
            self.assertIn("<table>", result)
            self.assertIn("Score", result)
        finally:
            os.unlink(name)

    def test_empty_csv(self):
        name = self._write_csv("")
        try:
            result = render._render_csv(__import__("pathlib").Path(name))
            self.assertIn("Empty", result)
        finally:
            os.unlink(name)

    def test_xss_in_csv(self):
        name = self._write_csv("Col\n<script>evil</script>")
        try:
            result = render._render_csv(__import__("pathlib").Path(name))
            self.assertNotIn("<script>", result)
        finally:
            os.unlink(name)


class TestDetectColTypes(unittest.TestCase):
    def test_text_column(self):
        rows = [["Alice"], ["Bob"], ["Carol"]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["text"])

    def test_numeric_column(self):
        rows = [["100"], ["200"], ["300"]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["num"])

    def test_currency_column(self):
        rows = [["$1,234.56"], ["$200.00"], ["$99.99"]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["currency"])

    def test_percentage_column(self):
        rows = [["12.5%"], ["30%"], ["100%"]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["pct"])

    def test_empty_column_defaults_to_text(self):
        rows = [[""], [""], [""]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["text"])

    def test_mixed_col_falls_back_to_text(self):
        # Less than 60% numeric → text
        rows = [["100"], ["abc"], ["200"], ["def"], ["xyz"]]
        types = render._detect_col_types(rows, 1)
        self.assertEqual(types, ["text"])

    def test_multi_col_detection(self):
        rows = [["Alice", "100"], ["Bob", "200"], ["Carol", "300"]]
        types = render._detect_col_types(rows, 2)
        self.assertEqual(types[0], "text")
        self.assertEqual(types[1], "num")


class TestFmtCell(unittest.TestCase):
    def test_text_unchanged(self):
        self.assertEqual(render._fmt_cell("hello", "text"), "hello")

    def test_empty_value_returned_as_is(self):
        self.assertEqual(render._fmt_cell("", "num"), "")

    def test_dash_returned_as_is(self):
        self.assertEqual(render._fmt_cell("-", "num"), "-")

    def test_na_returned_as_is(self):
        self.assertEqual(render._fmt_cell("N/A", "num"), "N/A")

    def test_num_integer_formatted(self):
        self.assertEqual(render._fmt_cell("1000", "num"), "1,000")

    def test_num_with_comma_formatted(self):
        self.assertEqual(render._fmt_cell("1,000,000", "num"), "1,000,000")

    def test_num_float_formatted(self):
        result = render._fmt_cell("1234.56", "num")
        self.assertIn(",", result)
        self.assertIn("1,234", result)

    def test_currency_formatted(self):
        self.assertEqual(render._fmt_cell("$1234", "currency"), "$1,234.00")

    def test_pct_returned_unchanged(self):
        self.assertEqual(render._fmt_cell("45.5%", "pct"), "45.5%")

    def test_date_returned_unchanged(self):
        self.assertEqual(render._fmt_cell("2024-01-15", "date"), "2024-01-15")


class TestIsWithin(unittest.TestCase):
    def test_child_inside_parent(self):
        self.assertTrue(is_within(Path("/a/b/c.md"), Path("/a/b")))

    def test_child_is_parent(self):
        self.assertTrue(is_within(Path("/a/b"), Path("/a/b")))

    def test_child_outside_parent(self):
        self.assertFalse(is_within(Path("/etc/passwd"), Path("/a/b")))

    def test_prefix_not_enough(self):
        # /a/bc should not be within /a/b
        self.assertFalse(is_within(Path("/a/bc/file.md"), Path("/a/b")))


class TestRenderMdExtended(unittest.TestCase):
    def test_horizontal_rule(self):
        result = render._render_md("---")
        self.assertIn("<hr", result)

    def test_strikethrough(self):
        result = render._render_md("~~deleted~~")
        self.assertIn("<del>deleted</del>", result)

    def test_nested_list_items(self):
        src = "- parent\n  - child"
        result = render._render_md(src)
        self.assertIn("<ul>", result)

    def test_xss_in_code_fence_escaped(self):
        src = "```\n<script>alert(1)</script>\n```"
        result = render._render_md(src)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_blank_input_returns_empty_or_whitespace(self):
        result = render._render_md("")
        self.assertIsInstance(result, str)

    def test_task_checkbox_unchecked(self):
        result = render._render_md("- [ ] Todo item")
        self.assertIn("Todo item", result)

    def test_task_checkbox_checked(self):
        result = render._render_md("- [x] Done item")
        self.assertIn("Done item", result)


if __name__ == "__main__":
    unittest.main()
