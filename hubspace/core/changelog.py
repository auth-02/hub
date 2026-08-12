"""Polished Excalidraw scene for the change-log skill's diagram (S32).

Where :mod:`hubspace.core.graph` renders the *timeline* lineage as plain kind
columns, this renders a **change map** to look designed: numbered cards with a
left colour-accent bar, a bold title + mono sub-line, a change-verb badge, and
labelled dependency arrows on a dot-grid paper ground — the look of a workflow
canvas (HQFlow-style), not a wireframe.

Still deterministic and model-free: the agent hands it the change-graph
(nodes + edges) it reasoned out; this only lays it out and emits a valid
Excalidraw scene. Layout is a left→right dependency flow (a node is placed to
the right of everything that depends on it), so arrows read forward. The same
graph always yields the same scene, so it is unit-testable without a browser.

Node:  {id, kind, path (title), at (verb), note (sub-line)}
Edge:  {from, to, rel?}   # rel = a short relationship word drawn on the arrow
"""
from __future__ import annotations

import textwrap

from .graph import PAPER_BG, _stable_seed, color_for

# Palette — accent per kind reuses graph.color_for (hub.css badges); the light
# tint is the card wash behind it, and ink/mute/line are the neutral text/edges.
INK = "#1A1A1A"
MUTE = "#6A6357"
LINE = "#CFC6AE"
EDGE = "#9A8F7A"
CARD_BG = "#FBF7EC"          # near-paper card, a touch lighter than the ground
KIND_TINT = {
    "task": "#F1DEDA", "doc": "#D8E6EA", "artifact": "#E6E0F0",
    "run": "#DBE8E0", "data": "#D6E8EB", "draw": "#F1E4D0",
    "note": "#F3E1D4", "prompt": "#F0E7CC", "script": "#E0E7EC",
}
_TINT_DEFAULT = "#ECE5D2"


def _tint(kind: str) -> str:
    return KIND_TINT.get(kind or "", _TINT_DEFAULT)


# Geometry (px).
CARD_W = 312
CARD_H = 92        # legacy default (a card's height is computed per node now)
ACCENT_W = 8
COL_PITCH = 400
ROW_PITCH = 200    # generous so a 3-line title + 3-line summary never overlaps
X0 = 72
Y0 = 210           # cards start below the pill + title + subtitle header
PAD_L = 24         # card text inset (past the accent bar)
PAD_R = 16
TITLE_WRAP = 34    # chars/line for the title (body font)
SUM_WRAP = 42      # chars/line for the summary (mono)


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    """Wrap `text` to `width` chars, capped at `max_lines` (… on overflow)."""
    text = " ".join((text or "").split())
    if not text:
        return []
    lines = textwrap.wrap(text, width=width) or [text]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip()[: width - 1] + "…"
    return lines


def _card_height(title: str, summary: str) -> int:
    tl = max(1, len(_wrap(title, TITLE_WRAP, 3)))
    sl = len(_wrap(summary, SUM_WRAP, 3))
    return 14 + 22 + tl * 20 + (6 + sl * 17 if sl else 0) + 14


# ── layout: left→right dependency flow ───────────────────────────────────────
def _ranks(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    """Column index per node: 0 when nothing points to it, else one past the
    deepest thing that does. Edge ``from→to`` means *from depends on to*, so a
    dependency lands to the right of its dependents and arrows read forward.
    Cycle-safe (a back-edge just doesn't deepen the rank)."""
    ids = {n["id"] for n in nodes}
    incoming: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("from") in ids and e.get("to") in ids:
            incoming[e["to"]].append(e["from"])

    rank: dict[str, int] = {}
    visiting: set[str] = set()

    def r(nid: str) -> int:
        if nid in rank:
            return rank[nid]
        if nid in visiting or not incoming[nid]:
            return 0
        visiting.add(nid)
        val = 1 + max(r(src) for src in incoming[nid])
        visiting.discard(nid)
        rank[nid] = val
        return val

    for n in nodes:
        rank[n["id"]] = r(n["id"])
    return rank


def _positions(nodes: list[dict], edges: list[dict]) -> dict[str, dict]:
    rank = _ranks(nodes, edges)
    cols: dict[int, list[dict]] = {}
    for n in nodes:
        cols.setdefault(rank[n["id"]], []).append(n)
    # Tallest column sets the vertical centre so shorter columns sit centred.
    tallest = max((len(v) for v in cols.values()), default=1)
    pos: dict[str, dict] = {}
    for col, items in sorted(cols.items()):
        items = sorted(items, key=lambda n: (n.get("path") or "", n["id"]))
        offset = (tallest - len(items)) / 2.0
        for row, n in enumerate(items):
            pos[n["id"]] = {"x": X0 + col * COL_PITCH,
                            "y": Y0 + int((row + offset) * ROW_PITCH)}
    return pos


# ── element factories (fields mirror graph.py, which loads cleanly) ──────────
def _base(eid: str, typ: str, x: float, y: float, w: float, h: float,
          stroke: str, **extra) -> dict:
    seed = _stable_seed(eid)
    el = {
        "id": eid, "type": typ, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": stroke, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": None, "seed": seed, "version": 1, "versionNonce": seed,
        "isDeleted": False, "boundElements": None, "updated": 1, "link": None,
        "locked": False,
    }
    el.update(extra)
    return el


def _text(eid: str, x: float, y: float, txt: str, size: int, color: str,
          *, mono: bool = False, align: str = "left", w: float | None = None,
          group: str | None = None) -> dict:
    fam = 3 if mono else 2
    width = w if w is not None else max(10.0, len(txt) * size * 0.6)
    el = _base(eid, "text", x, y, width, size * 1.25, color)
    el.update({
        "fillStyle": "solid", "text": txt, "fontSize": size, "fontFamily": fam,
        "textAlign": align, "verticalAlign": "top", "containerId": None,
        "originalText": txt, "lineHeight": 1.25, "baseline": int(size * 0.8),
    })
    if group:
        el["groupIds"] = [group]
    return el


def _card_elements(node: dict, n_label: str, x: float, y: float,
                   card_h: float) -> list[dict]:
    """One numbered card: accent bar; a top row of number (left) + verb badge
    (top-right); then the wrapped title and wrapped summary, each contained in
    the box. Grouped so it drags as a unit. The card body carries the FULL node
    (incl. deep-dive detail) in `customData.cl` so a saved scene rebuilds the
    interactive HTML."""
    kind = node.get("kind", "")
    accent = color_for(kind)
    gid = "g-" + node["id"]
    title = (node.get("title") or node.get("path") or node.get("id") or "").strip()
    verb = (node.get("verb") or node.get("at") or "").strip()
    note = (node.get("summary") or node.get("note") or "").strip()

    els: list[dict] = []
    body = _base("card-" + node["id"], "rectangle", x, y, CARD_W, card_h, LINE,
                 backgroundColor=_tint(kind), fillStyle="solid", strokeWidth=1,
                 roundness={"type": 3}, groupIds=[gid])
    body["customData"] = {"cl": {"role": "node", "node": node}}
    els.append(body)
    # Left colour-accent bar.
    bar = _base("bar-" + node["id"], "rectangle", x, y, ACCENT_W, card_h, accent,
                backgroundColor=accent, fillStyle="solid", strokeWidth=1,
                roundness={"type": 3}, groupIds=[gid])
    els.append(bar)
    # Top row: number (left) + verb badge pinned to the top-RIGHT corner.
    els.append(_text("num-" + node["id"], x + PAD_L, y + 15, n_label, 13, MUTE,
                     mono=True, group=gid))
    if verb:
        bw = len(verb) * 8 + 4
        els.append(_text("vrb-" + node["id"], x + CARD_W - PAD_R - bw, y + 15,
                         verb.lower(), 12, accent, mono=True, align="right",
                         w=bw, group=gid))
    # Title (wrapped inside the box), tagged so an edit can be read back on save.
    t_lines = _wrap(title, TITLE_WRAP, 3)
    ttl = _text("ttl-" + node["id"], x + PAD_L, y + 40, "\n".join(t_lines), 15,
                INK, w=CARD_W - PAD_L - PAD_R, group=gid)
    ttl["customData"] = {"cl": {"role": "title", "id": node["id"], "orig": title}}
    els.append(ttl)
    # Summary (wrapped inside the box) under the title.
    if note:
        sy = y + 40 + len(t_lines) * 20 + 6
        els.append(_text("nte-" + node["id"], x + PAD_L, sy,
                         "\n".join(_wrap(note, SUM_WRAP, 3)), 12, MUTE,
                         mono=True, w=CARD_W - PAD_L - PAD_R, group=gid))
    return els


def _edge_elements(edge: dict, i: int, pos: dict[str, dict],
                   heights: dict[str, float] | None = None) -> list[dict]:
    src, dst = edge.get("from"), edge.get("to")
    if src not in pos or dst not in pos:
        return []
    heights = heights or {}
    a, b = pos[src], pos[dst]
    # Anchor on the facing edges of the two cards (vertical centre of each card).
    forward = b["x"] >= a["x"]
    sx = a["x"] + (CARD_W if forward else 0)
    ex = b["x"] + (0 if forward else CARD_W)
    sy = a["y"] + heights.get(src, CARD_H) / 2
    ey = b["y"] + heights.get(dst, CARD_H) / 2
    aid = f"edge-{src}-{dst}-{i}"
    arrow = _base(aid, "arrow", sx, sy, abs(ex - sx), abs(ey - sy), EDGE,
                  strokeWidth=1, roundness={"type": 2})
    arrow.update({
        "points": [[0, 0], [(ex - sx) * 0.5, (ey - sy) * 0.5 - 18],
                   [ex - sx, ey - sy]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": "card-" + src, "focus": 0.1, "gap": 6},
        "endBinding": {"elementId": "card-" + dst, "focus": 0.1, "gap": 6},
        "startArrowhead": None, "endArrowhead": "triangle",
    })
    arrow["customData"] = {"cl": {"role": "edge", "from": src, "to": dst,
                                  "rel": edge.get("rel") or ""}}
    els = [arrow]
    rel = (edge.get("rel") or "").strip()
    if rel:
        # Sit the label beside the line (just above its midpoint), centred, with
        # a width wide enough that it never wraps and never lands on a node.
        w = len(rel) * 8 + 12
        mx = (sx + ex) / 2
        my = (sy + ey) / 2 - 20
        els.append(_text(aid + "-lbl", mx - w / 2, my, rel, 11, MUTE,
                         mono=True, align="center", w=w))
    return els


def _change_log_name(title: str, meta: dict | None) -> str:
    """The '<name>' for the 'change-log: <name>' header — an explicit meta.name,
    else the title with a leading 'Change-log —/:' stripped."""
    if meta and meta.get("name"):
        return str(meta["name"]).strip()
    t = (title or "").strip()
    for pre in ("Change-log — ", "Change-log: ", "change-log — ", "change-log: "):
        if t.startswith(pre):
            return t[len(pre):].strip()
    return t


def _header_block(title: str, subtitle: str, meta: dict | None,
                  interactive_href: str | None) -> list[dict]:
    """Header, top-down: the interactive-version pill (if any), then the
    'change-log: <name>' title, then the subtitle."""
    els: list[dict] = []
    y = 40
    if interactive_href:
        # ONE link: the pill rectangle carries it; the label text does not (so
        # Excalidraw shows a single link glyph, not two).
        gid = "g-cl-link"
        els.append(_base("cl-link", "rectangle", X0, y, 236, 34, color_for("task"),
                         backgroundColor=_tint("task"), fillStyle="solid",
                         strokeWidth=1, roundness={"type": 3}, groupIds=[gid],
                         link=interactive_href))
        els.append(_text("cl-link-tx", X0 + 16, y + 9, "▶  interactive version",
                         13, color_for("task"), mono=True, group=gid))
        y += 52
    name = _change_log_name(title, meta)
    t = _text("hdr-title", X0, y, f"change-log: {name}", 28, INK)
    # Stash the change-map meta (title/subtitle/provenance) so a saved scene
    # rebuilds with the same header + provenance in the interactive HTML.
    m = dict(meta or {})
    m.setdefault("title", title)
    m.setdefault("subtitle", subtitle)
    t["customData"] = {"cl": {"role": "meta", "meta": m}}
    els.append(t)
    if subtitle:
        els.append(_text("hdr-sub", X0, y + 42, subtitle, 14, MUTE, mono=True))
    return els


def _legend(nodes: list[dict], y: float) -> list[dict]:
    """A colour→kind key, only for the kinds actually present."""
    seen: list[str] = []
    for n in nodes:
        k = n.get("kind", "")
        if k and k not in seen:
            seen.append(k)
    els: list[dict] = []
    x = X0
    els.append(_text("lgd-label", x, y - 2, "KINDS", 11, MUTE, mono=True))
    x += 62
    for k in seen:
        els.append(_base(f"lgd-sw-{k}", "rectangle", x, y - 3, 26, 16,
                         color_for(k), backgroundColor=_tint(k),
                         fillStyle="solid", strokeWidth=1,
                         roundness={"type": 3}))
        els.append(_text(f"lgd-tx-{k}", x + 33, y, k, 12, MUTE, mono=True))
        x += 33 + len(k) * 8 + 26
    return els


def to_scene(nodes: list[dict], edges: list[dict] | None = None,
             title: str = "", subtitle: str = "",
             source: str = "hub-change-log", meta: dict | None = None,
             interactive_href: str | None = None) -> dict:
    """Build the polished change-log Excalidraw scene (see module docstring).

    `meta` (title/subtitle/provenance) rides in the header element's customData
    and `interactive_href` adds a clickable pill linking to the rendered HTML, so
    the saved draw is a complete, self-describing source for the interactive map.
    """
    edges = edges or []
    pos = _positions(nodes, edges)
    heights = {n["id"]: _card_height(
        n.get("title") or n.get("path") or n.get("id") or "",
        n.get("summary") or n.get("note") or "") for n in nodes}
    elements: list[dict] = []
    elements += _header_block(title, subtitle, meta, interactive_href)
    # Edges first so cards paint over the arrow tails.
    for i, e in enumerate(edges):
        elements += _edge_elements(e, i, pos, heights)
    # Number cards in reading order (column, then row).
    order = sorted(nodes, key=lambda n: (pos[n["id"]]["x"], pos[n["id"]]["y"]))
    numbers = {n["id"]: f"{i + 1:02d}" for i, n in enumerate(order)}
    for n in nodes:
        p = pos[n["id"]]
        elements += _card_elements(n, numbers[n["id"]], p["x"], p["y"],
                                   heights[n["id"]])
    # Legend under the lowest card (its own height respected).
    if nodes:
        low = max(pos[n["id"]]["y"] + heights[n["id"]] for n in nodes) + 56
        elements += _legend(nodes, low)
    return {
        "type": "excalidraw", "version": 2, "source": source,
        "elements": elements,
        # No grid — a clean paper ground (the checks read as busy on a change map).
        "appState": {"gridSize": None, "viewBackgroundColor": PAPER_BG},
        "files": {},
    }


def scene_to_graph(scene: dict) -> dict:
    """Rebuild the change-graph from a (possibly hand-edited) change-log scene.

    Reads the model back out of element `customData.cl` — the inverse of
    :func:`to_scene`. Node cards carry the full node (incl. deep-dive detail) and
    their current x/y (so the reader reflects the user's arrangement); an edited
    title text element overrides the node's title (label edits win); edges and
    header meta come from their tagged elements. Elements without a `cl` tag are
    ignored, so free-hand annotations on the canvas do no harm. Returns
    ``{meta, nodes, edges, positions}`` ready for :func:`changemap.render_html`.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    meta: dict = {}
    positions: dict[str, dict] = {}
    tagged: dict[str, str] = {}      # node id → title-element text (unwrapped)
    tag_orig: dict[str, str] = {}    # node id → the title we AUTHORED (to detect edits)
    bound: dict[str, str] = {}       # node id → bound text on the card rect
    card_box: dict[str, tuple] = {}  # node id → (x, y, w, h) of the card rect
    texts: list[dict] = []           # all live text elements (for positional fallback)

    def _unwrap(el):
        # Collapse our soft-wrap newlines back to one line for comparison/title.
        return " ".join((el.get("text") or "").split())

    for el in scene.get("elements", []):
        if el.get("isDeleted"):
            continue
        if el.get("type") == "text":
            texts.append(el)
            # A user double-clicking a card makes Excalidraw bind a NEW text to the
            # rect (containerId == "card-<id>") — that is the edited title.
            cid = el.get("containerId")
            if isinstance(cid, str) and cid.startswith("card-"):
                t = _unwrap(el)
                if t:
                    bound[cid[len("card-"):]] = t
        cl = (el.get("customData") or {}).get("cl")
        if not isinstance(cl, dict):
            continue
        role = cl.get("role")
        if role == "node" and isinstance(cl.get("node"), dict):
            n = dict(cl["node"])
            nid = n.get("id")
            if not nid:
                continue
            nodes.append(n)
            positions[nid] = {"x": el.get("x", 0), "y": el.get("y", 0)}
            card_box[nid] = (el.get("x", 0), el.get("y", 0),
                             el.get("width", 0), el.get("height", 0))
        elif role == "edge":
            edges.append({"from": cl.get("from"), "to": cl.get("to"),
                          "rel": cl.get("rel") or ""})
        elif role == "meta" and isinstance(cl.get("meta"), dict):
            meta = dict(cl["meta"])
        elif role == "title" and cl.get("id"):
            tagged[cl["id"]] = _unwrap(el)
            tag_orig[cl["id"]] = " ".join((cl.get("orig") or "").split())

    def _positional_title(nid):
        # Fallback: the largest-font text whose centre sits inside the card box —
        # recovers an edited title even if Excalidraw dropped our customData tag.
        box = card_box.get(nid)
        if not box:
            return None
        x, y, w, h = box
        best, best_sz = None, -1.0
        for el in texts:
            if el.get("customData", {}).get("cl", {}).get("role") == "meta":
                continue
            cx = el.get("x", 0) + el.get("width", 0) / 2
            cy = el.get("y", 0) + el.get("height", 0) / 2
            if x <= cx <= x + w and y <= cy <= y + h:
                sz = el.get("fontSize", 0)
                if sz > best_sz:
                    best, best_sz = _unwrap(el), sz
        return best

    # Recover each node's CURRENT title. Our own soft-wrapping is NOT an edit —
    # the tagged title only overrides when its text differs from what we authored
    # (`orig`). Precedence: a new bound text > an edited tagged title > positional.
    for n in nodes:
        nid = n.get("id")
        authored = " ".join((n.get("title") or "").split())
        edited = None
        if nid in bound and bound[nid] != authored:
            edited = bound[nid]
        elif nid in tagged and tagged[nid] and tagged[nid] != tag_orig.get(nid, authored):
            edited = tagged[nid]
        elif nid not in tagged:  # tag dropped entirely → best-effort positional
            pos_t = _positional_title(nid)
            if pos_t and pos_t != authored:
                edited = pos_t
        if edited:
            n["title"] = edited
    return {"meta": meta, "nodes": nodes, "edges": edges, "positions": positions}
