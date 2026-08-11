"""Graph-order derivation for the 2b timeline canvas (roadmap 2b).

Pure, stdlib-only helpers that turn the 2b timeline contract
(`query.timeline` → ``{task, nodes, edges}``) into (a) deterministic canvas
coordinates in *graph order* and (b) a valid Excalidraw scene. There is no
storage and no query here — the caller supplies the already-derived nodes/edges
(the same lineage Hub already holds). Nothing here is intelligent: the graph is
a pure second *rendering* of the timeline, laid out by edge/kind/date instead of
by date alone.

These functions are the single source of truth for the "save to draws/"
conversion (server-side, reused by the canvas) and for the ``hub draw`` blank
scene. The layout is deterministic — the same nodes always land in the same
place, so a saved diagram matches what was on the canvas and the positions are
unit-testable without a browser.

See docs/HUB-LAYOUT.md (kinds, lineage rel_types) for the vocabulary.
"""
from __future__ import annotations

# Paper ground — must match hub.css --bg so a saved diagram opens on the same
# dot-grid paper the canvas uses, never a white sheet (the whole point of 2b).
PAPER_BG = "#F4EFE4"

# Kind → column (graph order): the task manifest anchors the left edge; its
# produced/owned children fan out to the right, one column per kind, in a fixed
# order so the layout is stable. Unknown kinds share the last column.
_KIND_COL = {
    "task": 0, "prompt": 1, "run": 2, "artifact": 3, "script": 4,
    "note": 5, "doc": 6, "draw": 7, "data": 8,
}
_FALLBACK_COL = 9

# Kind → accent colour, mirrored from hub.css badge colours so the derived scene
# reads in Hub's palette (oxblood task, deep-sea doc, …).
KIND_COLOR = {
    "task": "#7A2828", "doc": "#1E5A6B", "artifact": "#5C4A7A",
    "run": "#2F6B4F", "data": "#2E7D8A", "draw": "#B5651D",
    "note": "#C15F3C", "prompt": "#C99A20", "script": "#556B7D",
}
_DEFAULT_COLOR = "#8A8377"

# Canvas geometry (px). Column pitch / row pitch / origin + card size.
COL_W = 260
ROW_H = 130
X0 = 80
Y0 = 80
CARD_W = 200
CARD_H = 84
# Extra card height (and row pitch) per label line beyond the base 3
# (KIND / name / at). Only spent when a node carries a `note` — e.g. the
# change-log skill's change verb + one-line "why" — so note-less scenes (the
# timeline canvas) keep their exact geometry. One text line ≈ fontSize 14 ×
# lineHeight 1.25 plus a little breathing room.
NOTE_LINE_H = 24


def _col(kind: str) -> int:
    return _KIND_COL.get(kind or "", _FALLBACK_COL)


def color_for(kind: str) -> str:
    """Accent colour for a node kind (hub.css badge palette)."""
    return KIND_COLOR.get(kind or "", _DEFAULT_COLOR)


def layout(nodes: list[dict], edges: list[dict] | None = None,
           row_h: float = ROW_H) -> dict[str, dict]:
    """Deterministic graph-order positions: ``{node_id: {"x", "y"}}``.

    Nodes are bucketed into kind columns (task left, children fanned right) and,
    within a column, ordered by ``(at, path)`` — i.e. topological/kind columns +
    date. Pure and stable: the same node set always yields the same coordinates,
    so the canvas render and a saved diagram agree. ``edges`` is accepted for a
    symmetric signature and future edge-aware ordering; the current layout is
    column-based and does not need it.
    """
    cols: dict[int, list[dict]] = {}
    for n in nodes:
        cols.setdefault(_col(n.get("kind", "")), []).append(n)
    pos: dict[str, dict] = {}
    for col, items in cols.items():
        items = sorted(items, key=lambda n: (n.get("at") or "", n.get("path") or "", n.get("id") or ""))
        for row, n in enumerate(items):
            pos[n["id"]] = {"x": X0 + col * COL_W, "y": Y0 + row * row_h}
    return pos


# ── Excalidraw scene emission ────────────────────────────────────────────────
# Minimal-but-valid element dicts. Excalidraw is tolerant on load; we populate
# the fields it reads (geometry, style, bindings) and leave optional ones at the
# shapes Excalidraw itself writes (see example/…/draws/draw.excalidraw).

def _stable_seed(s: str) -> int:
    """A small deterministic positive int from a string (no randomness allowed)."""
    h = 2166136261
    for ch in s:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h or 1


def _rect(node: dict, x: float, y: float, arrow_ids: list[str],
          card_h: float = CARD_H) -> dict:
    rid = "rect-" + node["id"]
    seed = _stable_seed(rid)
    bound = [{"id": "txt-" + node["id"], "type": "text"}]
    bound += [{"id": aid, "type": "arrow"} for aid in arrow_ids]
    return {
        "id": rid, "type": "rectangle", "x": x, "y": y,
        "width": CARD_W, "height": card_h, "angle": 0,
        "strokeColor": color_for(node.get("kind", "")),
        "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": {"type": 3},
        "seed": seed, "version": 1, "versionNonce": seed, "isDeleted": False,
        "boundElements": bound, "updated": 1, "link": None, "locked": False,
    }


def _label(node: dict) -> str:
    name = (node.get("path") or node.get("id") or "").split("/")[-1]
    kind = (node.get("kind") or "").upper()
    at = node.get("at") or ""
    base = f"{kind}\n{name}\n{at}".strip()
    # Optional 4th line: a short change note (the change-log skill's "why").
    # Absent on timeline nodes, so their label is byte-for-byte unchanged.
    note = (node.get("note") or "").strip()
    return f"{base}\n{note}" if note else base


def _text(node: dict, x: float, y: float, card_h: float = CARD_H) -> dict:
    tid = "txt-" + node["id"]
    seed = _stable_seed(tid)
    txt = _label(node)
    return {
        "id": tid, "type": "text", "x": x + 8, "y": y + 8,
        "width": CARD_W - 16, "height": card_h - 16, "angle": 0,
        "strokeColor": color_for(node.get("kind", "")),
        "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": seed, "version": 1, "versionNonce": seed, "isDeleted": False,
        "boundElements": None, "updated": 1, "link": None, "locked": False,
        "text": txt, "fontSize": 14, "fontFamily": 3,
        "textAlign": "left", "verticalAlign": "top",
        "containerId": "rect-" + node["id"], "originalText": txt,
        "lineHeight": 1.25, "baseline": 12,
    }


def _arrow(edge: dict, i: int, pos: dict[str, dict],
           card_h: float = CARD_H) -> dict | None:
    src, dst = edge.get("from"), edge.get("to")
    if src not in pos or dst not in pos:
        return None
    aid = f"arrow-{src}-{dst}-{i}"
    seed = _stable_seed(aid)
    # Start at the right edge of the source card, end at the left edge of the dst.
    sx = pos[src]["x"] + CARD_W
    sy = pos[src]["y"] + card_h / 2
    ex = pos[dst]["x"]
    ey = pos[dst]["y"] + card_h / 2
    return {
        "id": aid, "type": "arrow", "x": sx, "y": sy,
        "width": abs(ex - sx), "height": abs(ey - sy), "angle": 0,
        "strokeColor": _DEFAULT_COLOR, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 2}, "seed": seed, "version": 1,
        "versionNonce": seed, "isDeleted": False, "boundElements": None,
        "updated": 1, "link": None, "locked": False,
        "points": [[0, 0], [ex - sx, ey - sy]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": "rect-" + src, "focus": 0, "gap": 4},
        "endBinding": {"elementId": "rect-" + dst, "focus": 0, "gap": 4},
        "startArrowhead": None, "endArrowhead": "arrow",
    }


def _scene(elements: list[dict], source: str) -> dict:
    return {
        "type": "excalidraw", "version": 2, "source": source,
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": PAPER_BG},
        "files": {},
    }


def to_excalidraw(nodes: list[dict], edges: list[dict] | None = None,
                  positions: dict[str, dict] | None = None,
                  source: str = "hub-timeline") -> dict:
    """Convert a derived graph (nodes + edges) into a valid Excalidraw scene.

    Each node becomes a bordered rectangle (coloured by kind) with a bound text
    label; each edge becomes an arrow bound source→destination. ``positions`` is
    used verbatim when supplied (so the saved diagram matches the canvas exactly)
    and otherwise computed by :func:`layout`. Returns a plain dict ready for
    ``json.dumps`` and the ``/draw/save`` writer — ``type:"excalidraw"``, an
    ``elements`` array, and the paper-ground ``appState``.
    """
    edges = edges or []
    # Grow the card + row pitch by one line ONLY when a node carries a `note`
    # (the change-log skill's change verb + "why"), so that 4th label line has
    # room. Note-less scenes — the timeline canvas — keep CARD_H/ROW_H exactly,
    # so their emitted geometry is byte-for-byte unchanged.
    extra = NOTE_LINE_H if any((n.get("note") or "").strip() for n in nodes) else 0
    card_h = CARD_H + extra
    row_h = ROW_H + extra
    pos = positions or layout(nodes, edges, row_h=row_h)
    # First pass: which arrows bind to each rect (so rects list them too).
    arrows: list[dict] = []
    rect_arrows: dict[str, list[str]] = {}
    for i, e in enumerate(edges):
        a = _arrow(e, i, pos, card_h=card_h)
        if a is None:
            continue
        arrows.append(a)
        rect_arrows.setdefault("rect-" + e["from"], []).append(a["id"])
        rect_arrows.setdefault("rect-" + e["to"], []).append(a["id"])
    elements: list[dict] = []
    for n in nodes:
        p = pos.get(n["id"])
        if not p:
            continue
        elements.append(_rect(n, p["x"], p["y"], rect_arrows.get("rect-" + n["id"], []), card_h=card_h))
        elements.append(_text(n, p["x"], p["y"], card_h=card_h))
    elements.extend(arrows)
    return _scene(elements, source)


def blank_scene(source: str = "hub-draw") -> dict:
    """A minimal blank Excalidraw scene on paper ground (for ``hub draw``)."""
    return _scene([], source)
