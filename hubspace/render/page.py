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

# Shared doc chrome: the "⤓ PDF" print button + print stylesheet. Reused by both
# the markdown page wrapper (_CSS/_PAGE) and injected HTML docs (_inject_into_html).
_DOC_CHROME_CSS = _css_asset("chrome.css")
_DOC_PRINT_BTN = (
    '<button class="doc-print" onclick="window.print()" '
    'title="Save as PDF (Cmd/Ctrl+P)">⤓ PDF</button>'
)


def _favicon_href(port: int) -> str:
    return f"http://localhost:{port}" + quote(str(config.static_dir() / "favicon.svg"), safe="/:@")


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
<body class="{body_class}"><button class="doc-print" onclick="window.print()" title="Save as PDF (Cmd/Ctrl+P)">⤓ PDF</button>{outline}<div class="page">
{nav}
{body}
</div></body>
</html>
"""


# ── Markdown renderer (stdlib only) ────────────────────────────────────────

