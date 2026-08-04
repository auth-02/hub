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
  const ORDER=['belongs_to_task','belongs_to_skill','task_has_run','task_has_artifact','task_has_draw','task_has_data','task_has_note','task_has_prompt','task_has_doc','skill_has_ref'];
  const LABELS={'belongs_to_task':'↑ task','belongs_to_skill':'↑ skill','task_has_run':'runs','task_has_artifact':'artifacts','task_has_draw':'draws','task_has_data':'data','task_has_note':'notes','task_has_prompt':'prompts','task_has_doc':'docs','skill_has_ref':'references'};
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
  const LIN_ORDER=['task_has_run','task_has_artifact','task_has_draw','task_has_note','task_has_prompt','task_has_data','task_has_doc'];
  const LIN_LABELS={'task_has_run':'Runs','task_has_artifact':'Artifacts','task_has_draw':'Draws','task_has_note':'Notes','task_has_prompt':'Prompts','task_has_data':'Data','task_has_doc':'Docs'};
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
    return [
      {type:'action',write:true,id:'act:new-task',key:'N',ic:'✎',label:'New task',
       cli:'hub new task <slug>',prim:()=>openNewTask('')},
      {type:'action',write:true,id:'act:new-draw',key:'D',ic:'✎',label:'New draw',
       cli:'hub draw',prim:()=>{closePalette();window.open('/draw','_blank','noopener');}},
      {type:'action',write:true,id:'act:new-note',key:'C',ic:'✎',label:'New note',
       cli:'hub note <path>',prim:()=>openNewNote(null)},
      {type:'action',write:true,id:'act:add-data',ic:'✎',label:'Add data',
       cli:'hub data <path>',prim:()=>openAddData(null)},
      {type:'action',write:true,id:'act:publish',ic:'✎',label:'Publish',
       cli:'hub publish',prim:()=>{flash('Publish lands in a later layer');}},
    ];
  }
  function taskItems(){
    return TASKS_DATA.map(t=>({
      type:'task',id:'task:'+t.rp+':'+t.sl,label:tagName(t.sl),
      sub:t.rp+' · tasks/'+t.sl,cli:'hub trace tasks/'+t.sl,abs:t.abs,
      _match:t.sl+' '+t.rp,copyText:'tasks/'+t.sl,
      prim:()=>{closePalette();openTrace(t);},
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
        prim:()=>{closePalette();window.open(r.href,'_blank','noopener');},
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

  function currentTerm(){
    let v=palInput.value;
    if(scope) return v;          // scope already stripped from value
    if(v && SCOPE_TYPE[v[0]]) return v.slice(1).trimStart();
    return v;
  }

  function render(){
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
    if(noteScreen) noteScreen.classList.add('hidden');
    searchScreen.classList.remove('hidden');
    scope=scopeChar&&SCOPE_TYPE[scopeChar]?scopeChar:'';
    pal.classList.add('show');
    palInput.value='';
    render();
    setTimeout(()=>{palInput.focus();},0);
  }
  function closePalette(){pal.classList.remove('show');scope='';}
  window._openPalette=openPalette;

  palInput.addEventListener('input',render);
  palInput.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'||(e.ctrlKey&&e.key==='n')){e.preventDefault();move(1);}
    else if(e.key==='ArrowUp'||(e.ctrlKey&&e.key==='p')){e.preventDefault();move(-1);}
    else if(e.key==='Enter'){e.preventDefault();
      activate(palItems[palSel], e.altKey?'alt':e.shiftKey?'shift':'prim');}
    else if(e.key==='Escape'){e.preventDefault();
      if(scope){scope='';palScope.classList.remove('show');render();}
      else closePalette();}
    else if(e.key==='Backspace'&&scope&&palInput.value===''){scope='';render();}
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
    const today=new Date().toISOString().slice(0,10);
    const lines=['---','status: '+status,'title: '+title,'created: '+today,'---','','# '+title];
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
    const _nt=document.getElementById('pal-note-screen');if(_nt)_nt.classList.add('hidden');
    repoSel.innerHTML=repoList().map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');
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
  function openAddData(files){
    help.classList.remove('show');
    if(!pal.classList.contains('show')) pal.classList.add('show');
    searchScreen.classList.add('hidden');ntScreen.classList.add('hidden');
    if(noteScreen)noteScreen.classList.add('hidden');
    adScreen.classList.remove('hidden');
    adStaged=[];
    adTaskSel.innerHTML = TASKS_DATA.length
      ? TASKS_DATA.map((t,i)=>'<option value="'+i+'">'+esc(t.rp+' · tasks/'+t.sl)+'</option>').join('')
      : '<option value="">no tasks yet — create one first</option>';
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

  // ── new-note screen (1e) ──────────────────────────────────────────────────
  // A note is one markdown file at tasks/<slug>/comments/<date>-<slug>.md with a
  // front-matter anchor (target/range). The sole network call is POST /_note,
  // where the server re-enforces the guards (repo/slug/target-escape/collision).
  const noteScreen=document.getElementById('pal-note-screen');
  const noteTaskSel=document.getElementById('pal-note-task');
  const noteTarget=document.getElementById('pal-note-target');
  const noteRange=document.getElementById('pal-note-range');
  const noteText=document.getElementById('pal-note-text');
  const noteDest=document.getElementById('pal-note-dest');
  const noteSaveBtn=document.getElementById('pal-note-save');

  function noteRender(){
    const t=TASKS_DATA[+noteTaskSel.value];
    const tgt=(noteTarget.value||'').trim()||'manifest.md';
    noteDest.textContent = t
      ? ((t.rp&&t.rp!=='(root)'?t.rp+'/':'')+'tasks/'+t.sl+'/comments/  ← target: '+tgt)
      : '';
    noteSaveBtn.disabled=!(t && noteText.value.trim());
  }
  function openNewNote(prefill){
    help.classList.remove('show');
    if(!pal.classList.contains('show')) pal.classList.add('show');
    searchScreen.classList.add('hidden');ntScreen.classList.add('hidden');
    if(adScreen)adScreen.classList.add('hidden');
    noteScreen.classList.remove('hidden');
    noteTaskSel.innerHTML = TASKS_DATA.length
      ? TASKS_DATA.map((t,i)=>'<option value="'+i+'">'+esc(t.rp+' · tasks/'+t.sl)+'</option>').join('')
      : '<option value="">no tasks yet — create one first</option>';
    // A prefill may pin the task + target (e.g. from a file row's dataset).
    if(prefill&&prefill.slug){
      const idx=TASKS_DATA.findIndex(t=>t.sl===prefill.slug&&(!prefill.repo||t.rp===prefill.repo));
      if(idx>=0)noteTaskSel.value=String(idx);
    }
    noteTarget.value=(prefill&&prefill.target)||'';
    noteRange.value='';
    noteText.value='';
    noteRender();
    setTimeout(()=>{(prefill&&prefill.target?noteText:noteTarget).focus();},0);
  }
  window._openNewNote=openNewNote;
  function noteBack(){noteScreen.classList.add('hidden');searchScreen.classList.remove('hidden');openPalette('');}

  function noteSave(){
    const t=TASKS_DATA[+noteTaskSel.value];
    if(!t){flash('pick a task');return;}
    const bodyText=noteText.value.trim();
    if(!bodyText){flash('note body required');return;}
    const target=(noteTarget.value||'').trim()||'manifest.md';
    const range=(noteRange.value||'').trim();
    noteSaveBtn.disabled=true;
    fetch('/_note',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({repo:t.rp,slug:t.sl,target:target,range:range,body:bodyText})})
      .then(r=>r.json().then(d=>({ok:r.ok,d:d})).catch(()=>({ok:r.ok,d:{}})))
      .then(res=>{
        if(res.ok){flashSticky('saving note…');softReload();return;}
        noteSaveBtn.disabled=false;
        const d=res.d||{};
        flash('note failed: '+(d.detail||d.error||'unknown'));
      }).catch(()=>{noteSaveBtn.disabled=false;flash('note failed');});
  }

  noteTaskSel.addEventListener('change',noteRender);
  noteTarget.addEventListener('input',noteRender);
  noteText.addEventListener('input',noteRender);
  noteText.addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();noteSave();}
    else if(e.key==='Escape'){e.preventDefault();noteBack();}
  });
  noteTarget.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();noteBack();}});
  document.getElementById('pal-nt-note-back').addEventListener('click',noteBack);
  document.getElementById('pal-note-cancel').addEventListener('click',closePalette);
  noteSaveBtn.addEventListener('click',noteSave);

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
    else if(k==='c'){e.preventDefault();openNewNote(null);}
    else if(e.key==='?'){e.preventDefault();help.classList.add('show');}
    else if(k==='y'){e.preventDefault();document.getElementById('tl-tab').click();}
    else if('1234'.includes(e.key)&&window._setView){
      e.preventDefault();window._setView(['work','list','board','calendar'][+e.key-1]);}
  });
})();
