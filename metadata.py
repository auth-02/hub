"""Metadata extraction for hub: title and body text from markdown/html files."""
from __future__ import annotations
import re
import zipfile
from pathlib import Path

# Pre-compiled patterns — compiled once at import time, not per call.
_FRONTMATTER   = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_FM_TITLE      = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)
_FM_STATUS     = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)
_PLAN_ITEM     = re.compile(r"^- \[( |x)\] (.+)$", re.MULTILINE | re.IGNORECASE)
_H1            = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_MD_FM_STRIP   = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.DOTALL)
_MD_FENCE      = re.compile(r"```[\s\S]*?```")
_MD_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_IMAGE      = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK       = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_TAG        = re.compile(r"<[^>]{1,200}>")
_MD_PUNCT      = re.compile(r"[#*_~>|\\]")
_WHITESPACE    = re.compile(r"\s+")
_CSV_WS        = re.compile(r"\s+")

_HTML_SCRIPT   = re.compile(r"<(script|style|head)[^>]*>[\s\S]*?</\1>", re.IGNORECASE)
_HTML_BLOCK    = re.compile(
    r"</?(?:p|div|h[1-6]|li|tr|blockquote|pre|section|article|header|footer|main|br)[^>]*>",
    re.IGNORECASE,
)
_HTML_TAG      = re.compile(r"<[^>]{1,400}>")
_HTML_AMP      = re.compile(r"&amp;")
_HTML_LT       = re.compile(r"&lt;")
_HTML_GT       = re.compile(r"&gt;")
_HTML_NBSP     = re.compile(r"&nbsp;|&#160;")
_HTML_ENTITY   = re.compile(r"&[a-z]+;|&#\d+;")
_HTML_MULTI_SP = re.compile(r"  +")
_HTML_MULTI_NL = re.compile(r"\n{3,}")

# Input is truncated to this many chars before regex processing — we only need
# 2000 chars of plain-text output, so running patterns over full 400KB files is waste.
_READ_LIMIT = 30_000


def read_safe(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def extract_title(path: str, text: str) -> str:
    """Return first # heading, frontmatter title:, or filename stem."""
    # Only look at the top of the file for frontmatter / headings.
    head = text[:2000]
    if head.startswith("---"):
        m = _FRONTMATTER.match(head)
        if m:
            t = _FM_TITLE.search(m.group(1))
            if t:
                return t.group(1).strip()
    m = _H1.search(head)
    if m:
        return m.group(1).strip()
    return Path(path).stem.replace("-", " ").replace("_", " ").title()


_VALID_STATUSES = {"ongoing", "paused", "completed"}


def extract_status(text: str) -> str:
    """Return status from frontmatter, defaulting to 'ongoing' per spec §4.1."""
    head = text[:2000]
    if head.startswith("---"):
        m = _FRONTMATTER.match(head)
        if m:
            s = _FM_STATUS.search(m.group(1))
            if s:
                val = s.group(1).lower().strip("\"'")
                if val in _VALID_STATUSES:
                    return val
    return "ongoing"


def extract_plan(text: str) -> list:
    """Extract plan checkboxes from markdown. Returns [{d: bool, t: str}, ...]."""
    items = []
    for m in _PLAN_ITEM.finditer(text[:10_000]):
        items.append({"d": m.group(1).lower() == "x", "t": m.group(2).strip()})
    return items


def extract_body(path: str, text: str, max_chars: int = 2000) -> str:
    """Strip markup → searchable plain text. HTML files get paragraph-aware stripping."""
    ext = Path(path).suffix.lower()
    if ext in (".html", ".htm"):
        return _extract_html_body(text[:_READ_LIMIT], max_chars)
    if ext in (".pdf", ".xls"):
        return ""
    if ext == ".xlsx":
        return _extract_xlsx_body(path, max_chars)
    if ext in (".csv", ".tsv"):
        return _CSV_WS.sub(" ", text[:_READ_LIMIT]).strip()[:max_chars]
    # markdown / txt
    text = text[:_READ_LIMIT]
    if text.startswith("---"):
        text = _MD_FM_STRIP.sub("", text, count=1)
    text = _MD_FENCE.sub(" ", text)
    text = _MD_INLINE_CODE.sub(" ", text)
    text = _MD_IMAGE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MD_TAG.sub(" ", text)
    text = _MD_PUNCT.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()[:max_chars]


def _extract_xlsx_body(path: str, max_chars: int) -> str:
    """Concatenate shared-string text from an .xlsx workbook for searching."""
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                raw = zf.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            except KeyError:
                return ""
        texts = re.findall(r"<t[^>]*>(.*?)</t>", raw, re.DOTALL)
        joined = " ".join(
            t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            for t in texts
        )
        return _WHITESPACE.sub(" ", joined).strip()[:max_chars]
    except Exception:
        return ""


def _extract_html_body(text: str, max_chars: int) -> str:
    """Extract readable text from HTML, preserving paragraph breaks."""
    text = _HTML_SCRIPT.sub(" ", text)
    text = _HTML_BLOCK.sub("\n\n", text)
    text = _HTML_TAG.sub(" ", text)
    text = _HTML_AMP.sub("&", text)
    text = _HTML_LT.sub("<", text)
    text = _HTML_GT.sub(">", text)
    text = _HTML_NBSP.sub(" ", text)
    text = _HTML_ENTITY.sub(" ", text)
    # Collapse runs of spaces per line without looping over every line.
    text = _HTML_MULTI_SP.sub(" ", text)
    text = _HTML_MULTI_NL.sub("\n\n", text)
    return text.strip()[:max_chars]
