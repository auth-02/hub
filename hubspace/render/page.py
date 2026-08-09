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


def doc_published_open_item(url: str) -> str:
    """A ⋯ menu item that opens THIS doc's live published URL (S20).

    Present only when the file already has a recorded published-state entry, so
    a reader who opens a published doc's page can jump straight to its live copy.
    Best-effort: Hub bakes the URL from ``published.json`` at render time."""
    return (
        f'<a class="doc-menu-item" href="{_esc_attr(url)}" target="_blank" '
        'rel="noopener" title="Open this doc\'s live published URL">'
        '↗ Open published</a>'
    )


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


def doc_republish_item() -> str:
    """A ⋯ menu item that RE-runs the publish for an already-published doc (S27).

    Re-runs the same scan→publish path as :func:`doc_publish_item` (idempotent —
    S26's deterministic worker slug yields the same live URL). The file's path is
    read from the enclosing ``.doc-pub-actions`` wrapper, so no attribute here."""
    return (
        '<button class="doc-menu-item" onclick="hubRepublish(this)" '
        'title="Re-publish this doc (same URL)">↻ Republish</button>'
    )


def doc_unpublish_item() -> str:
    """A ⋯ menu item that takes THIS doc's live URL down via POST /_publish-revoke
    (S27 — parity with the task-bundle ✕ Unpublish).

    Really deletes the Cloudflare worker (dak unpublish, server-side) and forgets
    the local entry, then swaps the menu back to a single Publish in place — no
    reload. The file's path comes from the enclosing ``.doc-pub-actions``."""
    return (
        '<button class="doc-menu-item" onclick="hubUnpublish(this)" '
        'title="Take this doc\'s live URL down">✕ Unpublish</button>'
    )


def doc_pub_actions(pub_path: str, pub_url: str = "") -> str:
    """The publish-state control block for a doc page's ⋯ menu (S27).

    Wraps the publish affordances in a ``.doc-pub-actions`` span (``data-pub-path``
    baked on it) so the inline :data:`DOC_PUBLISH_SCRIPT` can rewrite them IN PLACE
    after a publish/unpublish — no full reload. When ``pub_url`` is present the doc
    is published, so it offers **↗ Open published / ↻ Republish / ✕ Unpublish**
    (parity with the task marker); otherwise a single **↗ Publish**. The span uses
    ``display:contents`` so its children stay direct flex items of the menu list."""
    if pub_url:
        inner = (doc_published_open_item(pub_url)
                 + doc_republish_item() + doc_unpublish_item())
    else:
        inner = doc_publish_item(pub_path)
    return (f'<span class="doc-pub-actions" data-pub-path="{_esc_attr(pub_path)}">'
            f'{inner}</span>')


# Tiny self-contained publisher for doc pages (no SPA). Scans server-side first
# (so any secrets are redacted before the file leaves the machine, mirroring the
# SPA's redact-everything default), then POSTs /_publish and renders an HONEST
# result line (#3): a live link only on a real publish, a clearly-marked preview
# on a dry-run (never shown as "published"), and dak's error detail on failure.
DOC_PUBLISH_SCRIPT = """
<script>
(function(){
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function fname(path){var p=String(path||'');return p.split('/').pop()||p;}
function show(html,cls){var el=document.getElementById('doc-pub-result');
if(!el){el=document.createElement('div');el.id='doc-pub-result';document.body.appendChild(el);}
el.className='doc-pub-result '+(cls||'');el.innerHTML=html;}
// ── tiny self-contained sticky toast (mirrors the SPA's flashSticky/flashOpen) ──
function toastEl(){var t=document.getElementById('doc-toast');
if(!t){t=document.createElement('div');t.id='doc-toast';t.className='doc-toast';document.body.appendChild(t);}return t;}
function toastSticky(msg){var t=toastEl();clearTimeout(t._t);t.textContent=msg;t.className='doc-toast show';}
function toastFlash(msg){var t=toastEl();t.textContent=msg;t.className='doc-toast show';
clearTimeout(t._t);t._t=setTimeout(function(){t.className='doc-toast';t.textContent='';},2600);}
function toastOpen(msg,url){var t=toastEl();
t.innerHTML=esc(msg)+' <a class="doc-toast-open" href="'+esc(url)+'" target="_blank" rel="noopener">open \\u2197</a>';
t.className='doc-toast show has-open';clearTimeout(t._t);
t._t=setTimeout(function(){t.className='doc-toast';t.textContent='';},6000);}
// ── swap the ⋯ menu's publish items IN PLACE (published <-> unpublished) ────────
function wrapOf(btn){return btn&&btn.closest?btn.closest('.doc-pub-actions'):null;}
function pathOf(btn){var w=wrapOf(btn);
return (w&&w.getAttribute('data-pub-path'))||btn.getAttribute('data-pub-path')||'';}
function setPubActions(wrap,url){
if(!wrap)return;var path=wrap.getAttribute('data-pub-path')||'';
if(url){wrap.innerHTML='<a class="doc-menu-item" href="'+esc(url)+'" target="_blank" rel="noopener" '+
'title="Open this doc\\'s live published URL">\\u2197 Open published</a>'+
'<button class="doc-menu-item" onclick="hubRepublish(this)" title="Re-publish this doc (same URL)">\\u21bb Republish</button>'+
'<button class="doc-menu-item" onclick="hubUnpublish(this)" title="Take this doc\\'s live URL down">\\u2715 Unpublish</button>';}
else{wrap.innerHTML='<button class="doc-menu-item" onclick="hubPublish(this)" data-pub-path="'+esc(path)+'" '+
'title="Publish this doc to a shareable URL">\\u2197 Publish</button>';}
}
// ── publish / republish share one honest scan->review->publish path ────────────
// S28 — `name` (optional) picks the URL worker slug on a FRESH publish; republish
// passes nothing so the server reuses the recorded worker (stays idempotent).
function doPublish(btn,verb,name){
var wrap=wrapOf(btn);var path=pathOf(btn);
btn.disabled=true;btn.textContent=verb+'\\u2026';toastSticky(verb+' '+fname(path)+'\\u2026');show(verb+'\\u2026','');
fetch('/_publish-scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path})})
.then(function(r){return r.json();}).catch(function(){return {};})
.then(function(sc){var f=(sc&&sc.findings)||[];var idx=f.map(function(_x,i){return i;});
return fetch('/_publish',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({path:path,redact_indices:idx,review:true,name:(name||'')})})
.then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});});})
.then(function(res){btn.disabled=false;
var d=(res&&res.d)||{};
if(res&&res.ok&&d.url){
if(d.dryRun){show('<span class="dpr-tag dry">dry-run \\u2014 not uploaded (URL not live)</span>'+
'<span class="dpr-preview">preview: '+esc(d.url)+'</span>','dry');
toastFlash('dry-run \\u2014 not uploaded');}
else{show('<span class="dpr-tag ok">\\u2713 published</span>'+
'<a class="dpr-url" href="'+esc(d.url)+'" target="_blank" rel="noopener">'+esc(d.url)+'</a>','ok');
toastOpen('published \\u00b7 '+fname(path),d.url);
setPubActions(wrap,d.url);}      // swap to Open / Republish / Unpublish in place
}else{var det=d.detail?String(d.detail).split('\\n').slice(-1)[0]
:(d.error==='dak_unavailable'?'dak not configured \\u2014 run its setup':(d.error||'publish failed'));
show('<span class="dpr-tag err">publish failed</span><span class="dpr-detail">'+esc(det)+'</span>','err');
toastFlash('publish failed');
if(!wrap)btn.textContent='\\u2197 Publish';}
}).catch(function(){btn.disabled=false;if(!wrap)btn.textContent='\\u2197 Publish';
show('<span class="dpr-tag err">publish failed</span>','err');toastFlash('publish failed');});
}
window.hubPublish=function(btn){var nm=window.prompt('publish as\\u2026 (URL name; blank = default)','');
if(nm===null)return;doPublish(btn,'publishing',nm.trim());};
window.hubRepublish=function(btn){doPublish(btn,'republishing');};
// ── unpublish: real dak take-down via /_publish-revoke, then swap in place ──────
window.hubUnpublish=function(btn){
var wrap=wrapOf(btn);var path=pathOf(btn);
btn.disabled=true;btn.textContent='unpublishing\\u2026';toastSticky('unpublishing '+fname(path)+'\\u2026');
fetch('/_publish-revoke',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path})})
.then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
.then(function(res){var d=(res&&res.d)||{};
if(res&&res.ok&&d.ok){
setPubActions(wrap,'');           // swap back to a single Publish in place
show('<span class="dpr-tag ok">'+(d.unpublished?'\\u2713 unpublished':'\\u2713 forgotten locally')+'</span>','ok');
toastFlash(d.unpublished?'unpublished'
:('forgotten locally'+(d.detail?(' \\u2014 '+String(d.detail).split('\\n').slice(-1)[0]):'')));
}else{btn.disabled=false;btn.textContent='\\u2715 Unpublish';
show('<span class="dpr-tag err">unpublish failed</span>','err');toastFlash('unpublish failed');}
}).catch(function(){btn.disabled=false;btn.textContent='\\u2715 Unpublish';
show('<span class="dpr-tag err">unpublish failed</span>','err');toastFlash('unpublish failed');});
};
})();
</script>
"""


import json as _json


def doc_edit_item() -> str:
    """A ⋯ menu item that edits THIS doc in place (S21 — ported off the reader).

    Present only for editable text docs (.md/.txt/… — never .html). Clicking it
    calls ``hubDocEdit()`` from :data:`DOC_PAGE_SCRIPT`, which fetches the raw
    source (GET /_doc-raw), swaps the rendered body for a line-numbered textarea,
    and saves via POST /_edit-doc under the same mtime-conflict guard the SPA
    used. Never emitted into a published bundle (bundles skip these helpers)."""
    return (
        '<button class="doc-menu-item" onclick="hubDocEdit()" '
        'title="Edit this document in place">✎ Edit</button>'
    )


def doc_config_script(cfg: dict) -> str:
    """Bake this file's own comment/edit context for :data:`DOC_PAGE_SCRIPT`.

    ``cfg`` carries {repo, slug, target, path, editable, notes:[…]} so the
    standalone doc page owns its inline comments + composer WITHOUT any SPA
    parent / postMessage (S21 #3). ``</`` is escaped so a comment body can never
    close the <script> early. Emitted only on LIVE-served pages — never bundles.
    """
    payload = _json.dumps(cfg or {}).replace("</", "<\\/")
    return f"<script>window.HUB_DOC={payload};</script>"


# S21 — self-sufficient companion script for LIVE-served doc pages. The S17-era
# reader overlay is gone; the standalone page IS the canonical full view, so this
# script gives it everything the reader used to lend it, with NO parent frame:
#   • renders this file's inline comments (baked into window.HUB_DOC by the
#     server) — anchored ones under the block whose data-src-line matches, general
#     ones in a compact block at the top;
#   • a persistent left "+" gutter LANE (fixed clickability): the button stays
#     alive while the pointer is over a block OR heading into the gutter lane, so
#     it is reliably clickable — click → an on-page composer that POSTs /_note;
#   • ⌘C / Ctrl+C opens the composer too, but ONLY when nothing is selected (a
#     real text selection falls through to the native copy);
#   • ✎ Edit-in-place (hubDocEdit): raw source in a line-numbered textarea, Save →
#     POST /_edit-doc (mtime-guarded), Cancel/Esc reverts, ⌘↵ saves.
# Deliberately NEVER added to published bundles (they render through
# render.bundle, not these helpers) — bundles must stay self-contained.
DOC_PAGE_SCRIPT = """
<script>
(function(){
var CFG=window.HUB_DOC||{};
var canComment=CFG.repo!==undefined&&CFG.slug!==undefined&&CFG.target!==undefined;
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function ago(iso){
  if(!iso)return'';var t=Date.parse(iso);if(isNaN(t))return'';
  var d=(Date.now()-t)/1000;
  if(d<90)return'just now';
  if(d<3600)return Math.floor(d/60)+'m ago';
  if(d<86400)return Math.floor(d/3600)+'h ago';
  return Math.floor(d/86400)+'d ago';
}
function lineOf(range){var m=/(\\d+)/.exec(range||'');return m?parseInt(m[1],10):null;}

// ── inline comment cards (baked, self-sufficient) ───────────────────────────
function card(n){
  var agent=/(agent|bot)/i.test(n.author||'');
  var meta='<span class="note-author'+(agent?' agent':'')+'">'+(agent?'\\u25b8 ':'')+
    esc(n.author||'anon')+'</span><span class="note-time">'+esc(ago(n.created))+'</span>'+
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
function renderNotes(){
  var page=document.querySelector('.page');if(!page)return;
  var old=page.querySelectorAll('.hub-inline-note,.hub-inline-notes');
  for(var i=0;i<old.length;i++)old[i].parentNode.removeChild(old[i]);
  var notes=(CFG.notes||[]).map(function(n){
    return {author:n.author,body:n.body,created:n.created,line:lineOf(n.range)};});
  var general=[];
  notes.forEach(function(n){
    if(n.line){var blk=blockForLine(n.line);var c=card(n);
      if(blk&&blk.parentNode){blk.parentNode.insertBefore(c,blk.nextSibling);}else{general.push(n);}}
    else{general.push(n);}
  });
  if(general.length){
    var wrap=document.createElement('div');wrap.className='hub-inline-notes';
    wrap.innerHTML='<div class="hub-inline-notes-label">// comments \\u00b7 '+general.length+'</div>';
    general.forEach(function(n){wrap.appendChild(card(n));});
    var firstBlk=page.querySelector('[data-src-line]');
    if(firstBlk){firstBlk.parentNode.insertBefore(wrap,firstBlk);}else{page.appendChild(wrap);}
  }
}

// ── on-page comment composer (POST /_note → reload) ─────────────────────────
var composerEl=null;
function closeComposer(){if(composerEl){composerEl.parentNode.removeChild(composerEl);composerEl=null;}}
function openComposer(line){
  if(!canComment)return;
  closeComposer();
  composerEl=document.createElement('div');
  composerEl.className='hub-composer';
  composerEl.innerHTML='<div class="hub-composer-head">'+(line?('comment on L'+line):'comment')+'</div>'+
    '<textarea class="hub-composer-ta" placeholder="write a comment\\u2026"></textarea>'+
    '<div class="hub-composer-foot"><span class="hub-composer-hint">\\u2318\\u21b5 save \\u00b7 esc cancel</span>'+
    '<span><button type="button" class="hub-composer-cancel">cancel</button>'+
    '<button type="button" class="hub-composer-save">save</button></span></div>';
  document.body.appendChild(composerEl);
  var ta=composerEl.querySelector('.hub-composer-ta');ta.focus();
  function save(){
    var body=ta.value.trim();if(!body)return;
    var payload={repo:CFG.repo,slug:CFG.slug,target:CFG.target,body:body};
    if(line)payload.range='L'+line;
    fetch('/_note',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
      .then(function(r){return r.json().catch(function(){return{};});})
      .then(function(d){if(d&&d.ok){location.reload();}
        else{alert((d&&d.detail)||(d&&d.error)||'comment failed');}})
      .catch(function(){alert('comment failed');});
  }
  composerEl.querySelector('.hub-composer-save').addEventListener('click',save);
  composerEl.querySelector('.hub-composer-cancel').addEventListener('click',closeComposer);
  ta.addEventListener('keydown',function(e){
    if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeComposer();}
    else if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();e.stopPropagation();save();}
  });
}

// ── persistent "+" gutter lane (reliably clickable) ─────────────────────────
var lane=document.createElement('div');lane.className='hub-gutter-lane';
var addBtn=document.createElement('button');addBtn.type='button';addBtn.className='hub-line-add';
addBtn.textContent='+';addBtn.title='comment on this line';addBtn.style.display='none';
lane.appendChild(addBtn);
var curLine=null,hideT=null;
function keepBtn(){if(hideT){clearTimeout(hideT);hideT=null;}}
function scheduleHide(){keepBtn();hideT=setTimeout(function(){addBtn.style.display='none';curLine=null;},450);}
function showAt(blk){
  var ln=parseInt(blk.getAttribute('data-src-line'),10);if(isNaN(ln))return;
  curLine=ln;var r=blk.getBoundingClientRect();
  addBtn.style.top=Math.max(2,r.top)+'px';
  // sit just LEFT of the text block (not the viewport edge)
  addBtn.style.left=Math.max(2,r.left-30)+'px';
  addBtn.style.display='flex';
}
addBtn.addEventListener('click',function(ev){
  ev.preventDefault();ev.stopPropagation();if(curLine!=null)openComposer(curLine);});
lane.addEventListener('mouseenter',keepBtn);
lane.addEventListener('mouseleave',scheduleHide);
// the button is now positioned next to the text (not in the edge lane), so it
// needs its own hover-persistence to stay clickable while the pointer is on it.
addBtn.addEventListener('mouseenter',keepBtn);
addBtn.addEventListener('mouseleave',scheduleHide);
document.addEventListener('mousemove',function(e){
  if(!canComment)return;
  var blk=e.target&&e.target.closest&&e.target.closest('.page [data-src-line]');
  if(blk&&!blk.classList.contains('hub-inline-note')){keepBtn();showAt(blk);}
});

// ── ⌘C / Ctrl+C → composer (guarded: only when nothing is selected) ─────────
document.addEventListener('keydown',function(e){
  var k=(e.key||'').toLowerCase();
  if(!((e.metaKey||e.ctrlKey)&&!e.altKey&&!e.shiftKey&&k==='c'))return;
  var sel=window.getSelection&&window.getSelection();
  if(sel&&String(sel).length>0)return;                 // real selection → native copy
  var tag=(e.target&&e.target.tagName)||'';
  if(tag==='INPUT'||tag==='TEXTAREA'||(e.target&&e.target.isContentEditable))return;
  if(!canComment)return;
  e.preventDefault();openComposer(curLine);
});

// ── ✎ Edit in place (S18 editor, ported off the reader) ─────────────────────
var editing=false,rawOrig='',baseMtime=null,pageSaved=null;
window.hubDocEdit=function(){
  if(editing||!CFG.editable)return;
  var page=document.querySelector('.page');if(!page)return;
  fetch('/_doc-raw?path='+encodeURIComponent(CFG.path)).then(function(r){
    if(!r.ok)throw 0;baseMtime=r.headers.get('X-Doc-Mtime');return r.text();
  }).then(function(text){
    rawOrig=text;editing=true;addBtn.style.display='none';curLine=null;pageSaved=page.innerHTML;
    page.innerHTML='<div class="hub-editor"><div class="editor-body">'+
      '<div class="editor-gutter" id="hub-ed-gutter" aria-hidden="true"></div>'+
      '<textarea id="hub-ed-ta" spellcheck="false" wrap="off"></textarea></div>'+
      '<div class="editor-foot"><span>editing raw source \\u2014 \\u2318\\u21b5 save \\u00b7 esc cancel</span>'+
      '<span class="ef-dirty" id="hub-ed-dirty"></span>'+
      '<span class="ef-btns"><button type="button" id="hub-ed-cancel">cancel</button>'+
      '<button type="button" id="hub-ed-save">save</button></span></div></div>';
    var ta=document.getElementById('hub-ed-ta');ta.value=text;
    var gutter=document.getElementById('hub-ed-gutter');
    function sync(){var n=(ta.value.match(/\\n/g)||[]).length+1;var s='';
      for(var k=1;k<=n;k++)s+=k+'\\n';gutter.textContent=s;gutter.scrollTop=ta.scrollTop;}
    function dirty(){document.getElementById('hub-ed-dirty').textContent=
      (ta.value!==rawOrig)?'\\u25cf unsaved':'';}
    ta.addEventListener('input',function(){dirty();sync();});
    ta.addEventListener('scroll',function(){gutter.scrollTop=ta.scrollTop;});
    ta.addEventListener('keydown',function(ev){
      if(ev.key==='Escape'){ev.preventDefault();ev.stopPropagation();cancelEdit();}
      else if((ev.metaKey||ev.ctrlKey)&&ev.key==='Enter'){ev.preventDefault();ev.stopPropagation();saveEdit();}
    });
    document.getElementById('hub-ed-cancel').addEventListener('click',cancelEdit);
    document.getElementById('hub-ed-save').addEventListener('click',saveEdit);
    sync();ta.focus();
  }).catch(function(){alert('could not open for editing');});
};
function cancelEdit(){
  if(!editing)return;
  var ta=document.getElementById('hub-ed-ta');
  if(ta&&ta.value!==rawOrig&&!window.confirm('Discard your unsaved changes?'))return;
  editing=false;var page=document.querySelector('.page');
  if(page&&pageSaved!=null){page.innerHTML=pageSaved;renderNotes();}
}
function saveEdit(){
  var ta=document.getElementById('hub-ed-ta');if(!ta)return;
  fetch('/_edit-doc',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:CFG.path,content:ta.value,base_mtime:baseMtime})})
    .then(function(r){return r.json().then(function(d){return{status:r.status,ok:r.ok,d:d};});})
    .then(function(res){
      if(res.status===409){alert('file changed on disk \\u2014 reloading');location.reload();return;}
      if(!res.ok||!res.d.ok){alert((res.d&&res.d.detail)||(res.d&&res.d.error)||'save failed');return;}
      location.reload();
    }).catch(function(){alert('save failed');});
}

function init(){document.body.appendChild(lane);renderNotes();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
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
                      provenance_html: str = "", pub_path: str = "",
                      pub_url: str = "", doc_cfg: dict | None = None) -> str:
    """Inject backlinks CSS + HTML into an existing HTML document.

    ``doc_cfg`` (S21) carries this file's comment context so the self-sufficient
    :data:`DOC_PAGE_SCRIPT` can render baked inline comments + the "+" gutter
    composer on a top-level tab. HTML docs are never editable, so no ✎ Edit item
    is offered here."""
    src, outline_html = _add_outline(src)
    head_inject = f"<style>{_BACKLINKS_CSS}{_DOC_CHROME_CSS}</style>"
    if favicon:
        head_inject = f'<link rel="icon" type="image/svg+xml" href="{favicon}">' + head_inject
    src = re.sub(r"</head>", head_inject + "</head>", src, count=1, flags=re.IGNORECASE)
    # ⋯ menu (Open published? + Publish + Save as PDF) goes right after <body>
    # so it floats over the doc; the tiny publisher script goes at end-of-body.
    if pub_path:
        # S27 — one wrapped publish-state control (Publish, or Open/Republish/
        # Unpublish when live) the inline script rewrites in place, + Save as PDF.
        items = [doc_pub_actions(pub_path, pub_url), DOC_PDF_ITEM]
        menu = doc_menu(items)
    else:
        menu = _DOC_PRINT_BTN
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
    # S21 — self-sufficient inline comments + "+" gutter composer on the doc page
    # itself (no SPA parent). Config first (window.HUB_DOC), then the script.
    page_scripts = doc_config_script(doc_cfg or {}) + DOC_PAGE_SCRIPT
    if re.search(r"</body>", src, re.IGNORECASE):
        src = re.sub(r"</body>", lambda _mo: page_scripts + "</body>",
                     src, count=1, flags=re.IGNORECASE)
    else:
        src += page_scripts
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

