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


def _esc_attr(s: str) -> str:
    return (s.replace("&", "&amp;").replace('"', "&quot;")
             .replace("<", "&lt;").replace(">", "&gt;"))


def doc_publish_item(pub_path: str) -> str:
    """A ⋯ menu item that publishes THIS doc via POST /_publish (S14 / #5).

    ``pub_path`` (scan-root-relative or absolute) is baked into the button so
    the tiny inline :data:`DOC_PUBLISH_SCRIPT` targets the right file. Present
    on every publishable doc page (.md/.html); it hands off to dak server-side
    and shows the honest published / dry-run / error state inline."""
    return (
        '<button class="doc-menu-item" onclick="hubPublish(this)" '
        f'data-pub-path="{_esc_attr(pub_path)}" '
        'title="Publish this doc to a shareable URL">↗ Publish</button>'
    )


# Tiny self-contained publisher for doc pages (no SPA). Scans server-side first
# (so any secrets are redacted before the file leaves the machine, mirroring the
# SPA's redact-everything default), then POSTs /_publish and renders an HONEST
# result line (#3): a live link only on a real publish, a clearly-marked preview
# on a dry-run (never shown as "published"), and dak's error detail on failure.
DOC_PUBLISH_SCRIPT = """
<script>
(function(){
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function show(html,cls){var el=document.getElementById('doc-pub-result');
if(!el){el=document.createElement('div');el.id='doc-pub-result';document.body.appendChild(el);}
el.className='doc-pub-result '+(cls||'');el.innerHTML=html;}
window.hubPublish=function(btn){
var path=btn.getAttribute('data-pub-path');
btn.disabled=true;btn.textContent='publishing\\u2026';show('publishing\\u2026','');
fetch('/_publish-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path})})
.then(function(r){return r.json();}).catch(function(){return {};})
.then(function(sc){var f=(sc&&sc.findings)||[];var idx=f.map(function(_x,i){return i;});
return fetch('/_publish',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({path:path,redact_indices:idx,review:true})})
.then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});});})
.then(function(res){btn.disabled=false;btn.textContent='\\u2197 Publish';
var d=(res&&res.d)||{};
if(res&&res.ok&&d.url){
if(d.dryRun){show('<span class="dpr-tag dry">dry-run \\u2014 not uploaded (URL not live)</span>'+
'<span class="dpr-preview">preview: '+esc(d.url)+'</span>','dry');}
else{show('<span class="dpr-tag ok">\\u2713 published</span>'+
'<a class="dpr-url" href="'+esc(d.url)+'" target="_blank" rel="noopener">'+esc(d.url)+'</a>','ok');}
}else{var det=d.detail?String(d.detail).split('\\n').slice(-1)[0]
:(d.error==='dak_unavailable'?'dak not configured \\u2014 run its setup':(d.error||'publish failed'));
show('<span class="dpr-tag err">publish failed</span><span class="dpr-detail">'+esc(det)+'</span>','err');}
}).catch(function(){btn.disabled=false;btn.textContent='\\u2197 Publish';
show('<span class="dpr-tag err">publish failed</span>','err');});
};
})();
</script>
"""


# S17/S19 — companion script for LIVE-served doc bodies shown inside the SPA
# reading-view iframe. A doc page opened as a top-level tab (window.parent===
# window) short-circuits immediately, so deep-links / new-tab behave exactly as
# before. When embedded it:
#   • forwards ⌘K/⌘P/c/Esc keydowns the iframe would otherwise swallow, so the
#     palette / composer / close shortcuts work with focus inside the file;
#   • answers `hub-reader-scroll` by scrolling to an anchor;
#   • (S19) shows a hover "+" gutter on any block carrying data-src-line and, on
#     click, postMessages the parent {type:'hub-comment-line', line:<n>} so the
#     composer opens prefilled with that line — the user never types "L4";
#   • (S19) renders this file's comments INLINE on the document — anchored ones
#     right under the block whose data-src-line matches (comments live ON the
#     doc, not a side rail); general ones in a compact block at the top.
# Same-origin, so postMessage reaches the SPA shell. Deliberately NEVER added to
# published bundles (they render through render.bundle, not these helpers) —
# bundles must stay self-contained.
DOC_EMBED_SCRIPT = """
<script>
(function(){
if(window.parent===window) return;
function fwd(key){try{window.parent.postMessage({source:'hub-doc',type:'hub-key',key:key},'*');}catch(_){}}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
document.addEventListener('keydown',function(e){
  var k=(e.key||'').toLowerCase();
  if((e.metaKey||e.ctrlKey)&&!e.altKey&&(k==='k'||k==='p')){e.preventDefault();fwd(k);return;}
  var tag=(e.target&&e.target.tagName)||'';
  if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT'||(e.target&&e.target.isContentEditable))return;
  if(e.metaKey||e.ctrlKey||e.altKey)return;
  if(k==='c'){fwd('c');}
  else if(k==='escape'){fwd('escape');}
});
window.addEventListener('message',function(e){
  var d=e.data;if(!d)return;
  if(d.type==='hub-reader-scroll'){
    var a=String(d.anchor||'');
    var el=a&&document.getElementById(a);
    if(el){el.scrollIntoView({block:'start',behavior:'smooth'});
      var o=el.style.backgroundColor;el.style.transition='background .3s';
      el.style.backgroundColor='rgba(193,95,60,.20)';
      setTimeout(function(){el.style.backgroundColor=o;},1400);}
    else{window.scrollTo({top:0,behavior:'smooth'});}
    return;
  }
  if(d.type==='hub-doc-notes'){renderNotes(d.notes||[]);return;}
});

// ── S19: hover "+" line gutter ──────────────────────────────────────────────
// A single floating button trails the pointer to the currently-hovered block.
var addBtn=document.createElement('button');
addBtn.type='button';addBtn.className='hub-line-add';addBtn.textContent='+';
addBtn.title='comment on this line';addBtn.style.display='none';
var curLine=null;
addBtn.addEventListener('click',function(ev){
  ev.preventDefault();ev.stopPropagation();
  if(curLine==null)return;
  try{window.parent.postMessage({source:'hub-doc',type:'hub-comment-line',line:curLine},'*');}catch(_){}
});
document.addEventListener('DOMContentLoaded',function(){document.body.appendChild(addBtn);});
if(document.body)document.body.appendChild(addBtn);
document.addEventListener('mousemove',function(e){
  var blk=e.target&&e.target.closest&&e.target.closest('[data-src-line]');
  if(!blk||blk.classList.contains('hub-inline-note')){addBtn.style.display='none';curLine=null;return;}
  var ln=parseInt(blk.getAttribute('data-src-line'),10);
  if(isNaN(ln)){addBtn.style.display='none';curLine=null;return;}
  curLine=ln;
  var r=blk.getBoundingClientRect();
  addBtn.style.top=(window.scrollY+r.top)+'px';
  addBtn.style.left=(window.scrollX+r.left-30)+'px';
  addBtn.style.display='flex';
});

// ── S19: inline comment cards ───────────────────────────────────────────────
function card(n){
  var agent=!!n.agent;
  var meta='<span class="note-author'+(agent?' agent':'')+'">'+(agent?'\\u25b8 ':'')+
    esc(n.author||'anon')+'</span><span class="note-time">'+esc(n.timeAgo||'')+'</span>'+
    (n.line?'<span class="note-on">L'+esc(n.line)+'</span>':'');
  var el=document.createElement('div');
  el.className='note-card hub-inline-note'+(agent?' agent':'')+(n.line?' anchored':'');
  el.innerHTML='<div class="note-meta">'+meta+'</div><div class="note-body">'+esc(n.body||'')+'</div>';
  return el;
}
function blockForLine(line){
  var blocks=document.querySelectorAll('.page [data-src-line]');
  var exact=null,best=null,bestLn=-1;
  for(var i=0;i<blocks.length;i++){
    if(blocks[i].classList.contains('hub-inline-note'))continue;
    var ln=parseInt(blocks[i].getAttribute('data-src-line'),10);
    if(ln===line){exact=blocks[i];break;}
    if(ln<line&&ln>bestLn){bestLn=ln;best=blocks[i];}
  }
  return exact||best;
}
function renderNotes(notes){
  var page=document.querySelector('.page');if(!page)return;
  // Clear any previously-inserted cards (re-render after a new comment saves).
  var old=page.querySelectorAll('.hub-inline-note,.hub-inline-notes');
  for(var i=0;i<old.length;i++)old[i].parentNode.removeChild(old[i]);
  var general=[];
  notes.forEach(function(n){
    if(n.line){
      var blk=blockForLine(n.line);
      var c=card(n);
      if(blk&&blk.parentNode){blk.parentNode.insertBefore(c,blk.nextSibling);}
      else{general.push(n);}
    }else{general.push(n);}
  });
  if(general.length){
    var wrap=document.createElement('div');
    wrap.className='hub-inline-notes';
    wrap.innerHTML='<div class="hub-inline-notes-label">// comments \\u00b7 '+general.length+'</div>';
    general.forEach(function(n){wrap.appendChild(card(n));});
    var firstBlk=page.querySelector('[data-src-line]');
    if(firstBlk){firstBlk.parentNode.insertBefore(wrap,firstBlk);}
    else{page.appendChild(wrap);}
  }
}
// Tell the parent we're ready for this file's comments (covers the case where
// the parent posted before this script's listener was attached).
try{window.parent.postMessage({source:'hub-doc',type:'hub-doc-ready'},'*');}catch(_){}
})();
</script>
"""


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


def _inject_into_html(src: str, lineage_html: str, favicon: str = "",
                      provenance_html: str = "", pub_path: str = "") -> str:
    """Inject backlinks CSS + HTML into an existing HTML document."""
    src, outline_html = _add_outline(src)
    head_inject = f"<style>{_BACKLINKS_CSS}{_DOC_CHROME_CSS}</style>"
    if favicon:
        head_inject = f'<link rel="icon" type="image/svg+xml" href="{favicon}">' + head_inject
    src = re.sub(r"</head>", head_inject + "</head>", src, count=1, flags=re.IGNORECASE)
    # ⋯ menu (Publish + Save as PDF) goes right after <body> so it floats over
    # the doc; the tiny publisher script goes at end-of-body.
    menu = doc_menu([doc_publish_item(pub_path), DOC_PDF_ITEM]) if pub_path else _DOC_PRINT_BTN
    src = re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + menu, src, count=1, flags=re.IGNORECASE)
    if pub_path:
        # lambda replacement so \u escapes in the script aren't re-interpreted.
        if re.search(r"</body>", src, re.IGNORECASE):
            src = re.sub(r"</body>", lambda _mo: DOC_PUBLISH_SCRIPT + "</body>",
                         src, count=1, flags=re.IGNORECASE)
        else:
            src += DOC_PUBLISH_SCRIPT
    if outline_html:
        src = re.sub(r"<body[^>]*>", lambda mo: mo.group(0) + outline_html, src, count=1, flags=re.IGNORECASE)
    # S17 — forward palette/composer/close keydowns from inside the SPA reader.
    if re.search(r"</body>", src, re.IGNORECASE):
        src = re.sub(r"</body>", lambda _mo: DOC_EMBED_SCRIPT + "</body>",
                     src, count=1, flags=re.IGNORECASE)
    else:
        src += DOC_EMBED_SCRIPT
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

