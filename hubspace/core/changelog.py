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
CARD_H = 92
ACCENT_W = 8
COL_PITCH = 400
ROW_PITCH = 148
X0 = 72
Y0 = 150            # cards start below the title header


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


def _card_elements(node: dict, n_label: str, x: float, y: float) -> list[dict]:
    """One numbered card: accent bar + number + bold title + verb badge + note,
    grouped so it drags as a unit even though the texts are unbound."""
    kind = node.get("kind", "")
    accent = color_for(kind)
    gid = "g-" + node["id"]
    title = (node.get("path") or node.get("id") or "").strip()
    verb = (node.get("at") or "").strip()
    note = (node.get("note") or "").strip()

    els: list[dict] = []
    # Card body (rounded, tinted wash, thin line border).
    body = _base("card-" + node["id"], "rectangle", x, y, CARD_W, CARD_H, LINE,
                 backgroundColor=_tint(kind), fillStyle="solid", strokeWidth=1,
                 roundness={"type": 3}, groupIds=[gid])
    els.append(body)
    # Left colour-accent bar (the signature look).
    bar = _base("bar-" + node["id"], "rectangle", x, y, ACCENT_W, CARD_H, accent,
                backgroundColor=accent, fillStyle="solid", strokeWidth=1,
                roundness={"type": 3}, groupIds=[gid])
    els.append(bar)
    # Row 1: number chip + bold title (title spans the full width — the verb
    # badge sits on row 2 so a long title never collides with it).
    els.append(_text("num-" + node["id"], x + 24, y + 18, n_label, 13, MUTE,
                     mono=True, group=gid))
    els.append(_text("ttl-" + node["id"], x + 58, y + 16, title, 16, INK,
                     w=CARD_W - 76, group=gid))
    # Row 2: mono note (left) + verb badge (right), which cannot overlap.
    if note:
        els.append(_text("nte-" + node["id"], x + 24, y + 54, note, 13, MUTE,
                         mono=True, w=CARD_W - 130, group=gid))
    if verb:
        els.append(_text("vrb-" + node["id"], x + CARD_W - 100, y + 54, verb,
                         12, accent, mono=True, align="right", w=84, group=gid))
    return els


def _edge_elements(edge: dict, i: int, pos: dict[str, dict]) -> list[dict]:
    src, dst = edge.get("from"), edge.get("to")
    if src not in pos or dst not in pos:
        return []
    a, b = pos[src], pos[dst]
    # Anchor on the facing edges of the two cards.
    forward = b["x"] >= a["x"]
    sx = a["x"] + (CARD_W if forward else 0)
    ex = b["x"] + (0 if forward else CARD_W)
    sy = a["y"] + CARD_H / 2
    ey = b["y"] + CARD_H / 2
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
    els = [arrow]
    rel = (edge.get("rel") or "").strip()
    if rel:
        mx = min(sx, ex) + abs(ex - sx) / 2
        my = (sy + ey) / 2 - 30
        els.append(_text(aid + "-lbl", mx - len(rel) * 3, my, rel, 11, MUTE,
                         mono=True))
    return els


def _title_block(title: str, subtitle: str) -> list[dict]:
    els: list[dict] = []
    if title:
        els.append(_text("hdr-title", X0, 44, title, 30, INK))
    if subtitle:
        els.append(_text("hdr-sub", X0, 90, subtitle, 14, MUTE, mono=True))
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
             source: str = "hub-change-log") -> dict:
    """Build the polished change-log Excalidraw scene (see module docstring)."""
    edges = edges or []
    pos = _positions(nodes, edges)
    elements: list[dict] = []
    elements += _title_block(title, subtitle)
    # Edges first so cards paint over the arrow tails.
    for i, e in enumerate(edges):
        elements += _edge_elements(e, i, pos)
    # Number cards in reading order (column, then row).
    order = sorted(nodes, key=lambda n: (pos[n["id"]]["x"], pos[n["id"]]["y"]))
    numbers = {n["id"]: f"{i + 1:02d}" for i, n in enumerate(order)}
    for n in nodes:
        p = pos[n["id"]]
        elements += _card_elements(n, numbers[n["id"]], p["x"], p["y"])
    # Legend under the lowest card.
    if nodes:
        low = max(p["y"] for p in pos.values()) + CARD_H + 56
        elements += _legend(nodes, low)
    return {
        "type": "excalidraw", "version": 2, "source": source,
        "elements": elements,
        # gridSize renders the dot grid (the workflow-canvas look).
        "appState": {"gridSize": 20, "viewBackgroundColor": PAPER_BG},
        "files": {},
    }
