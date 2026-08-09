"""Read-only query layer over the existing hub index (SINGLE SOURCE OF TRUTH).

Pure functions that READ the SQLite index (`hub.db`) and return plain, JSON-
serialisable Python dicts/lists. These are reused verbatim by both the MCP stdio
server (`cli/mcp.py`) and the read CLI verbs (`hub trace`, `hub timeline`) so the
two surfaces can never drift — roadmap item 2c (one verb table).

Design invariants:
  - Stdlib-only. No new storage, no write path — every function only reads.
  - The DB is disposable: a missing DB, a missing table, or a missing row must
    degrade to empty results, never crash. Every query is guarded.
  - Layout semantics follow docs/HUB-LAYOUT.md (kinds, lineage rel_types, §5
    time semantics). We reuse the schema built by db.py rather than re-deriving.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from . import config
from . import metadata
from ..utils.paths import env_path

# Child kinds a task manifest owns, mirrored from db.build_lineage()'s TASK_KIND_REL.
_CHILD_KINDS = ("run", "artifact", "prompt", "doc", "data", "draw")
_RUN_DATE = re.compile(r"runs/(\d{4}-\d{2}-\d{2})/")


# ── DB location + read-only connection ───────────────────────────────────────
def default_db_path() -> Path:
    """Resolve the index path exactly as the rest of hub does: HUB_DB > state dir."""
    return env_path("HUB_DB", config.state_dir() / "hub.db")


def connect(db_path: Path | str | None = None) -> sqlite3.Connection | None:
    """Open a read-only connection to the index, or None if it does not exist.

    Callers must treat None as "empty index" and still return well-formed empty
    results (the query functions below all accept conn=None).
    """
    p = Path(db_path) if db_path else default_db_path()
    if not p.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error:
        return None


# ── helpers ──────────────────────────────────────────────────────────────────
def _iso_date(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return ""


def _node_at(rel: str, mtime: float) -> str:
    """§5 timestamp for a node: a run takes its runs/<YYYY-MM-DD>/ dir date;
    everything else falls back to the file mtime as an ISO date."""
    m = _RUN_DATE.search(rel or "")
    if m:
        return m.group(1)
    return _iso_date(mtime)


# ── 1h read surfaces ──────────────────────────────────────────────────────────
def search(conn: sqlite3.Connection | None, query: str,
           kind: str | None = None, limit: int = 20) -> list[dict]:
    """Full-text search over the `fts` FTS5 table.

    Returns [{path, repo, kind, title, snippet}]. An empty/blank query or a query
    that FTS5 cannot parse yields [] rather than an error.
    """
    if conn is None or not query or not query.strip():
        return []
    sql = (
        "SELECT f.abs, f.repo, f.kind, f.title, "
        "snippet(fts, 1, '[', ']', '…', 12) "
        "FROM fts JOIN files f ON f.id = fts.rowid "
        "WHERE fts MATCH ?"
    )
    params: list = [query]
    if kind:
        sql += " AND f.kind = ?"
        params.append(kind)
    sql += " ORDER BY rank LIMIT ?"
    params.append(max(1, int(limit)))
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    return [
        {"path": r[0], "repo": r[1], "kind": r[2] or "",
         "title": r[3] or "", "snippet": r[4] or ""}
        for r in rows
    ]


def _find_manifest(conn: sqlite3.Connection, slug: str,
                   repo: str | None) -> tuple | None:
    sql = ("SELECT abs, rel, title, task_repo, mtime FROM files "
           "WHERE kind='task' AND task_slug=?")
    params: list = [slug]
    if repo:
        sql += " AND task_repo=?"
        params.append(repo)
    sql += " ORDER BY mtime DESC LIMIT 1"
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None


def get_task(conn: sqlite3.Connection | None, slug: str,
             repo: str | None = None) -> dict | None:
    """Assemble a task manifest view, or None if no such task exists.

    Reuses metadata.extract_plan/extract_decisions (the same extraction the HTML
    build uses) for plan/notes, and the task_status table for status.
    """
    if conn is None or not slug:
        return None
    row = _find_manifest(conn, slug, repo)
    if row is None:
        return None
    abs_path, rel, title, task_repo, _mtime = row

    # status — user toggle wins (task_status table), else 'ongoing' per §4.1.
    status = "ongoing"
    try:
        s = conn.execute(
            "SELECT status FROM task_status WHERE task_slug=? AND task_repo=?",
            (slug, task_repo),
        ).fetchone()
        if s and s[0]:
            status = s[0]
    except sqlite3.Error:
        pass

    text = metadata.read_safe(abs_path)
    plan = [{"text": p["t"], "done": p["d"]} for p in metadata.extract_plan(text)]
    notes = metadata.extract_decisions(text)

    # Comments (S7) — parsed from the task's append-only comments/notes.jsonl.
    # Each line is one comment {id,target,range?,author,created,body}.
    from . import tasks as _tasks
    comments = _tasks.read_notes(Path(abs_path).parent)

    def _children(kind: str) -> list[dict]:
        try:
            rows = conn.execute(
                "SELECT abs, rel, title, mtime FROM files "
                "WHERE task_slug=? AND task_repo=? AND kind=? ORDER BY rel",
                (slug, task_repo, kind),
            ).fetchall()
        except sqlite3.Error:
            return []
        return [
            {"path": r[0], "rel": r[1], "title": r[2] or "",
             "at": _node_at(r[1], r[3])}
            for r in rows
        ]

    return {
        "slug": slug,
        "repo": task_repo,
        "status": status,
        "title": title or slug,
        "plan": plan,
        "notes": notes,
        "comments": comments,
        "runs": _children("run"),
        "artifacts": _children("artifact"),
        "path": abs_path,
    }


def _resolve_file(conn: sqlite3.Connection, path: str) -> tuple | None:
    """Resolve an abs OR scan-root-relative path to a files row (id, abs, rel, kind,
    task_slug, task_repo). Returns None if not indexed."""
    tries = (
        ("SELECT id, abs, rel, kind, task_slug, task_repo FROM files WHERE abs=?", path),
        ("SELECT id, abs, rel, kind, task_slug, task_repo FROM files WHERE rel=?", path),
        ("SELECT id, abs, rel, kind, task_slug, task_repo FROM files WHERE abs LIKE ? "
         "ORDER BY LENGTH(abs) LIMIT 1", "%/" + path.lstrip("/")),
    )
    for sql, param in tries:
        try:
            row = conn.execute(sql, (param,)).fetchone()
        except sqlite3.Error:
            row = None
        if row:
            return row
    return None


def trace(conn: sqlite3.Connection | None, path: str) -> dict:
    """Lineage graph around one file: {path, kind, task, up, down, siblings}.

    Accepts an absolute path OR a scan-root-relative path. Unknown/missing files
    degrade to an empty graph (kind/task None) rather than erroring.
    """
    empty = {"path": path, "kind": None, "task": None,
             "up": [], "down": [], "siblings": []}
    if conn is None or not path:
        return empty
    row = _resolve_file(conn, path)
    if row is None:
        return empty
    fid, abs_path, rel, kind, task_slug, task_repo = row

    def _edges(direction: str) -> list[dict]:
        # direction 'down' = edges out of this node (task_has_*);
        # 'up' = edges out of this node that point back to its manifest.
        try:
            rows = conn.execute(
                "SELECT f.abs, f.rel, f.kind, l.rel_type "
                "FROM lineage l JOIN files f ON f.id = l.dst_id "
                "WHERE l.src_id = ?",
                (fid,),
            ).fetchall()
        except sqlite3.Error:
            return []
        out = []
        for dabs, drel, dkind, rel_type in rows:
            is_up = rel_type.startswith("belongs_to_")
            if (direction == "up") == is_up:
                out.append({"path": dabs, "rel": drel,
                            "kind": dkind or "", "rel_type": rel_type})
        return out

    siblings: list[dict] = []
    if task_slug and task_repo:
        try:
            rows = conn.execute(
                "SELECT abs, rel, kind FROM files "
                "WHERE task_slug=? AND task_repo=? AND id!=? AND kind!='task' "
                "ORDER BY rel",
                (task_slug, task_repo, fid),
            ).fetchall()
        except sqlite3.Error:
            rows = []
        siblings = [{"path": r[0], "rel": r[1], "kind": r[2] or ""} for r in rows]

    return {
        "path": abs_path,
        "kind": kind,
        "task": task_slug,
        "up": _edges("up"),
        "down": _edges("down"),
        "siblings": siblings,
    }


def timeline(conn: sqlite3.Connection | None, slug: str,
             repo: str | None = None) -> dict:
    """The 2b JSON contract: a plain SQL walk of the lineage table for one task.

    { "task": <slug>,
      "nodes": [ {"id","kind","path","at"}, ... ],
      "edges": [ {"from","to","rel","external"}, ... ] }

    No coordinates/colours (layout is the canvas's job). Node ids (n1, n2 …) are
    stable within the response: the manifest is always n1, children follow in a
    deterministic (kind, rel) order.
    """
    result: dict = {"task": slug, "nodes": [], "edges": []}
    if conn is None or not slug:
        return result

    row = _find_manifest(conn, slug, repo)
    if row is None:
        # Orphan task (children but no manifest) still gets a timeline.
        task_repo = repo
    else:
        task_repo = row[3]

    sql = ("SELECT id, rel, kind, mtime, abs FROM files WHERE task_slug=?")
    params: list = [slug]
    if task_repo:
        sql += " AND task_repo=?"
        params.append(task_repo)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return result
    if not rows:
        return result

    # Order: task manifest first, then children by (kind, rel) — deterministic.
    def _order(r):
        return (0 if r[2] == "task" else 1, r[2] or "", r[1] or "")
    rows.sort(key=_order)

    # A file id maps to one node — EXCEPT a comments/notes.jsonl file (kind
    # 'note'), which expands into one NOTE node per comment LINE (S7): each line
    # is its own timeline event carrying its own `created` date. So node_ids maps
    # file id -> [nid, ...].
    from . import tasks as _tasks
    node_ids: dict = {}
    counter = 0
    for fid, rel, kind, mtime, abs_path in rows:
        if kind == "note":
            # abs_path is <task_dir>/comments/notes.jsonl → task_dir is two up.
            recs = _tasks.read_notes(Path(abs_path).parent.parent)
            nids = []
            for rec in recs:
                counter += 1
                nid = f"n{counter}"
                at = (str(rec.get("created") or "")[:10]) or _iso_date(mtime)
                # `label` carries the comment text (not the notes.jsonl filename)
                # so the Trace spine and graph canvas can render the comment
                # itself; `path` stays the raw file so lineage/layout are unchanged.
                body = " ".join(str(rec.get("body") or "").split())
                label = (body[:57] + "…") if len(body) > 58 else body
                result["nodes"].append(
                    {"id": nid, "kind": "note", "path": rel, "at": at,
                     "label": label or "comment",
                     "author": rec.get("author") or ""}
                )
                nids.append(nid)
            node_ids[fid] = nids
        else:
            counter += 1
            nid = f"n{counter}"
            result["nodes"].append(
                {"id": nid, "kind": kind or "", "path": rel,
                 "at": _node_at(rel, mtime)}
            )
            node_ids[fid] = [nid]

    ids = list(node_ids.keys())
    placeholders = ",".join("?" for _ in ids)
    try:
        edge_rows = conn.execute(
            f"SELECT src_id, dst_id, rel_type FROM lineage "
            f"WHERE src_id IN ({placeholders}) AND rel_type LIKE 'task_has_%'",
            ids,
        ).fetchall()
    except sqlite3.Error:
        edge_rows = []
    for src, dst, rel_type in edge_rows:
        # A single task_has_note edge (manifest → notes.jsonl) fans out to one
        # edge per expanded comment-line node.
        for s_nid in node_ids.get(src, []):
            for d_nid in node_ids.get(dst, []):
                result["edges"].append({
                    "from": s_nid, "to": d_nid,
                    "rel": rel_type,
                    # Lineage is built per-task, so every edge here is internal;
                    # the flag is part of the contract for cross-task graphs.
                    "external": False,
                })
    return result
