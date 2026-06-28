"""CSV / XLSX files -> HTML tables (stdlib csv + zipfile + ElementTree)."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path

from .columns import _detect_col_types, _fmt_cell
from ..utils.text import esc_html


def _rows_to_table(rows: list) -> str:
    """Build an HTML table from a list of row lists; first row → header."""
    if not rows:
        return "<p>Empty file.</p>"
    head = rows[0]
    body_rows = rows[1:]
    col_types = _detect_col_types([[str(c) for c in r] for r in body_rows], len(head))
    ths = "".join(f"<th>{esc_html(c)}</th>" for c in head)
    trs = "".join(
        "<tr>" + "".join(
            "<td>"
            + esc_html(_fmt_cell(str(c), col_types[j] if j < len(col_types) else "text"))
            + "</td>"
            for j, c in enumerate(row)
        ) + "</tr>"
        for row in body_rows
    )
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>"


def _render_csv(path: Path) -> str:
    """Render a .csv/.tsv file as an HTML table (stdlib csv)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".tsv":
            delim = "\t"
        else:
            try:
                delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
            except Exception:
                delim = ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        return _rows_to_table(rows)
    except Exception as e:
        return f'<p class="empty">Could not parse {esc_html(path.name)}: {esc_html(str(e))}</p>'


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


# Built-in numFmtId values that denote dates/times (ECMA-376 §18.8.30).
_XLSX_DATE_FMTS = {14, 15, 16, 17, 22}
_XLSX_TIME_FMTS = {18, 19, 20, 21, 45, 46, 47}


def _date_kind_from_code(code: str) -> str | None:
    """Classify a custom numFmt format code as 'date', 'datetime', or None."""
    # Drop quoted literals and bracketed sections ([Red], [h], locale tags).
    c = re.sub(r'"[^"]*"', "", code.lower())
    c = re.sub(r"\[[^\]]*\]", "", c)
    has_date = "y" in c or "d" in c or "mmm" in c
    has_time = "h" in c or "s" in c or "mm:" in c or ":mm" in c
    if has_time:
        return "datetime" if has_date else "datetime"
    return "date" if has_date else None


def _xlsx_date_styles(zf: zipfile.ZipFile, names: list[str]) -> dict[int, str]:
    """Map cellXfs index → 'date'/'datetime' for date-formatted styles."""
    import xml.etree.ElementTree as ET
    if "xl/styles.xml" not in names:
        return {}
    root = ET.fromstring(zf.read("xl/styles.xml"))
    custom: dict[int, str] = {}
    for el in root.iter():
        if _strip_ns(el.tag) == "numFmt":
            fid = el.get("numFmtId")
            kind = _date_kind_from_code(el.get("formatCode") or "")
            if fid is not None and kind:
                custom[int(fid)] = kind
    styles: dict[int, str] = {}
    for el in root.iter():
        if _strip_ns(el.tag) != "cellXfs":
            continue
        idx = 0
        for xf in el:
            if _strip_ns(xf.tag) != "xf":
                continue
            nfid = xf.get("numFmtId")
            if nfid is not None:
                n = int(nfid)
                if n in _XLSX_DATE_FMTS:
                    styles[idx] = "datetime" if n == 22 else "date"
                elif n in _XLSX_TIME_FMTS:
                    styles[idx] = "datetime"
                elif n in custom:
                    styles[idx] = custom[n]
            idx += 1
        break
    return styles


def _excel_serial_to_str(val: str, kind: str) -> str:
    """Convert an Excel serial date number to an ISO date/datetime string."""
    from datetime import datetime, timedelta
    try:
        n = float(val)
    except ValueError:
        return val
    # Excel's epoch is 1899-12-30 (the offset absorbs the fictional 1900 leap day).
    dt = datetime(1899, 12, 30) + timedelta(days=n)
    if kind == "datetime" and (dt.hour or dt.minute or dt.second):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y-%m-%d")


def _render_xlsx(path: Path) -> str:
    """Render the first worksheet of an .xlsx file as an HTML table (stdlib zipfile + xml)."""
    import xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for si in ss_root:
                    parts = [t.text or "" for t in si.iter()
                             if _strip_ns(t.tag) == "t"]
                    shared.append("".join(parts))

            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in names:
                sheets = sorted(n for n in names
                                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
                if not sheets:
                    return '<p class="empty">No worksheet found.</p>'
                sheet_name = sheets[0]
            sheet_root = ET.fromstring(zf.read(sheet_name))
            date_styles = _xlsx_date_styles(zf, names)

        rows: list = []
        for el in sheet_root.iter():
            if _strip_ns(el.tag) != "row":
                continue
            cells: list[str] = []
            for c in el:
                if _strip_ns(c.tag) != "c":
                    continue
                ctype = c.get("t")
                val = ""
                for child in c:
                    if _strip_ns(child.tag) == "v":
                        val = child.text or ""
                        break
                    if _strip_ns(child.tag) == "is":
                        val = "".join(t.text or "" for t in child.iter()
                                      if _strip_ns(t.tag) == "t")
                        break
                if ctype == "s":
                    try:
                        val = shared[int(val)]
                    except (ValueError, IndexError):
                        val = ""
                elif ctype in (None, "n") and val:
                    # Numeric cell: a date-formatted style means the raw value is
                    # an Excel serial number — convert it to a readable date.
                    sidx = c.get("s")
                    kind = date_styles.get(int(sidx)) if sidx is not None else None
                    if kind:
                        val = _excel_serial_to_str(val, kind)
                cells.append(val)
            rows.append(cells)
        return _rows_to_table(rows)
    except Exception as e:
        return f'<p class="empty">Could not parse {esc_html(path.name)}: {esc_html(str(e))}</p>'


