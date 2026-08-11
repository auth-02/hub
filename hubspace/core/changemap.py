"""Interactive HTML change-map for the change-log skill (S32).

A self-contained, offline HTML page that renders a change as a **functional
flow** — nodes are *changes* (a capability that moved), not files — and lets a
reviewer **click a node to deep-dive** into that change's file / function /
test-level detail in a side inspector (the HQFlow-style panel). This is the
primary change-log deliverable; the Excalidraw scene (:mod:`changelog`) stays as
an optional hand-annotatable canvas.

Still deterministic and model-free: the agent hands over the change-graph it
reasoned out (each node carrying its own deep-dive `details`); this only lays it
out left→right by dependency and emits the page. No external hosts, fonts, or
scripts — publishable as-is by ``hub publish``.

Node:
    {id, kind, title, verb, summary,
     files:     [{path, change}],          # file-level
     functions: [{symbol, note}],          # code/function-level
     tests:     [str],
     note:      str}
Edge: {from, to, rel?}
"""
from __future__ import annotations

import html as _html
import json as _json

from .graph import color_for  # kind → accent, reused from the hub.css palette

KIND_TINT = {
    "task": "#F1DEDA", "doc": "#DCE8EC", "artifact": "#E6E0F0",
    "run": "#DBE8E0", "data": "#D6E8EB", "draw": "#F1E4D0",
    "note": "#F3E1D4", "prompt": "#F0E7CC", "script": "#E0E7EC",
}
_TINT_DEFAULT = "#ECE5D2"

# Canvas geometry (px).
NODE_W = 280
NODE_H = 96
COL_PITCH = 372
ROW_PITCH = 150
PAD = 48


def _tint(kind: str) -> str:
    return KIND_TINT.get(kind or "", _TINT_DEFAULT)


def _ranks(nodes, edges):
    """Column per node: 0 when nothing depends-out to it, else one past the
    deepest dependent (edge from→to = *from depends on to*), so dependencies sit
    to the right and arrows read left→right. Cycle-safe."""
    ids = {n["id"] for n in nodes}
    incoming = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("from") in ids and e.get("to") in ids:
            incoming[e["to"]].append(e["from"])
    rank, visiting = {}, set()

    def r(nid):
        if nid in rank:
            return rank[nid]
        if nid in visiting or not incoming[nid]:
            return 0
        visiting.add(nid)
        val = 1 + max(r(s) for s in incoming[nid])
        visiting.discard(nid)
        rank[nid] = val
        return val

    for n in nodes:
        rank[n["id"]] = r(n["id"])
    return rank


def _positions(nodes, edges):
    rank = _ranks(nodes, edges)
    cols = {}
    for n in nodes:
        cols.setdefault(rank[n["id"]], []).append(n)
    tallest = max((len(v) for v in cols.values()), default=1)
    pos = {}
    for col, items in sorted(cols.items()):
        items = sorted(items, key=lambda n: (n.get("title") or "", n["id"]))
        offset = (tallest - len(items)) / 2.0
        for row, n in enumerate(items):
            pos[n["id"]] = (PAD + col * COL_PITCH,
                            PAD + int((row + offset) * ROW_PITCH))
    return pos


def _normalize(positions: dict, ids: set) -> dict:
    """Map scene (Excalidraw) coords → HTML canvas coords: shift to origin + pad,
    keeping the user's relative arrangement. Only nodes present in `ids`."""
    pts = {k: v for k, v in positions.items() if k in ids}
    if not pts:
        return {}
    minx = min(p["x"] for p in pts.values())
    miny = min(p["y"] for p in pts.values())
    return {k: (int(p["x"] - minx) + PAD, int(p["y"] - miny) + PAD)
            for k, p in pts.items()}


def _e(s) -> str:
    return _html.escape("" if s is None else str(s))


_CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#F4EFE4;--card:#FBF7EC;--ink:#1A1A1A;--mute:#7A7264;--line:#D9D1BC;
  --accent:#7A2828;--accent2:#1E5A6B;--edge:#B4A98F;
  --serif:'Fraunces',Georgia,'Times New Roman',serif;
  --body:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono','SF Mono',Menlo,'Cascadia Code',monospace;
}
body{background:var(--bg);color:var(--ink);font-family:var(--body);
  -webkit-font-smoothing:antialiased;overflow-x:auto;}
.head{padding:34px 40px 8px;}
.head .eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--accent);margin-bottom:8px;}
.head h1{font-family:var(--serif);font-weight:600;font-size:34px;color:var(--ink);
  letter-spacing:-.01em;line-height:1.1;}
.head .sub{font-family:var(--mono);font-size:12px;color:var(--mute);margin-top:8px;
  letter-spacing:.03em;}
.head .hint{font-family:var(--mono);font-size:11px;color:var(--accent2);margin-top:10px;}
#stage{position:relative;padding:16px 40px 60px;}
#canvas{position:relative;}
#edges{position:absolute;inset:0;overflow:visible;pointer-events:none;}
.elabel{fill:var(--mute);font-family:var(--mono);font-size:10.5px;letter-spacing:.02em;}
.node{position:absolute;width:280px;min-height:96px;background:var(--card);
  border:1px solid var(--line);border-radius:12px;overflow:hidden;cursor:pointer;
  box-shadow:0 1px 2px rgba(60,50,30,.05);transition:box-shadow .14s,transform .14s,border-color .14s;}
.node:hover{box-shadow:0 8px 22px rgba(60,50,30,.14);transform:translateY(-1px);}
.node.sel{border-color:var(--ink);box-shadow:0 10px 26px rgba(60,50,30,.20);}
.node .bar{position:absolute;left:0;top:0;bottom:0;width:8px;}
.node .in{padding:14px 16px 14px 22px;}
.node .r1{display:flex;align-items:baseline;gap:10px;}
.node .num{font-family:var(--mono);font-size:12px;color:var(--mute);}
.node .ttl{font-size:16px;font-weight:600;color:var(--ink);line-height:1.25;flex:1;}
.node .verb{font-family:var(--mono);font-size:10px;letter-spacing:.08em;
  text-transform:uppercase;padding:2px 7px;border-radius:999px;white-space:nowrap;}
.node .sum{font-family:var(--body);font-size:12.5px;color:var(--mute);margin-top:7px;
  line-height:1.45;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.legend{display:flex;gap:20px;flex-wrap:wrap;align-items:center;
  font-family:var(--mono);font-size:11px;color:var(--mute);padding:8px 40px 30px;}
.legend .lk{display:flex;align-items:center;gap:7px;}
.legend .sw{width:22px;height:14px;border-radius:4px;border:1px solid var(--line);}
.head{position:relative;}
.headbtns{position:absolute;top:34px;right:40px;display:flex;gap:8px;align-items:center;}
.headbtns .editbtn,.headbtns .refreshbtn{font-family:var(--mono);font-size:12px;letter-spacing:.06em;
  padding:8px 16px;border-radius:8px;cursor:pointer;text-decoration:none;line-height:1.2;}
.headbtns .editbtn{color:#fff;background:var(--accent);border:1px solid var(--accent);
  box-shadow:0 2px 8px rgba(122,40,40,.22);}
.headbtns .editbtn:hover{background:#66201f;}
.headbtns .refreshbtn{color:var(--accent);background:var(--card);border:1px solid var(--line);}
.headbtns .refreshbtn:hover{border-color:var(--accent);}
.prov{padding:4px 40px 34px;font-family:var(--mono);font-size:10px;letter-spacing:.05em;color:var(--mute);}
.prov .provnote{margin-left:12px;color:var(--accent);letter-spacing:.12em;text-transform:uppercase;font-size:9px;}
/* Inspector */
#scrim{position:fixed;inset:0;background:rgba(26,22,16,.28);opacity:0;
  pointer-events:none;transition:opacity .2s;z-index:9;}
#scrim.on{opacity:1;pointer-events:auto;}
#insp{position:fixed;top:0;right:0;height:100vh;width:min(460px,92vw);z-index:10;
  background:var(--bg);border-left:1px solid var(--line);box-shadow:-14px 0 40px rgba(60,50,30,.16);
  transform:translateX(100%);transition:transform .24s cubic-bezier(.4,0,.2,1);
  display:flex;flex-direction:column;}
#insp.on{transform:translateX(0);}
#insp .ihead{padding:26px 28px 18px;border-bottom:1px solid var(--line);}
#insp .ieyebrow{display:flex;align-items:center;gap:10px;font-family:var(--mono);
  font-size:11px;color:var(--mute);margin-bottom:10px;}
#insp h2{font-family:var(--serif);font-weight:600;font-size:23px;line-height:1.18;color:var(--ink);}
#insp .chips{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;}
#insp .chip{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  padding:3px 9px;border-radius:999px;border:1px solid var(--line);}
#insp .ibody{padding:18px 28px 40px;overflow-y:auto;}
#insp .sec{margin-top:22px;}
#insp .sec:first-child{margin-top:4px;}
#insp .sl{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--mute);margin-bottom:9px;}
#insp .purpose{font-size:14.5px;line-height:1.55;color:var(--ink);}
#insp .row{display:flex;gap:10px;align-items:baseline;padding:7px 0;border-bottom:1px dashed var(--line);}
#insp .row:last-child{border-bottom:none;}
#insp .path{font-family:var(--mono);font-size:12px;color:var(--accent2);word-break:break-all;flex:1;}
#insp .chg{font-family:var(--mono);font-size:10px;color:var(--accent);white-space:nowrap;}
#insp .sym{font-family:var(--mono);font-size:12px;color:var(--ink);}
#insp .snote{color:var(--mute);font-size:12px;}
#insp .test{font-family:var(--mono);font-size:12px;color:var(--mute);padding:4px 0 4px 16px;position:relative;}
#insp .test:before{content:'✓';position:absolute;left:0;color:#2F6B4F;}
#insp .note{font-size:13px;color:var(--mute);line-height:1.55;font-style:italic;}
#insp .close{position:absolute;top:20px;right:22px;width:30px;height:30px;border:1px solid var(--line);
  background:var(--card);border-radius:8px;font-size:15px;color:var(--mute);cursor:pointer;line-height:1;}
#insp .close:hover{color:var(--ink);border-color:var(--ink);}
#insp .empty{color:var(--mute);font-size:12px;font-style:italic;}
@media print{#scrim,#insp{display:none;}}
"""

_JS = """
(function(){
  var D=window.CMAP.details||{};
  var insp=document.getElementById('insp'),scrim=document.getElementById('scrim');
  var body=document.getElementById('ibody'),head=document.getElementById('ihead');
  function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function sec(label,inner){return inner?('<div class="sec"><div class="sl">'+label+'</div>'+inner+'</div>'):'';}
  function open(id){
    var d=D[id];if(!d)return;
    document.querySelectorAll('.node').forEach(function(n){n.classList.toggle('sel',n.dataset.id===id);});
    var accent=d.accent||'#7A2828';
    head.innerHTML='<button class="close" id="iclose" aria-label="close">\\u2715</button>'+
      '<div class="ieyebrow"><span>'+esc(d.num)+'</span><span>change</span></div>'+
      '<h2>'+esc(d.title)+'</h2>'+
      '<div class="chips">'+
        '<span class="chip" style="color:'+accent+';border-color:'+accent+'">'+esc(d.kind)+'</span>'+
        (d.verb?'<span class="chip" style="color:'+accent+'">'+esc(d.verb)+'</span>':'')+
      '</div>';
    var files=(d.files||[]).map(function(f){return '<div class="row"><span class="path">'+esc(f.path)+'</span><span class="chg">'+esc(f.change)+'</span></div>';}).join('');
    var fns=(d.functions||[]).map(function(f){return '<div class="row"><span class="sym">'+esc(f.symbol)+'</span><span class="snote">'+esc(f.note||'')+'</span></div>';}).join('');
    var tests=(d.tests||[]).map(function(t){return '<div class="test">'+esc(t)+'</div>';}).join('');
    body.innerHTML=
      sec('Purpose', d.summary?'<div class="purpose">'+esc(d.summary)+'</div>':'')+
      sec('Files touched', files||'<div class="empty">\\u2014</div>')+
      sec('Functions / symbols', fns)+
      sec('Tests', tests)+
      sec('Note', d.note?'<div class="note">'+esc(d.note)+'</div>':'');
    insp.classList.add('on');scrim.classList.add('on');
    document.getElementById('iclose').onclick=close;
  }
  function close(){insp.classList.remove('on');scrim.classList.remove('on');
    document.querySelectorAll('.node.sel').forEach(function(n){n.classList.remove('sel');});}
  document.querySelectorAll('.node').forEach(function(n){n.onclick=function(){open(n.dataset.id);};});
  scrim.onclick=close;
  document.addEventListener('keydown',function(e){if(e.key==='Escape')close();});
})();
"""


def _edges_svg(nodes, edges, pos, w, h) -> str:
    parts = [f'<svg id="edges" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<defs><marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3" '
             'orient="auto" markerUnits="userSpaceOnUse">'
             '<path d="M0,0 L7,3 L0,6 Z" fill="#9A8F7A"/></marker></defs>']
    ids = {n["id"] for n in nodes}
    for e in edges:
        s, t = e.get("from"), e.get("to")
        if s not in ids or t not in ids or s not in pos or t not in pos:
            continue
        sx, sy = pos[s]
        tx, ty = pos[t]
        forward = tx >= sx
        x1 = sx + (NODE_W if forward else 0)
        y1 = sy + NODE_H / 2
        x2 = tx + (0 if forward else NODE_W)
        y2 = ty + NODE_H / 2
        dx = max(40, abs(x2 - x1) * 0.45)
        c1x = x1 + (dx if forward else -dx)
        c2x = x2 - (dx if forward else -dx)
        parts.append(
            f'<path d="M {x1:.0f} {y1:.0f} C {c1x:.0f} {y1:.0f} {c2x:.0f} {y2:.0f} '
            f'{x2:.0f} {y2:.0f}" fill="none" stroke="#B4A98F" stroke-width="1.6" '
            f'marker-end="url(#ah)"/>')
        rel = (e.get("rel") or "").strip()
        if rel:
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2 - 8
            parts.append(f'<rect x="{mx - len(rel) * 3.2 - 5:.0f}" y="{my - 11:.0f}" '
                         f'width="{len(rel) * 6.4 + 10:.0f}" height="16" rx="4" fill="#F4EFE4"/>')
            parts.append(f'<text class="elabel" x="{mx:.0f}" y="{my:.0f}" '
                         f'text-anchor="middle">{_e(rel)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _node_html(node, num, x, y) -> str:
    kind = node.get("kind", "")
    accent = color_for(kind)
    verb = (node.get("verb") or node.get("at") or "").strip()
    verb_html = (f'<span class="verb" style="color:{accent};background:{_tint(kind)}">'
                 f'{_e(verb)}</span>') if verb else ""
    return (
        f'<div class="node" data-id="{_e(node["id"])}" '
        f'style="left:{x}px;top:{y}px">'
        f'<span class="bar" style="background:{accent}"></span>'
        f'<div class="in"><div class="r1">'
        f'<span class="num">{num}</span>'
        f'<span class="ttl">{_e(node.get("title") or node.get("id"))}</span>'
        f'{verb_html}</div>'
        f'<div class="sum">{_e(node.get("summary") or node.get("note") or "")}</div>'
        f'</div></div>')


def render_html(meta: dict, nodes: list[dict], edges: list[dict] | None = None,
                positions: dict | None = None) -> str:
    """Render the interactive change-map to one self-contained HTML string.

    ``positions`` (scene/Excalidraw coords per node id) — when supplied, e.g. by
    the draw→save pipeline — is normalized and used verbatim so the HTML mirrors
    the user's canvas arrangement; otherwise a left→right flow is computed."""
    edges = edges or []
    meta = meta or {}
    ids = {n["id"] for n in nodes}
    pos = _normalize(positions, ids) if positions else {}
    # Any node missing a supplied position falls back to the computed flow.
    if len(pos) < len(nodes):
        pos = {**_positions(nodes, edges), **pos}
    w = max((x for x, _ in pos.values()), default=0) + NODE_W + PAD
    h = max((y for _, y in pos.values()), default=0) + NODE_H + PAD
    # Number in reading order (column, then row).
    order = sorted(nodes, key=lambda n: (pos[n["id"]][0], pos[n["id"]][1]))
    nums = {n["id"]: f"{i + 1:02d}" for i, n in enumerate(order)}

    nodes_html = "".join(_node_html(n, nums[n["id"]], *pos[n["id"]]) for n in nodes)
    edges_svg = _edges_svg(nodes, edges, pos, w, h)

    kinds_seen = []
    for n in nodes:
        k = n.get("kind", "")
        if k and k not in kinds_seen:
            kinds_seen.append(k)
    legend = "".join(
        f'<span class="lk"><span class="sw" style="background:{_tint(k)};'
        f'border-color:{color_for(k)}"></span>{_e(k)}</span>' for k in kinds_seen)

    # Deep-dive payload, one entry per node (escaped at render time in JS).
    details = {}
    for n in nodes:
        details[n["id"]] = {
            "num": nums[n["id"]], "title": n.get("title") or n["id"],
            "kind": n.get("kind", ""), "accent": color_for(n.get("kind", "")),
            "verb": n.get("verb") or n.get("at") or "",
            "summary": n.get("summary") or "",
            "files": n.get("files") or [], "functions": n.get("functions") or [],
            "tests": n.get("tests") or [], "note": n.get("note") or "",
        }
    data = _json.dumps({"details": details}).replace("</", "<\\/")

    title = _e(meta.get("title") or "Change-log")
    subtitle = _e(meta.get("subtitle") or "")
    slug = _e(meta.get("slug") or "")

    # Provenance front matter (an HTML comment so it never renders) — Hub reads
    # these fields off the file to show the "written by …" line + "ask again".
    prov = ""
    if meta.get("generated_by"):
        prov = ("<!--\n---\n"
                f'generated_by: "{meta.get("generated_by")}"\n'
                f'commit_range: "{meta.get("commit_range", "")}"\n'
                f'written_at: {meta.get("written_at", "")}\n'
                f'task: {meta.get("slug", "")}\n'
                "---\n-->\n")

    # Visible provenance footer (this page opts out of Hub's injected chrome via
    # the hub:standalone marker, so it carries its own "written by …" line).
    prov_foot = ""
    if meta.get("generated_by"):
        bits = [_e(meta.get("generated_by"))]
        if meta.get("written_at"):
            bits.append(_e(meta.get("written_at")))
        if meta.get("commit_range"):
            bits.append(_e(meta.get("commit_range")))
        prov_foot = ('<div class="prov">written by ' + " · ".join(bits) +
                     '<span class="provnote">Hub did not generate this file.</span></div>')

    # View-first: this page is the default surface; the Edit button jumps to the
    # editable Excalidraw canvas. A Refresh button reloads the map to pull the
    # latest render after a canvas edit. (Canvas → back here via its pill.)
    edit_link = ""
    if meta.get("edit_href"):
        edit_link = (
            '<div class="headbtns">'
            '<button class="refreshbtn" type="button" onclick="location.reload()" '
            'title="Reload to show the latest render">↻ Refresh</button>'
            f'<a class="editbtn" href="{_e(meta["edit_href"])}" '
            'title="Edit this change-map in the draw canvas">✎ Edit</a>'
            '</div>')

    return (
        prov +
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        '<meta name="hub:standalone" content="1">'
        f"<title>{title}</title><style>{_CSS}</style></head><body>"
        f'<div class="head">{edit_link}<div class="eyebrow">change-log · {slug}</div>'
        f'<h1>{title}</h1>'
        + (f'<div class="sub">{subtitle}</div>' if subtitle else "")
        + '<div class="hint">click any change to deep-dive its files, functions & tests →</div>'
        + '</div>'
        f'<div id="stage"><div id="canvas" style="width:{w}px;height:{h}px">'
        f'{edges_svg}{nodes_html}</div></div>'
        f'<div class="legend"><span>KINDS</span>{legend}</div>'
        + prov_foot +
        '<div id="scrim"></div>'
        '<aside id="insp" aria-label="change detail"><div class="ihead" id="ihead"></div>'
        '<div class="ibody" id="ibody"></div></aside>'
        f'<script>window.CMAP={data};</script><script>{_JS}</script>'
        "</body></html>")
