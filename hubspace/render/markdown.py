"""Markdown -> HTML: inline spans, block rendering, and the doc outline."""
from __future__ import annotations

import re

from .columns import _detect_col_types, _fmt_cell
from ..utils.text import slugify


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
    """Convert a markdown string to an HTML fragment.

    Every top-level block element (headings, paragraphs, list items, code
    blocks, blockquotes) is annotated with a ``data-src-line="<n>"`` attribute
    giving the 1-based source line where that block begins. The reading view's
    per-line comment gutter and inline anchored-comment cards key off this
    (see render/page.py::DOC_EMBED_SCRIPT); it is inert for everyone else.
    """

    # Strip YAML frontmatter — but remember how many source lines it occupied so
    # every downstream data-src-line still points at the ORIGINAL source line.
    fm_offset = 0
    m_fm = re.match(r"^---[ \t]*\n.*?\n---[ \t]*\n?", src, flags=re.DOTALL)
    if m_fm:
        fm_offset = src[: m_fm.end()].count("\n")
        src = src[m_fm.end():]

    # Protect fenced code blocks. The placeholder keeps the SAME number of
    # trailing newlines as the original fence so every later line keeps its
    # index — line tracking survives multi-line code blocks.
    fences: list[str] = []

    def _fence(m: re.Match) -> str:
        lang = m.group(1).strip()
        body = m.group(2).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cls = f' class="language-{lang}"' if lang else ""
        fences.append(f"<pre><code{cls}>{body}</code></pre>")
        return f"\x02{len(fences)-1}\x03" + "\n" * m.group(0).count("\n")

    src = re.sub(r"`{3,}(\w*)\n([\s\S]*?)`{3,}", _fence, src)

    def _sl(idx: int) -> int:
        """1-based ORIGINAL source line for line index ``idx``."""
        return idx + fm_offset + 1

    lines = src.splitlines()
    N = len(lines)
    out: list[str] = []
    i = 0

    while i < N:
        line = lines[i]
        stripped = line.strip()

        # Fence placeholder
        if re.match(r"^\x02\d+\x03$", stripped):
            fh = fences[int(stripped[1:-1])]
            out.append(fh.replace("<pre>", f'<pre data-src-line="{_sl(i)}">', 1))
            i += 1
            continue

        # Blank line
        if not stripped:
            i += 1
            continue

        sln = _sl(i)  # source line where this block begins

        # ATX heading
        m = re.match(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$", line)
        if m:
            lvl = len(m.group(1))
            out.append(f'<h{lvl} data-src-line="{sln}">{_inline(m.group(2).strip())}</h{lvl}>')
            i += 1
            continue

        # Horizontal rule (standalone ---, ***, ___)
        if re.match(r"^(\*[ \t]*){3,}$|^(-[ \t]*){3,}$|^(_[ \t]*){3,}$", stripped):
            out.append(f'<hr data-src-line="{sln}">')
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
            out.append(f'<blockquote data-src-line="{sln}">{inner}</blockquote>')
            continue

        # Unordered list
        if re.match(r"^[ \t]*[-*+][ \t]+", line):
            items: list[str] = []
            while i < N and re.match(r"^[ \t]*[-*+][ \t]+", lines[i]):
                content = re.sub(r"^[ \t]*[-*+][ \t]+", "", lines[i])
                items.append(f'<li data-src-line="{_sl(i)}">{_inline(content)}</li>')
                i += 1
            out.append(f'<ul data-src-line="{sln}">\n' + "\n".join(items) + "\n</ul>")
            continue

        # Ordered list
        if re.match(r"^[ \t]*\d+\.[ \t]+", line):
            items = []
            while i < N and re.match(r"^[ \t]*\d+\.[ \t]+", lines[i]):
                content = re.sub(r"^[ \t]*\d+\.[ \t]+", "", lines[i])
                items.append(f'<li data-src-line="{_sl(i)}">{_inline(content)}</li>')
                i += 1
            out.append(f'<ol data-src-line="{sln}">\n' + "\n".join(items) + "\n</ol>")
            continue

        # Table (header | separator row)
        if "|" in line and i + 1 < N and re.match(r"^[\s|:=-]+$", lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2  # skip separator
            rows: list[list[str]] = []
            while i < N and "|" in lines[i]:
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            col_types = _detect_col_types(rows, len(headers))
            ths = "".join(
                f'<th class="col-{col_types[j] if j < len(col_types) else "text"}">'
                f'{_inline(h)}</th>'
                for j, h in enumerate(headers)
            )
            trs = "".join(
                "<tr>" + "".join(
                    f'<td class="col-{col_types[j] if j < len(col_types) else "text"}">'
                    f'{_inline(_fmt_cell(c, col_types[j] if j < len(col_types) else "text"))}</td>'
                    for j, c in enumerate(row)
                ) + "</tr>"
                for row in rows
            )
            out.append(f'<table data-src-line="{sln}"><thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table>')
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
                out.append(f'<h1 data-src-line="{_sl(i)}">{_inline(ls)}</h1>')
                i += 2
                para = None
                break

            # Setext h2
            if i + 1 < N and re.match(r"^-+[ \t]*$", lines[i + 1]):
                out.append(f'<h2 data-src-line="{_sl(i)}">{_inline(ls)}</h2>')
                i += 2
                para = None
                break

            assert para is not None
            para.append(ls)
            i += 1

        if para:
            out.append(f'<p data-src-line="{sln}">{_inline(" ".join(para))}</p>')

    result = "\n".join(out)
    for idx, fence in enumerate(fences):
        result = result.replace(f"\x02{idx}\x03", fence)
    return result


# ── Document outline / TOC ───────────────────────────────────────────────────


def _add_outline(body_html: str) -> tuple[str, str]:
    """Inject ids into h1-h3 tags and build a floating outline nav.

    Returns (body_html_with_ids, outline_html). If fewer than 2 headings are
    found, returns (body_html, "") unchanged.
    """
    headings: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}

    def _inject(m: re.Match) -> str:
        level = int(m.group(1))
        attrs = m.group(2)  # preserve any existing attrs (e.g. data-src-line)
        inner = m.group(3)
        plain = re.sub(r"<[^>]+>", "", inner).strip()
        slug = slugify(plain) or "section"
        if slug in seen:
            seen[slug] += 1
            slug = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 1
        headings.append((level, plain, slug))
        return f'<h{level}{attrs} id="{slug}">{inner}</h{level}>'

    body_html = re.sub(r"<h([1-3])((?:\s[^>]*)?)>(.*?)</h\1>", _inject, body_html, flags=re.DOTALL)

    if len(headings) < 2:
        return body_html, ""

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    toggle = (
        "var n=this.closest('.outline');n.classList.toggle('collapsed');"
        "try{localStorage.setItem('hub_outline_collapsed',"
        "n.classList.contains('collapsed')?'1':'0')}catch(e){}"
    )
    parts = [
        '<nav class="outline" id="doc-outline">',
        f'<div class="outline-label" onclick="{toggle}">'
        '// outline <span class="outline-caret">▾</span></div>',
        '<div class="outline-links">',
    ]
    for level, plain, slug in headings:
        cls = f" lvl{level}" if level > 1 else ""
        parts.append(f'<a class="outline-link{cls}" href="#{slug}">{_esc(plain)}</a>')
    parts.append("</div></nav>")
    parts.append(
        '<script>(function(){var n=document.getElementById("doc-outline");'
        'if(n){try{if(localStorage.getItem("hub_outline_collapsed")==="1")'
        'n.classList.add("collapsed");}catch(e){}}})();</script>'
    )
    return body_html, "".join(parts)


# ── Request handler ─────────────────────────────────────────────────────────


# ── Data file renderers (csv / tsv / xlsx → HTML table) ─────────────────────


