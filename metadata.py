"""Metadata extraction for hub: title and body text from markdown/html files."""
from __future__ import annotations
import re
from pathlib import Path


def read_safe(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def extract_title(path: str, text: str) -> str:
    """Return first # heading, frontmatter title:, or filename stem."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if m:
        t = re.search(r"^title:\s*['\"]?(.+?)['\"]?\s*$", m.group(1), re.MULTILINE)
        if t:
            return t.group(1).strip()
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return Path(path).stem.replace("-", " ").replace("_", " ").title()


def extract_body(path: str, text: str, max_chars: int = 2000) -> str:
    """Strip markup → searchable plain text. HTML files get paragraph-aware stripping."""
    ext = Path(path).suffix.lower()
    if ext in (".html", ".htm"):
        return _extract_html_body(text, max_chars)
    # markdown / txt
    text = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, flags=re.DOTALL)
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]{1,200}>", " ", text)
    text = re.sub(r"[#*_~>|\\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _extract_html_body(text: str, max_chars: int) -> str:
    """Extract readable text from HTML, preserving paragraph breaks."""
    # drop script, style, head entirely
    text = re.sub(r"<(script|style|head)[^>]*>[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    # block elements → double newline
    BLOCKS = r"p|div|h[1-6]|li|tr|blockquote|pre|section|article|header|footer|main|br"
    text = re.sub(rf"</?(?:{BLOCKS})[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    # strip remaining tags
    text = re.sub(r"<[^>]{1,400}>", " ", text)
    # decode common entities
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&[a-z]+;|&#\d+;", " ", text)
    # collapse whitespace within lines, keep paragraph breaks
    lines = [re.sub(r" {2,}", " ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_chars]
