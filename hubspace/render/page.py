"""Served-document chrome: backlinks/trace, outline, print button, and the
page wrapper (CSS + HTML shell) for markdown and injected HTML docs."""
from __future__ import annotations

import re
from urllib.parse import quote

from ..core import config
from .markdown import _add_outline
from functools import lru_cache


@lru_cache(maxsize=None)
def _css_asset(name: str) -> str:
    """Read a stylesheet from hubspace/static (cached)."""
    return (config.static_dir() / name).read_text(encoding="utf-8")


_LINEAGE_ORDER = [
    "belongs_to_task", "belongs_to_skill",
    "task_has_run", "task_has_artifact", "task_has_draw", "task_has_data",
    "task_has_prompt", "task_has_doc",
    "skill_has_ref",
]
_LINEAGE_LABELS = {
    "belongs_to_task": "↑ task",
    "belongs_to_skill": "↑ skill",
    "task_has_run": "runs",
    "task_has_artifact": "artifacts",
    "task_has_draw": "draws",
    "task_has_data": "data",
    "task_has_prompt": "prompts",
    "task_has_doc": "docs",
    "skill_has_ref": "references",
}


_BACKLINKS_CSS = _css_asset("backlinks.css")

# Shared doc chrome: a "⋯" actions dropdown + print stylesheet. Reused by both
# the markdown page wrapper (_CSS/_PAGE via server._serve_page) and injected HTML
# docs (_inject_into_html).
_DOC_CHROME_CSS = _css_asset("chrome.css")

# A ⋯ menu item that prints the page to PDF. Present on every doc page.
DOC_PDF_ITEM = (
    '<button class="doc-menu-item" onclick="window.print()" '
    'title="Save as PDF (Cmd/Ctrl+P)">⤓ Save as PDF</button>'
)


def doc_menu(items: list) -> str:
    """A floating ⋯ dropdown of document actions (fixed top-right).

    items — inner HTML strings (``<a>``/``<button class="doc-menu-item">``).
    Uses a native <details> so it needs no JavaScript on the doc page.
    """
    inner = "".join(items)
    return (
        '<details class="doc-menu">'
        '<summary class="doc-menu-btn" title="Actions">⋯</summary>'
        f'<div class="doc-menu-list">{inner}</div>'
        "</details>"
    )


# Back-compat alias: the PDF-only menu used where no other actions apply.
_DOC_PRINT_BTN = doc_menu([DOC_PDF_ITEM])


def _favicon_href(port: int) -> str:
    return f"http://localhost:{port}" + quote(str(config.static_dir() / "favicon.svg"), safe="/:@")


def render_provenance(prov: dict | None) -> str:
    """A small "written by …" line for agent-generated artifacts (S6 / 2a).

    ``prov`` is ``metadata.extract_provenance()`` output. Returns ``""`` for a
    normal file (no provenance front matter), so ordinary artifacts are
    unaffected. Hub only *reports* this — it did not generate the file.
    """
    if not prov:
        return ""

    def _esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parts = [f'written by {_esc(prov["generated_by"])}']
    written = prov.get("written_at")
    if written:
        parts.append(_esc(written))
    rng = prov.get("commit_range")
    if rng:
        parts.append(f'<span class="prov-range">{_esc(rng)}</span>')
    line = " · ".join(parts)
    return (
        '<div class="provenance">'
        f'<span class="prov-line">{line}</span>'
        '<span class="prov-note">Hub did not generate this file.</span>'
        "</div>"
    )


def _inject_into_html(src: str, lineage_html: str, favicon: str = "", provenance_html: str = "") -> str:
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
    inject_html = lineage_html + provenance_html
    m = re.search(r"</h1>", src, re.IGNORECASE)
    if m:
        return src[: m.end()] + inject_html + src[m.end() :]
    return re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + inject_html, src, count=1, flags=re.IGNORECASE)


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


_CSS = _css_asset("page.css")

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
<body class="{body_class}">{outline}<div class="page">
{nav}
{body}
</div></body>
</html>
"""


# ── Markdown renderer (stdlib only) ────────────────────────────────────────

