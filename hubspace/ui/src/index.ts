// @ts-nocheck — moved verbatim from static/hub.js. Vanilla DOM script that reads
// lexical globals (FTS_DATA, _currentRoot, …) injected by hub.html's inline
// <script>; not type-checked. The CSS import below is bundled to static/hub.css.
import "./hub.css";

const ftsMap=new Map(FTS_DATA.map(d=>[d.a,d]));
const STATUS_CYCLE=['ongoing','completed','paused'];

// ── DOM refs ──────────────────────────────────────────────────────────────
const q=document.getElementById('q');
const rows=[...document.querySelectorAll('.row')];
const chips=[...document.querySelectorAll('.chip')];
const preview=document.getElementById('preview');
const pvTitle=document.getElementById('pv-title');
const pvOpen=document.getElementById('pv-open');
const pvBody=document.getElementById('pv-body');
const pvLineage=document.getElementById('pv-lineage');
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

function softReload(){location.reload();}
setInterval(()=>softReload(),120000);

// ── Activity helpers (shared by the activity view + timeline) ──────────────
const FEED_ACTIONS={
  task:    {created:'New task started',    updated:'Task plan updated'},
  run:     {created:'Run logged',          updated:'Run notes updated'},
  artifact:{created:'Artifact created',    updated:'Artifact revised'},
  prompt:  {created:'Prompt added',        updated:'Prompt updated'},
  doc:     {created:'Doc added',           updated:'Doc updated'},
  data:    {created:'Data file added',     updated:'Data file updated'},
  claude:  {created:'CLAUDE.md updated',   updated:'CLAUDE.md updated'},
  readme:  {created:'README updated',      updated:'README updated'},
};
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

function openPreview(row){
  pvTitle.textContent=row.querySelector('.path').textContent;
  pvOpen.href=row.href;
  const abs=row.dataset.abs||'';
  const links=LINEAGE_DATA[abs]||[];
  if(links.length){pvLineage.innerHTML=buildLineage(links);pvLineage.classList.add('show');}
  else pvLineage.classList.remove('show');
  pvBody.classList.add('iframe-mode');
  pvBody.innerHTML=`<iframe class="pv-iframe" src="${row.href}"></iframe>`;
  preview.classList.add('open');
}

function closePreview(){
  preview.classList.remove('open');
  pvBody.classList.remove('iframe-mode');
  pvBody.innerHTML='';
  if(selRows[selIdx]) selRows[selIdx].classList.remove('selected');
  selIdx=-1;
}

rows.forEach(r=>r.addEventListener('click',e=>{
  e.preventDefault();
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
  const close=document.createElement('button');
  close.className='float-ctl';close.type='button';close.textContent='✕';
  head.appendChild(ttl);head.appendChild(open);head.appendChild(close);
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

// ── Keyboard nav ──────────────────────────────────────────────────────────
document.addEventListener('keydown',e=>{
  const tag=document.activeElement.tagName;
  if(tag==='INPUT'||tag==='TEXTAREA') return;
  if(document.getElementById('trace').classList.contains('show')){
    if(e.key==='Escape') closeTrace();
    return;
  }
  if(e.key==='j'||e.key==='ArrowDown'){e.preventDefault();selectRow(selIdx<0?0:selIdx+1);}
  else if(e.key==='k'||e.key==='ArrowUp'){e.preventDefault();selectRow(Math.max(selIdx-1,0));}
  else if(e.key==='Escape'){closePreview();}
  else if(e.key==='Enter'&&selIdx>=0&&selRows[selIdx]){window.open(selRows[selIdx].href,'_blank');}
  else if(e.key==='/'&&!modal.classList.contains('show')){e.preventDefault();q.focus();}
});

// ── Lineage builder ───────────────────────────────────────────────────────
function buildLineage(links){
  const groups={};
  links.forEach(l=>{(groups[l.r]=groups[l.r]||[]).push(l);});
  const ORDER=['belongs_to_task','belongs_to_skill','task_has_run','task_has_artifact','task_has_data','task_has_prompt','task_has_doc','skill_has_ref'];
  const LABELS={'belongs_to_task':'↑ task','belongs_to_skill':'↑ skill','task_has_run':'runs','task_has_artifact':'artifacts','task_has_data':'data','task_has_prompt':'prompts','task_has_doc':'docs','skill_has_ref':'references'};
  let h='<div class="ln-label">// trace</div>';
  ORDER.forEach(r=>{
    if(!groups[r]) return;
    h+=`<div class="ln-group"><span class="ln-type">${LABELS[r]||r}</span>`;
    groups[r].forEach(l=>{
      const name=l.p.split('/').pop();
      h+=`<a class="ln-item" href="${fileHref(l.a)}" target="_blank" title="${esc(l.p)}">${esc(name)}</a>`;
    });
    h+='</div>';
  });
  return h;
}

function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function fileHref(abs){return SERVER_ORIGIN?SERVER_ORIGIN+encodeURI(abs):'file://'+encodeURI(abs);}

// ── Workspace Timeline ────────────────────────────────────────────────────
(function(){
  const el=document.getElementById('hub-timeline');
  const tasks=TIMELINE_DATA.tasks||[];
  const commits=TIMELINE_DATA.commits||[];
  if(!tasks.length&&!commits.length){el.innerHTML='';return;}

  const now=Date.now()/1000;
  const todayStart=(()=>{const d=new Date();d.setHours(0,0,0,0);return d.getTime()/1000;})();
  const yesterdayStart=todayStart-86400;
  const weekStart=todayStart-6*86400;

  function bucket(ts){
    if(ts>=todayStart) return 'today';
    if(ts>=yesterdayStart) return 'yesterday';
    if(ts>=weekStart) return 'week';
    return null;
  }

  const grouped={today:[],yesterday:[],week:[]};
  tasks.forEach(t=>{const b=bucket(t.ts);if(b)grouped[b].push(t);});

  const cIdx={};
  commits.forEach(c=>{
    const b=bucket(c.ts);if(!b)return;
    const k=b+':'+c.rp;
    if(!cIdx[k])cIdx[k]=[];
    if(cIdx[k].length<3)cIdx[k].push(c.msg);
  });

  function renderTask(t,b){
    const name=t.sl.replace(/[-_]/g,' ').replace(/^./,c=>c.toUpperCase());
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
      ${bullets.length?`<ul class="tl-bullets">${bullets.map(b=>`<li class="tl-bullet">${esc(b)}</li>`).join('')}</ul>`:''}
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
  el.innerHTML=h;
})();

// ── Timeline drawer ───────────────────────────────────────────────────────
(function(){
  const drawer=document.getElementById('tl-drawer');
  const tab=document.getElementById('tl-tab');
  function openTl(){drawer.classList.add('open');tab.classList.add('open');tab.textContent='‹';}
  function closeTl(){drawer.classList.remove('open');tab.classList.remove('open');tab.textContent='// timeline';}
  window.closeTl=closeTl;
  tab.addEventListener('click',()=>drawer.classList.contains('open')?closeTl():openTl());
  document.getElementById('tl-close').addEventListener('click',closeTl);
  document.addEventListener('keydown',e=>{
    if((e.ctrlKey||e.metaKey)&&e.key==='t'){e.preventDefault();drawer.classList.contains('open')?closeTl():openTl();}
    else if(e.key==='Escape'&&drawer.classList.contains('open'))closeTl();
  });
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
  card.addEventListener('click',()=>{if(t.abs)window.open(fileHref(t.abs),'_blank','noopener');});
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
      return `<a class="cal-chip s-${st}" href="${fileHref(t.abs)}" target="_blank" rel="noopener" title="${esc(t.rp+' / '+t.sl)}">${esc(tagName(t.sl))}</a>`;
    }).join('');
    h+=`<div class="cal-cell${today?' cal-today':''}"><div class="cal-day">${day}</div>${chips}</div>`;
  }
  grid.innerHTML=h;
}
document.getElementById('cal-prev').addEventListener('click',()=>{calRef.setMonth(calRef.getMonth()-1);renderCalendar();});
document.getElementById('cal-next').addEventListener('click',()=>{calRef.setMonth(calRef.getMonth()+1);renderCalendar();});

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
    return `<div class="task-row" data-abs="${esc(t.abs||'')}" data-sl="${esc(t.sl)}" data-rp="${esc(t.rp)}">
      <span class="task-tick ${dotCls}"></span>
      <div class="task-body">
        <div class="task-name">${esc(tagName(t.sl))}${orphanBadge}</div>
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
        return `<a class="loose-row" href="${r.href}" target="_blank" rel="noopener">
          <span class="loose-kd">${esc(kd)}</span>
          <span>${esc(path)}</span>
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
function openTrace(t){
  const st=t.status||'ongoing';
  const stMap={ongoing:'ts-on',paused:'ts-pause',completed:'ts-done'};

  document.getElementById('trace-crumb').innerHTML=
    `${esc(t.rp)} / <span class="tc-accent">tasks</span> / ${esc(t.sl)}`+
    (t.orphan?' <span style="font-family:var(--mono);font-size:9px;color:var(--mute);border:1px solid var(--line);padding:1px 6px;margin-left:6px">no manifest</span>':'');
  document.getElementById('trace-title').textContent=tagName(t.sl);
  document.getElementById('trace-status').className='trace-status '+(stMap[st]||'ts-on');
  document.getElementById('trace-status').textContent=st+' · updated '+feedAgo(t.mtime);

  const planEl=document.getElementById('trace-plan');
  if(t.plan&&t.plan.length){
    planEl.innerHTML=t.plan.map(p=>
      `<li class="${p.d?'tp-done':'tp-todo'}">${esc(p.t)}</li>`
    ).join('');
  } else {
    planEl.innerHTML='<li class="tp-todo" style="color:var(--mute);font-style:italic">no plan checklist in manifest</li>';
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
  const LIN_ORDER=['task_has_run','task_has_artifact','task_has_prompt','task_has_data','task_has_doc'];
  const LIN_LABELS={'task_has_run':'Runs','task_has_artifact':'Artifacts','task_has_prompt':'Prompts','task_has_data':'Data','task_has_doc':'Docs'};
  const groups={};
  links.forEach(l=>{(groups[l.r]=groups[l.r]||[]).push(l);});
  let linH='';
  LIN_ORDER.forEach(rel=>{
    if(!groups[rel]) return;
    linH+=`<div class="tl-lbl">${LIN_LABELS[rel]||rel}</div>
      <div class="tl-files">`;
    groups[rel].forEach(l=>{
      const name=l.p.split('/').pop();
      const meta=l.p.split('/').slice(-2,-1)[0]||'';
      linH+=`<a class="tl-file" href="${fileHref(l.a)}" target="_blank" rel="noopener">
        <span>${esc(name)}</span>
        <span class="tl-fmeta">${esc(meta)}</span>
      </a>`;
    });
    linH+='</div>';
  });
  lin.innerHTML=linH||'<div class="tl-lbl" style="color:var(--mute)">—</div><div class="tl-files" style="padding:12px 0 12px 16px;border-left:1px solid var(--line);color:var(--mute);font-family:var(--mono);font-size:11px">no children indexed yet</div>';

  const actionsEl=document.getElementById('trace-actions');
  actionsEl.innerHTML='';
  if(t.abs){
    const a=document.createElement('a');
    a.className='trace-btn primary';
    a.href=fileHref(t.abs);
    a.target='_blank';
    a.rel='noopener';
    a.textContent='Open manifest';
    actionsEl.appendChild(a);
  }

  traceEl.classList.add('show');
  traceEl.scrollTop=0;
}
function closeTrace(){
  traceEl.classList.remove('show');
}
document.getElementById('trace-back').addEventListener('click',closeTrace);

// ── Activity view ─────────────────────────────────────────────────────────
function renderActivityView(){
  const el=document.getElementById('act-content');
  // Merge ACTIVITY_DATA events with TIMELINE_DATA tasks, sort desc by ts
  const events=[];
  (ACTIVITY_DATA||[]).forEach(ev=>{
    const name=ev.sl||ev.p.split('/').pop().replace(/\.[^.]+$/,'');
    const actions=FEED_ACTIONS[ev.k]||{created:'File added',updated:'File modified'};
    const actionText=(actions[ev.ev]||'Changed');
    events.push({ts:ev.ts,title:name.replace(/[-_]/g,' ').replace(/^./,c=>c.toUpperCase()),type:actionText,repo:ev.rp||''});
  });
  // Also add timeline task summaries as events
  (TIMELINE_DATA.tasks||[]).forEach(t=>{
    const name=tagName(t.sl);
    const parts=[];
    if(t.runs)parts.push(t.runs+' run'+(t.runs>1?'s':''));
    if(t.artifacts)parts.push(t.artifacts+' artifact'+(t.artifacts>1?'s':''));
    const detail=parts.join(', ')||(t.status||'updated');
    events.push({ts:t.ts,title:name,type:detail,repo:t.rp||''});
  });
  events.sort((a,b)=>b.ts-a.ts);

  if(!events.length){
    el.innerHTML='<div class="act-empty">No recent activity yet.</div>';
    return;
  }

  // Group by calendar day
  const byDay=new Map();
  events.forEach(ev=>{
    const d=new Date(ev.ts*1000);
    const key=d.toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'});
    if(!byDay.has(key))byDay.set(key,[]);
    byDay.get(key).push(ev);
  });

  let h='';
  byDay.forEach((evs,day)=>{
    h+=`<div class="act-day">${esc(day)}</div>`;
    evs.forEach(ev=>{
      h+=`<div class="act-ev">
        <div class="act-title">${esc(ev.title)}</div>
        <div class="act-detail"><span class="ad-type">${esc(ev.type)}</span>${ev.repo?' · '+esc(ev.repo):''}</div>
      </div>`;
    });
  });
  el.innerHTML=h;
}

// ── View toggle ───────────────────────────────────────────────────────────
(function(){
  const layout=document.querySelector('.hub-layout');
  const board=document.getElementById('board');
  const cal=document.getElementById('calendar');
  const workView=document.getElementById('work-view');
  const actView=document.getElementById('activity-view');
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
    actView.classList.toggle('show',v==='activity');
    if(v==='board')renderBoard();
    if(v==='calendar')renderCalendar();
    if(v==='work')renderWorkView();
    if(v==='activity')renderActivityView();
  }
  pills.forEach(p=>p.addEventListener('click',()=>setView(p.dataset.view)));
  setView(view);
  // expose for apply()
  window._setView=setView;
  window._currentView=()=>view;
})();

// Run apply after view toggle is wired
apply();

const REBUILD_CMD=`/usr/bin/python3 ${HUBPY}`;
const toast=document.getElementById('toast');
function flash(msg){toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2400);}
// Persistent toast — stays visible until the page swaps (used during rebuild)
function flashSticky(msg){toast.textContent=msg;toast.classList.add('show');}
async function copy(text,msg){
  try{await navigator.clipboard.writeText(text);flash(msg);}
  catch(e){window.prompt('Copy this command:',text);}
}

// ── Modal ─────────────────────────────────────────────────────────────────
const modal=document.getElementById('modal');
const modalInput=document.getElementById('modal-input');
function openModal(){modalInput.value=_currentRoot;modal.classList.add('show');setTimeout(()=>{modalInput.focus();modalInput.select();},0);}
function closeModal(){modal.classList.remove('show');}
function submitModal(){
  const p=modalInput.value.trim();
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
modalInput.addEventListener('keydown',e=>{if(e.key==='Enter')submitModal();else if(e.key==='Escape')closeModal();});
document.getElementById('rebuild').addEventListener('click',e=>{
  e.preventDefault();
  flashSticky('rebuilding…');
  fetch('/_rebuild')
    .then(r=>r.ok?Promise.resolve():Promise.reject())
    .then(()=>softReload())
    .catch(()=>flash('rebuild failed'));
});
