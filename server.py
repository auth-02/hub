#!/usr/bin/env python3
"""
server.py — serve hub's scan root, rendering .md files on request.

Usage:
    python3 server.py              # default port 8787
    python3 server.py --port 9000
    HUB_SERVER_PORT=9000 python3 server.py

Rebuild after starting so links use localhost:
    HUB_SERVER_PORT=8787 python3 hub.py
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import re
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote

# ── Scan root resolution (mirrors hub.py) ──────────────────────────────────
_HERE = Path(__file__).resolve().parent
_SIDECAR = Path.home() / "agents" / "hub" / ".scan_root"
_DB_PATH = Path.home() / ".hub-state" / "hub.db"


def _get_lineage(abs_path: str) -> list:
    """Return lineage links for abs_path from hub.db (empty list if DB missing or file unknown)."""
    try:
        if not _DB_PATH.exists():
            return []
        conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        rows = conn.execute(
            """SELECT f2.abs, f2.rel, f2.kind, l.rel_type
               FROM lineage l
               JOIN files f1 ON f1.id = l.src_id
               JOIN files f2 ON f2.id = l.dst_id
               WHERE f1.abs = ?""",
            (abs_path,),
        ).fetchall()
        conn.close()
        return [{"a": r[0], "p": r[1], "k": r[2] or "", "r": r[3]} for r in rows]
    except Exception:
        return []


_LINEAGE_ORDER = [
    "belongs_to_task", "task_has_run", "task_has_artifact", "task_has_prompt", "task_has_doc",
]
_LINEAGE_LABELS = {
    "belongs_to_task": "↑ task",
    "task_has_run": "runs",
    "task_has_artifact": "artifacts",
    "task_has_prompt": "prompts",
    "task_has_doc": "docs",
}


_BACKLINKS_CSS = (
    ":root{--bg:#F4EFE4;--alt:#ECE5D2;--line:#D9D1BC;--accent:#7A2828;--accent2:#1E5A6B;"
    "--mute:#8A8377;--mono:'SF Mono',Menlo,'Cascadia Code',monospace;}"
    ".backlinks{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:10px 0;"
    "border-bottom:1px solid var(--line);margin-bottom:1.5rem;}"
    ".backlinks-label{font-family:var(--mono);font-size:9px;letter-spacing:.18em;"
    "text-transform:uppercase;color:var(--accent);flex-shrink:0;}"
    ".backlinks-group{display:flex;align-items:center;gap:6px;flex-shrink:0;}"
    ".backlinks-type{font-family:var(--mono);font-size:9px;color:var(--mute);}"
    ".backlinks-item{font-family:var(--mono);font-size:10px;padding:3px 8px;"
    "border:1px solid var(--line);color:var(--mute);background:var(--alt);"
    "white-space:nowrap;text-decoration:none;display:inline-block;}"
    ".backlinks-item:hover{border-color:var(--accent2);color:var(--accent2);}"
    "html{scroll-behavior:smooth;}"
    "h1,h2,h3{scroll-margin-top:90px;}"
    ".outline{position:fixed;top:80px;left:max(16px,calc(50% - 600px));width:180px;"
    "max-height:calc(100vh - 120px);overflow-y:auto;font-family:var(--mono);"
    "font-size:11px;line-height:1.5;z-index:50;}"
    ".outline-label{font-size:9px;letter-spacing:.18em;text-transform:uppercase;"
    "color:var(--accent);margin-bottom:8px;}"
    ".outline a{display:block;color:var(--mute);text-decoration:none;padding:2px 0;"
    "border-left:1px solid var(--line);padding-left:10px;}"
    ".outline a:hover{color:var(--accent2);border-left-color:var(--accent2);}"
    ".outline a.lvl2{padding-left:22px;}"
    ".outline a.lvl3{padding-left:34px;}"
    "@media (max-width:1200px){.outline{display:none;}}"
    "@media print{.outline{display:none;}}"
)

# Shared doc chrome: the "⤓ PDF" print button + print stylesheet. Reused by both
# the markdown page wrapper (_CSS/_PAGE) and injected HTML docs (_inject_into_html).
_DOC_CHROME_CSS = (
    ".doc-print{position:fixed;top:18px;right:18px;z-index:40;font-family:var(--mono);"
    "font-size:10px;letter-spacing:.12em;text-transform:uppercase;padding:7px 12px;"
    "border:1px solid var(--line);background:var(--alt);color:var(--accent);cursor:pointer;}"
    ".doc-print:hover{border-color:var(--accent);background:var(--accent);color:#fff;}"
    "@media print{"
    ".doc-print,nav,.backlinks,.outline{display:none!important;}"
    "body{padding:0!important;background:#fff!important;background-image:none!important;"
    "-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
    ".page{max-width:100%!important;margin:0!important;}"
    "pre,code,th,blockquote,td{-webkit-print-color-adjust:exact;print-color-adjust:exact;}"
    "a{color:var(--ink)!important;text-decoration:none!important;}"
    "}"
)
_DOC_PRINT_BTN = (
    '<button class="doc-print" onclick="window.print()" '
    'title="Save as PDF (Cmd/Ctrl+P)">⤓ PDF</button>'
)


def _favicon_href(port: int) -> str:
    return f"http://localhost:{port}" + quote(str(_HERE / "assets" / "favicon.svg"), safe="/:@")


def _inject_into_html(src: str, lineage_html: str, favicon: str = "") -> str:
    """Inject backlinks CSS + HTML into an existing HTML document."""
    src, outline_html = _add_outline(src)
    head_inject = f"<style>{_BACKLINKS_CSS}{_DOC_CHROME_CSS}</style>"
    if favicon:
        head_inject = f'<link rel="icon" type="image/svg+xml" href="{favicon}">' + head_inject
    src = re.sub(r"</head>", head_inject + "</head>", src, count=1, flags=re.IGNORECASE)
    # Print button goes right after <body> so it floats over the doc.
    src = re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + _DOC_PRINT_BTN, src, count=1, flags=re.IGNORECASE)
    if outline_html:
        src = re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + outline_html, src, count=1, flags=re.IGNORECASE)
    m = re.search(r"</h1>", src, re.IGNORECASE)
    if m:
        return src[: m.end()] + lineage_html + src[m.end() :]
    return re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + lineage_html, src, count=1, flags=re.IGNORECASE)


def _render_lineage_html(links: list, port: int) -> str:
    """Render lineage links as a backlinks section appended to the doc page."""
    if not links:
        return ""

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    groups: dict = {}
    for link in links:
        groups.setdefault(link["r"], []).append(link)

    parts = ['<div class="backlinks"><div class="backlinks-label">// trace</div>']
    for rel_type in _LINEAGE_ORDER:
        if rel_type not in groups:
            continue
        label = _LINEAGE_LABELS.get(rel_type, rel_type)
        parts.append(
            f'<div class="backlinks-group">'
            f'<span class="backlinks-type">{_esc(label)}</span>'
        )
        for link in groups[rel_type]:
            name = link["p"].split("/")[-1]
            href = f"http://localhost:{port}" + quote(link["a"], safe="/:@")
            parts.append(
                f'<a class="backlinks-item" href="{href}" title="{_esc(link["p"])}">'
                f'{_esc(name)}</a>'
            )
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


def _resolve_scan_root() -> Path:
    env = os.environ.get("HUB_SCAN_ROOT")
    if env:
        return Path(env).expanduser()
    try:
        text = _SIDECAR.read_text(encoding="utf-8").strip()
        if text:
            return Path(text).expanduser()
    except OSError:
        pass
    return Path.home() / "tifin"


SCAN_ROOT = _resolve_scan_root()
_active_root: Path = SCAN_ROOT  # updated by _set_root(); used by rebuild + watcher

# ── Hub theme (CSS vars match hub_template.html) ───────────────────────────
_CSS = """
:root{
  --bg:#F4EFE4;--alt:#ECE5D2;--deep:#E4DCC4;
  --ink:#1A1A1A;--mute:#8A8377;--line:#D9D1BC;
  --accent:#7A2828;--accent2:#1E5A6B;
  --disp:Georgia,'Times New Roman',serif;
  --body:system-ui,-apple-system,sans-serif;
  --mono:'SF Mono',Menlo,'Cascadia Code',monospace;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{
  background:var(--bg);color:var(--ink);
  font-family:var(--body);font-size:15px;line-height:1.75;
  padding:2.5rem 1.5rem 5rem;
  background-image:radial-gradient(circle,#C9BFA3 .7px,transparent .7px);
  background-size:22px 22px;
}
.page{max-width:860px;margin:0 auto;}
nav{
  font-family:var(--mono);font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--mute);
  margin-bottom:2rem;padding-bottom:1rem;border-bottom:1px solid var(--line);
}
nav a{color:var(--accent);text-decoration:none;}
nav a:hover{text-decoration:underline;}

/* Headings */
h1{font-family:var(--disp);font-weight:500;font-style:italic;font-size:2rem;
   color:var(--accent);margin:0 0 1.25rem;letter-spacing:-.01em;line-height:1.25;}
h2{font-family:var(--disp);font-style:italic;font-size:1.4rem;
   color:var(--ink);margin:2rem 0 .6rem;font-weight:500;}
h3{font-family:var(--mono);font-size:.8rem;letter-spacing:.14em;
   text-transform:uppercase;color:var(--mute);margin:1.5rem 0 .4rem;}
h4,h5,h6{font-size:.9375rem;color:var(--ink);margin:1.25rem 0 .4rem;}
p{margin:.75rem 0;}
a{color:var(--accent2);}

/* Code */
code{font-family:var(--mono);font-size:.84em;background:var(--deep);
     border:1px solid var(--line);padding:.12em .4em;border-radius:3px;}
pre{background:var(--deep);border:1px solid var(--line);
    padding:1rem 1.1rem;overflow-x:auto;margin:1rem 0;border-radius:4px;}
pre code{background:none;border:none;padding:0;font-size:.84rem;line-height:1.55;}

/* Block elements */
blockquote{border-left:3px solid var(--accent);padding:.3rem 0 .3rem 1rem;
           color:var(--mute);margin:1rem 0;}
blockquote p{margin:.2rem 0;}
table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.9rem;}
th,td{border:1px solid var(--line);padding:.45rem .75rem;text-align:left;}
th{background:var(--deep);font-family:var(--mono);font-size:.8rem;
   letter-spacing:.06em;text-transform:uppercase;}
tr:nth-child(even) td{background:rgba(0,0,0,.02);}
hr{border:none;border-top:1px solid var(--line);margin:2rem 0;}
ul,ol{margin:.75rem 0 .75rem 1.75rem;}
li{margin:.25rem 0;}
img{max-width:100%;border-radius:4px;display:block;margin:1rem 0;}

/* Backlinks / trace */
.backlinks{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line);margin-bottom:1.5rem;}
.backlinks-label{font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent);flex-shrink:0;}
.backlinks-group{display:flex;align-items:center;gap:6px;flex-shrink:0;}
.backlinks-type{font-family:var(--mono);font-size:9px;color:var(--mute);}
.backlinks-item{font-family:var(--mono);font-size:10px;padding:3px 8px;border:1px solid var(--line);color:var(--mute);background:var(--alt);white-space:nowrap;text-decoration:none;display:inline-block;}
.backlinks-item:hover{border-color:var(--accent2);color:var(--accent2);}

/* Document outline / TOC */
html{scroll-behavior:smooth;}
h1,h2,h3{scroll-margin-top:90px;}
.outline{position:fixed;top:80px;left:max(16px,calc(50% - 600px));width:180px;
  max-height:calc(100vh - 120px);overflow-y:auto;font-family:var(--mono);
  font-size:11px;line-height:1.5;z-index:50;}
.outline-label{font-size:9px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px;}
.outline a{display:block;color:var(--mute);text-decoration:none;padding:2px 0;
  border-left:1px solid var(--line);padding-left:10px;}
.outline a:hover{color:var(--accent2);border-left-color:var(--accent2);}
.outline a.lvl2{padding-left:22px;}
.outline a.lvl3{padding-left:34px;}
@media (max-width:1200px){.outline{display:none;}}
@media print{.outline{display:none;}}

/* Directory listing */
.dir-list{list-style:none;margin:0;padding:0;}
.dir-list li{border-bottom:1px solid var(--line);}
.dir-list li:last-child{border-bottom:none;}
.dir-list a{
  display:flex;align-items:center;gap:.75rem;
  padding:.6rem .25rem;text-decoration:none;color:var(--ink);
  font-family:var(--mono);font-size:.8125rem;
}
.dir-list a:hover{background:var(--alt);}
.dir-list .ext{margin-left:auto;color:var(--mute);font-size:.75rem;}
"""

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" type="image/svg+xml" href="{favicon}">
<style>{css}</style>
</head>
<body><button class="doc-print" onclick="window.print()" title="Save as PDF (Cmd/Ctrl+P)">⤓ PDF</button><div class="page">
{nav}
{body}
</div></body>
</html>
"""


# ── Markdown renderer (stdlib only) ────────────────────────────────────────

def _inline(text: str) -> str:
    """Apply inline markdown: code, images, links, bold, italic, strikethrough."""
    # Protect inline code
    icodes: list[str] = []

    def _save(m: re.Match) -> str:
        s = m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        icodes.append(s)
        return f"\x04{len(icodes)-1}\x05"

    text = re.sub(r"`([^`\n]+)`", _save, text)

    # Images before links
    text = re.sub(
        r"!\[([^\]]*)\]\(([^\s)]+)\)",
        lambda m: f'<img src="{m.group(2)}" alt="{m.group(1)}">',
        text,
    )
    # Links
    text = re.sub(
        r"\[([^\]]+)\]\(([^\s)]+)\)",
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>',
        text,
    )
    # Auto-links
    text = re.sub(
        r"<(https?://[^\s>]+)>",
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>',
        text,
    )

    # Bold + italic (order: longest first)
    text = re.sub(r"\*{3}(.+?)\*{3}", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"_{3}(.+?)_{3}", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*{2}(.+?)\*{2}", r"<strong>\1</strong>", text)
    text = re.sub(r"_{2}(.+?)_{2}", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"_([^_\n]+)_", r"<em>\1</em>", text)
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)

    for idx, code in enumerate(icodes):
        text = text.replace(f"\x04{idx}\x05", f"<code>{code}</code>")

    return text


def _render_md(src: str) -> str:
    """Convert a markdown string to an HTML fragment."""

    # Strip YAML frontmatter
    src = re.sub(r"^---[ \t]*\n.*?\n---[ \t]*\n?", "", src, count=1, flags=re.DOTALL)

    # Protect fenced code blocks
    fences: list[str] = []

    def _fence(m: re.Match) -> str:
        lang = m.group(1).strip()
        body = m.group(2).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cls = f' class="language-{lang}"' if lang else ""
        fences.append(f"<pre><code{cls}>{body}</code></pre>")
        return f"\x02{len(fences)-1}\x03"

    src = re.sub(r"`{3,}(\w*)\n([\s\S]*?)`{3,}", _fence, src)

    lines = src.splitlines()
    N = len(lines)
    out: list[str] = []
    i = 0

    while i < N:
        line = lines[i]
        stripped = line.strip()

        # Fence placeholder
        if re.match(r"^\x02\d+\x03$", stripped):
            out.append(fences[int(stripped[1:-1])])
            i += 1
            continue

        # Blank line
        if not stripped:
            i += 1
            continue

        # ATX heading
        m = re.match(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        # Horizontal rule (standalone ---, ***, ___)
        if re.match(r"^(\*[ \t]*){3,}$|^(-[ \t]*){3,}$|^(_[ \t]*){3,}$", stripped):
            out.append("<hr>")
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            bq: list[str] = []
            while i < N and (lines[i].startswith(">") or (bq and not lines[i].strip())):
                l = lines[i]
                if l.startswith(">"):
                    bq.append(l[2:] if l[1:2] == " " else l[1:])
                else:
                    bq.append("")
                i += 1
            while bq and not bq[-1]:
                bq.pop()
            inner = _render_md("\n".join(bq))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # Unordered list
        if re.match(r"^[ \t]*[-*+][ \t]+", line):
            items: list[str] = []
            while i < N and re.match(r"^[ \t]*[-*+][ \t]+", lines[i]):
                content = re.sub(r"^[ \t]*[-*+][ \t]+", "", lines[i])
                items.append(f"<li>{_inline(content)}</li>")
                i += 1
            out.append("<ul>\n" + "\n".join(items) + "\n</ul>")
            continue

        # Ordered list
        if re.match(r"^[ \t]*\d+\.[ \t]+", line):
            items = []
            while i < N and re.match(r"^[ \t]*\d+\.[ \t]+", lines[i]):
                content = re.sub(r"^[ \t]*\d+\.[ \t]+", "", lines[i])
                items.append(f"<li>{_inline(content)}</li>")
                i += 1
            out.append("<ol>\n" + "\n".join(items) + "\n</ol>")
            continue

        # Table (header | separator row)
        if "|" in line and i + 1 < N and re.match(r"^[\s|:=-]+$", lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator
            rows: list[list[str]] = []
            while i < N and "|" in lines[i]:
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            ths = "".join(f"<th>{_inline(h)}</th>" for h in headers)
            trs = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>"
                for row in rows
            )
            out.append(f"<table><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>")
            continue

        # Paragraph — collect until a block-level boundary
        para: list[str] | None = []
        while i < N:
            l = lines[i]
            ls = l.strip()

            if (not ls
                    or re.match(r"^#{1,6}\s", l)
                    or re.match(r"^(\*[ \t]*){3,}$|^(-[ \t]*){3,}$|^(_[ \t]*){3,}$", ls)
                    or l.startswith(">")
                    or re.match(r"^[ \t]*[-*+][ \t]+", l)
                    or re.match(r"^[ \t]*\d+\.[ \t]+", l)
                    or re.match(r"^\x02\d+\x03$", ls)):
                break

            # Setext h1
            if i + 1 < N and re.match(r"^=+[ \t]*$", lines[i + 1]):
                out.append(f"<h1>{_inline(ls)}</h1>")
                i += 2
                para = None
                break

            # Setext h2
            if i + 1 < N and re.match(r"^-+[ \t]*$", lines[i + 1]):
                out.append(f"<h2>{_inline(ls)}</h2>")
                i += 2
                para = None
                break

            assert para is not None
            para.append(ls)
            i += 1

        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")

    result = "\n".join(out)
    for idx, fence in enumerate(fences):
        result = result.replace(f"\x02{idx}\x03", fence)
    return result


# ── Document outline / TOC ───────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Lowercase, strip HTML tags, collapse non-alphanumeric runs to '-', trim."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _add_outline(body_html: str) -> tuple[str, str]:
    """Inject ids into h1-h3 tags and build a floating outline nav.

    Returns (body_html_with_ids, outline_html). If fewer than 2 headings are
    found, returns (body_html, "") unchanged.
    """
    headings: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}

    def _inject(m: re.Match) -> str:
        level = int(m.group(1))
        inner = m.group(2)
        plain = re.sub(r"<[^>]+>", "", inner).strip()
        slug = _slugify(plain) or "section"
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 1
        headings.append((level, plain, slug))
        return f'<h{level} id="{slug}">{inner}</h{level}>'

    body_html = re.sub(r"<h([1-3])>(.*?)</h\1>", _inject, body_html, flags=re.DOTALL)

    if len(headings) < 2:
        return body_html, ""

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts = ['<nav class="outline"><div class="outline-label">// outline</div>']
    for level, plain, slug in headings:
        cls = f" lvl{level}" if level > 1 else ""
        parts.append(f'<a class="outline-link{cls}" href="#{slug}">{_esc(plain)}</a>')
    parts.append("</nav>")
    return body_html, "".join(parts)


# ── Request handler ─────────────────────────────────────────────────────────

def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


class HubHandler(http.server.BaseHTTPRequestHandler):
    server_port: int = 8787

    def do_GET(self) -> None:
        url_path = unquote(self.path.split("?")[0])

        # Rebuild trigger
        if url_path == "/_rebuild":
            self._run_rebuild()
            return

        # Root → hub index
        if url_path in ("/", ""):
            docs = _HERE / "build" / "docs-index.html"
            if docs.exists():
                self._send(200, "text/html; charset=utf-8", docs.read_bytes())
            else:
                self._send(404, "text/plain", b"docs-index.html not found - run hub.py first.")
            return

        fs_path = Path(url_path)

        # Absolute path from hub _href() → use directly.
        # Relative/short path (e.g. after replaceState rewrites URL) →
        # resolve against active scan root.
        if not fs_path.is_absolute() or not fs_path.exists():
            candidate = _active_root / url_path.lstrip("/")
            if candidate.exists():
                fs_path = candidate

        # Security: must be within scan root or hub directory
        resolved = fs_path.resolve()
        if not (
            _is_within(resolved, _active_root.resolve())
            or _is_within(resolved, _HERE.resolve())
        ):
            self._send(403, "text/plain", b"Forbidden")
            return

        if not fs_path.exists():
            self._send(404, "text/plain", f"Not found: {fs_path}".encode())
            return

        if fs_path.is_dir():
            self._serve_dir(fs_path, url_path)
        elif fs_path.suffix.lower() == ".md":
            self._serve_md(fs_path)
        elif fs_path.suffix.lower() in (".html", ".htm"):
            src = fs_path.read_text(encoding="utf-8", errors="replace")
            links = _get_lineage(str(fs_path.resolve()))
            lineage_html = _render_lineage_html(links, self.__class__.server_port) if links else ""
            src = _inject_into_html(src, lineage_html, _favicon_href(self.__class__.server_port))
            self._send(200, "text/html; charset=utf-8", src.encode("utf-8"))
        elif fs_path.suffix.lower() == ".txt":
            src = fs_path.read_text(encoding="utf-8", errors="replace")
            escaped = src.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._serve_page(fs_path.name, fs_path, f"<pre><code>{escaped}</code></pre>")
        else:
            ct, _ = mimetypes.guess_type(str(fs_path))
            self._send(200, ct or "application/octet-stream", fs_path.read_bytes())

    def do_POST(self) -> None:
        url_path = unquote(self.path.split("?")[0])
        if url_path == "/_set-root":
            length = int(self.headers.get("Content-Length", 0))
            new_root = self.rfile.read(length).decode("utf-8").strip()
            self._set_root(new_root)
        elif url_path == "/_task-status":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                task_slug = body["task_slug"]
                task_repo = body["task_repo"]
                status = body["status"]
                if status not in ("ongoing", "completed", "paused"):
                    self._send(400, "text/plain", b"invalid status")
                    return
                import sys as _sys
                _sys.path.insert(0, str(_HERE))
                import db as _db
                conn = sqlite3.connect(str(_DB_PATH))
                _db.set_status(conn, task_slug, task_repo, status)
                conn.close()
                self._send(200, "text/plain", b"ok")
            except Exception as e:
                self._send(400, "text/plain", str(e).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def _set_root(self, new_root: str) -> None:
        global _active_root
        p = Path(new_root).expanduser().resolve()
        if not p.is_dir():
            self._send(400, "text/plain", b"Not a directory")
            return
        try:
            _SIDECAR.write_text(str(p), encoding="utf-8")
        except OSError as e:
            self._send(500, "text/plain", str(e).encode())
            return
        _active_root = p
        result = self._rebuild(p)
        if result.returncode == 0:
            self._send(200, "text/plain", b"ok")
        else:
            self._send(500, "text/plain", result.stderr.encode())

    def _run_rebuild(self) -> None:
        result = self._rebuild(_active_root)
        if result.returncode == 0:
            self._send(200, "text/plain", b"ok")
        else:
            self._send(500, "text/plain", result.stderr.encode())

    @staticmethod
    def _rebuild(root: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HUB_SERVER_PORT"] = str(HubHandler.server_port)
        env["HUB_SCAN_ROOT"] = str(root)
        return subprocess.run(
            [sys.executable, str(_HERE / "hub.py")],
            env=env, capture_output=True, text=True,
        )

    def _serve_md(self, path: Path) -> None:
        src = path.read_text(encoding="utf-8", errors="replace")
        body = _render_md(src)
        self._serve_page(path.name, path, body)

    def _serve_dir(self, path: Path, url_path: str) -> None:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        rows: list[str] = []

        parent = str(Path(url_path).parent)
        if url_path != str(SCAN_ROOT):
            rows.append(f'<li><a href="{parent}">↑ ../</a></li>')

        for entry in entries:
            if entry.is_dir():
                icon, href = "📁", str(Path(url_path) / entry.name) + "/"
                ext_html = ""
            else:
                icon = "📝" if entry.suffix.lower() in (".md", ".txt") else "📄"
                href = str(Path(url_path) / entry.name)
                ext_html = f'<span class="ext">{entry.suffix}</span>' if entry.suffix else ""
            rows.append(
                f'<li><a href="{href}">{icon} {entry.name}{ext_html}</a></li>'
            )

        body = f"<ul class='dir-list'>{''.join(rows)}</ul>"
        self._serve_page(url_path, path, body)

    def _serve_page(self, title: str, path: Path, body: str) -> None:
        try:
            rel = path.resolve().relative_to(_active_root.resolve())
            parts = [_active_root.name] + list(rel.parts)
            nav_html = f'<nav>{" / ".join(parts)}</nav>'
        except ValueError:
            nav_html = ""

        body, outline = _add_outline(body)
        if outline:
            body = outline + body

        links = _get_lineage(str(path.resolve()))
        lineage_html = _render_lineage_html(links, self.__class__.server_port)

        if lineage_html:
            m = re.search(r"</h1>", body)
            if m:
                body = body[:m.end()] + lineage_html + body[m.end():]
            else:
                body = lineage_html + body

        html = _PAGE.format(
            title=title,
            css=_CSS + _DOC_CHROME_CSS,
            nav=nav_html,
            body=body,
            favicon=_favicon_href(self.__class__.server_port),
        ).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", html)

    def _send(self, code: int, ct: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"  {fmt % args}")


# ── File watcher ────────────────────────────────────────────────────────────

_WATCH_EXCLUDE = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".turbo", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".idea", ".vscode", ".cache",
}


def _scan_mtime() -> float:
    """Return the latest mtime of any file under _active_root."""
    best = 0.0
    try:
        for dirpath, dirnames, filenames in os.walk(_active_root):
            dirnames[:] = [d for d in dirnames if d not in _WATCH_EXCLUDE]
            for fn in filenames:
                try:
                    m = (Path(dirpath) / fn).stat().st_mtime
                    if m > best:
                        best = m
                except OSError:
                    pass
    except OSError:
        pass
    return best


def _watcher(port: int, interval: float = 3.0) -> None:
    last = _scan_mtime()
    while True:
        time.sleep(interval)
        cur = _scan_mtime()
        if cur != last:
            last = cur
            HubHandler._rebuild(_active_root)
            print(f"  [watcher] rebuilt ({_active_root.name})")


# ── Server (dual-stack IPv4+IPv6, threaded) ─────────────────────────────────

import socket as _socket


class _HubServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    address_family = _socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self) -> None:
        self.socket.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_V6ONLY, 0)
        super().server_bind()


# ── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="hub markdown server")
    ap.add_argument(
        "--port", "-p",
        type=int,
        default=int(os.environ.get("HUB_SERVER_PORT", "8787")),
        metavar="PORT",
    )
    args = ap.parse_args()

    HubHandler.server_port = args.port

    threading.Thread(target=_watcher, args=(args.port,), daemon=True).start()

    with _HubServer(("::", args.port), HubHandler) as srv:
        print(f"  Scan root : {SCAN_ROOT}")
        print(f"  Listening : http://localhost:{args.port}")
        print()
        print("  Ctrl+C to stop")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
