"""Rendering regression tests for the known M2 problem cases (PRD §10).

Not pixel snapshots (can't render headlessly with stdlib) — these pin the
*output shape* of the three documents that historically broke rendering:
  1. an XIRR-style .xlsx workbook (stdlib zipfile shared-string extraction),
  2. a 1,000-row markdown table (no truncation, well-formed),
  3. a deeply-nested CLAUDE.md outline (the overlap fix, b307882).
"""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace import metadata, server


def _make_xlsx(path: Path, shared_strings: list[str]) -> None:
    """Write a minimal .xlsx whose sharedStrings.xml holds the given <t> values."""
    ts = "".join(f"<si><t>{s}</t></si>" for s in shared_strings)
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">{ts}</sst>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", shared)


class TestXlsxXirr(unittest.TestCase):
    def test_xirr_workbook_body_extracted(self):
        with tempfile.TemporaryDirectory() as d:
            xlsx = Path(d) / "xirr.xlsx"
            _make_xlsx(xlsx, ["XIRR", "Cash Flow", "Date", "2026-01-01", "Net Return"])
            body = metadata._extract_xlsx_body(str(xlsx), 2000)
        self.assertIn("XIRR", body)
        self.assertIn("Cash Flow", body)
        self.assertIn("Net Return", body)

    def test_no_shared_strings_returns_empty(self):
        with tempfile.TemporaryDirectory() as d:
            xlsx = Path(d) / "empty.xlsx"
            with zipfile.ZipFile(xlsx, "w") as zf:
                zf.writestr("xl/workbook.xml", "<workbook/>")
            self.assertEqual(metadata._extract_xlsx_body(str(xlsx), 2000), "")

    def test_corrupt_file_returns_empty_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.xlsx"
            bad.write_bytes(b"not a zip")
            self.assertEqual(metadata._extract_xlsx_body(str(bad), 2000), "")


class TestLargeTable(unittest.TestCase):
    def test_thousand_row_table_not_truncated(self):
        header = "| id | value |\n| --- | --- |\n"
        rows = "".join(f"| {i} | v{i} |\n" for i in range(1000))
        html = server._render_md(header + rows)
        self.assertEqual(html.count("<table>"), 1)
        # 1000 body rows (header <tr> lives inside <thead>, counted separately).
        tbody = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
        self.assertEqual(tbody.count("<tr>"), 1000)
        self.assertIn("v999", html)


class TestDeepOutline(unittest.TestCase):
    def test_deep_headings_get_anchors_and_outline(self):
        # Mimic a deep CLAUDE.md: many headings, h1..h4.
        levels = [1, 2, 3, 4, 2, 3, 3, 2]
        html = "".join(f"<h{n}>Heading {i}</h{n}>" for i, n in enumerate(levels))
        body, outline = server._add_outline(html)
        # h1–h3 get an id injected so anchors resolve; h4+ are intentionally
        # left out of the outline (the depth cap that fixed the overlap).
        expected_ids = sum(1 for n in levels if n <= 3)
        self.assertEqual(body.count("id="), expected_ids)
        self.assertIn("Heading 3", body)            # the h4 heading still renders
        self.assertNotRegex(body, r'<h4 id=')        # …just without an outline anchor
        # An outline is produced with navigable links.
        self.assertIn("outline", outline)
        self.assertGreaterEqual(outline.count("<a "), 2)

    def test_outline_depth_capped_to_lvl3(self):
        # The overlap fix caps indentation classes at lvl3 — deeper headings
        # must not emit lvl4+ classes that would run off the panel.
        html = "".join(f"<h{n}>H{n}</h{n}>" for n in (1, 2, 3, 4, 5, 6))
        _body, outline = server._add_outline(html)
        self.assertNotIn("lvl4", outline)
        self.assertNotIn("lvl5", outline)


if __name__ == "__main__":
    unittest.main()
