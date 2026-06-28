"""Served-document chrome: backlinks/trace, outline, print button, and the
page wrapper (CSS + HTML shell) for markdown and injected HTML docs."""
from __future__ import annotations

import re
from urllib.parse import quote

from ..core import config
from .markdown import _add_outline


_LINEAGE_ORDER = [
    "belongs_to_task", "belongs_to_skill",
    "task_has_run", "task_has_artifact", "task_has_data",
    "task_has_prompt", "task_has_doc",
    "skill_has_ref",
]
_LINEAGE_LABELS = {
    "belongs_to_task": "↑ task",
    "belongs_to_skill": "↑ skill",
    "task_has_run": "runs",
    "task_has_artifact": "artifacts",
    "task_has_data": "data",
    "task_has_prompt": "prompts",
    "task_has_doc": "docs",
    "skill_has_ref": "references",
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
    ".outline{position:fixed;top:80px;left:32px;width:200px;word-break:break-word;"
    "max-height:calc(100vh - 120px);overflow-y:auto;font-family:var(--mono);"
    "font-size:11px;line-height:1.5;z-index:50;}"
    ".outline-label{font-size:9px;letter-spacing:.18em;text-transform:uppercase;"
    "color:var(--accent);margin-bottom:8px;}"
    ".outline a{display:block;color:var(--mute);text-decoration:none;padding:2px 0;"
    "border-left:1px solid var(--line);padding-left:10px;}"
    ".outline a:hover{color:var(--accent2);border-left-color:var(--accent2);}"
    ".outline a.lvl2{padding-left:22px;}"
    ".outline a.lvl3{padding-left:34px;}"
    ".outline-label{cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px;}"
    ".outline-caret{font-size:8px;display:inline-block;transition:transform .15s;}"
    ".outline.collapsed .outline-caret{transform:rotate(-90deg);}"
    ".outline.collapsed .outline-links{display:none;}"
    ".outline.collapsed{width:auto;}"
    "@media (max-width:1340px){.outline{display:none;}}"
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
td.col-num,td.col-sci,td.col-currency,td.col-pct{text-align:right;font-family:var(--mono);font-size:.85rem;}
th.col-num,th.col-sci,th.col-currency,th.col-pct{text-align:right;}
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
.outline{position:fixed;top:80px;left:32px;width:200px;word-break:break-word;
  max-height:calc(100vh - 120px);overflow-y:auto;font-family:var(--mono);
  font-size:11px;line-height:1.5;z-index:50;}
.outline-label{font-size:9px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--accent);margin-bottom:8px;}
.outline a{display:block;color:var(--mute);text-decoration:none;padding:2px 0;
  border-left:1px solid var(--line);padding-left:10px;}
.outline a:hover{color:var(--accent2);border-left-color:var(--accent2);}
.outline a.lvl2{padding-left:22px;}
.outline a.lvl3{padding-left:34px;}
.outline-label{cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px;}
.outline-caret{font-size:8px;display:inline-block;transition:transform .15s;}
.outline.collapsed .outline-caret{transform:rotate(-90deg);}
.outline.collapsed .outline-links{display:none;}
.outline.collapsed{width:auto;}
@media (max-width:1340px){.outline{display:none;}}
@media print{.outline{display:none;}}
@media (min-width:1340px){
  body.with-outline{display:grid;grid-template-columns:220px minmax(0,1fr);gap:0 24px;padding-left:24px;}
  body.with-outline .outline{position:sticky;top:80px;width:auto;left:auto;max-width:200px;align-self:start;}
  body.with-outline .page{max-width:860px;margin:0;}
}

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
<body class="{body_class}"><button class="doc-print" onclick="window.print()" title="Save as PDF (Cmd/Ctrl+P)">⤓ PDF</button>{outline}<div class="page">
{nav}
{body}
</div></body>
</html>
"""


# ── Markdown renderer (stdlib only) ────────────────────────────────────────

