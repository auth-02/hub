"""bundle.py — freeze a task subtree to ONE self-contained HTML file (roadmap 1g).

"Publish a task with lineage." Hub renders lineage *live* from SQLite, so a task
shared out of the hub would otherwise arrive as a dead husk — every trace link a
404, every artifact a broken reference. This module does the real work of item
1g: it walks a task's subtree via the existing read queries
(:func:`core.query.get_task` / :func:`core.query.timeline`) and stitches the
manifest, its trace, and every child file into a SINGLE standalone HTML string.

Two hard invariants make the output shareable:

  * **The trace is baked STATIC.** We render the lineage graph from the timeline
    contract at bundle time and freeze it into the page. There is no live DB
    call, no ``/trace`` fetch, no server dependency — the whole point of 1g.
  * **No external host.** Every asset is inlined; the only URLs are in-page
    ``#anchor`` links between the manifest, the trace, and the child sections.
    CSS is embedded, the favicon is a ``data:`` URI. The page opens offline.

Cross-task edges (a lineage link to a file OUTSIDE the task) are handled by a
choice: with ``include_external`` the referenced file is inlined too; otherwise
it is listed with a visible "excluded" note rather than rendered as a dead link.
Hub's per-task lineage is a star today, so external refs are rare — either way
the page never ships a link that resolves to nothing.

Pure and testable: :func:`render_task_bundle` takes a connection + (repo, slug)
and returns the HTML string. It makes no network call (nothing in ``hubspace/``
does); the upload is dak's job, invoked by the ``hub publish --task`` verb.
"""
from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from ..core import config, graph, metadata, query
from ..utils.text import esc_html, slugify
from .markdown import _render_md
from .tabular import _render_csv, _render_xlsx

# Child kinds shown as their own inlined sections, in this display order.
_SECTION_ORDER = ("artifact", "run", "draw", "data", "prompt", "doc", "note")
_SECTION_LABEL = {
    "artifact": "Artifacts", "run": "Runs", "draw": "Diagrams",
    "data": "Data", "prompt": "Prompts", "doc": "Docs", "note": "Notes",
}


# ── CSS + favicon, embedded (no external host) ────────────────────────────────
@lru_cache(maxsize=None)
def _bundle_css() -> str:
    """The doc page stylesheet, read from static/ and embedded inline."""
    try:
        return (config.static_dir() / "page.css").read_text(encoding="utf-8")
    except OSError:
        return ""


@lru_cache(maxsize=None)
def _favicon_data_uri() -> str:
    """The bundled favicon as a self-contained ``data:`` URI (never a URL)."""
    import base64
    try:
        raw = (config.static_dir().parent / "assets" / "favicon.svg").read_bytes()
    except OSError:
        try:
            raw = (config.static_dir() / "favicon.svg").read_bytes()
        except OSError:
            return ""
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


# ── file → HTML fragment, self-contained per kind ─────────────────────────────
def _read(abs_path: str) -> str:
    try:
        return Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _inline_html_body(src: str) -> str:
    """Reduce a full HTML document to embeddable body content.

    Keeps only the ``<body>`` inner HTML when the file is a complete document so
    a bundled artifact does not nest ``<html>``/``<head>`` inside the page; a
    bare fragment is returned unchanged.
    """
    import re
    m = re.search(r"<body[^>]*>(.*)</body>", src, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    # No <body> — strip a leading <head>…</head>/doctype if present, else as-is.
    src = re.sub(r"<!doctype[^>]*>", "", src, flags=re.IGNORECASE)
    src = re.sub(r"<head[^>]*>.*?</head>", "", src, flags=re.IGNORECASE | re.DOTALL)
    src = re.sub(r"</?html[^>]*>", "", src, flags=re.IGNORECASE)
    return src


def _render_file(abs_path: str, kind: str, rel: str) -> str:
    """Render ONE task file to a self-contained HTML fragment (no external refs).

    Markdown/notes → the shared markdown renderer; HTML artifacts → body inlined;
    tabular → the shared table renderers; Excalidraw scenes → a static summary
    (the live canvas needs a JS bundle we deliberately do not ship into an
    offline page); anything else → an escaped ``<pre>``.
    """
    ext = Path(abs_path).suffix.lower()
    if ext in (".md", ".markdown", ".txt"):
        return _render_md(_read(abs_path))
    if ext in (".html", ".htm"):
        return _inline_html_body(_read(abs_path))
    if ext in (".csv", ".tsv"):
        return _render_csv(Path(abs_path))
    if ext in (".xlsx",):
        return _render_xlsx(Path(abs_path))
    if ext == ".excalidraw":
        return _render_draw_static(abs_path)
    if ext == ".jsonl":
        return _render_notes_jsonl(abs_path)
    return f"<pre><code>{esc_html(_read(abs_path))}</code></pre>"


def _render_notes_jsonl(abs_path: str) -> str:
    """Render a comments/notes.jsonl log as a list of comment cards (S7).

    Each line is one comment ``{target,range?,author,created,body}``; malformed
    lines are skipped. Offline-safe, no external refs.
    """
    import json
    parts = ['<ul class="bundle-notes">']
    for line in _read(abs_path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(rec, dict):
            continue
        anchor = esc_html(str(rec.get("target", "")))
        rng = rec.get("range")
        if rng:
            anchor += " · " + esc_html(str(rng))
        meta = " · ".join(
            x for x in (esc_html(str(rec.get("author", ""))),
                        esc_html(str(rec.get("created", "")))) if x
        )
        parts.append(
            '<li class="bundle-note">'
            f'<div class="bundle-note-head"><code>{anchor}</code>'
            f'<span class="bundle-note-meta">{meta}</span></div>'
            f'<div class="bundle-note-body">{esc_html(str(rec.get("body", "")))}</div>'
            '</li>'
        )
    parts.append('</ul>')
    return "".join(parts)


def _render_draw_static(abs_path: str) -> str:
    """A static, offline-safe summary of an Excalidraw scene.

    The interactive canvas is a lazy-loaded React bundle; embedding it would pull
    an external dependency and break the "opens offline" invariant. Instead we
    show the diagram's shape (element/kind counts) so the bundle stands alone.
    """
    import json
    try:
        scene = json.loads(_read(abs_path))
        elements = scene.get("elements", []) if isinstance(scene, dict) else []
    except (ValueError, TypeError):
        elements = []
    by_type: dict[str, int] = {}
    for el in elements:
        if isinstance(el, dict):
            by_type[el.get("type", "?")] = by_type.get(el.get("type", "?"), 0) + 1
    summary = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items())) or "empty"
    return (
        '<div class="bundle-draw">'
        f'<span class="bundle-draw-label">Excalidraw diagram</span> '
        f'<span class="bundle-draw-count">{esc_html(summary)}</span>'
        '</div>'
    )


# ── task subtree assembly (reads the index; NO network) ───────────────────────
def _task_files(conn: sqlite3.Connection, repo: str | None,
                slug: str) -> list[dict]:
    """All indexed files for a task, with abs paths, ordered (manifest first)."""
    sql = ("SELECT id, abs, rel, kind, title, mtime FROM files WHERE task_slug=?")
    params: list = [slug]
    if repo and repo != "(root)":
        sql += " AND task_repo=?"
        params.append(repo)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []

    def _order(r):
        return (0 if r[3] == "task" else 1, r[3] or "", r[2] or "")

    return [
        {"id": r[0], "abs": r[1], "rel": r[2], "kind": r[3] or "",
         "title": r[4] or "", "mtime": r[5]}
        for r in sorted(rows, key=_order)
    ]


def _external_refs(conn: sqlite3.Connection,
                   task_ids: set[int]) -> list[dict]:
    """Lineage edges leaving the task — targets NOT among the task's own files.

    Returns ``[{abs, rel, kind}]`` for each cross-task reference. Hub builds
    lineage per-task (a star), so this is usually empty; when it is not, the
    bundle either inlines the target (include) or marks it excluded, never a
    dead link. De-dupes by file id.
    """
    if not task_ids:
        return []
    placeholders = ",".join("?" for _ in task_ids)
    try:
        rows = conn.execute(
            f"SELECT DISTINCT f.id, f.abs, f.rel, f.kind FROM lineage l "
            f"JOIN files f ON f.id = l.dst_id "
            f"WHERE l.src_id IN ({placeholders}) "
            f"AND l.dst_id NOT IN ({placeholders})",
            list(task_ids) + list(task_ids),
        ).fetchall()
    except sqlite3.Error:
        return []
    seen: set[int] = set()
    out: list[dict] = []
    for fid, abs_path, rel, kind in rows:
        if fid in seen:
            continue
        seen.add(fid)
        out.append({"abs": abs_path, "rel": rel, "kind": kind or ""})
    return out


# ── static trace (baked from the timeline contract — NOT a live DB call) ──────
def _anchor(rel: str) -> str:
    """A stable in-page anchor id for a task-relative path."""
    return "f-" + slugify(rel.replace("/", "-")) or "f"


def _render_trace(nodes: list[dict], edges: list[dict]) -> str:
    """Render the lineage as a FROZEN static block: nodes grouped by kind, with
    in-page ``#anchor`` links and a plain edge list. No live DB, no external host.
    """
    if not nodes:
        return ""
    by_id = {n["id"]: n for n in nodes}
    parts = ['<section id="trace" class="bundle-trace">',
             '<h2>Trace <span class="bundle-static-note">(frozen from lineage)</span></h2>']
    # Nodes grouped by kind.
    groups: dict[str, list[dict]] = {}
    for n in nodes:
        groups.setdefault(n.get("kind", ""), []).append(n)
    parts.append('<ul class="bundle-trace-nodes">')
    for kind in ["task"] + [k for k in _SECTION_ORDER if k in groups]:
        for n in groups.get(kind, []):
            color = graph.color_for(kind)
            rel = n.get("path", "")
            parts.append(
                f'<li><span class="bundle-dot" style="background:{esc_html(color)}"></span>'
                f'<a href="#{_anchor(rel)}"><code>{esc_html(rel)}</code></a> '
                f'<span class="bundle-kind">{esc_html(kind)}</span> '
                f'<span class="bundle-at">{esc_html(n.get("at", ""))}</span></li>'
            )
    parts.append("</ul>")
    # Edges — the star, frozen.
    if edges:
        parts.append('<ul class="bundle-trace-edges">')
        for e in edges:
            src = by_id.get(e.get("from"), {}).get("path", e.get("from", ""))
            dst = by_id.get(e.get("to"), {}).get("path", e.get("to", ""))
            rel = (e.get("rel") or "").replace("task_has_", "").replace("_", " ")
            ext = ' <span class="bundle-ext-flag">external</span>' if e.get("external") else ""
            parts.append(
                f'<li><code>{esc_html(src)}</code> '
                f'<span class="bundle-rel">— {esc_html(rel)} →</span> '
                f'<code>{esc_html(dst)}</code>{ext}</li>'
            )
        parts.append("</ul>")
    parts.append("</section>")
    return "".join(parts)


# ── the public entry point ────────────────────────────────────────────────────
def render_task_bundle(conn: sqlite3.Connection | None, repo: str | None,
                       slug: str, port: int = 0,
                       include_external: bool = False) -> str:
    """Render a task's whole subtree to ONE self-contained HTML string.

    Reuses :func:`core.query.get_task` (manifest + plan/notes/status) and
    :func:`core.query.timeline` (the baked nodes/edges) — the trace is frozen
    into the page, never fetched live. Every child file is inlined via the
    shared renderers. External (cross-task) references are inlined when
    ``include_external`` is set, otherwise listed as excluded with a note.

    Raises :class:`ValueError` when the task does not exist. ``port`` is accepted
    for signature symmetry with the rest of hub but is intentionally unused: a
    bundle carries no server URL (that would defeat "opens offline").
    """
    if conn is None:
        raise ValueError(f"no index — cannot bundle task '{slug}'")
    task = query.get_task(conn, slug, repo=repo)
    if task is None:
        raise ValueError(f"no such task: {slug!r}" + (f" in {repo!r}" if repo else ""))
    task_repo = task["repo"]
    tl = query.timeline(conn, slug, repo=task_repo)
    files = _task_files(conn, task_repo, slug)
    task_ids = {f["id"] for f in files}
    externals = _external_refs(conn, task_ids)

    title = task.get("title") or slug

    # ── manifest ──
    manifest_html = ""
    if task.get("path"):
        manifest_html = _render_md(_read(task["path"]))

    # ── status/plan chip strip ──
    plan = task.get("plan") or []
    done = sum(1 for p in plan if p.get("done"))
    meta_bits = [f'<span class="bundle-status bundle-status-{esc_html(task.get("status",""))}">'
                 f'{esc_html(task.get("status",""))}</span>']
    if plan:
        meta_bits.append(f'<span class="bundle-plan">{done}/{len(plan)} plan</span>')
    meta_bits.append(f'<span class="bundle-repo">{esc_html(task_repo)}</span>')

    # ── trace (frozen) ──
    trace_html = _render_trace(tl.get("nodes", []), tl.get("edges", []))

    # ── child sections (each file inlined, anchored) ──
    sections: list[str] = []
    by_kind: dict[str, list[dict]] = {}
    for f in files:
        if f["kind"] == "task":
            continue
        by_kind.setdefault(f["kind"], []).append(f)
    for kind in _SECTION_ORDER:
        items = by_kind.get(kind)
        if not items:
            continue
        blocks = [f'<h2>{esc_html(_SECTION_LABEL.get(kind, kind))}</h2>']
        for f in items:
            frag = _render_file(f["abs"], kind, f["rel"])
            blocks.append(
                f'<article id="{_anchor(f["rel"])}" class="bundle-file bundle-file-{esc_html(kind)}">'
                f'<div class="bundle-file-head"><code>{esc_html(f["rel"])}</code></div>'
                f'{frag}</article>'
            )
        sections.append('<section class="bundle-section">' + "".join(blocks) + "</section>")

    # ── external (cross-task) references ──
    ext_html = ""
    if externals:
        rows = []
        for ex in externals:
            if include_external:
                frag = _render_file(ex["abs"], ex["kind"], ex["rel"])
                rows.append(
                    f'<article id="{_anchor(ex["rel"])}" '
                    f'class="bundle-file bundle-external-included">'
                    f'<div class="bundle-file-head"><code>{esc_html(ex["rel"])}</code> '
                    f'<span class="bundle-ext-flag">external — included</span></div>'
                    f'{frag}</article>'
                )
            else:
                rows.append(
                    f'<li class="bundle-external-excluded"><code>{esc_html(ex["rel"])}</code> '
                    f'<span class="bundle-ext-flag">external — excluded from this bundle</span></li>'
                )
        if include_external:
            ext_html = ('<section class="bundle-section"><h2>External references</h2>'
                        + "".join(rows) + "</section>")
        else:
            ext_html = ('<section class="bundle-section bundle-external-note">'
                        '<h2>External references</h2>'
                        '<p>These lineage links point outside the task and were '
                        '<strong>not inlined</strong>. Re-run with '
                        '<code>--include-external</code> to embed them.</p>'
                        f'<ul>{"".join(rows)}</ul></section>')

    css = _bundle_css() + _EXTRA_CSS
    favicon = _favicon_data_uri()
    favicon_tag = (f'<link rel="icon" type="image/svg+xml" href="{favicon}">'
                   if favicon else "")

    body = (
        f'<header class="bundle-header">'
        f'<div class="bundle-frozen">frozen bundle · self-contained · opens offline</div>'
        f'<h1>{esc_html(title)}</h1>'
        f'<div class="bundle-meta">{"".join(meta_bits)}</div>'
        f'</header>'
        f'{trace_html}'
        f'<section class="bundle-section" id="manifest"><h2>Manifest</h2>{manifest_html}</section>'
        + "".join(sections)
        + ext_html
    )

    return _SHELL.format(
        title=esc_html(title),
        favicon=favicon_tag,
        css=css,
        body=body,
    )


# Minimal shell — CSS embedded, favicon a data: URI, zero external hosts.
_SHELL = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{favicon}
<style>{css}</style>
</head>
<body class="bundle">
<div class="page bundle-page">
{body}
</div>
</body>
</html>
"""

# Small on-theme additions layered over page.css (deep-sea trace chrome).
_EXTRA_CSS = """
.bundle-frozen{font:11px/1.4 ui-monospace,monospace;letter-spacing:.06em;
  text-transform:uppercase;opacity:.6;margin-bottom:.4rem}
.bundle-meta{display:flex;gap:.5rem;flex-wrap:wrap;margin:.5rem 0 1rem;
  font:12px/1 ui-monospace,monospace}
.bundle-meta span{padding:.2rem .5rem;border-radius:4px;background:rgba(30,90,107,.12)}
.bundle-status-completed{background:rgba(47,107,79,.18)}
.bundle-status-paused{background:rgba(201,154,32,.18)}
.bundle-trace{border:1px solid rgba(30,90,107,.3);border-radius:8px;
  padding:.75rem 1rem;margin:1rem 0;background:rgba(30,90,107,.05)}
.bundle-trace h2{margin-top:0}
.bundle-static-note{font:11px/1 ui-monospace,monospace;opacity:.55;font-weight:400}
.bundle-trace-nodes,.bundle-trace-edges{list-style:none;padding:0;margin:.5rem 0;
  font:12px/1.7 ui-monospace,monospace}
.bundle-dot{display:inline-block;width:8px;height:8px;border-radius:50%;
  margin-right:.4rem;vertical-align:middle}
.bundle-kind,.bundle-at,.bundle-rel{opacity:.6}
.bundle-ext-flag{color:#B5651D;font-weight:600}
.bundle-file{margin:1rem 0;padding-top:.5rem;border-top:1px dashed rgba(0,0,0,.12)}
.bundle-file-head{font:12px/1 ui-monospace,monospace;opacity:.6;margin-bottom:.4rem}
.bundle-draw{padding:.75rem 1rem;border:1px dashed rgba(181,101,29,.5);border-radius:6px}
.bundle-draw-label{font-weight:600;color:#B5651D}
.bundle-external-note{opacity:.85}
"""
