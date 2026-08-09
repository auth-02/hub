// @ts-nocheck — moved verbatim from static/hub.js. Vanilla DOM script that reads
// lexical globals (FTS_DATA, _currentRoot, …) injected by hub.html's inline
// <script>; not type-checked. The CSS import below is bundled to static/hub.css.
import "./hub.css";

const ftsMap=new Map(FTS_DATA.map(d=>[d.a,d]));
const STATUS_CYCLE=['ongoing','completed','paused'];

// 1g — published-state lookup. PUBLISHED_DATA is the baked state_dir()/published.json
// map keyed by "<repo>\t<slug>" → {url, at, mode}. Missing/undefined → not published.
function publishedFor(t){
  if(typeof PUBLISHED_DATA==='undefined'||!PUBLISHED_DATA) return null;
  return PUBLISHED_DATA[(t.rp||'(root)')+'\t'+t.sl]||null;
}
// S20 — published-state for a single file/artifact. The SAME baked
// PUBLISHED_DATA map also holds asset entries keyed "asset\t<abspath>" (mirror
// of core.publish.published_asset_key). Missing/undefined → not published.
function publishedForFile(abs){
  if(typeof PUBLISHED_DATA==='undefined'||!PUBLISHED_DATA||!abs) return null;
  return PUBLISHED_DATA['asset\t'+abs]||null;
}
// The PUBLISHED chip for a single file — a deep-sea marker linking to the live
// URL plus republish (↻) / revoke (✕) actions. Actions carry data-pub-file*
// attributes so ONE delegated handler drives them wherever a file row appears.
// Buttons (never nested <a>) so they sit safely inside the row's own anchor.
function filePubChip(abs){
  const pub=publishedForFile(abs);
  if(!pub) return '';
  const url=pub.url||'';
  return `<span class="task-pub file-pub" title="published ${esc(pub.at||'')}">`+
    `<button class="file-pub-open" type="button" data-pub-file-open="${esc(abs)}"${url?'':' disabled'} title="Open the live published URL">PUBLISHED</button>`+
    `<button class="task-pub-act" type="button" data-pub-file-republish="${esc(abs)}" title="Republish (scan + hand off to dak)">↻</button>`+
    `<button class="task-pub-act" type="button" data-pub-file-revoke="${esc(abs)}" title="Unpublish (take the live URL down + forget it)">✕</button></span>`;
}
// (Re)decorate a file row anchor with (or without) its PUBLISHED chip. Idempotent
// — strips any existing chip first, so it can run after a publish/revoke.
function decorateFileRow(r){
  if(!r) return;
  const old=r.querySelector(':scope > .file-pub'); if(old) old.remove();
  const chip=filePubChip(r.dataset.abs);
  if(!chip) return;
  const path=r.querySelector('.path');
  if(path) path.insertAdjacentHTML('afterend',chip); else r.insertAdjacentHTML('beforeend',chip);
}
function decorateFileRowByAbs(abs){
  if(typeof rows==='undefined') return;
  rows.forEach(r=>{if(r.dataset.abs===abs) decorateFileRow(r);});
}

// 1g / S26 — the PUBLISHED chip for a TASK row (PUBLISHED link + republish ↻ /
// unpublish ✕). Factored so renderWorkView bakes it AND the in-place update
// after publish/revoke can re-render it without a full reload.
function taskPubBadge(t){
  const pub=publishedFor(t);
  if(!pub) return '';
  return `<span class="task-pub" title="published ${esc(pub.at||'')}">${
    pub.url?`<a href="${esc(pub.url)}" target="_blank" rel="noopener">PUBLISHED</a>`:'PUBLISHED'
  }<button class="task-pub-act" data-pub-republish title="Republish (re-render + hand off to dak)">↻</button>`+
    `<button class="task-pub-act" data-pub-revoke title="Unpublish (take the live URL down + forget it)">✕</button></span>`;
}
// (Re)decorate any visible task row(s) for <sl,rp> with the current marker —
// idempotent (strips an existing chip first). Lets publish/revoke update the
// marker IN PLACE so the user stays on their current view (no home nav).
function decorateTaskRow(sl,rp){
  document.querySelectorAll('.task-row').forEach(r=>{
    if(r.dataset.sl!==sl||r.dataset.rp!==rp) return;
    const nameEl=r.querySelector('.task-name'); if(!nameEl) return;
    const old=nameEl.querySelector('.task-pub'); if(old) old.remove();
    const badge=taskPubBadge({sl:sl,rp:rp});
    if(badge) nameEl.insertAdjacentHTML('beforeend',badge);
  });
}
// S26 — reflect a just-(un)published task's marker WITHOUT a full reload: mutate
// the baked PUBLISHED_DATA (a later reload re-bakes it from published.json) then
// re-decorate its row(s). Mirrors the single-file _markFilePublished path.
function _markTaskPublished(t,url,mode){
  if(typeof PUBLISHED_DATA==='object'&&PUBLISHED_DATA)
    PUBLISHED_DATA[(t.rp||'(root)')+'\t'+t.sl]={url:url,at:'',mode:mode||'live'};
  decorateTaskRow(t.sl,t.rp);
}
function _unmarkTaskPublished(sl,rp){
  if(typeof PUBLISHED_DATA==='object'&&PUBLISHED_DATA)
    delete PUBLISHED_DATA[(rp||'(root)')+'\t'+sl];
  decorateTaskRow(sl,rp);
}

// ── DOM refs ──────────────────────────────────────────────────────────────
const q=document.getElementById('q');
const rows=[...document.querySelectorAll('.row')];
// S20 — surface any single-file PUBLISHED marker on its row (chip + actions).
rows.forEach(decorateFileRow);
const chips=[...document.querySelectorAll('.chip')];
const preview=document.getElementById('preview');
const pvTitle=document.getElementById('pv-title');
const pvOpen=document.getElementById('pv-open');
const pvBody=document.getElementById('pv-body');
const pvLineage=document.getElementById('pv-lineage');
const pvAsk=document.getElementById('pv-ask');
if(pvAsk) pvAsk.addEventListener('click',()=>{const cmd=askAgainCmd(_openPreviewAbs);if(cmd) copy(cmd,'copied: '+cmd);});
let kind=sessionStorage.getItem('docs_hub_kind')||'all';
if(sessionStorage.getItem('docs_hub_root')!==_currentRoot){
  sessionStorage.setItem('docs_hub_root',_currentRoot);
  sessionStorage.removeItem('docs_hub_repos');
  sessionStorage.removeItem('docs_hub_q');
}
let activeRepos=new Set((sessionStorage.getItem('docs_hub_repos')||'').split(',').filter(Boolean));
let selIdx=-1,selRows=[];

// ── FTS body enrichment ───────────────────────────────────────────────────
rows.forEach(r=>{
  const fts=ftsMap.get(r.dataset.abs);
  if(fts) r._fts=fts;
});

// ── Task status badges ────────────────────────────────────────────────────
rows.forEach(r=>{
  if(r.dataset.kind!=='task'||!r.dataset.taskSlug) return;
  const key=r.dataset.taskRepo+':'+r.dataset.taskSlug;
  const status=TASK_STATUS_DATA[key]||'ongoing';
  const badge=document.createElement('span');
  badge.className='status-badge s-'+status;
  badge.textContent=status;
  badge.dataset.s=status;
  r.querySelector('.ago').insertAdjacentElement('beforebegin',badge);
  badge.addEventListener('click',function(e){
    e.preventDefault();e.stopPropagation();
    const next=STATUS_CYCLE[(STATUS_CYCLE.indexOf(this.dataset.s)+1)%STATUS_CYCLE.length];
    this.dataset.s=next;
    this.className='status-badge s-'+next;
    this.textContent=next;
    TASK_STATUS_DATA[key]=next;
    fetch('/_task-status',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({task_slug:r.dataset.taskSlug,task_repo:r.dataset.taskRepo,status:next})
    }).catch(()=>flash('status update failed'));
  });
});

// ── Filter ────────────────────────────────────────────────────────────────
function apply(){
  const raw=q.value.trim().toLowerCase();
  const rm=raw.match(/(?:^|\s)repo:(\S*)/);
  const typedRepo=rm?rm[1]:'';
  const rs=raw.match(/(?:^|\s)status:(\S*)/);
  const typedStatus=rs?rs[1]:'';
  const rk=raw.match(/(?:^|\s)kind:(\S*)/);
  const typedKind=rk?rk[1]:'';
  const t=raw.replace(/(?:^|\s)(?:repo|status|kind):\S*/g,'').trim();
  sessionStorage.setItem('docs_hub_q',raw);
  sessionStorage.setItem('docs_hub_kind',kind);
  sessionStorage.setItem('docs_hub_repos',[...activeRepos].join(','));
  chips.forEach(c=>c.classList.toggle('active',c.dataset.kind===kind));
  document.querySelectorAll('.rchip').forEach(el=>el.classList.toggle('active',activeRepos.has(el.dataset.repo)));
  document.querySelectorAll('.repo-name').forEach(el=>el.classList.toggle('pinned',activeRepos.has(el.dataset.repo)));
  rows.forEach(r=>{
    const rowRepo=r.dataset.search.split(' ')[0];
    const okKind=kind==='all'||r.dataset.kind===kind;
    const okChip=activeRepos.size===0||activeRepos.has(rowRepo);
    const okTyped=!typedRepo||rowRepo.startsWith(typedRepo);
    const terms=t.split(/\s+/).filter(Boolean);
    const body=r._fts?(r._fts.b+' '+r._fts.t).toLowerCase():'';
    const okText=terms.length===0||terms.every(w=>r.dataset.search.includes(w)||body.includes(w));
    const okStatus=!typedStatus||(r.dataset.status||'')=== typedStatus;
    const okKind2=!typedKind||(r.dataset.kind||'').startsWith(typedKind);
    r.classList.toggle('hidden',!(okKind&&okKind2&&okChip&&okTyped&&okText&&okStatus));
  });
  document.querySelectorAll('.repo').forEach(s=>{
    const any=[...s.querySelectorAll('.row')].some(r=>!r.classList.contains('hidden'));
    s.classList.toggle('hidden',!any);
  });
  selIdx=-1; selRows=[];
  renderWorkView();
}
q.addEventListener('input',apply);
chips.forEach(c=>c.addEventListener('click',()=>{kind=c.dataset.kind;apply();}));
function toggleRepo(repo){
  activeRepos.has(repo)?activeRepos.delete(repo):activeRepos.add(repo);
  apply();
}
document.querySelectorAll('.rchip').forEach(el=>el.addEventListener('click',()=>toggleRepo(el.dataset.repo)));
document.querySelectorAll('.repo-name').forEach(el=>el.addEventListener('click',()=>toggleRepo(el.dataset.repo)));
q.value=sessionStorage.getItem('docs_hub_q')||'';
activeRepos=new Set((sessionStorage.getItem('docs_hub_repos')||'').split(',').filter(Boolean));

// ── Preserve the open overlay + scroll across softReload()/manual refresh ───
// A rebuild (watcher, any write, or the 120s tick) does a full location.reload();
// without this, the open preview/trace/graph closes and you land back on the
// index — "back to home". Capture what's open + scrollY, restore it on load.
let _openPreviewAbs=null, _openTraceT=null;
window._graphCurrent=null;
function _captureViewState(){
  try{
    const pvEl=document.getElementById('preview');
    const trEl=document.getElementById('trace');
    const gcEl=document.getElementById('gcanvas');
    let ov=null;
    // Graph is checked first: it overlays the Trace (both can be `show` at once),
    // so an open graph must win the restore.
    if(gcEl&&gcEl.classList.contains('show')&&window._graphCurrent){
      ov={k:'graph',sl:window._graphCurrent.sl,rp:window._graphCurrent.rp};
    }else if(pvEl&&pvEl.classList.contains('open')&&_openPreviewAbs){
      ov={k:'preview',abs:_openPreviewAbs};
    }else if(trEl&&trEl.classList.contains('show')&&_openTraceT){
      ov={k:'trace',sl:_openTraceT.sl,rp:_openTraceT.rp};
    }
    sessionStorage.setItem('hub_view_state',
      JSON.stringify({ov:ov,y:window.scrollY||window.pageYOffset||0}));
  }catch(_){}
}
// beforeunload also covers a manual browser refresh, not just softReload().
window.addEventListener('beforeunload',_captureViewState);
function softReload(){_captureViewState();location.reload();}
setInterval(()=>softReload(),120000);

// ── Relative-time helper (used by board / work / timeline / trace) ─────────
function feedAgo(ts){
  const d=(Date.now()/1000)-ts;
  if(d<90) return 'just now';
  if(d<3600) return Math.floor(d/60)+'m ago';
  if(d<86400) return Math.floor(d/3600)+'h ago';
  return Math.floor(d/86400)+'d ago';
}

// ── Preview ───────────────────────────────────────────────────────────────
function getVisible(){return rows.filter(r=>!r.classList.contains('hidden'));}

function selectRow(idx){
  if(selRows[selIdx]) selRows[selIdx].classList.remove('selected');
  selRows=getVisible();
  if(idx<0||idx>=selRows.length) return;
  selIdx=idx;
  selRows[selIdx].classList.add('selected');
  selRows[selIdx].scrollIntoView({block:'nearest'});
  openPreview(selRows[selIdx]);
}

// S6 (2a) — build the /changelog command for an artifact that carries the
// skill's provenance front matter. The "ask again" button COPIES this string;
// it never calls an endpoint or runs anything. Hub stays a consumer.
function askAgainCmd(abs){
  if(typeof PROVENANCE_DATA==='undefined'||!PROVENANCE_DATA) return null;
  const prov=PROVENANCE_DATA[abs];
  if(!prov) return null;
  const slug=prov.task||'<task-slug>';
  const rng=prov.commit_range||'';
  const end=rng.includes('..')?rng.split('..').pop():rng;
  return end?`/changelog ${slug} --since ${end}`:`/changelog ${slug}`;
}
function openPreview(row){
  // Reverted (S24) to the pre-S21 preview: full // trace lineage (incl. the data
  // group) + the separate ask-again/⧉ buttons; no inline ⋯ menu.
  pvTitle.textContent=row.querySelector('.path').textContent;
  pvOpen.href=row.href;
  const abs=row.dataset.abs||'';
  pvOpen.dataset.abs=abs;   // Open → the delegated router opens the doc page (new tab)
  _openPreviewAbs=abs;
  const links=LINEAGE_DATA[abs]||[];
  if(links.length){
    pvLineage.innerHTML=buildLineage(links);pvLineage.classList.add('show');
    const nl=pvLineage.querySelector('.ln-notes-link');
    if(nl)nl.onclick=()=>{const tk=taskForNoteAbs(nl.dataset.noteAbs);if(tk){closePreview();openTaskNotes(tk);}};
  }
  else pvLineage.classList.remove('show');
  if(pvAsk) pvAsk.style.display=askAgainCmd(abs)?'':'none';
  pvBody.classList.add('iframe-mode');
  pvBody.innerHTML=`<iframe class="pv-iframe" src="${row.href}"></iframe>`;
  preview.classList.add('open');
}

function closePreview(){
  _openPreviewAbs=null;
  preview.classList.remove('open');
  pvBody.classList.remove('iframe-mode');
  pvBody.innerHTML='';
  if(selRows[selIdx]) selRows[selIdx].classList.remove('selected');
  selIdx=-1;
}

rows.forEach(r=>r.addEventListener('click',e=>{
  e.preventDefault();
  // Excalidraw diagrams need room to edit, so open the full canvas in a new tab
  // instead of the narrow preview iframe.
  if(r.dataset.kind==='draw'){window.open(r.href,'_blank','noopener');return;}
  selRows=getVisible();
  const vi=selRows.indexOf(r);
  if(vi>=0){
    if(selRows[selIdx]) selRows[selIdx].classList.remove('selected');
    selIdx=vi;
    selRows[selIdx].classList.add('selected');
    openPreview(r);
  }
}));

document.getElementById('pv-close').addEventListener('click',closePreview);

// ── Floating windows ──────────────────────────────────────────────────────
const FLOAT_WINS=new Map();
let floatZ=60,floatN=0;
function clamp(v,min,max){return Math.max(min,Math.min(max,v));}
function openFloat(abs,title,href){
  if(!abs) return;
  const existing=FLOAT_WINS.get(abs);
  if(existing){existing.style.zIndex=++floatZ;return;}
  const w=document.createElement('div');
  w.className='float-win';
  const n=floatN++;
  const left=clamp(80+28*n,0,Math.max(0,window.innerWidth-540));
  const top=clamp(80+28*n,0,Math.max(0,window.innerHeight-460));
  w.style.left=left+'px';w.style.top=top+'px';
  w.style.width='520px';w.style.height='440px';
  w.style.zIndex=++floatZ;
  const head=document.createElement('div');
  head.className='float-head';
  const ttl=document.createElement('span');
  ttl.className='float-title';ttl.textContent=title||abs;ttl.title=abs;
  const open=document.createElement('a');
  open.className='float-ctl';open.href=href;open.target='_blank';open.rel='noopener';open.textContent='⤤ open';
  // S14 / #6 — publish this floating doc via the safe scan→review→publish sheet.
  const pub=document.createElement('button');
  pub.className='float-ctl';pub.type='button';pub.textContent='↗ pub';
  pub.title='publish this file to a shareable URL';
  pub.addEventListener('click',e=>{e.stopPropagation();if(window._openPublish)window._openPublish({abs:abs});});
  const close=document.createElement('button');
  close.className='float-ctl';close.type='button';close.textContent='✕';
  head.appendChild(ttl);head.appendChild(open);head.appendChild(pub);head.appendChild(close);
  const body=document.createElement('div');
  body.className='float-body';
  const ifr=document.createElement('iframe');
  ifr.src=href;
  body.appendChild(ifr);
  w.appendChild(head);w.appendChild(body);
  document.body.appendChild(w);
  FLOAT_WINS.set(abs,w);
  w.addEventListener('mousedown',()=>{w.style.zIndex=++floatZ;});
  close.addEventListener('click',e=>{e.stopPropagation();FLOAT_WINS.delete(abs);w.remove();});
  let drag=null;
  head.addEventListener('pointerdown',e=>{
    if(e.target.classList.contains('float-ctl')) return;
    drag={dx:e.clientX-w.offsetLeft,dy:e.clientY-w.offsetTop};
    head.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  head.addEventListener('pointermove',e=>{
    if(!drag) return;
    const nx=clamp(e.clientX-drag.dx,0,Math.max(0,window.innerWidth-w.offsetWidth));
    const ny=clamp(e.clientY-drag.dy,0,Math.max(0,window.innerHeight-head.offsetHeight));
    w.style.left=nx+'px';w.style.top=ny+'px';
  });
  function endDrag(e){if(drag){drag=null;try{head.releasePointerCapture(e.pointerId);}catch(_){}}}
  head.addEventListener('pointerup',endDrag);
  head.addEventListener('pointercancel',endDrag);
}
document.getElementById('pv-float').addEventListener('click',()=>{
  if(selIdx<0||!selRows[selIdx]) return;
  const r=selRows[selIdx];
  openFloat(r.dataset.abs,r.querySelector('.path').textContent,r.href);
  closePreview();
});
rows.forEach(r=>r.addEventListener('dblclick',e=>{
  e.preventDefault();
  openFloat(r.dataset.abs,r.querySelector('.path').textContent,r.href);
}));

// ── Floating comment composer (S7 · 1e) ─────────────────────────────────────
// Pressing `c` (or the preview/trace "write a comment…" affordance, or the
// palette's New-note row) opens a compact floating box — NOT the palette. It is
// anchored to the current context: the open preview/trace/graph file+task, else
// the selected row's file, else the first task's manifest. ⌘↵/Ctrl↵ appends the
// comment (POST /_note → one JSONL line) then softReloads; esc cancels. The box
// is transient UI — deliberately NOT part of hub_view_state, so it never
// interferes with the overlay-restore logic.
function _taskDirOf(t){return (t&&t.abs||'').replace(/\/manifest\.md$/,'');}
function _ctxForAbs(abs){
  if(!abs||typeof TASKS_DATA==='undefined') return null;
  for(const t of TASKS_DATA){
    const dir=_taskDirOf(t);
    if(dir&&(abs===dir||abs.indexOf(dir+'/')===0)){
      return {task:t,target:abs===dir?'manifest.md':abs.slice(dir.length+1)};
    }
  }
  return null;
}
function composerContext(){
  // 1) an open trace / 2) an open graph → that task, general (manifest) target.
  if(_openTraceT) return {task:_openTraceT,target:'manifest.md'};
  if(window._graphCurrent&&typeof TASKS_DATA!=='undefined'){
    const g=window._graphCurrent;
    const t=TASKS_DATA.find(x=>x.sl===g.sl&&x.rp===g.rp);
    if(t) return {task:t,target:'manifest.md'};
  }
  // 3) an open preview → the previewed file's owning task + task-relative target.
  if(_openPreviewAbs){const c=_ctxForAbs(_openPreviewAbs);if(c) return c;}
  // 4) the selected list row's file.
  if(selIdx>=0&&selRows[selIdx]){const c=_ctxForAbs(selRows[selIdx].dataset.abs);if(c) return c;}
  // 5) fall back to the first task's manifest.
  const t0=(typeof TASKS_DATA!=='undefined'&&TASKS_DATA.length)?TASKS_DATA[0]:null;
  return t0?{task:t0,target:'manifest.md'}:null;
}
let _composerEl=null,_composerCtx=null;
function _buildComposer(){
  if(_composerEl) return;
  const el=document.createElement('div');
  el.id='composer';el.className='composer';
  el.innerHTML=
    '<div class="composer-head"><span class="composer-title" id="cmp-title">comment</span>'+
    '<button class="composer-x" id="cmp-x" type="button" title="cancel (esc)">✕</button></div>'+
    '<div class="composer-dest" id="cmp-dest"></div>'+
    '<input class="composer-range" id="cmp-range" type="text" autocomplete="off" '+
    'spellcheck="false" placeholder="range — L41-L48 (optional, inline)">'+
    '<textarea class="composer-body" id="cmp-body" rows="4" '+
    'placeholder="write a comment…"></textarea>'+
    '<div class="composer-foot"><span class="composer-hint">⌘↵ save · esc cancel</span>'+
    '<button class="composer-save" id="cmp-save" type="button">Comment</button></div>';
  document.body.appendChild(el);
  _composerEl=el;
  const body=el.querySelector('#cmp-body');
  el.querySelector('#cmp-x').addEventListener('click',closeComposer);
  el.querySelector('#cmp-save').addEventListener('click',_composerSave);
  function onKey(e){
    if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();_composerSave();}
    else if(e.key==='Escape'){e.preventDefault();closeComposer();}
    e.stopPropagation();  // don't leak keys to the global hotkey handler
  }
  body.addEventListener('keydown',onKey);
  el.querySelector('#cmp-range').addEventListener('keydown',onKey);
}
function openComposer(ctx){
  ctx=ctx||composerContext();
  if(!ctx||!ctx.task){flash('no task to comment on — create one first');return;}
  _buildComposer();
  _composerCtx=ctx;
  const t=ctx.task,tgt=ctx.target||'manifest.md';
  _composerEl.querySelector('#cmp-title').textContent='comment on '+tgt;
  _composerEl.querySelector('#cmp-dest').textContent=
    (t.rp&&t.rp!=='(root)'?t.rp+'/':'')+'tasks/'+t.sl+'/comments/notes.jsonl';
  // S19 — a line-click prefills the range (e.g. "L4") so the comment anchors
  // to that line without the user typing it; the field stays editable.
  _composerEl.querySelector('#cmp-range').value=ctx.range||'';
  _composerEl.querySelector('#cmp-body').value='';
  _composerEl.classList.add('show');
  setTimeout(()=>_composerEl.querySelector('#cmp-body').focus(),0);
}
function closeComposer(){if(_composerEl)_composerEl.classList.remove('show');_composerCtx=null;}
function _composerSave(){
  if(!_composerCtx){closeComposer();return;}
  const t=_composerCtx.task;
  const body=(_composerEl.querySelector('#cmp-body').value||'').trim();
  if(!body){flash('comment body required');return;}
  const target=_composerCtx.target||'manifest.md';
  const range=(_composerEl.querySelector('#cmp-range').value||'').trim();
  const saveBtn=_composerEl.querySelector('#cmp-save');saveBtn.disabled=true;
  fetch('/_note',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({repo:t.rp,slug:t.sl,target:target,range:range,body:body})})
    .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
    .then(res=>{
      if(res.ok){closeComposer();flashSticky('comment saved…');softReload();return;}
      saveBtn.disabled=false;
      const d=res.d||{};
      flash('comment failed: '+(d.detail||d.error||'unknown'));
    }).catch(()=>{saveBtn.disabled=false;flash('comment failed');});
}
window._openComposer=openComposer;

// ── Opening a file (S21) — navigate the tab to the canonical doc page ───────
// The S17 in-workspace reading overlay is gone. Opening a file now navigates the
// current tab to the standalone served doc page (render/page.py), which is fully
// self-sufficient: it renders its own inline comments, hosts the "+" gutter
// composer, and carries ✎ Edit / ↗ Publish in its ⋯ menu. Browser Back returns
// to the SPA. Modified clicks / an explicit ↗ new-tab affordance still pop a raw
// tab. window._openReader stays as an alias so older callsites keep working.
function openDoc(abs,href){
  const u=href||(abs?fileHref(abs):'');
  if(u)window.open(u,'_blank','noopener');   // always a new tab — SPA stays put
}
window._openReader=(abs,opts)=>openDoc(abs,opts&&opts.href);

// Delegated router: any in-app browsing link marked data-open-reader navigates
// the tab to the doc page. Plain <a> anchors (href already set to the doc page)
// navigate natively; this handles the few non-anchor / dataset-only callers and
// keeps modified clicks (⌘/Ctrl/⇧/middle) falling through to a raw tab.
document.addEventListener('click',e=>{
  const a=e.target.closest&&e.target.closest('[data-open-reader]');
  if(!a)return;
  if(e.metaKey||e.ctrlKey||e.shiftKey||e.button===1)return;
  const abs=a.dataset.abs;
  const href=a.getAttribute&&a.getAttribute('href');
  if(!abs&&!href)return;
  e.preventDefault();
  openDoc(abs,href||undefined);
});

// ── Keyboard nav ──────────────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  const tag=document.activeElement.tagName;
  if(tag==='INPUT'||tag==='TEXTAREA') return;
  if(document.getElementById('trace').classList.contains('show')){
    if(e.key==='Escape') closeTrace();
    else if((e.key==='g'||e.key==='G')&&_openTraceT){e.preventDefault();if(window._openGraphFor)window._openGraphFor(_openTraceT);}
    return;
  }
  if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();selectRow(selIdx<0?0:selIdx+1);}
  else if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();selectRow(Math.max(selIdx-1,0));}
  else if(e.key==='Escape'){closePreview();}
  else if(e.key==='Enter'&&selIdx>=0&&selRows[selIdx]){
    const r=selRows[selIdx];
    // Diagrams still open in the full canvas (new tab); everything else navigates
    // the tab to the canonical doc page (S21).
    if(r.dataset.kind==='draw')window.open(r.href,'_blank','noopener');
    else openDoc(r.dataset.abs,r.href);
  }
  else if(e.key==='/'&&!modal.classList.contains('show')){e.preventDefault();q.focus();}
});

// ── Lineage builder ───────────────────────────────────────────────────────
function buildLineage(links,withLabel=true){
  const groups={};
  links.forEach(l=>{(groups[l.r]=groups[l.r]||[]).push(l);});
  const ORDER=['belongs_to_task','belongs_to_skill','task_has_run','task_has_artifact','task_has_script','task_has_draw','task_has_data','task_has_note','task_has_prompt','task_has_doc','skill_has_ref'];
  const LABELS={'belongs_to_task':'↑ task','belongs_to_skill':'↑ skill','task_has_run':'runs','task_has_artifact':'artifacts','task_has_script':'scripts','task_has_draw':'draws','task_has_data':'data','task_has_note':'notes','task_has_prompt':'prompts','task_has_doc':'docs','skill_has_ref':'references'};
  let h=withLabel?'<div class="ln-label">// trace</div>':'';
  ORDER.forEach(r=>{
    if(!groups[r]) return;
    h+=`<div class="ln-group"><span class="ln-type">${LABELS[r]||r}</span>`;
    if(r==='task_has_note'){
      // Internal comment log — route to the // NOTES view, never link the raw
      // notes.jsonl (which would download). data-note-abs lets the delegated
      // handler resolve the owning task from the path.
      const l=groups[r][0];
      h+=`<button class="ln-item ln-notes-link" type="button" data-note-abs="${esc(l.a)}" title="open comments">${groups[r].length} comment${groups[r].length===1?'':'s'} →</button>`;
      h+='</div>';
      return;
    }
    groups[r].forEach(l=>{
      const name=l.p.split('/').pop();
      h+=`<a class="ln-item" href="${fileHref(l.a)}" data-open-reader data-abs="${esc(l.a)}" title="${esc(l.p)}">${esc(name)}</a>`;
    });
    h+='</div>';
  });
  return h;
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function fileHref(abs){return SERVER_ORIGIN?SERVER_ORIGIN+encodeURI(abs):'file://'+encodeURI(abs);}

// ── Themed dropdown (S8) ────────────────────────────────────────────────────
// Native <select> renders as an OS popup (a dark glassy macOS list) that clashes
// with the paper/oxblood/mono theme. themeSelect() wraps a real <select> — kept
// in the DOM and hidden — with a themed button + option panel drawn on the paper
// ground. The hidden <select> stays the source of truth: existing code still
// sets `sel.innerHTML` of <option>s, reads `sel.value`, and listens for `change`.
// Picking a themed option writes `sel.value` and dispatches a native `change`,
// so all New-task / Add-data / Publish wiring keeps working unchanged. After
// repopulating a select's options, call the returned controller's `.refresh()`.
// Transient UI only — never persisted to hub_view_state.
function themeSelect(sel){
  if(!sel||sel._dd) return sel&&sel._dd;
  const wrap=document.createElement('div');
  wrap.className='pal-dd';
  sel.parentNode.insertBefore(wrap,sel);
  wrap.appendChild(sel);
  sel.classList.add('pal-dd-native');
  sel.tabIndex=-1;  // the themed button is the tab stop; keep the native one out
  const btn=document.createElement('button');
  btn.type='button';btn.className='pal-dd-btn';
  btn.setAttribute('aria-haspopup','listbox');btn.setAttribute('aria-expanded','false');
  btn.innerHTML='<span class="pal-dd-val"></span><span class="pal-dd-caret">▾</span>';
  const panel=document.createElement('div');
  panel.className='pal-dd-panel';panel.setAttribute('role','listbox');
  wrap.appendChild(btn);wrap.appendChild(panel);
  const valEl=btn.querySelector('.pal-dd-val');
  let open=false,hi=-1;
  function opts(){return [...sel.options];}
  function selectedIdx(){return Math.max(0,sel.selectedIndex);}
  function refresh(){
    const os=opts();
    valEl.textContent=os.length?(os[selectedIdx()]?os[selectedIdx()].textContent:''):'';
    panel.innerHTML=os.map((o,i)=>
      '<div class="pal-dd-opt'+(i===sel.selectedIndex?' sel':'')+'" role="option" data-i="'+i+'"'+
      (i===sel.selectedIndex?' aria-selected="true"':'')+'>'+esc(o.textContent)+'</div>').join('');
    btn.disabled=!os.length;
  }
  function paintHi(){
    [...panel.children].forEach((el,i)=>el.classList.toggle('hi',i===hi));
    const el=panel.children[hi];if(el)el.scrollIntoView({block:'nearest'});
  }
  function openPanel(){
    if(open||btn.disabled) return;
    open=true;wrap.classList.add('open');btn.setAttribute('aria-expanded','true');
    hi=selectedIdx();paintHi();
  }
  function closePanel(){
    if(!open) return;
    open=false;wrap.classList.remove('open');btn.setAttribute('aria-expanded','false');
  }
  function pick(i){
    const os=opts();if(i<0||i>=os.length) return;
    if(sel.selectedIndex!==i){sel.selectedIndex=i;sel.dispatchEvent(new Event('change',{bubbles:true}));}
    refresh();closePanel();btn.focus();
  }
  btn.addEventListener('click',e=>{e.preventDefault();open?closePanel():openPanel();});
  btn.addEventListener('keydown',e=>{
    if(e.key==='Enter'||e.key===' '||e.key==='ArrowDown'){
      e.preventDefault();
      if(!open){openPanel();return;}
      if(e.key==='ArrowDown'){hi=Math.min(opts().length-1,hi+1);paintHi();return;}
      pick(hi);
    }else if(e.key==='ArrowUp'){e.preventDefault();if(open){hi=Math.max(0,hi-1);paintHi();}else openPanel();}
    else if(e.key==='Escape'){if(open){e.preventDefault();e.stopPropagation();closePanel();}}
  });
  panel.addEventListener('mousedown',e=>{
    const o=e.target.closest('.pal-dd-opt');if(!o)return;
    e.preventDefault();pick(+o.dataset.i);
  });
  panel.addEventListener('mousemove',e=>{
    const o=e.target.closest('.pal-dd-opt');if(!o)return;
    hi=+o.dataset.i;paintHi();
  });
  document.addEventListener('mousedown',e=>{if(open&&!wrap.contains(e.target))closePanel();});
  refresh();
  const ctl={refresh:refresh,el:wrap};
  sel._dd=ctl;
  return ctl;
}

// ── Timeline (ONE renderer, TWO scopes: 'global' | 'task') ─────────────────
// 1c: the same component renders at the head of Work ("what have I been doing")
// and inside Trace ("how did this task get here") — differing only by which
// query feeds it. Authoring kinds (things you create) read oxblood --accent;
// navigation kinds (structure you move through) read deep-sea --accent2.
const TL_AUTHOR=new Set(['artifact','run','note','draw','data','script']);
const TL_EVENT_LABEL={task:'Task opened',artifact:'Artifact added',run:'Run logged',note:'Note',prompt:'Prompt written',doc:'Doc written',draw:'Diagram',data:'Data added'};
// Shared kind → card colour (the graph canvas + the Trace spine both read this,
// so the two renderings stay chromatically identical). Authoring kinds skew
// oxblood/warm; navigation kinds skew deep-sea/cool.
const KIND_COLOR={task:'#7A2828',doc:'#1E5A6B',artifact:'#5C4A7A',run:'#2F6B4F',data:'#2E7D8A',draw:'#B5651D',note:'#C15F3C',prompt:'#C99A20',script:'#556B7D'};
const colorForKind=k=>KIND_COLOR[k]||'#8A8377';
const _MON3=['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
// "2026-07-22" → "JUL 22"; anything unparseable is passed through untouched.
function fmtEventDate(at){
  const m=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(at||''));
  if(!m) return String(at||'');
  return _MON3[(+m[2]-1)%12]+' '+(+m[3]);
}
// A task node's path lives under tasks/<slug>/ ; anything else the timeline pulls
// in is "outside the task" (a referenced doc, a cross-task file).
function nodeInTask(path,slug){return String(path||'').indexOf('tasks/'+slug+'/')>=0;}
// One short, human descriptor per event, matching the comp's spine cards.
function eventDesc(ev,t){
  const kind=ev.kind||'doc';
  const name=(ev.path||'').split('/').pop()||'';
  if(kind==='task'){
    const n=(t&&t.plan&&t.plan.length)||0;
    return 'task opened'+(n?' · '+n+' plan item'+(n>1?'s':''):'');
  }
  // A NOTE event is one comment line — show its text (+ author), never the
  // notes.jsonl filename. `label` is baked by query.timeline (S13).
  if(kind==='note'){
    const body=ev.label||'comment';
    return ev.author?(body+' — '+ev.author):body;
  }
  return name||(TL_EVENT_LABEL[kind]||kind);
}

// The 2b timeline nodes for a task, chronological (oldest first = evolution).
// ISO `at` dates sort lexically, so no Date parsing needed.
function taskGraph(t){
  const g=(typeof TASK_TIMELINE_DATA!=='undefined'&&TASK_TIMELINE_DATA[t.rp+'\t'+t.sl])||null;
  if(!g) return {nodes:[],edges:[]};
  return {nodes:g.nodes||[],edges:g.edges||[]};
}
function taskTimelineEvents(t){
  return taskGraph(t).nodes.slice().sort((a,b)=>(a.at<b.at?-1:a.at>b.at?1:0));
}

// Global scope: bucket a unix ts into today / yesterday / this-week (or null).
function tlBucket(ts,now){
  const todayStart=(()=>{const d=new Date(now*1000);d.setHours(0,0,0,0);return d.getTime()/1000;})();
  if(ts>=todayStart) return 'today';
  if(ts>=todayStart-86400) return 'yesterday';
  if(ts>=todayStart-6*86400) return 'week';
  return null;
}

// scope==='global' → renders TIMELINE_DATA into `mount`, returns a one-line
// summary string. scope==='task' → renders the per-task spine, returns event count.
function renderTimeline(mount,scope,task){
  if(!mount) return scope==='task'?0:'';
  if(scope==='task'){
    const evs=taskTimelineEvents(task);
    mount.innerHTML=evs.map(ev=>{
      const kind=ev.kind||'doc';
      const ext=!nodeInTask(ev.path,task.sl);
      const desc=eventDesc(ev,task);
      // NOTE events open the in-UI // NOTES view; every other event carries no
      // click here (the spine is a read-only overview).
      const note=kind==='note';
      return `<div class="tlx-item ${TL_AUTHOR.has(kind)?'tlx-author':'tlx-nav'}${ext?' tlx-ext':''}${note?' tlx-note':''}"${note?' role="button" tabindex="0"':''}>
        <span class="tlx-when">${esc(fmtEventDate(ev.at))}</span>
        <span class="tlx-dot" style="--kc:${colorForKind(kind)}"></span>
        <span class="tlx-badge" style="--kc:${colorForKind(kind)}">${esc((kind||'').toUpperCase())}</span>
        <span class="tlx-desc">${esc(desc)}</span>
      </div>`;
    }).join('');
    mount.querySelectorAll('.tlx-note').forEach(it=>{
      it.onclick=()=>openTaskNotes(task);
      it.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openTaskNotes(task);}};
    });
    return evs.length;
  }
  // scope==='global'
  const tasks=TIMELINE_DATA.tasks||[];
  const commits=TIMELINE_DATA.commits||[];
  if(!tasks.length&&!commits.length){mount.innerHTML='';return '';}
  const now=Date.now()/1000;
  const grouped={today:[],yesterday:[],week:[]};
  tasks.forEach(t=>{const b=tlBucket(t.ts,now);if(b)grouped[b].push(t);});
  const cIdx={};
  let commitCount=0;
  commits.forEach(c=>{
    const b=tlBucket(c.ts,now);if(!b)return;
    commitCount++;
    const k=b+':'+c.rp;
    if(!cIdx[k])cIdx[k]=[];
    if(cIdx[k].length<3)cIdx[k].push(c.msg);
  });
  function renderTask(t,b){
    const name=tagName(t.sl);
    const bullets=[];
    if(t.manifest)bullets.push(t.manifest>1?`manifest revised ×${t.manifest}`:'manifest revised');
    if(t.runs)bullets.push(t.runs===1?'1 run logged':`${t.runs} runs logged`);
    if(t.artifacts)bullets.push(t.artifacts===1?'1 artifact generated':`${t.artifacts} artifacts generated`);
    if(t.prompts)bullets.push(t.prompts===1?'prompt updated':`${t.prompts} prompts updated`);
    if(t.docs)bullets.push('doc updated');
    const repoCommits=cIdx[b+':'+t.rp]||[];
    const statusCls=t.status==='ongoing'?'ongoing':t.status==='completed'?'completed':'paused';
    return `<div class="tl-task">
      <div class="tl-head">
        <span class="tl-name">${esc(name)}</span>
        <span class="tl-repo">${esc(t.rp)}</span>
        <span class="tl-status ${statusCls}">${esc(t.status)}</span>
      </div>
      ${bullets.length?`<ul class="tl-bullets">${bullets.map(x=>`<li class="tl-bullet">${esc(x)}</li>`).join('')}</ul>`:''}
      ${repoCommits.map(m=>`<div class="tl-commit">${esc(m)}</div>`).join('')}
    </div>`;
  }
  const LABELS={today:'What have I been working on?',yesterday:'What did I work on yesterday?',week:'What did I work on this week?'};
  let h='';
  ['today','yesterday','week'].forEach(b=>{
    if(!grouped[b].length)return;
    h+=`<div class="tl-period">${LABELS[b]}</div>`;
    h+=grouped[b].map(t=>renderTask(t,b)).join('');
  });
  mount.innerHTML=h;
  const taskCount=grouped.today.length+grouped.yesterday.length+grouped.week.length;
  const parts=[];
  if(taskCount)parts.push(`${taskCount} task${taskCount>1?'s':''} active`);
  if(commitCount)parts.push(`${commitCount} commit${commitCount>1?'s':''}`);
  return parts.length?parts.join(' · ')+' this week':'';
}

// ── Head-of-Work timeline: render + collapse (persisted) ───────────────────
(function(){
  const panel=document.getElementById('tl-panel');
  const mount=document.getElementById('hub-timeline');
  const summaryEl=document.getElementById('tl-panel-summary');
  const btn=document.getElementById('tl-collapse');
  if(!panel||!mount) return;
  const summary=renderTimeline(mount,'global');
  if(!summary){panel.style.display='none';return;}  // empty → no panel at all
  summaryEl.textContent=summary;
  // Always-on for a new workspace, then remember the user's choice.
  const KEY='hub_tl_collapsed';
  let collapsed=false;
  try{collapsed=localStorage.getItem(KEY)==='1';}catch(_){}
  function apply(){
    panel.classList.toggle('collapsed',collapsed);
    btn.textContent=collapsed?'+':'–';
    btn.title=(collapsed?'expand':'collapse')+' timeline (y)';
  }
  function toggle(){
    collapsed=!collapsed;
    try{localStorage.setItem(KEY,collapsed?'1':'0');}catch(_){}
    apply();
  }
  apply();
  btn.addEventListener('click',toggle);
  window._toggleTimeline=toggle;  // wired to the `y` hotkey
})();

// ── Task Board (kanban) ───────────────────────────────────────────────────
function tagName(sl){return String(sl).replace(/[-_]/g,' ').replace(/^./,c=>c.toUpperCase());}
function buildCard(t){
  const card=document.createElement('div');
  card.className='kanban-card';
  card.draggable=true;
  card.dataset.sl=t.sl;card.dataset.rp=t.rp;card.dataset.abs=t.abs;
  const chips=[];
  if(t.runs)chips.push(t.runs+' run'+(t.runs>1?'s':''));
  if(t.artifacts)chips.push(t.artifacts+' artifact'+(t.artifacts>1?'s':''));
  if(t.prompts)chips.push(t.prompts+' prompt'+(t.prompts>1?'s':''));
  if(t.docs)chips.push(t.docs+' doc'+(t.docs>1?'s':''));
  if(t.data)chips.push(t.data+' data');
  card.innerHTML=`<div class="kc-name">${esc(tagName(t.sl))}</div>`+
    `<div class="kc-repo">${esc(t.rp)}</div>`+
    (chips.length?`<div class="kc-chips">${chips.map(c=>`<span class="kc-chip">${esc(c)}</span>`).join('')}</div>`:'')+
    `<div class="kc-ago">${feedAgo(t.mtime)}</div>`;
  card.addEventListener('click',()=>{if(t.abs)openDoc(t.abs);});
  card.addEventListener('dragstart',e=>{
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed='move';
    e.dataTransfer.setData('text/plain',t.rp+':'+t.sl);
  });
  card.addEventListener('dragend',()=>card.classList.remove('dragging'));
  return card;
}
function renderBoard(){
  const boardEmpty=document.getElementById('board-empty');
  const kanbanCols=document.querySelectorAll('.kanban-col');
  if(!TASKS_DATA.length){
    kanbanCols.forEach(c=>c.style.display='none');
    boardEmpty.style.display='block';
    return;
  }
  kanbanCols.forEach(c=>c.style.display='');
  boardEmpty.style.display='none';
  const counts={ongoing:0,paused:0,completed:0};
  document.querySelectorAll('.kanban-body').forEach(b=>b.innerHTML='');
  TASKS_DATA.forEach(t=>{
    const st=['ongoing','paused','completed'].includes(t.status)?t.status:'ongoing';
    const body=document.querySelector('.kanban-body[data-status="'+st+'"]');
    if(body){body.appendChild(buildCard(t));counts[st]++;}
  });
  ['ongoing','paused','completed'].forEach(st=>{
    document.querySelector('.kanban-count[data-count="'+st+'"]').textContent=counts[st];
    const body=document.querySelector('.kanban-body[data-status="'+st+'"]');
    if(!counts[st])body.innerHTML='<div class="kanban-empty">— none —</div>';
  });
}
document.querySelectorAll('.kanban-col').forEach(col=>{
  const status=col.dataset.status;
  const body=col.querySelector('.kanban-body');
  col.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';col.classList.add('over');});
  col.addEventListener('dragleave',()=>col.classList.remove('over'));
  col.addEventListener('drop',e=>{
    e.preventDefault();col.classList.remove('over');
    // Use dataTransfer — more reliable than .dragging class which may be
    // removed by dragend before drop fires in some browsers.
    const raw=e.dataTransfer.getData('text/plain');
    if(!raw)return;
    const sep=raw.indexOf(':');
    const rp=raw.slice(0,sep),sl=raw.slice(sep+1);
    const card=document.querySelector(`.kanban-card[data-sl="${sl}"][data-rp="${rp}"]`);
    if(!card)return;
    const empty=body.querySelector('.kanban-empty');if(empty)empty.remove();
    body.appendChild(card);
    const t=TASKS_DATA.find(x=>x.sl===sl&&x.rp===rp);
    if(t)t.status=status;
    fetch('/_task-status',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({task_slug:sl,task_repo:rp,status:status})
    }).then(r=>{
      if(!r.ok){flash('status update failed');return;}
      // Server has already rebuilt the HTML with the new status.
      // Reload so TASKS_DATA reflects the DB — keeps board accurate across view switches.
      softReload();
    }).catch(()=>flash('status update failed'));
    document.querySelectorAll('.kanban-body').forEach(b=>{
      const s=b.dataset.status,n=b.querySelectorAll('.kanban-card').length;
      document.querySelector('.kanban-count[data-count="'+s+'"]').textContent=n;
      if(!n&&!b.querySelector('.kanban-empty'))b.innerHTML='<div class="kanban-empty">— none —</div>';
    });
  });
});

// ── Calendar ──────────────────────────────────────────────────────────────
let calRef=new Date();calRef.setDate(1);
const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
function renderCalendar(){
  const grid=document.getElementById('cal-grid');
  const y=calRef.getFullYear(),mo=calRef.getMonth();
  document.getElementById('cal-title').textContent=MONTHS[mo]+' '+y;
  const byDay={};
  TASKS_DATA.forEach(t=>{
    const d=new Date(t.mtime*1000);
    if(d.getFullYear()===y&&d.getMonth()===mo){(byDay[d.getDate()]=byDay[d.getDate()]||[]).push({_t:t,type:'task'});}
  });
  const now=new Date();
  const isThisMonth=now.getFullYear()===y&&now.getMonth()===mo;
  const firstDow=new Date(y,mo,1).getDay();
  const days=new Date(y,mo+1,0).getDate();
  let h='';
  ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d=>h+=`<div class="cal-dow">${d}</div>`);
  for(let i=0;i<firstDow;i++)h+='<div class="cal-cell blank"></div>';
  for(let day=1;day<=days;day++){
    const today=isThisMonth&&now.getDate()===day;
    const entries=byDay[day]||[];
    const chips=entries.map(e=>{
      const t=e._t;
      const st=['ongoing','paused','completed'].includes(t.status)?t.status:'ongoing';
      return `<a class="cal-chip s-${st}" href="${fileHref(t.abs)}" data-open-reader data-abs="${esc(t.abs)}" title="${esc(t.rp+' / '+t.sl)}">${esc(tagName(t.sl))}</a>`;
    }).join('');
    h+=`<div class="cal-cell${today?' cal-today':''}"><div class="cal-day">${day}</div>${chips}</div>`;
  }
  grid.innerHTML=h;
}
document.getElementById('cal-prev').addEventListener('click',()=>{calRef.setMonth(calRef.getMonth()-1);renderCalendar();});
document.getElementById('cal-next').addEventListener('click',()=>{calRef.setMonth(calRef.getMonth()+1);renderCalendar();});

// 1g — PUBLISHED marker actions (republish / revoke). Delegated once at module
// scope so re-renders never stack listeners. Republish re-runs the bundle flow;
// revoke forgets the local published-state entry (server: POST /_publish-revoke).
document.addEventListener('click',e=>{
  const row=e.target.closest&&e.target.closest('.task-row');
  if(!row)return;
  if(e.target.closest('[data-pub-republish]')){
    e.preventDefault();e.stopPropagation();
    if(window._publishBundle)window._publishBundle({sl:row.dataset.sl,rp:row.dataset.rp});
    return;
  }
  if(e.target.closest('[data-pub-revoke]')){
    e.preventDefault();e.stopPropagation();
    const sl=row.dataset.sl,rp=row.dataset.rp;
    fetch('/_publish-revoke',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({slug:sl,repo:rp})})
      .then(r=>r.json()).then(d=>{
        if(d&&d.ok){
          // S26 — clear the marker IN PLACE (no home nav). "unpublished" when the
          // worker was taken down; else "forgotten locally" + the take-down detail.
          _unmarkTaskPublished(sl,rp);
          flash(d.unpublished?('unpublished '+sl)
                :('forgotten locally'+(d.detail?(' — '+String(d.detail).split('\n').slice(-1)[0]):'')));
        } else flash('unpublish failed');
      }).catch(()=>flash('unpublish failed'));
  }
});

// S20 — republish a single file: reuse the honest scan→review→publish sheet,
// prefilled to this file (same flow + dry-run handling as first publish). Revoke
// forgets the local asset entry (server: POST /_publish-revoke with {path}).
function revokeFile(abs){
  fetch('/_publish-revoke',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:abs})})
    .then(r=>r.json()).then(d=>{
      if(d&&d.ok){
        // S26 — clear the marker IN PLACE (no home nav); mirror the asset publish
        // path. "unpublished" when dak took the worker down, else "forgotten
        // locally" with the take-down detail.
        if(typeof PUBLISHED_DATA==='object'&&PUBLISHED_DATA) delete PUBLISHED_DATA['asset\t'+abs];
        decorateFileRowByAbs(abs);
        flash(d.unpublished?'unpublished'
              :('forgotten locally'+(d.detail?(' — '+String(d.detail).split('\n').slice(-1)[0]):'')));
      } else flash('unpublish failed');
    }).catch(()=>flash('unpublish failed'));
}
function republishFile(abs){
  if(window._openPublish)window._openPublish({abs:abs});
}
window._republishFile=republishFile;window._revokeFile=revokeFile;

// S20 — file PUBLISHED chip actions (rows + reader). Delegated once at module
// scope; the data-pub-file* attributes carry the file's abs path so the handler
// works wherever a chip is rendered. Runs in the CAPTURE phase so it intercepts
// the click BEFORE the enclosing row's own (bubble-phase) open handler —
// stop/prevent then keep the chip action from also opening the row.
document.addEventListener('click',e=>{
  if(!e.target.closest)return;
  const openBtn=e.target.closest('[data-pub-file-open]');
  if(openBtn){
    e.preventDefault();e.stopPropagation();
    const pub=publishedForFile(openBtn.getAttribute('data-pub-file-open'));
    if(pub&&pub.url)window.open(pub.url,'_blank','noopener');
    return;
  }
  const rep=e.target.closest('[data-pub-file-republish]');
  if(rep){e.preventDefault();e.stopPropagation();republishFile(rep.getAttribute('data-pub-file-republish'));return;}
  const rev=e.target.closest('[data-pub-file-revoke]');
  if(rev){e.preventDefault();e.stopPropagation();revokeFile(rev.getAttribute('data-pub-file-revoke'));return;}
},true);

// ── Work view ─────────────────────────────────────────────────────────────
function renderWorkView(){
  const raw=q.value.trim().toLowerCase();
  const rm=raw.match(/(?:^|\s)repo:(\S*)/);
  const typedRepo=rm?rm[1]:'';
  const rs2=raw.match(/(?:^|\s)status:(\S*)/);
  const typedStatus2=rs2?rs2[1]:'';
  const textQ=raw.replace(/(?:^|\s)(?:repo|status|kind):\S*/g,'').trim();
  const terms=textQ.split(/\s+/).filter(Boolean);

  function taskMatches(t){
    if(activeRepos.size>0&&!activeRepos.has(t.rp.toLowerCase())) return false;
    if(typedRepo&&!t.rp.toLowerCase().startsWith(typedRepo)) return false;
    if(typedStatus2&&(t.status||'ongoing')!==typedStatus2) return false;
    if(!terms.length) return true;
    const haystack=(t.sl+' '+t.rp).toLowerCase();
    return terms.every(w=>haystack.includes(w));
  }

  const statStrip=document.getElementById('stat-strip');
  const taskRowsEl=document.getElementById('task-rows');
  const looseEl=document.getElementById('loose-section');

  const filtered=TASKS_DATA.filter(taskMatches);
  const counts={ongoing:0,paused:0,completed:0};
  filtered.forEach(t=>{const s=t.status||'ongoing';if(counts[s]!==undefined)counts[s]++;});

  if(filtered.length){
    statStrip.innerHTML=
      `<span><span class="stat-dot d-on"></span><b>${counts.ongoing}</b>ongoing</span>`+
      `<span><span class="stat-dot d-pause"></span><b>${counts.paused}</b>paused</span>`+
      `<span><span class="stat-dot d-done"></span><b>${counts.completed}</b>completed</span>`;
  } else {
    statStrip.innerHTML='';
  }

  const STATUS_DOT={ongoing:'d-on',paused:'d-pause',completed:'d-done'};
  taskRowsEl.innerHTML=filtered.map(t=>{
    const st=t.status||'ongoing';
    const dotCls=STATUS_DOT[st]||'d-on';
    const linParts=[];
    if(t.runs)linParts.push(`<b>${t.runs}</b> run${t.runs>1?'s':''}`);
    if(t.artifacts)linParts.push(`<b>${t.artifacts}</b> artifact${t.artifacts>1?'s':''}`);
    if(t.prompts)linParts.push(`<b>${t.prompts}</b> prompt${t.prompts>1?'s':''}`);
    if(t.data)linParts.push(`<b>${t.data}</b> data`);
    if(t.plan&&t.plan.length){
      const done=t.plan.filter(p=>p.d).length;
      linParts.push(`plan ${done}/${t.plan.length}`);
    }
    const orphanBadge=t.orphan?`<span style="font-family:var(--mono);font-size:9px;letter-spacing:.08em;color:var(--mute);border:1px solid var(--line);padding:1px 5px;margin-left:6px;vertical-align:middle">no manifest</span>`:'';
    const pubBadge=taskPubBadge(t);
    return `<div class="task-row" data-abs="${esc(t.abs||'')}" data-sl="${esc(t.sl)}" data-rp="${esc(t.rp)}">
      <span class="task-tick ${dotCls}"></span>
      <div class="task-body">
        <div class="task-name">${esc(tagName(t.sl))}${orphanBadge}${pubBadge}</div>
        <div class="task-loc"><span class="t-repo">${esc(t.rp)}</span> · tasks/${esc(t.sl)}</div>
        ${linParts.length?`<div class="task-lin">${linParts.join(' · ')}</div>`:''}
      </div>
      <div class="task-when">${feedAgo(t.mtime)}</div>
    </div>`;
  }).join('');

  // Loose files: rows not under any task (kind not in task family and no task_slug)
  const taskAbsSet=new Set(TASKS_DATA.map(t=>t.abs));
  const taskSlugs=new Set(TASKS_DATA.map(t=>t.sl));
  const looseRows=rows.filter(r=>{
    if(r.classList.contains('hidden')) return false;
    const slug=r.dataset.taskSlug;
    return !slug;
  });
  if(looseRows.length){
    looseEl.innerHTML=`<div class="loose-head">// loose files — not under a task (${looseRows.length})</div>`+
      looseRows.map(r=>{
        const kd=(r.dataset.kind||r.dataset.search.split(' ')[0]||'').toUpperCase()||'MD';
        const path=r.querySelector('.path')?.textContent||'';
        return `<a class="loose-row" href="${r.href}" data-open-reader data-abs="${esc(r.dataset.abs||'')}">
          <span class="loose-kd">${esc(kd)}</span>
          <span>${esc(path)}</span>
          ${filePubChip(r.dataset.abs)}
        </a>`;
      }).join('');
  } else {
    looseEl.innerHTML='';
  }

  // Wire up task row clicks → trace
  taskRowsEl.querySelectorAll('.task-row').forEach(el=>{
    el.addEventListener('click',()=>{
      const t=TASKS_DATA.find(x=>x.sl===el.dataset.sl&&x.rp===el.dataset.rp);
      if(t) openTrace(t);
    });
  });
}

// ── Trace overlay ─────────────────────────────────────────────────────────
const traceEl=document.getElementById('trace');
const _ST_MAP={ongoing:'ts-on',paused:'ts-pause',completed:'ts-done'};
const _ST_ORDER=['ongoing','paused','completed'];

// 1i — inline manifest editing. The manifest file on disk is the source of
// truth: every edit POSTs the whole plan (and/or status) to /_manifest-edit,
// which rewrites ONLY the frontmatter status line + the ## Plan block. We send
// the mtime we last read (base_mtime); a 409 means the file changed under us —
// hub never wins that race, so we reload to re-read rather than overwrite.
async function saveManifest(t,patch){
  const body=Object.assign({repo:t.rp,slug:t.sl,base_mtime:t.mtime},patch);
  try{
    const r=await fetch('/_manifest-edit',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(r.status===409){
      flashSticky('file changed on disk — reloading…');
      setTimeout(()=>location.reload(),700);
      return false;
    }
    if(!r.ok){flash('save failed');return false;}
    const out=await r.json().catch(()=>null);
    if(out&&out.mtime)t.mtime=out.mtime;  // fresh base for the next edit
    flash('saved');
    return true;
  }catch(e){flash('save failed');return false;}
}

// Resolve a scan-root-relative node path to an abs path via the file rows.
function resolveNodeAbs(rel){
  if(!rel) return null;
  let hit=null;
  rows.forEach(r=>{const a=r.dataset.abs;if(a&&a.replace(/\\/g,'/').endsWith('/'+rel))hit=hit||a;});
  return hit;
}
// The edges that leave a task: timeline edges with exactly one endpoint outside
// tasks/<slug>/. Returns [{inName, extPath, extAbs}] (inner filename ← outside path).
function taskExternalEdges(t){
  const g=taskGraph(t);
  const byId={};g.nodes.forEach(n=>{byId[n.id]=n;});
  const out=[];
  (g.edges||[]).forEach(e=>{
    const a=byId[e.from],b=byId[e.to];if(!a||!b)return;
    const aIn=nodeInTask(a.path,t.sl),bIn=nodeInTask(b.path,t.sl);
    if(aIn===bIn) return;                       // both inside or both outside — not a boundary
    const inside=aIn?a:b, outside=aIn?b:a;
    const extPath=outside.path||outside.id;
    out.push({inName:(inside.path||'').split('/').pop()||inside.id,
              extPath:extPath,extAbs:resolveNodeAbs(outside.path)});
  });
  return out;
}
// list|graph segmented toggle state (transient — never persisted).
function setTraceMode(m){
  const seg=document.getElementById('trace-modeseg');
  if(!seg) return;
  seg.querySelectorAll('.trace-mode').forEach(b=>b.classList.toggle('active',b.dataset.mode===m));
}
window._setTraceMode=setTraceMode;

// Relative time from a comment's ISO `created` string (feedAgo wants unix secs).
function noteAgo(created){
  const ms=Date.parse(created);
  return isNaN(ms)?(created||''):feedAgo(ms/1000);
}

// // NOTES section — render the task's stored comments (S12). Keyed by
// "<repo>\t<slug>" in NOTES_DATA, matching TASK_TIMELINE_DATA. Bodies arrive as
// raw data and are escaped here; line breaks are preserved via white-space CSS.
function renderTraceNotes(t){
  const el=document.getElementById('trace-notes');
  if(!el) return;
  const notes=(typeof NOTES_DATA!=='undefined'&&NOTES_DATA[t.rp+'\t'+t.sl])||[];
  let h=`<div class="trace-section-label">// notes · ${notes.length}</div>`;
  if(notes.length){
    h+='<div class="notes-list">'+notes.map(c=>{
      const agent=/(agent|bot)/i.test(c.author||'');
      const anchored=c.target&&c.target!=='manifest.md';
      let meta=`<span class="note-author${agent?' agent':''}">`+
        (agent?'▸ ':'')+esc(c.author||'anon')+'</span>'+
        `<span class="note-time">${esc(noteAgo(c.created))}</span>`;
      if(anchored){
        meta+=`<span class="note-on">on ${esc(c.target)}`+
          (c.range?` · ${esc(c.range)}`:'')+`</span>`;
      }
      return `<div class="note-card${agent?' agent':''}">`+
        `<div class="note-meta">${meta}</div>`+
        `<div class="note-body">${esc(c.body||'')}</div></div>`;
    }).join('')+'</div>';
  }else{
    h+='<div class="notes-empty">no comments yet — '+
      '<button class="note-add-link" id="note-add-empty" type="button">write a comment…</button></div>';
  }
  el.innerHTML=h;
  const addBtn=document.getElementById('note-add-empty');
  if(addBtn)addBtn.onclick=()=>{if(window._openComposer)window._openComposer({task:t,target:'manifest.md'});};
}

// Route any "note" affordance (lineage group, spine NOTE event, a comment ref)
// to the in-UI // NOTES view — NEVER to the raw notes.jsonl file (which would
// download). Opens the owning task's Trace and scrolls the // NOTES section
// into view + briefly highlights it.
function openTaskNotes(t){
  if(!t) return;
  const already=_openTraceT&&_openTraceT.sl===t.sl&&_openTraceT.rp===t.rp;
  if(!already) openTrace(t);
  requestAnimationFrame(()=>{
    const el=document.getElementById('trace-notes');
    if(!el) return;
    el.scrollIntoView({block:'nearest',behavior:'smooth'});
    el.classList.remove('notes-flash');void el.offsetWidth;el.classList.add('notes-flash');
  });
}
// Resolve the task that owns a note path (abs or task-relative) from TASKS_DATA.
function taskForNoteAbs(abs){
  const c=_ctxForAbs(abs);
  return c?c.task:null;
}

function openTrace(t){
  _openTraceT=t;
  const stMap=_ST_MAP;
  const editable=!!t.abs;  // an orphan (no manifest) stays read-only

  document.getElementById('trace-crumb').innerHTML=
    `${esc(t.rp)} / <span class="tc-accent">tasks</span> / ${esc(t.sl)}`+
    (t.orphan?' <span style="font-family:var(--mono);font-size:9px;color:var(--mute);border:1px solid var(--line);padding:1px 6px;margin-left:6px">no manifest</span>':'');
  document.getElementById('trace-title').textContent=tagName(t.sl);

  // Status pill — click to cycle ongoing → paused → completed, persisted to the
  // manifest frontmatter (and the status sidecar) so the file stays the truth.
  const statusEl=document.getElementById('trace-status');
  function renderStatus(){
    const s=t.status||'ongoing';
    statusEl.className='trace-status '+(stMap[s]||'ts-on')+(editable?' editable':'');
    statusEl.textContent=s+' · updated '+feedAgo(t.mtime)+(editable?' · click to cycle':'');
  }
  renderStatus();
  statusEl.onclick=editable?async function(){
    const prev=t.status||'ongoing';
    const next=_ST_ORDER[(_ST_ORDER.indexOf(prev)+1)%_ST_ORDER.length];
    t.status=next;renderStatus();
    const ok=await saveManifest(t,{status:next});
    if(ok){const key=t.rp+':'+t.sl;if(typeof TASK_STATUS_DATA!=='undefined')TASK_STATUS_DATA[key]=next;renderStatus();}
    else{t.status=prev;renderStatus();}
  }:null;

  const planEl=document.getElementById('trace-plan');
  if(!editable){
    if(t.plan&&t.plan.length){
      planEl.innerHTML=t.plan.map(p=>
        `<li class="${p.d?'tp-done':'tp-todo'}">${esc(p.t)}</li>`
      ).join('');
    } else {
      planEl.innerHTML='<li class="tp-todo" style="color:var(--mute);font-style:italic">no plan checklist in manifest</li>';
    }
  } else {
    // Editable checklist: toggle a box, edit a line's text (↵ save · esc revert),
    // or "+ add a plan item". Each mutation re-sends the whole plan.
    let planItems=(t.plan||[]).map(p=>({t:p.t,d:!!p.d}));
    function persistPlan(){
      t.plan=planItems.map(p=>({t:p.t,d:p.d}));
      return saveManifest(t,{plan:planItems.map(p=>({text:p.t,done:p.d}))});
    }
    function startEdit(span,p){
      const input=document.createElement('input');
      input.className='tp-input';input.value=p.t;
      span.replaceWith(input);input.focus();input.select();
      let done=false;
      const finish=async(save)=>{
        if(done)return;done=true;
        if(save){
          const val=input.value.trim();
          if(val===p.t){renderPlan();return;}
          p.t=val;
          if(!val)planItems=planItems.filter(x=>x!==p);  // emptied → drop the line
          renderPlan();await persistPlan();
        } else {
          if(!p.t)planItems=planItems.filter(x=>x!==p);  // abandoned a fresh empty line
          renderPlan();
        }
      };
      input.onkeydown=(e)=>{
        if(e.key==='Enter'){e.preventDefault();finish(true);}
        else if(e.key==='Escape'){e.preventDefault();finish(false);}
      };
      input.onblur=()=>finish(true);
    }
    function renderPlan(){
      planEl.innerHTML='';
      planItems.forEach(p=>{
        const li=document.createElement('li');
        li.className='tp-edit '+(p.d?'tp-done':'tp-todo');
        const box=document.createElement('button');
        box.type='button';box.className='tp-box';box.title='toggle done';
        box.onclick=async()=>{p.d=!p.d;renderPlan();await persistPlan();};
        const span=document.createElement('span');
        span.className='tp-text';span.textContent=p.t;
        span.title='click to edit · ↵ save · esc revert';
        span.onclick=()=>startEdit(span,p);
        li.appendChild(box);li.appendChild(span);
        planEl.appendChild(li);
      });
      const add=document.createElement('button');
      add.type='button';add.className='tp-add';add.textContent='+ add a plan item';
      add.onclick=()=>{
        const p={t:'',d:false};planItems.push(p);renderPlan();
        const spans=planEl.querySelectorAll('.tp-text');
        if(spans.length)startEdit(spans[spans.length-1],p);
      };
      planEl.appendChild(add);
    }
    renderPlan();
  }

  const decisionsEl=document.getElementById('trace-decisions');
  const decisionsLbl=document.getElementById('trace-decisions-label');
  if(t.decisions&&t.decisions.length){
    decisionsEl.innerHTML=t.decisions.map((d,i)=>
      `<li><span class="td-num">${i+1}.</span><span>${esc(d)}</span></li>`
    ).join('');
    decisionsLbl.style.display='block';
  } else {
    decisionsEl.innerHTML='';
    decisionsLbl.style.display='none';
  }

  // Lineage grid from LINEAGE_DATA keyed by manifest abs
  const lin=document.getElementById('trace-lineage');
  const links=LINEAGE_DATA[t.abs]||[];
  const LIN_ORDER=['task_has_run','task_has_artifact','task_has_script','task_has_draw','task_has_note','task_has_prompt','task_has_data','task_has_doc'];
  const LIN_LABELS={'task_has_run':'Runs','task_has_artifact':'Artifacts','task_has_script':'Scripts & probes','task_has_draw':'Draws','task_has_note':'Notes','task_has_prompt':'Prompts','task_has_data':'Data','task_has_doc':'Docs'};
  const groups={};
  links.forEach(l=>{(groups[l.r]=groups[l.r]||[]).push(l);});
  let linH='';
  LIN_ORDER.forEach(rel=>{
    if(!groups[rel]) return;
    // NOTE lineage is internal storage (comments/notes.jsonl), not a document:
    // show the comment count and route the whole group to the // NOTES view
    // instead of linking to the raw .jsonl (which would download).
    if(rel==='task_has_note'){
      const n=(NOTES_DATA[t.rp+'\t'+t.sl]||[]).length;
      linH+=`<div class="tl-lbl">${LIN_LABELS[rel]||rel}</div>
        <div class="tl-files"><button class="tl-file tl-notes-link" type="button">
        <span>${n} comment${n===1?'':'s'} →</span>
        <span class="tl-fmeta">notes</span></button></div>`;
      return;
    }
    linH+=`<div class="tl-lbl">${LIN_LABELS[rel]||rel}</div>
      <div class="tl-files">`;
    groups[rel].forEach(l=>{
      const name=l.p.split('/').pop();
      const meta=l.p.split('/').slice(-2,-1)[0]||'';
      linH+=`<a class="tl-file" href="${fileHref(l.a)}" data-open-reader data-abs="${esc(l.a)}">
        <span>${esc(name)}</span>
        <span class="tl-fmeta">${esc(meta)}</span>
      </a>`;
    });
    linH+='</div>';
  });
  lin.innerHTML=linH||'<div class="tl-lbl" style="color:var(--mute)">—</div><div class="tl-files" style="padding:12px 0 12px 16px;border-left:1px solid var(--line);color:var(--mute);font-family:var(--mono);font-size:11px">no children indexed yet</div>';
  const linNotes=lin.querySelector('.tl-notes-link');
  if(linNotes)linNotes.onclick=()=>openTaskNotes(t);

  // Per-task timeline spine — "how did this task get here" (1c). Same renderer
  // as the head-of-Work timeline, scope='task'. NOTE events (S3b comments/) are
  // included because they carry a task_slug and flow through query.timeline.
  const tlHead=document.getElementById('trace-tl-head');
  const tlLabel=document.getElementById('trace-tl-label');
  const n=renderTimeline(document.getElementById('trace-timeline'),'task',t);
  if(n){
    tlLabel.textContent=`// how this task got here · ${n} event${n>1?'s':''}`;
    tlHead.style.display='flex';
  } else {
    tlHead.style.display='none';
  }
  // // NOTES (S12) — the task's stored comments rendered as cards. Read fresh
  // from the baked NOTES_DATA on every open, so a comment added since the last
  // rebuild appears after the softReload re-bakes the map. Each card is
  // author · relative-time · body; a note anchored to a file/line shows its
  // target (and range). No comments → a subtle hint + the composer affordance.
  renderTraceNotes(t);

  window._graphTaskCtx=t;  // last task in focus — the palette G row opens this

  // The list|graph toggle always lands on `list` when the Trace (re)opens; the
  // graph canvas overlays and hands the mode back to `list` when it closes.
  setTraceMode('list');

  // LINEAGE footer (2b) — the edges that *leave* this task: any timeline edge
  // touching a node whose path lives outside tasks/<slug>/ (a referenced doc or
  // cross-task file). Rendered as `<inner> ← <outside>`. Actions: publish the
  // task's dak bundle, or copy the spine as a markdown list.
  const foot=document.getElementById('trace-linfoot');
  const ext=taskExternalEdges(t);
  let fh=`<div class="linfoot-label">LINEAGE — ${ext.length} edge${ext.length===1?'':'s'} leave${ext.length===1?'s':''} this task</div>`;
  if(ext.length){
    fh+='<div class="linfoot-edges">'+ext.map(e=>
      `<div class="linfoot-edge"><span class="lf-in">${esc(e.inName)}</span>`+
      `<span class="lf-arr">←</span>`+
      (e.extAbs?`<a class="lf-ext" href="${fileHref(e.extAbs)}" data-open-reader data-abs="${esc(e.extAbs)}" title="${esc(e.extPath)}">${esc(e.extPath)}</a>`
               :`<span class="lf-ext" title="${esc(e.extPath)}">${esc(e.extPath)}</span>`)+
      `</div>`).join('')+'</div>';
  } else {
    fh+='<div class="linfoot-none">self-contained — nothing outside the task feeds it</div>';
  }
  fh+='<div class="linfoot-acts">';
  if(t.abs&&(typeof PRIVATE==='undefined'||!PRIVATE))
    fh+='<button class="trace-btn primary" id="linfoot-pub" type="button">↗ Publish task</button>';
  fh+='<button class="trace-btn" id="linfoot-copy" type="button">Copy as markdown</button></div>';
  foot.innerHTML=fh;
  const pubBtn=document.getElementById('linfoot-pub');
  if(pubBtn)pubBtn.onclick=()=>{if(window._publishBundle)window._publishBundle(t);};
  document.getElementById('linfoot-copy').onclick=()=>{
    const evs=taskTimelineEvents(t);
    const md=`# How "${tagName(t.sl)}" evolved\n\n`+evs.map(ev=>{
      const label=TL_EVENT_LABEL[ev.kind||'doc']||(ev.kind||'').toUpperCase();
      const name=(ev.path||'').split('/').pop()||'';
      return `- ${ev.at||''} · ${label} · ${name}`;
    }).join('\n')+'\n';
    copy(md,'timeline copied as markdown');
  };

  const actionsEl=document.getElementById('trace-actions');
  actionsEl.innerHTML='';
  if(t.abs){
    const a=document.createElement('a');
    a.className='trace-btn primary';
    a.href=fileHref(t.abs);
    a.dataset.openReader='';
    a.dataset.abs=t.abs;
    a.textContent='Open manifest';
    actionsEl.appendChild(a);
  }
  // Modest affordance: comment on this task (opens the floating composer, 1e/S7).
  const cbtn=document.createElement('button');
  cbtn.type='button';cbtn.className='trace-btn';
  cbtn.textContent='write a comment… ⌘↵';
  cbtn.title='comment on this task (c)';
  cbtn.onclick=()=>{if(window._openComposer)window._openComposer({task:t,target:'manifest.md'});};
  actionsEl.appendChild(cbtn);

  traceEl.classList.add('show');
  traceEl.scrollTop=0;
}
function closeTrace(){
  _openTraceT=null;
  traceEl.classList.remove('show');
}
document.getElementById('trace-back').addEventListener('click',closeTrace);
// list|graph toggle: `graph` overlays the S4b canvas for this task; `list`
// closes the canvas and returns to the spine. Two renderings of one task.
document.getElementById('trace-mode-list').addEventListener('click',()=>{
  setTraceMode('list');
  if(window._graphCurrent&&window._closeGraph)window._closeGraph();
});
document.getElementById('trace-mode-graph').addEventListener('click',()=>{
  if(_openTraceT&&window._openGraphFor)window._openGraphFor(_openTraceT);
});

// ── View toggle ───────────────────────────────────────────────────────────
(function(){
  const layout=document.querySelector('.hub-layout');
  const board=document.getElementById('board');
  const cal=document.getElementById('calendar');
  const workView=document.getElementById('work-view');
  const pills=[...document.querySelectorAll('.view-pill')];
  const hasWork=TASKS_DATA.length>0;
  const savedView=sessionStorage.getItem('docs_hub_view');
  // Configured default_view (hub.toml) wins over the heuristic, but never lands
  // on an empty work view; sessionStorage (last manual choice) still wins overall.
  const cfgView=(typeof DEFAULT_VIEW!=='undefined'&&DEFAULT_VIEW&&(DEFAULT_VIEW!=='work'||hasWork))?DEFAULT_VIEW:'';
  let view=savedView||cfgView||(hasWork?'work':'list');

  function setView(v){
    view=v;sessionStorage.setItem('docs_hub_view',v);
    pills.forEach(p=>p.classList.toggle('active',p.dataset.view===v));
    layout.classList.toggle('hidden',v!=='list');
    board.classList.toggle('show',v==='board');
    cal.classList.toggle('show',v==='calendar');
    workView.classList.toggle('show',v==='work');
    if(v==='board')renderBoard();
    if(v==='calendar')renderCalendar();
    if(v==='work')renderWorkView();
  }
  pills.forEach(p=>p.addEventListener('click',()=>setView(p.dataset.view)));
  setView(view);
  // expose for apply()
  window._setView=setView;
  window._currentView=()=>view;
})();

// Run apply after view toggle is wired
apply();

// Restore the overlay + scroll captured before the last softReload()/refresh,
// so a rebuild leaves you exactly where you were instead of back on the index.
// Deferred to a macrotask: the graph module assigns window._openGraphFor further
// down this file, so restore must run AFTER the whole module has executed.
setTimeout(function restoreViewState(){
  let s=null;
  try{s=JSON.parse(sessionStorage.getItem('hub_view_state')||'null');}catch(_){s=null;}
  if(!s)return;
  const ov=s.ov;
  if(ov){
    if(ov.k==='preview'){
      const row=[...document.querySelectorAll('.row')].find(r=>r.dataset.abs===ov.abs);
      if(row)openPreview(row);
    }else if(ov.k==='trace'){
      const t=(typeof TASKS_DATA!=='undefined')&&TASKS_DATA.find(x=>x.sl===ov.sl&&x.rp===ov.rp);
      if(t)openTrace(t);
    }else if(ov.k==='graph'){
      const t=(typeof TASKS_DATA!=='undefined')&&TASKS_DATA.find(x=>x.sl===ov.sl&&x.rp===ov.rp);
      if(t&&window._openGraphFor)window._openGraphFor(t);
    }
  }
  // Restore scroll after layout settles (two rAFs: post-render, post-paint).
  if(typeof s.y==='number'){
    requestAnimationFrame(()=>requestAnimationFrame(()=>window.scrollTo(0,s.y)));
  }
},0);

const REBUILD_CMD=`/usr/bin/python3 ${HUBPY}`;
const toast=document.getElementById('toast');
function flash(msg){toast.classList.remove('has-open');toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2400);}
// Persistent toast — stays visible until the page swaps (used during rebuild)
function flashSticky(msg){toast.textContent=msg;toast.classList.add('show');}
// S20 — a toast that carries a clickable "open ↗" link to a just-published URL,
// so BOTH a bundle and a single-file publish offer an immediate Open. Stays a
// bit longer than a plain flash so the link is actually clickable.
function flashOpen(msg,url){
  toast.innerHTML=esc(msg)+' <a class="toast-open" href="'+esc(url)+'" target="_blank" rel="noopener">open ↗</a>';
  toast.classList.add('show','has-open');
  clearTimeout(toast._openT);
  toast._openT=setTimeout(()=>{toast.classList.remove('show','has-open');toast.textContent='';},6000);
}
async function copy(text,msg){
  try{await navigator.clipboard.writeText(text);if(msg)flash(msg);}
  catch(e){window.prompt('Copy this command:',text);}
}

// ── Modal ─────────────────────────────────────────────────────────────────
const modal=document.getElementById('modal');
const modalInput=document.getElementById('modal-input');
const pickerCrumbs=document.getElementById('picker-crumbs');
const pickerList=document.getElementById('picker-list');
// Server-backed directory picker: the browser navigates the server's filesystem
// via GET /_list-dirs (a native folder picker can't hand the server a real path).
// _pickerPath is the currently-browsed dir — that's what SAVE posts to /_set-root.
let _pickerPath='';       // absolute path currently browsed (from server's normalized `path`)
let _pickerRows=[];       // [{kind:'up'|'dir', path, name}] in display order
let _pickerSel=-1;        // keyboard-selected row index into _pickerRows

function openModal(){
  modalInput.value='';
  modal.classList.add('show');
  navigatePicker('');     // empty → server defaults to the current scan root
  setTimeout(()=>{pickerList.focus();},0);
}
function closeModal(){modal.classList.remove('show');}

function navigatePicker(path){
  const url='/_list-dirs'+(path?('?path='+encodeURIComponent(path)):'');
  fetch(url)
    .then(r=>r.json())
    .then(data=>{
      if(data.error){
        pickerCrumbs.textContent='';
        pickerList.innerHTML='<div class="picker-error">can’t open: '+escPicker(data.error)+'</div>';
        return;
      }
      _pickerPath=data.path;
      renderPicker(data);
    })
    .catch(()=>{pickerList.innerHTML='<div class="picker-error">listing failed</div>';});
}

function escPicker(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}

function renderPicker(data){
  // Breadcrumb — each segment jumps to that ancestor; the last one is "here".
  const parts=String(data.path).split('/').filter(Boolean);
  const crumbs=[{label:'/',path:'/'}];
  let acc='';
  for(const part of parts){acc+='/'+part;crumbs.push({label:part,path:acc});}
  pickerCrumbs.innerHTML='';
  crumbs.forEach((c,i)=>{
    const last=i===crumbs.length-1;
    const span=document.createElement('span');
    span.className='crumb'+(last?' here':'');
    span.textContent=c.label;
    if(!last)span.addEventListener('click',()=>navigatePicker(c.path));
    pickerCrumbs.appendChild(span);
    if(!last){const sep=document.createElement('span');sep.className='sep';sep.textContent=parts.length&&i===0?'':' / ';pickerCrumbs.appendChild(sep);}
  });

  // Rows: optional ".." (up), then each subdirectory.
  _pickerRows=[];
  if(data.parent)_pickerRows.push({kind:'up',path:data.parent,name:'..'});
  (data.dirs||[]).forEach(d=>_pickerRows.push({kind:'dir',path:d.path,name:d.name}));
  _pickerSel=-1;

  pickerList.innerHTML='';
  if(!_pickerRows.length){
    pickerList.innerHTML='<div class="picker-empty">no subdirectories here</div>';
    return;
  }
  _pickerRows.forEach((row,idx)=>{
    const el=document.createElement('div');
    el.className='picker-row'+(row.kind==='up'?' up':'');
    el.dataset.idx=String(idx);
    const glyph=document.createElement('span');
    glyph.className='glyph';
    glyph.textContent=row.kind==='up'?'↑':'📁';
    const label=document.createElement('span');
    label.textContent=row.kind==='up'?'.. (up)':row.name;
    el.appendChild(glyph);el.appendChild(label);
    el.addEventListener('click',()=>navigatePicker(row.path));
    pickerList.appendChild(el);
  });
}

function pickerSelect(idx){
  const rows=pickerList.querySelectorAll('.picker-row');
  if(!rows.length)return;
  _pickerSel=Math.max(0,Math.min(idx,rows.length-1));
  rows.forEach((r,i)=>r.classList.toggle('active',i===_pickerSel));
  rows[_pickerSel].scrollIntoView({block:'nearest'});
}

function submitModal(){
  // A typed path (power-user fallback) wins; otherwise save the browsed dir.
  const typed=modalInput.value.trim();
  const p=typed||_pickerPath;
  if(!p){closeModal();return;}
  closeModal();
  flashSticky('saving & rebuilding…');
  fetch('/_set-root',{method:'POST',body:p})
    .then(r=>r.ok?Promise.resolve():r.text().then(t=>Promise.reject(t)))
    .then(()=>softReload())
    .catch(e=>flash('failed: '+(e||'unknown error')));
}
document.getElementById('setroot').addEventListener('click',e=>{e.preventDefault();openModal();});
document.getElementById('modal-cancel').addEventListener('click',closeModal);
document.getElementById('modal-ok').addEventListener('click',submitModal);
modal.addEventListener('click',e=>{if(e.target===modal)closeModal();});
// Type-a-path fallback: Enter navigates the picker there; Esc closes.
modalInput.addEventListener('keydown',e=>{
  if(e.key==='Enter'){e.preventDefault();const v=modalInput.value.trim();if(v){navigatePicker(v);modalInput.value='';pickerList.focus();}}
  else if(e.key==='Escape')closeModal();
});
// Keyboard nav within the list: ↑↓ move, Enter descends, Esc closes.
pickerList.addEventListener('keydown',e=>{
  if(e.key==='ArrowDown'){e.preventDefault();pickerSelect(_pickerSel+1);}
  else if(e.key==='ArrowUp'){e.preventDefault();pickerSelect(_pickerSel-1);}
  else if(e.key==='Enter'){e.preventDefault();const row=_pickerRows[_pickerSel];if(row)navigatePicker(row.path);}
  else if(e.key==='Escape')closeModal();
});
document.getElementById('rebuild').addEventListener('click',e=>{
  e.preventDefault();
  flashSticky('rebuilding…');
  fetch('/_rebuild')
    .then(r=>r.ok?Promise.resolve():Promise.reject())
    .then(()=>softReload())
    .catch(()=>flash('rebuild failed'));
});

// ── Settings panel (S15) ────────────────────────────────────────────────────
// Gear fixed bottom-left of the home page opens a themed panel (modeled on the
// set-root modal). Section 1 (workspace prefs) → hub.toml via POST /_settings;
// Section 2 (Cloudflare creds) → ~/.dak/config.json. The API token is fetched
// only as a SET/UNSET flag (never its value); leaving the masked field unchanged
// on save keeps the existing token server-side.
(function(){
  const gear=document.getElementById('settings-gear');
  const panel=document.getElementById('settings');
  if(!gear||!panel) return;
  const $ = (id)=>document.getElementById(id);
  const viewSel=$('settings-view');
  const portIn=$('settings-port');
  const excludeIn=$('settings-exclude');
  const uploadsIn=$('settings-uploads');
  const privateIn=$('settings-private');
  const rootPathEl=$('settings-root-path');
  const tokenIn=$('settings-dak-token');
  const accountIn=$('settings-dak-account');
  const subdomainIn=$('settings-dak-subdomain');
  const MASK='••••••';
  let _tokenSet=false;   // whether a token already exists server-side
  let _lastFocus=null;

  const viewDD=themeSelect(viewSel);

  function fill(data){
    const hub=(data&&data.hub)||{}, dak=(data&&data.dak)||{};
    viewSel.value=hub.default_view||'';if(viewDD)viewDD.refresh();
    portIn.value=(hub.port!=null?String(hub.port):'');
    excludeIn.value=(hub.exclude_dirs||[]).join(', ');
    uploadsIn.value=(hub.upload_exts||[]).join(' ');
    privateIn.checked=!!hub.private;
    rootPathEl.textContent=hub.scan_root||_currentRoot||'';
    accountIn.value=dak.account_id||'';
    subdomainIn.value=dak.subdomain||'';
    _tokenSet=!!dak.api_token_set;
    // Show the mask for an existing token; leaving it untouched keeps it.
    tokenIn.value=_tokenSet?MASK:'';
    tokenIn.placeholder=_tokenSet?'token set — leave to keep':'Cloudflare API token';
  }

  function open(){
    _lastFocus=document.activeElement;
    rootPathEl.textContent=_currentRoot||'';
    panel.classList.add('show');
    fetch('/_settings').then(r=>r.json()).then(fill).catch(()=>{});
    setTimeout(()=>{if(viewDD&&viewDD.el){const b=viewDD.el.querySelector('.pal-dd-btn');if(b)b.focus();}},0);
  }
  function close(){
    panel.classList.remove('show');
    if(_lastFocus&&_lastFocus.focus)try{_lastFocus.focus();}catch(_){}
  }

  function save(){
    // Only send the token when the user typed a real new value (not the mask).
    const dak={account_id:accountIn.value.trim(),subdomain:subdomainIn.value.trim()};
    const tv=tokenIn.value;
    if(tv&&tv!==MASK) dak.api_token=tv;
    const body={
      hub:{
        default_view:viewSel.value,
        port:portIn.value.trim(),
        exclude_dirs:excludeIn.value,
        upload_exts:uploadsIn.value,
        private:privateIn.checked,
      },
      dak:dak,
    };
    const btn=$('settings-save');if(btn)btn.disabled=true;
    fetch('/_settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})))
      .then(({ok,d})=>{
        if(btn)btn.disabled=false;
        if(!ok||!d.ok){flash('save failed: '+((d&&d.error)||'error'));return;}
        close();
        const notes=(d.notes||[]);
        flash(notes.length?('settings saved · '+notes.join(' ')):'settings saved');
      })
      .catch(()=>{if(btn)btn.disabled=false;flash('save failed');});
  }

  gear.addEventListener('click',e=>{e.preventDefault();open();});
  $('settings-cancel').addEventListener('click',close);
  $('settings-save').addEventListener('click',save);
  // Reuse the EXISTING dir picker for scan root — don't rebuild it.
  $('settings-root-change').addEventListener('click',()=>{close();openModal();});
  panel.addEventListener('click',e=>{if(e.target===panel)close();});
  // Focus trap + Esc (the panel is the topmost dialog when shown).
  panel.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();close();return;}
    if(e.key!=='Tab')return;
    const f=panel.querySelectorAll('button,select,input,textarea,[tabindex]:not([tabindex="-1"])');
    const list=[...f].filter(el=>!el.disabled&&el.offsetParent!==null);
    if(!list.length)return;
    const first=list[0],last=list[list.length-1];
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
  });
})();

// ── Command palette (roadmap 1a/1b/2c) ──────────────────────────────────────
// The ONE write surface. Client-only over data already on the page; the sole
// network call is POST /_new-task. Distinct from the #q filter (a lens over the
// current view) — the palette *leaves* the view.
(function(){
  const IS_MAC=/Mac|iPhone|iPad|iPod/.test((navigator.platform||'')+' '+(navigator.userAgent||''));
  const MOD=IS_MAC?'⌘':'Ctrl';
  const pal=document.getElementById('palette');
  const palInput=document.getElementById('pal-input');
  const palResults=document.getElementById('pal-results');
  const palScope=document.getElementById('pal-scope');
  const searchScreen=document.getElementById('pal-search-screen');
  const ntScreen=document.getElementById('pal-newtask-screen');
  const help=document.getElementById('pal-help');
  const modLabel=document.getElementById('pal-help-mod');
  if(modLabel) modLabel.textContent=MOD+'K';

  // ── recents (client-only, cross-reload) ──
  let recents=[];
  try{recents=JSON.parse(localStorage.getItem('hub_pal_recent')||'[]');}catch(_){recents=[];}
  function pushRecent(id){
    recents=[id,...recents.filter(x=>x!==id)].slice(0,8);
    try{localStorage.setItem('hub_pal_recent',JSON.stringify(recents));}catch(_){}
  }
  const recRank=id=>{const i=recents.indexOf(id);return i<0?99:i;};

  // ── fuzzy scorer: subsequence match, boundary + streak bonuses ──
  function fuzzy(q,s){
    q=q.toLowerCase();s=(s||'').toLowerCase();
    if(!q) return 0;
    let qi=0,score=0,last=-2;
    for(let i=0;i<s.length&&qi<q.length;i++){
      if(s[i]===q[qi]){
        score+= (i===last+1)?3:1;
        if(i===0||/[\s/\-_.]/.test(s[i-1])) score+=2;
        last=i;qi++;
      }
    }
    return qi===q.length?score:-1;
  }

  function slugifyJS(s){
    return String(s).toLowerCase().replace(/<[^>]+>/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
  }
  function repoList(){
    const s=new Set();
    document.querySelectorAll('.rchip').forEach(el=>s.add(el.textContent.trim()));
    TASKS_DATA.forEach(t=>{if(t.rp)s.add(t.rp);});
    if(!s.size)s.add('(root)');
    return [...s];
  }

  const SEC_ORDER=['action','task','file','repo'];
  const SEC_LABEL={action:'Make',task:'Tasks',file:'Files',repo:'Repos'};
  const SEC_CLS={action:'make',task:'tasks',file:'files',repo:'repos'};
  const SCOPE_TYPE={'>':'action','@':'task','/':'file','#':'repo'};
  const SCOPE_LABEL={'>':'ACTIONS','@':'TASKS','/':'FILES','#':'REPOS'};

  // ── static action rows (Make section — WRITE, oxblood) ──
  function actions(){
    const a=[
      {type:'action',write:true,id:'act:new-task',key:'N',ic:'✎',label:'New task',
       cli:'hub new task <slug>',prim:()=>openNewTask('')},
      {type:'action',write:true,id:'act:new-draw',key:'D',ic:'✎',label:'New draw',
       cli:'hub draw',prim:()=>{closePalette();window.open('/draw','_blank','noopener');}},
      {type:'action',write:true,id:'act:new-note',key:'C',ic:'✎',label:'New comment',
       cli:'hub note <path>',prim:()=>{closePalette();if(window._openComposer)window._openComposer();}},
      {type:'action',id:'act:graph',key:'G',ic:'⌗',label:'Timeline · graph order',
       cli:'hub timeline <slug> --graph',prim:()=>{closePalette();if(window._openGraphFor)window._openGraphFor(null);}},
      // Task-aware: a task in context (open trace/graph/preview, or named in the
      // query) pre-scopes the add-data screen; otherwise its themed task
      // dropdown IS the picker. (S8)
      {type:'action',write:true,id:'act:add-data',ic:'✎',label:'Add data',
       cli:'hub data <path>',prim:()=>openAddData(null,paletteContextTask())},
    ];
    // Publishing leaves the machine. When the workspace is private, the row is
    // dropped entirely (baked from hub.toml [hub] private → the PRIVATE global).
    if(typeof PRIVATE==='undefined' || !PRIVATE){
      // Task-aware (S8): with a task in context, publish that task's dak bundle
      // directly; otherwise fall back to the file-publish sheet (its own asset
      // picker + redaction scan).
      a.push({type:'action',write:true,id:'act:publish',ic:'✎',label:'Publish',
       cli:'hub publish --task <slug>',prim:()=>{const t=paletteContextTask();if(t)publishBundle(t);else openPublish(null);}});
      // 1g — freeze the current/selected task's subtree to a self-contained
      // bundle (its trace baked static) and hand off to dak. ⇧B in the comp.
      a.push({type:'action',write:true,id:'act:bundle',key:'B',ic:'⌗',label:'Trace bundle',
       cli:'hub publish --task <slug>',prim:()=>publishBundle(null)});
    }
    return a;
  }
  function taskItems(){
    return TASKS_DATA.map(t=>({
      type:'task',id:'task:'+t.rp+':'+t.sl,label:tagName(t.sl),
      sub:t.rp+' · tasks/'+t.sl,cli:'hub trace tasks/'+t.sl,abs:t.abs,
      _match:t.sl+' '+t.rp,copyText:'tasks/'+t.sl,
      // S8: ↵ on a task opens its verbs (Add data · New comment · Publish ·
      // Trace · Timeline·graph); ⇧↵ still opens the manifest in a floating window.
      prim:()=>openTaskActions(t),
      shift:()=>{closePalette();if(t.abs)openFloat(t.abs,tagName(t.sl),fileHref(t.abs));},
    }));
  }
  function fileItems(){
    const out=[];
    rows.forEach(r=>{
      const abs=r.dataset.abs;if(!abs)return;
      const path=r.querySelector('.path')?r.querySelector('.path').textContent:abs;
      const repo=(r.dataset.search||'').split(' ')[0];
      out.push({type:'file',id:'file:'+abs,label:path,sub:repo,abs:abs,href:r.href,
        _match:r.dataset.search||path,copyText:abs,
        prim:()=>{closePalette();window._openReader?window._openReader(abs,{href:r.href}):window.open(r.href,'_blank','noopener');},
        shift:()=>{closePalette();openFloat(abs,path,r.href);}});
    });
    return out;
  }
  function repoItems(){
    return repoList().map(rp=>({type:'repo',id:'repo:'+rp,label:rp,sub:'filter to this repo',
      copyText:rp,
      prim:()=>{closePalette();toggleRepo(rp.toLowerCase());}}));
  }

  let scope='';           // one of > @ / #  or ''
  let palItems=[];        // flat, currently-rendered items
  let palSel=0;
  // S8 — task-scoped sub-view: showing ONE task's verbs. Transient palette state
  // (never persisted to hub_view_state).
  let taskActionsTask=null;

  // The task a global write action should act on: an open trace / graph / preview
  // for a task, else a task named exactly in the query. Null → ask the user.
  function paletteContextTask(){
    if(typeof TASKS_DATA==='undefined'||!TASKS_DATA.length) return null;
    if(_openTraceT) return _openTraceT;
    if(window._graphCurrent){const g=window._graphCurrent;const t=TASKS_DATA.find(x=>x.sl===g.sl&&x.rp===g.rp);if(t) return t;}
    if(_openPreviewAbs){const c=_ctxForAbs(_openPreviewAbs);if(c&&c.task) return c.task;}
    const term=currentTerm().trim().toLowerCase();
    if(term){
      const m=TASKS_DATA.filter(t=>t.sl.toLowerCase()===term||tagName(t.sl).toLowerCase()===term);
      if(m.length===1) return m[0];
    }
    return null;
  }

  // The verbs for ONE task — each acts on that task, each carries its 2c CLI
  // hint (⌥↵ copies it). Reuses the existing screens/flows: add-data, the S7
  // floating composer, the bundle publish, trace, and the graph-order timeline.
  function taskActionItems(t){
    const slug=t.sl;
    const a=[
      {type:'action',write:true,id:'ta:data:'+t.rp+':'+slug,ic:'✎',label:'Add data',
       sub:t.rp+' · tasks/'+slug,cli:'cp <files> tasks/'+slug+'/data/',
       prim:()=>openAddData(null,t)},
      {type:'action',write:true,id:'ta:note:'+t.rp+':'+slug,ic:'✎',label:'New comment',
       sub:'tasks/'+slug+'/comments',cli:'hub note tasks/'+slug+'/manifest.md',
       prim:()=>{closePalette();if(window._openComposer)window._openComposer({task:t,target:'manifest.md'});}},
    ];
    if(typeof PRIVATE==='undefined'||!PRIVATE){
      a.push({type:'action',write:true,id:'ta:pub:'+t.rp+':'+slug,ic:'⌗',label:'Publish (dak bundle)',
       sub:'self-contained trace bundle',cli:'hub publish --task '+slug,
       prim:()=>publishBundle(t)});
    }
    a.push(
      {type:'action',id:'ta:trace:'+t.rp+':'+slug,ic:'◇',label:'Trace',
       sub:'open the task trace',cli:'hub trace tasks/'+slug,
       prim:()=>{closePalette();openTrace(t);}},
      {type:'action',id:'ta:graph:'+t.rp+':'+slug,ic:'⌗',label:'Timeline · graph',
       sub:'how this evolved',cli:'hub timeline '+slug+' --graph',
       prim:()=>{closePalette();if(window._openGraphFor)window._openGraphFor(t);}});
    return a;
  }
  function openTaskActions(t){taskActionsTask=t;scope='';palInput.value='';render();setTimeout(()=>palInput.focus(),0);}

  function currentTerm(){
    let v=palInput.value;
    if(scope) return v;          // scope already stripped from value
    if(v && SCOPE_TYPE[v[0]]) return v.slice(1).trimStart();
    return v;
  }

  // A flat, single-section result list — used by the S8 task sub-views (task
  // actions / task picker). Honors the search term via the same fuzzy scorer.
  function renderFlat(items,label,cls){
    const term=palInput.value.trim();
    const scored=items.filter(it=>{const sc=fuzzy(term,it.label+' '+(it._match||it.sub||''));it._score=sc;return !(term&&sc<0);});
    if(term)scored.sort((a,b)=>b._score-a._score);
    let html='<div class="pal-sec '+cls+'">'+esc(label)+'</div>';
    const flat=[];
    scored.forEach(it=>{html+=rowHTML(it,flat.length);flat.push(it);});
    if(!flat.length)html+='<div class="pal-empty">no matches</div>';
    palResults.innerHTML=html;palItems=flat;palSel=flat.length?0:-1;paintSel();
  }

  function render(){
    // Task sub-views short-circuit the normal pool + scope logic.
    if(taskActionsTask){
      palScope.classList.add('show');palScope.textContent='TASK · '+tagName(taskActionsTask.sl);
      renderFlat(taskActionItems(taskActionsTask),tagName(taskActionsTask.sl),'tasks');return;
    }
    let raw=palInput.value;
    // Detect a scope prefix typed inline (only meaningful as first char)
    if(!scope && raw && SCOPE_TYPE[raw[0]]){
      scope=raw[0];
      palInput.value=raw.slice(1).trimStart();
    }
    palScope.classList.toggle('show',!!scope);
    palScope.textContent=scope?SCOPE_LABEL[scope]:'';
    const term=palInput.value.trim();

    let pool=[...actions(),...taskItems(),...fileItems(),...repoItems()];
    if(scope) pool=pool.filter(it=>it.type===SCOPE_TYPE[scope]);

    const bySec={action:[],task:[],file:[],repo:[]};
    pool.forEach(it=>{
      const hay=it.label+' '+(it._match||it.sub||'');
      const sc=fuzzy(term,hay);
      if(term && sc<0) return;
      it._score=sc;bySec[it.type].push(it);
    });
    Object.keys(bySec).forEach(k=>{
      bySec[k].sort((a,b)=> term ? (b._score-a._score)||(recRank(a.id)-recRank(b.id))
                                 : (recRank(a.id)-recRank(b.id)));
    });

    const flat=[];let html='';
    const total=SEC_ORDER.reduce((n,s)=>n+bySec[s].length,0);
    if(term && total===0){
      // Empty state → a dead-end becomes a producer.
      const it={type:'create',id:'create',write:true,ic:'✎',label:'Create task "'+term+'"',
        cli:'hub new task '+slugifyJS(term),prim:()=>openNewTask(term)};
      it.shift=it.prim;
      flat.push(it);
      html+='<div class="pal-sec make">Make</div>'+rowHTML(it,0);
    } else {
      SEC_ORDER.forEach(s=>{
        if(!bySec[s].length) return;
        html+='<div class="pal-sec '+SEC_CLS[s]+'">'+SEC_LABEL[s]+'</div>';
        bySec[s].forEach(it=>{html+=rowHTML(it,flat.length);flat.push(it);});
      });
      if(!flat.length) html='<div class="pal-empty">no matches</div>';
    }
    palResults.innerHTML=html;
    palItems=flat;
    palSel=flat.length?0:-1;
    paintSel();
  }

  function rowHTML(it,idx){
    const cls='pal-row'+(it.write?' write':'');
    const key=it.key?'<span class="pal-key">'+it.key+'</span>':'<span class="pal-key">·</span>';
    const ic=it.ic?'<span class="pal-ic">'+it.ic+'</span>':'<span class="pal-ic">'+(it.type==='task'?'◇':it.type==='repo'?'▦':'▪')+'</span>';
    const sub=it.sub?'<span class="pal-sub">'+esc(it.sub)+'</span>':'';
    const right=it.cli?'<span class="pal-cli">'+esc(it.cli)+'</span>'
              :it.type==='file'?'<span class="pal-badge">file</span>':'';
    return '<div class="'+cls+'" data-i="'+idx+'">'+key+ic+
      '<span class="pal-main"><span class="pal-label">'+esc(it.label)+'</span>'+sub+'</span>'+right+'</div>';
  }

  function paintSel(){
    [...palResults.querySelectorAll('.pal-row')].forEach(el=>{
      el.classList.toggle('sel',+el.dataset.i===palSel);
    });
    const sel=palResults.querySelector('.pal-row.sel');
    if(sel) sel.scrollIntoView({block:'nearest'});
  }
  function move(d){
    if(!palItems.length) return;
    palSel=(palSel+d+palItems.length)%palItems.length;
    paintSel();
  }
  function activate(it,mode){
    if(!it) return;
    if(mode==='alt'){
      if(it.type==='action'||it.type==='create'||it.type==='task') copy(it.cli||it.copyText,'copied: '+(it.cli||it.copyText));
      else copy(it.copyText,'copied path');
      return;
    }
    pushRecent(it.id);
    if(mode==='shift'&&it.shift) it.shift();
    else it.prim();
  }

  // ── palette open/close ──
  function openPalette(scopeChar){
    help.classList.remove('show');
    ntScreen.classList.add('hidden');
    if(adScreen) adScreen.classList.add('hidden');
    searchScreen.classList.remove('hidden');
    scope=scopeChar&&SCOPE_TYPE[scopeChar]?scopeChar:'';
    taskActionsTask=null;
    pal.classList.add('show');
    palInput.value='';
    render();
    setTimeout(()=>{palInput.focus();},0);
  }
  function closePalette(){pal.classList.remove('show');scope='';taskActionsTask=null;}
  window._openPalette=openPalette;

  palInput.addEventListener('input',render);
  palInput.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'||(e.ctrlKey&&e.key==='n')){e.preventDefault();move(1);}
    else if(e.key==='ArrowUp'||(e.ctrlKey&&e.key==='p')){e.preventDefault();move(-1);}
    else if(e.key==='Enter'){e.preventDefault();
      activate(palItems[palSel], e.altKey?'alt':e.shiftKey?'shift':'prim');}
    else if(e.key==='Escape'){e.preventDefault();
      if(taskActionsTask){taskActionsTask=null;render();}
      else if(scope){scope='';palScope.classList.remove('show');render();}
      else closePalette();}
    else if(e.key==='Backspace'&&palInput.value===''){
      if(taskActionsTask){taskActionsTask=null;render();}
      else if(scope){scope='';render();}}
  });
  palResults.addEventListener('click',e=>{
    const row=e.target.closest('.pal-row');if(!row)return;
    activate(palItems[+row.dataset.i], e.altKey?'alt':e.shiftKey?'shift':'prim');
  });
  pal.addEventListener('click',e=>{if(e.target===pal)closePalette();});
  document.getElementById('pal-help-open').addEventListener('click',()=>help.classList.add('show'));
  document.getElementById('pal-help-close').addEventListener('click',()=>help.classList.remove('show'));
  help.addEventListener('click',e=>{if(e.target===help)help.classList.remove('show');});

  // ── new-task screen (1b) ──
  const repoSel=document.getElementById('pal-nt-repo');
  const repoDD=themeSelect(repoSel);
  const titleInput=document.getElementById('pal-nt-title-input');
  const slugField=document.getElementById('pal-nt-slug');
  const statusWrap=document.getElementById('pal-nt-status');
  const planArea=document.getElementById('pal-nt-plan');
  const preEl=document.getElementById('pal-nt-pre');
  const pathEl=document.getElementById('pal-nt-path');
  const createBtn=document.getElementById('pal-nt-create');
  let ntStatus='ongoing',ntSlug='';

  function taskTaken(repo,slug){return TASKS_DATA.some(t=>t.sl===slug&&t.rp===repo);}
  function freeSlug(repo,slug){
    if(!taskTaken(repo,slug)) return {slug:slug,taken:false};
    let n=2;while(taskTaken(repo,slug+'-'+n))n++;
    return {slug:slug+'-'+n,taken:true};
  }
  function buildManifest(title,status,plan){
    // Mirrors core.tasks.render_manifest (S22): NO YAML frontmatter — just the
    // H1 (+ Plan). Status is persisted to the DB/sidecar, not the file, so the
    // preview shows exactly what gets written. (status param kept for the caller.)
    const lines=['# '+title];
    if(plan.length){lines.push('','## Plan');plan.forEach(p=>lines.push('- [ ] '+p));}
    return lines.join('\n')+'\n';
  }
  function ntRender(){
    const title=titleInput.value.trim();
    const repo=repoSel.value||'(root)';
    const base=slugifyJS(title);
    const fs=base?freeSlug(repo,base):{slug:'',taken:false};
    ntSlug=fs.slug;
    const plan=planArea.value.split('\n').map(s=>s.trim()).filter(Boolean);
    preEl.textContent=buildManifest(title||'…',ntStatus,plan);
    const loc=(repo&&repo!=='(root)'?repo:'tasks').replace(/^tasks$/,'');
    const prefix=(repo&&repo!=='(root)')?repo+'/':'';
    pathEl.textContent=prefix+'tasks/'+(ntSlug||'<slug>')+'/manifest.md';
    if(!base){slugField.innerHTML='';createBtn.disabled=true;return;}
    createBtn.disabled=false;
    slugField.innerHTML= fs.taken
      ? '→ <span class="taken">'+esc(base)+' already exists</span> · using <span class="ok">'+esc(ntSlug)+'</span>'
      : '→ <span class="ok">'+esc(ntSlug)+' · available</span>';
  }
  function openNewTask(prefillTitle){
    help.classList.remove('show');
    if(!pal.classList.contains('show')) pal.classList.add('show');
    searchScreen.classList.add('hidden');ntScreen.classList.remove('hidden');
    const _ad=document.getElementById('pal-adddata-screen');if(_ad)_ad.classList.add('hidden');
    repoSel.innerHTML=repoList().map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');
    repoDD.refresh();
    titleInput.value=prefillTitle||'';
    planArea.value='';
    ntStatus='ongoing';
    [...statusWrap.children].forEach(b=>b.classList.toggle('active',b.dataset.status==='ongoing'));
    ntRender();
    setTimeout(()=>{titleInput.focus();titleInput.select();},0);
  }
  function backToSearch(){ntScreen.classList.add('hidden');searchScreen.classList.remove('hidden');openPalette('');}

  titleInput.addEventListener('input',ntRender);
  planArea.addEventListener('input',ntRender);
  repoSel.addEventListener('change',ntRender);
  statusWrap.addEventListener('click',e=>{
    const b=e.target.closest('button');if(!b)return;
    ntStatus=b.dataset.status;
    [...statusWrap.children].forEach(x=>x.classList.toggle('active',x===b));
    ntRender();
  });
  document.getElementById('pal-nt-back').addEventListener('click',backToSearch);
  document.getElementById('pal-nt-cancel').addEventListener('click',closePalette);
  titleInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'){e.preventDefault();ntCreate();}
    else if(e.key==='Escape'){e.preventDefault();backToSearch();}
  });
  function ntCreate(){
    const title=titleInput.value.trim();
    if(!title){flash('title required');return;}
    const repo=repoSel.value||'(root)';
    const plan=planArea.value.split('\n').map(s=>s.trim()).filter(Boolean);
    createBtn.disabled=true;
    fetch('/_new-task',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({repo:repo,title:title,slug:ntSlug,status:ntStatus,plan:plan})})
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
      .then(res=>{
        if(res.ok){flashSticky('creating task…');softReload();return;}
        createBtn.disabled=false;
        const d=res.d||{};
        if(d.error==='exists'){flash('already exists — try "'+(d.suggestion||'')+'"');ntRender();}
        else flash('new task failed: '+(d.detail||d.error||'unknown'));
      }).catch(()=>{createBtn.disabled=false;flash('new task failed');});
  }
  createBtn.addEventListener('click',ntCreate);

  // ── add-data screen (1d) ──────────────────────────────────────────────────
  // Drop files anywhere on the index (or pick "Add data") → this screen. Files
  // are staged with a client-side pre-check (✓/✕); the sole network call is
  // POST /_upload, where the server re-enforces every guard.
  const adScreen=document.getElementById('pal-adddata-screen');
  const adTaskSel=document.getElementById('pal-ad-task');
  const adTaskDD=themeSelect(adTaskSel);
  const adDest=document.getElementById('pal-ad-dest');
  const adDrop=document.getElementById('pal-ad-drop');
  const adFileInput=document.getElementById('pal-ad-file');
  const adList=document.getElementById('pal-ad-list');
  const adAddBtn=document.getElementById('pal-ad-add');
  const UPLOAD_EXTS=new Set((typeof UPLOAD_EXTS_DATA!=='undefined'&&UPLOAD_EXTS_DATA.length)
    ? UPLOAD_EXTS_DATA : ['.pdf','.xlsx','.xls','.csv','.tsv','.json','.txt','.md']);
  const UPLOAD_MAX=64*1024*1024;
  let adStaged=[];  // {file,name,size,ext,ok,reason}

  function fmtSize(n){
    if(n<1024) return n+' B';
    if(n<1024*1024) return (n/1024).toFixed(1)+' KB';
    return (n/1024/1024).toFixed(1)+' MB';
  }
  function fileExt(name){const i=name.lastIndexOf('.');return i>=0?name.slice(i).toLowerCase():'';}
  function validateStaged(s){
    if(!UPLOAD_EXTS.has(s.ext)){s.ok=false;s.reason=(s.ext||'no extension')+' not allowed';return;}
    if(s.size>UPLOAD_MAX){s.ok=false;s.reason='over the 64 MB guard';return;}
    s.ok=true;s.reason='';
  }
  function stageFiles(fileList){
    [...fileList].forEach(f=>{
      const s={file:f,name:f.name,size:f.size,ext:fileExt(f.name),ok:true,reason:''};
      validateStaged(s);adStaged.push(s);
    });
    adRender();
  }
  function adRender(){
    const t=TASKS_DATA[+adTaskSel.value];
    adDest.textContent = t ? ((t.rp&&t.rp!=='(root)'?t.rp+'/':'')+'tasks/'+t.sl+'/data/') : '';
    adList.innerHTML = adStaged.length
      ? adStaged.map((s,i)=>{
          const meta = s.ok ? esc((s.ext||'file')+' · '+fmtSize(s.size)) : esc(s.reason);
          return '<div class="pal-ad-item '+(s.ok?'ok':'bad')+'">'+
            '<span class="pal-ad-mark">'+(s.ok?'✓':'✕')+'</span>'+
            '<span class="pal-ad-name">'+esc(s.name)+'</span>'+
            '<span class="pal-ad-meta">'+meta+'</span>'+
            '<button class="pal-ad-rm" type="button" data-rm="'+i+'" title="remove">✕</button></div>';
        }).join('')
      : '<div class="pal-ad-empty">no files staged</div>';
    const accepted=adStaged.filter(s=>s.ok).length;
    adAddBtn.disabled = !(accepted>0 && t);
    adAddBtn.textContent = accepted ? ('Add '+accepted+' file'+(accepted===1?'':'s')) : 'Add files';
  }
  function openAddData(files,task){
    help.classList.remove('show');
    if(!pal.classList.contains('show')) pal.classList.add('show');
    searchScreen.classList.add('hidden');ntScreen.classList.add('hidden');
    adScreen.classList.remove('hidden');
    adStaged=[];
    adTaskSel.innerHTML = TASKS_DATA.length
      ? TASKS_DATA.map((t,i)=>'<option value="'+i+'">'+esc(t.rp+' · tasks/'+t.sl)+'</option>').join('')
      : '<option value="">no tasks yet — create one first</option>';
    // Pre-scope to a task when the palette handed one over (task-scoped action or
    // a task in context); otherwise the themed dropdown IS the task picker.
    if(task){const i=TASKS_DATA.findIndex(x=>x.sl===task.sl&&x.rp===task.rp);if(i>=0)adTaskSel.value=String(i);}
    adTaskDD.refresh();
    if(files&&files.length) stageFiles(files); else adRender();
    setTimeout(()=>{adDrop.focus();},0);
  }
  window._openAddData=openAddData;
  function adBack(){adScreen.classList.add('hidden');searchScreen.classList.remove('hidden');openPalette('');}

  function adUpload(){
    const t=TASKS_DATA[+adTaskSel.value];
    if(!t){flash('pick a task');return;}
    const good=adStaged.filter(s=>s.ok);
    if(!good.length){flash('no valid files to add');return;}
    adAddBtn.disabled=true;
    Promise.all(good.map(s=>new Promise((res,rej)=>{
      const rd=new FileReader();
      rd.onload=()=>{const r=String(rd.result);const c=r.indexOf(',');
        res({name:s.name,dataBase64:c>=0?r.slice(c+1):r});};
      rd.onerror=()=>rej(rd.error);
      rd.readAsDataURL(s.file);
    }))).then(payload=>fetch('/_upload',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({repo:t.rp,slug:t.sl,files:payload})}))
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
      .then(res=>{
        const d=res.d||{};
        if(res.ok&&d.written){flashSticky('adding '+d.written+' file'+(d.written===1?'':'s')+'…');softReload();return;}
        adAddBtn.disabled=false;
        const rej=(d.results||[]).filter(x=>!x.ok);
        flash(rej.length?('rejected: '+rej.map(x=>x.reason).join('; ')):('upload failed'+(d.error?': '+d.error:'')));
        adRender();
      }).catch(()=>{adAddBtn.disabled=false;flash('upload failed');});
  }

  adTaskSel.addEventListener('change',adRender);
  adFileInput.addEventListener('change',()=>{if(adFileInput.files&&adFileInput.files.length){stageFiles(adFileInput.files);adFileInput.value='';}});
  adDrop.addEventListener('click',()=>adFileInput.click());
  adDrop.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();adFileInput.click();}});
  adDrop.addEventListener('dragenter',()=>adDrop.classList.add('over'));
  adDrop.addEventListener('dragleave',()=>adDrop.classList.remove('over'));
  adDrop.addEventListener('drop',()=>adDrop.classList.remove('over'));
  adList.addEventListener('click',e=>{
    const b=e.target.closest('.pal-ad-rm');if(!b)return;
    adStaged.splice(+b.dataset.rm,1);adRender();
  });
  document.getElementById('pal-ad-back').addEventListener('click',adBack);
  document.getElementById('pal-ad-cancel').addEventListener('click',closePalette);
  adAddBtn.addEventListener('click',adUpload);

  // ── comments — the floating composer (S7) replaces the old palette note
  // screen. The palette "New comment" row and the `c` hotkey both call
  // window._openComposer (defined at module scope); there is no in-palette note
  // screen anymore. See the "Floating comment composer" block above.

  // ── publish confirm sheet (1f / S11) ───────────────────────────────────────
  // Publishing is deliberately high-friction: scan → review/redact → confirm.
  // It NEVER fires on ↵. The scan is computed server-side (POST /_publish-scan)
  // so the UI and the `hub publish` CLI share ONE scanner (core/publish.py). The
  // redact toggles below apply only to the published COPY — the source file is
  // never modified. The Publish button is now ONE CLICK: POST /_publish, which
  // hands off to the bundled dak SUBPROCESS (Hub itself opens no socket — the
  // subprocess is the network edge), then shows the resulting URL inline. No
  // copy-a-command / run-it-yourself step.
  const pubScreen=document.getElementById('pal-publish-screen');
  const pubFileSel=document.getElementById('pal-pub-file');
  const pubFileDD=themeSelect(pubFileSel);
  const pubTitle=document.getElementById('pal-pub-title');
  const pubScanEl=document.getElementById('pal-pub-scan');
  const pubListEl=document.getElementById('pal-pub-list');
  const pubGoBtn=document.getElementById('pal-pub-go');
  let pubFindings=[];      // last scan result
  let pubKeep=[];          // per-finding redact toggle (true = redact this one)

  function pubFileOptions(){
    const seen=new Set(),opts=[];
    rows.forEach(r=>{
      const abs=r.dataset.abs;if(!abs||seen.has(abs))return;seen.add(abs);
      const path=r.querySelector('.path')?r.querySelector('.path').textContent:abs;
      opts.push({abs:abs,label:path});
    });
    return opts;
  }
  function pubRenderFindings(){
    if(!pubFindings.length){
      pubScanEl.textContent='✓ scan clean — nothing a public reader shouldn’t see';
      pubScanEl.className='pal-pub-scan ok';
      pubListEl.innerHTML='';
    }else{
      const n=pubFindings.length;
      pubScanEl.textContent='⚠ '+n+' finding'+(n===1?'':'s')+' — review before this leaves your machine';
      pubScanEl.className='pal-pub-scan warn';
      pubListEl.innerHTML=pubFindings.map((f,i)=>
        '<label class="pal-pub-item"><input type="checkbox" data-i="'+i+'"'+(pubKeep[i]?' checked':'')+'>'+
        '<span class="pal-pub-kind">'+esc(f.kind)+'</span>'+
        '<span class="pal-pub-loc">L'+f.line+'</span>'+
        '<span class="pal-pub-text">'+esc(f.text)+'</span>'+
        '<span class="pal-pub-tog">redact</span></label>'
      ).join('');
    }
    pubGoBtn.disabled=!pubFileSel.value;
  }
  function pubScan(){
    const abs=pubFileSel.value;
    const resEl=document.getElementById('pal-pub-result');
    if(resEl){resEl.classList.add('hidden');resEl.innerHTML='';}
    pubFindings=[];pubKeep=[];
    if(!abs){pubScanEl.textContent='pick an asset';pubScanEl.className='pal-pub-scan';pubListEl.innerHTML='';pubGoBtn.disabled=true;return;}
    pubScanEl.textContent='scanning…';pubScanEl.className='pal-pub-scan';
    fetch('/_publish-scan',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:abs})})
      .then(r=>r.json()).then(d=>{
        pubFindings=(d&&d.findings)||[];
        pubKeep=pubFindings.map(()=>true);  // default: redact everything
        pubRenderFindings();
      }).catch(()=>{pubScanEl.textContent='scan failed';pubScanEl.className='pal-pub-scan warn';});
  }
  function openPublish(prefill){
    if(typeof PRIVATE!=='undefined'&&PRIVATE){flash('this workspace is private');return;}
    help.classList.remove('show');
    if(!pal.classList.contains('show')) pal.classList.add('show');
    searchScreen.classList.add('hidden');ntScreen.classList.add('hidden');
    if(adScreen)adScreen.classList.add('hidden');
    pubScreen.classList.remove('hidden');
    const opts=pubFileOptions();
    pubFileSel.innerHTML=opts.length
      ? opts.map(o=>'<option value="'+esc(o.abs)+'">'+esc(o.label)+'</option>').join('')
      : '<option value="">no files to publish</option>';
    const want=prefill&&prefill.abs;
    if(want&&opts.some(o=>o.abs===want))pubFileSel.value=want;
    pubFileDD.refresh();
    pubTitle.value='';
    pubScan();
    setTimeout(()=>{pubFileSel.focus();},0);
  }
  window._openPublish=openPublish;
  function pubBack(){pubScreen.classList.add('hidden');searchScreen.classList.remove('hidden');openPalette('');}

  // S11 — render the published URL inline in the sheet: a clickable mono link
  // plus a small "copy URL" affordance. This replaces the old "copy this dak
  // command / run it yourself" step — publishing is now one click.
  function pubShowResult(url,dryRun){
    const el=document.getElementById('pal-pub-result');if(!el)return;
    el.classList.remove('hidden');
    // S14 / #3 — never present a dry-run URL as a live "published" link. A dry
    // run staged a URL but uploaded nothing, so it is NOT live.
    if(dryRun){
      el.innerHTML='<span class="pal-pub-live dry">dry-run — not uploaded (URL not live)</span>'+
        '<span class="pal-pub-url dry">preview: '+esc(url)+'</span>';
      return;
    }
    el.innerHTML='<span class="pal-pub-live">✓ published</span>'+
      '<a class="pal-pub-url" href="'+esc(url)+'" target="_blank" rel="noopener">'+esc(url)+'</a>'+
      '<a class="pal-pub-open" href="'+esc(url)+'" target="_blank" rel="noopener" title="open the live URL">open ↗</a>'+
      '<button class="pal-pub-copy" type="button" title="copy URL">copy</button>';
    const cp=el.querySelector('.pal-pub-copy');
    if(cp)cp.onclick=()=>copy(url,'URL copied');
  }
  // S20 — reflect a just-published file's marker everywhere WITHOUT a full
  // reload: add the asset entry to the in-memory PUBLISHED_DATA (mutating the
  // baked object; a later reload re-bakes it from published.json), then
  // re-decorate its row so the PUBLISHED marker appears without a full reload.
  function _markFilePublished(abs,url,mode){
    if(typeof PUBLISHED_DATA==='object'&&PUBLISHED_DATA)
      PUBLISHED_DATA['asset\t'+abs]={url:url,at:'',mode:mode||'snapshot'};
    decorateFileRowByAbs(abs);
  }
  function pubPublish(){
    const abs=pubFileSel.value;
    if(!abs){flash('pick an asset');return;}
    // Always send the reviewed redact set (even empty) — that opts past the
    // findings gate. Default is redact-everything (see pubScan).
    const redact_indices=pubKeep.map((k,i)=>k?i:-1).filter(i=>i>=0);
    pubGoBtn.disabled=true;pubGoBtn.textContent='publishing…';
    fetch('/_publish',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({path:abs,redact_indices:redact_indices,review:true,title:pubTitle.value.trim()})})
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
      .then(res=>{
        pubGoBtn.disabled=false;pubGoBtn.textContent='Publish';
        const d=res.d||{};
        if(res.ok&&d.url){
          pubShowResult(d.url,d.dryRun);
          // S14 — a dry-run uploaded nothing, so it earns no persistent marker.
          if(!d.dryRun)_markFilePublished(abs,d.url,d.mode);
          flash(d.dryRun?('dry-run — not uploaded · '+d.url):('published · '+d.url));
          return;
        }
        const detail=d.detail?(': '+String(d.detail).split('\n').slice(-1)[0]):'';
        flash(d.error==='private'?'this workspace is private':
              d.error==='dak_unavailable'?'dak not set up — run its one-time setup':
              ('publish failed'+detail));
      }).catch(()=>{pubGoBtn.disabled=false;pubGoBtn.textContent='Publish';flash('publish failed');});
  }

  // 1g / S11 — Trace bundle, ONE CLICK. Resolve the current/selected task, POST
  // /_publish-bundle (server renders the self-contained bundle, runs the same
  // scan, then hands off to the dak SUBPROCESS which uploads — Hub opens no
  // socket itself), and surface the resulting URL. We send redact:true so any
  // findings in the bundle are sanitized before it leaves the machine. The
  // server records published-state + rebuilds, so the row's PUBLISHED marker
  // (republish / revoke) appears on the next render.
  function currentTask(){
    if(window._graphTaskCtx) return window._graphTaskCtx;
    const el=document.querySelector('.task-card,[data-sl]');
    if(el&&el.dataset&&el.dataset.sl){
      const t=(typeof TASKS_DATA!=='undefined')&&TASKS_DATA.find(x=>x.sl===el.dataset.sl);
      if(t) return t;
    }
    return (typeof TASKS_DATA!=='undefined'&&TASKS_DATA.length)?TASKS_DATA[0]:null;
  }
  function publishBundle(task){
    if(typeof PRIVATE!=='undefined'&&PRIVATE){flash('this workspace is private');return;}
    const t=task||currentTask();
    if(!t){flash('no task to bundle');return;}
    closePalette();
    flashSticky('publishing bundle for '+t.sl+'…');
    fetch('/_publish-bundle',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({slug:t.sl,repo:t.rp,redact:true,review:true})})
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
      .then(res=>{
        const d=res.d||{};
        if(res.ok&&d.url){
          const n=(d.findings||[]).length;
          const red=n?(' · '+n+' finding'+(n!==1?'s':'')+' redacted'):'';
          // S14 / #3 — a dry-run uploaded nothing; don't claim "published" and
          // don't reload (the server recorded no published-state for it).
          if(d.dryRun){flash('dry-run — not uploaded (URL not live): '+d.url+red);return;}
          copy(d.url,null);
          // S20 — a clear inform-on-publish with a clickable Open (parity with
          // the single-file sheet's "open ↗"). S26 — the server recorded
          // published-state; reflect the row's PUBLISHED marker (republish /
          // unpublish) IN PLACE instead of a home-nav reload, so the user stays
          // on their current view (trace/board/doc). Mirrors _markFilePublished.
          _markTaskPublished(t,d.url,d.mode);
          flashOpen('published · '+t.sl+red,d.url);
          return;
        }
        const detail=d.detail?(': '+String(d.detail).split('\n').slice(-1)[0]):'';
        flash(d.error==='private'?'this workspace is private':
              d.error==='dak_unavailable'?'dak not set up — run its one-time setup':
              ('publish failed'+detail));
      }).catch(()=>flash('publish failed'));
  }
  window._publishBundle=publishBundle;

  pubFileSel.addEventListener('change',pubScan);
  pubListEl.addEventListener('change',e=>{
    const cb=e.target.closest('input[type=checkbox]');if(!cb)return;
    pubKeep[+cb.dataset.i]=cb.checked;
  });
  document.getElementById('pal-pub-back').addEventListener('click',pubBack);
  document.getElementById('pal-pub-cancel').addEventListener('click',closePalette);
  pubGoBtn.addEventListener('click',pubPublish);

  // Drop files anywhere on the page → open Add-data pre-scoped (or stage into it).
  function hasFiles(e){return e.dataTransfer&&[...(e.dataTransfer.types||[])].indexOf('Files')>=0;}
  document.addEventListener('dragover',e=>{if(hasFiles(e))e.preventDefault();});
  document.addEventListener('drop',e=>{
    if(!(e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files.length))return;
    e.preventDefault();
    const files=e.dataTransfer.files;
    if(adScreen&&!adScreen.classList.contains('hidden')) stageFiles(files);
    else openAddData(files);
  });

  // ── global hotkeys ──
  document.addEventListener('keydown',e=>{
    const k=(e.key||'').toLowerCase();
    // ⌘K / Ctrl+K (primary) and ⌘P / Ctrl+P — preventDefault both (⌘P collides
    // with browser print).
    if((e.metaKey||e.ctrlKey)&&(k==='k'||k==='p')&&!e.altKey){
      e.preventDefault();
      pal.classList.contains('show')?closePalette():openPalette('');
      return;
    }
    if(pal.classList.contains('show')) return;
    if(help.classList.contains('show')){if(e.key==='Escape')help.classList.remove('show');return;}
    const tag=document.activeElement.tagName;
    if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT') return;
    if(e.metaKey||e.ctrlKey||e.altKey) return;
    if(document.getElementById('trace').classList.contains('show')) return;
    if(modal.classList.contains('show')) return;
    // Single-key global shortcuts (n/c/? are new; 1–4/y are additive, no conflict
    // with the existing j/k/Enter/Esc//' handler above).
    if(k==='n'){e.preventDefault();openPalette('');openNewTask('');}
    else if(k==='c'){e.preventDefault();if(window._openComposer)window._openComposer();}
    else if(k==='g'){e.preventDefault();if(window._openGraphFor)window._openGraphFor(null);}
    else if(e.key==='?'){e.preventDefault();help.classList.add('show');}
    else if(k==='y'){e.preventDefault();if(window._toggleTimeline)window._toggleTimeline();}
    else if(k==='b'&&e.shiftKey){e.preventDefault();if(window._publishBundle)window._publishBundle(null);}
    else if('1234'.includes(e.key)&&window._setView){
      e.preventDefault();window._setView(['work','list','board','calendar'][+e.key-1]);}
  });
})();

// ── Timeline · graph order canvas (2b / S4b) ───────────────────────────────
// A second *rendering* of the per-task 2b timeline (same baked nodes/edges as
// the Trace spine), laid out by edge/kind — NOT by date. Pure derivation from
// the lineage Hub already holds: no model, no new store. Paper ground + dot-grid
// (Hub's theme), oxblood for selection, deep-sea for navigation. The graph is
// PURELY derived — never saved into a draw; the `list · g` control returns to
// the Trace spine (the two are one task, toggled).
(function(){
  const KIND_COL={task:0,prompt:1,run:2,artifact:3,script:4,note:5,doc:6,draw:7,data:8};
  const REL_LABEL={task_has_run:'run',task_has_artifact:'artifact',task_has_script:'script',task_has_prompt:'prompt',task_has_doc:'doc',task_has_draw:'draw',task_has_data:'data',task_has_note:'note',belongs_to_task:'task'};
  const COL_W=260,ROW_H=130,X0=40,Y0=40,CARD_W=200,CARD_H=84;
  const colOf=k=>KIND_COL[k]!==undefined?KIND_COL[k]:9;
  const colorOf=colorForKind;  // shared with the Trace spine — one palette
  // Deterministic graph-order layout — mirrors core/graph.py::layout so a saved
  // diagram matches the canvas: kind columns, date order within a column.
  function layout(nodes){
    const cols={};
    nodes.forEach(n=>{const c=colOf(n.kind);(cols[c]=cols[c]||[]).push(n);});
    const pos={};
    Object.keys(cols).forEach(c=>{
      const items=cols[c].slice().sort((a,b)=>{
        const ka=(a.at||'')+' '+(a.path||'')+' '+a.id;
        const kb=(b.at||'')+' '+(b.path||'')+' '+b.id;
        return ka<kb?-1:ka>kb?1:0;});
      items.forEach((n,r)=>{pos[n.id]={x:X0+(+c)*COL_W,y:Y0+r*ROW_H};});
    });
    return pos;
  }

  let el=null;         // overlay root (built lazily)
  let stage,svg,nodesLayer,inspector,zoomLbl,titleEl,replayIn,isolateIn,replayLbl,rangeLbl;
  let ST={t:null,nodes:[],edges:[],pos:{},sel:null,zoom:1,dates:[],cut:null,isolate:false};

  function build(){
    if(el) return;
    el=document.createElement('div');
    el.id='gcanvas';el.className='gcanvas';
    el.innerHTML=`
      <div class="gc-head">
        <div class="gc-head-l">
          <div class="gc-kicker">// timeline · graph order</div>
          <div class="gc-title"></div>
        </div>
        <div class="gc-tools">
          <div class="gc-modeseg" title="back to the trace list (g)">
            <button class="gc-mode" data-a="tolist">list <span class="gc-mode-key">· g</span></button>
            <span class="gc-mode-sep">|</span>
            <span class="gc-mode active">graph</span>
          </div>
          <div class="gc-zoom">
            <button data-a="zout" title="zoom out">−</button>
            <span class="gc-zlbl">100%</span>
            <button data-a="zin" title="zoom in">+</button>
          </div>
          <button class="gc-btn" data-a="close">✕ close</button>
        </div>
      </div>
      <div class="gc-replay">
        <span class="gc-replay-lbl">replay</span>
        <input type="range" class="gc-replay-in" min="0" max="0" value="0">
        <span class="gc-replay-at">all</span>
        <span class="gc-replay-hint">· drag to fold the graph back in time</span>
        <label class="gc-iso"><input type="checkbox" class="gc-iso-in"> isolate path</label>
      </div>
      <div class="gc-stage-wrap">
        <div class="gc-stage">
          <svg class="gc-edges"><defs>
            <marker id="gc-arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
              <path d="M0,0 L7,3 L0,6 Z" fill="#8A8377"></path></marker>
            <marker id="gc-arrow-sel" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
              <path d="M0,0 L7,3 L0,6 Z" fill="#7A2828"></path></marker>
          </defs></svg>
          <div class="gc-nodes"></div>
        </div>
      </div>
      <div class="gc-inspector" hidden></div>`;
    document.body.appendChild(el);
    stage=el.querySelector('.gc-stage');
    svg=el.querySelector('.gc-edges');
    nodesLayer=el.querySelector('.gc-nodes');
    inspector=el.querySelector('.gc-inspector');
    zoomLbl=el.querySelector('.gc-zlbl');
    titleEl=el.querySelector('.gc-title');
    replayIn=el.querySelector('.gc-replay-in');
    replayLbl=el.querySelector('.gc-replay-at');
    rangeLbl=el.querySelector('.gc-replay-lbl');
    isolateIn=el.querySelector('.gc-iso-in');
    el.addEventListener('click',e=>{
      const a=e.target.closest('[data-a]');if(!a)return;
      const act=a.dataset.a;
      if(act==='close')close();
      else if(act==='tolist')toList();
      else if(act==='zin')setZoom(ST.zoom+0.1);
      else if(act==='zout')setZoom(ST.zoom-0.1);
    });
    el.addEventListener('click',e=>{if(e.target===el)close();});
    replayIn.addEventListener('input',()=>{
      const i=+replayIn.value;
      ST.cut=(i>=ST.dates.length)?null:ST.dates[i];
      replayLbl.textContent=ST.cut===null?'all':ST.cut;
      applyDim();
    });
    isolateIn.addEventListener('change',()=>{ST.isolate=isolateIn.checked;applyDim();});
    document.addEventListener('keydown',e=>{
      if(!el||el.hidden)return;
      if(e.key==='Escape'){e.preventDefault();close();}
    });
  }

  function setZoom(z){
    ST.zoom=Math.max(0.4,Math.min(2,Math.round(z*10)/10));
    stage.style.transform='scale('+ST.zoom+')';
    zoomLbl.textContent=Math.round(ST.zoom*100)+'%';
  }

  // Upstream (ancestor) set of a node, walking edges backwards — for isolate.
  function upstream(id){
    const inc={};ST.edges.forEach(e=>{(inc[e.to]=inc[e.to]||[]).push(e.from);});
    const seen={},q=[id];
    while(q.length){const cur=q.pop();(inc[cur]||[]).forEach(p=>{if(!seen[p]){seen[p]=1;q.push(p);}});}
    seen[id]=1;return seen;
  }

  function applyDim(){
    const upset=(ST.isolate&&ST.sel)?upstream(ST.sel):null;
    ST.nodes.forEach(n=>{
      const card=nodesLayer.querySelector('[data-id="'+n.id+'"]');if(!card)return;
      let dim=false;
      if(ST.cut!==null&&(n.at||'')>ST.cut) dim=true;      // replay: fold later events
      if(upset&&!upset[n.id]) dim=true;                    // isolate: only ancestors
      card.classList.toggle('dim',dim);
    });
    drawEdges();
  }

  function drawEdges(){
    const sel=ST.sel;
    const incident={};
    if(sel)ST.edges.forEach(e=>{if(e.from===sel||e.to===sel)incident[e.from+'>'+e.to]=1;});
    let h='';
    ST.edges.forEach(e=>{
      const a=ST.pos[e.from],b=ST.pos[e.to];if(!a||!b)return;
      const x1=a.x+CARD_W,y1=a.y+CARD_H/2,x2=b.x,y2=b.y+CARD_H/2;
      const mx=(x1+x2)/2;
      const on=sel&&incident[e.from+'>'+e.to];
      const cls='gc-edge'+(on?' sel':'');
      h+=`<path class="${cls}" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" `
        +`marker-end="url(#gc-arrow${on?'-sel':''})"></path>`;
    });
    const defs=svg.querySelector('defs');
    svg.innerHTML='';svg.appendChild(defs);
    svg.insertAdjacentHTML('beforeend',h);
  }

  function incomingRel(id){
    const e=ST.edges.find(e=>e.to===id);
    return e?(REL_LABEL[e.rel]||e.rel):'';
  }

  function render(){
    const nodes=ST.nodes;
    ST.pos=layout(nodes);
    let maxX=0,maxY=0;
    Object.keys(ST.pos).forEach(id=>{maxX=Math.max(maxX,ST.pos[id].x+CARD_W);maxY=Math.max(maxY,ST.pos[id].y+CARD_H);});
    stage.style.width=(maxX+X0)+'px';stage.style.height=(maxY+Y0)+'px';
    svg.setAttribute('width',String(maxX+X0));svg.setAttribute('height',String(maxY+Y0));
    svg.setAttribute('viewBox','0 0 '+(maxX+X0)+' '+(maxY+Y0));
    const slug=ST.t?ST.t.sl:'';
    nodesLayer.innerHTML=nodes.map(n=>{
      // NOTE nodes show the comment text (baked `label`), every other kind the
      // filename — the two renderings (spine + graph) stay in sync.
      const p=ST.pos[n.id];const name=(n.kind==='note'&&n.label)?n.label:((n.path||'').split('/').pop()||n.id);
      const rel=incomingRel(n.id);
      // Nodes whose path lives outside tasks/<slug>/ are drawn dashed — they are
      // referenced from the task, not owned by it (the comp's DOC treatment).
      const ext=!nodeInTask(n.path,slug);
      return `<div class="gc-node k-${esc(n.kind||'doc')}${ext?' ext':''}" data-id="${esc(n.id)}"
        style="left:${p.x}px;top:${p.y}px;--kc:${colorOf(n.kind)}">
        <div class="gc-node-badge">${esc((n.kind||'').toUpperCase())}</div>
        <div class="gc-node-name">${esc(name)}</div>
        <div class="gc-node-meta">${esc(fmtEventDate(n.at))}${rel?' · '+esc(rel):''}</div>
      </div>`;
    }).join('');
    nodesLayer.querySelectorAll('.gc-node').forEach(card=>{
      card.addEventListener('click',ev=>{ev.stopPropagation();select(card.dataset.id);});
    });
    drawEdges();
    applyDim();
  }

  function select(id){
    ST.sel=id;
    nodesLayer.querySelectorAll('.gc-node').forEach(c=>c.classList.toggle('sel',c.dataset.id===id));
    const n=ST.nodes.find(x=>x.id===id);
    if(!n){inspector.hidden=true;return;}
    const derives=ST.edges.filter(e=>e.to===id).map(e=>ST.nodes.find(x=>x.id===e.from)).filter(Boolean);
    const produced=ST.edges.filter(e=>e.from===id).map(e=>ST.nodes.find(x=>x.id===e.to)).filter(Boolean);
    const li=arr=>arr.length?arr.map(x=>`<span class="gc-chip">${esc((x.path||'').split('/').pop())}</span>`).join(''):'<span class="gc-none">—</span>';
    // S6 — surface the changelog skill's provenance ("written by …") when the
    // selected artifact carries it, plus a short derivation line.
    const abs=nodeAbs(n);
    const prov=(abs&&typeof PROVENANCE_DATA!=='undefined'&&PROVENANCE_DATA)?PROVENANCE_DATA[abs]:null;
    let provH='';
    if(prov&&prov.generated_by){
      provH=`<div class="gc-ins-prov">written by <b>${esc(prov.generated_by)}</b>`+
        (prov.commit_range?` · reads git range <b>${esc(prov.commit_range)}</b>`:'')+`</div>`;
    }
    inspector.hidden=false;
    inspector.innerHTML=`
      <div class="gc-kicker">// selected node</div>
      <div class="gc-ins-path">${esc(n.path||n.id)}</div>
      ${provH}
      <div class="gc-ins-row"><span class="gc-ins-lbl">derives from</span>${li(derives)}</div>
      <div class="gc-ins-row"><span class="gc-ins-lbl">produced in</span>${li(produced)}</div>
      <div class="gc-ins-actions">
        <button class="gc-btn" data-ins="open">open</button>
        <button class="gc-btn" data-ins="isolate">isolate path</button>
      </div>`;
    inspector.querySelector('[data-ins="open"]').onclick=()=>{
      const a=nodeAbs(n);
      if(a)window._openReader?window._openReader(a):window.open(fileHref(a),'_blank','noopener');
      else flash('path not resolvable');
    };
    // Isolate the path feeding THIS node: turn on the isolate flag (mirrors the
    // header checkbox) and dim everything that is not an ancestor.
    inspector.querySelector('[data-ins="isolate"]').onclick=()=>{
      ST.isolate=!ST.isolate;isolateIn.checked=ST.isolate;applyDim();
    };
    if(ST.isolate)applyDim();else drawEdges();
  }

  // Resolve a node's abs path from the file rows when possible (2b paths are
  // scan-root-relative).
  function nodeAbs(n){
    const rel=n.path||'';
    if(!rel)return null;
    let hit=null;
    rows.forEach(r=>{const a=r.dataset.abs;if(a&&a.replace(/\\/g,'/').endsWith('/'+rel))hit=hit||a;});
    if(!hit&&ST.t&&ST.t.abs&&(n.kind==='task'))hit=ST.t.abs;
    return hit;
  }

  // The `list · g` control: close the derived graph and return to the Trace
  // spine for the same task (the two are one task, toggled).
  function toList(){
    const t=ST.t;
    close();
    if(t)openTrace(t);
  }

  function firstTaskWithGraph(){
    if(typeof TASKS_DATA==='undefined')return null;
    for(const t of TASKS_DATA){if(taskGraph(t).nodes.length)return t;}
    return null;
  }

  function open(t){
    build();
    if(!t)t=window._graphTaskCtx||firstTaskWithGraph();
    if(!t){flash('no task timeline to graph yet');return;}
    window._graphCurrent=t;
    const g=taskGraph(t);
    if(!g.nodes.length){flash('no events for '+tagName(t.sl));return;}
    ST={t:t,nodes:g.nodes,edges:g.edges,pos:{},sel:null,zoom:1,
        dates:[],cut:null,isolate:false};
    ST.dates=[...new Set(g.nodes.map(n=>n.at||'').filter(Boolean))].sort();
    titleEl.textContent=tagName(t.sl)+'  ·  '+t.rp;
    // Replay label carries the date range the slider folds through.
    rangeLbl.textContent=ST.dates.length
      ? fmtEventDate(ST.dates[0]).toLowerCase()+' → '+fmtEventDate(ST.dates[ST.dates.length-1]).toLowerCase()
      : 'replay';
    replayIn.max=String(ST.dates.length);replayIn.value=String(ST.dates.length);
    replayLbl.textContent='all';isolateIn.checked=false;
    inspector.hidden=true;
    el.hidden=false;el.classList.add('show');
    if(window._setTraceMode)window._setTraceMode('graph');
    setZoom(1);render();
  }
  function close(){
    window._graphCurrent=null;
    if(el){el.hidden=true;el.classList.remove('show');}
    if(window._setTraceMode)window._setTraceMode('list');
  }

  window._openGraphFor=open;
  window._closeGraph=close;

  // Deep link: hub timeline <slug> --graph prints /?graph=<slug>[&repo=R].
  (function(){
    const q=new URLSearchParams(location.search);
    const slug=q.get('graph');if(!slug)return;
    const repo=q.get('repo');
    const find=()=>{
      if(typeof TASKS_DATA==='undefined')return null;
      return TASKS_DATA.find(t=>t.sl===slug&&(!repo||t.rp===repo))||TASKS_DATA.find(t=>t.sl===slug)||null;
    };
    const t=find();if(t)setTimeout(()=>open(t),0);
  })();
})();
