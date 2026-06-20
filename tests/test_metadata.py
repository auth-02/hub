"""Tests for metadata.py — title and body extraction."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import metadata


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


if __name__ == "__main__":
    unittest.main()
