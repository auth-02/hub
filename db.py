"""SQLite persistence for hub: file metadata, lineage graph, FTS5 full-text index."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_STATUS_SIDECAR = Path.home() / ".hub-state" / "task-status.json"

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS files (
    id        INTEGER PRIMARY KEY,
    abs       TEXT NOT NULL UNIQUE,
    repo      TEXT NOT NULL,
    rel       TEXT NOT NULL,
    ext       TEXT NOT NULL,
    kind      TEXT,
    mtime     REAL NOT NULL,
    title     TEXT,
    body      TEXT,
    task_slug TEXT,
    task_repo TEXT,
    updated   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_log (
    id        INTEGER PRIMARY KEY,
    abs       TEXT NOT NULL,
    kind      TEXT,
    task_slug TEXT,
    task_repo TEXT,
    rel       TEXT NOT NULL,
    event     TEXT NOT NULL,
    ts        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_status (
    task_slug TEXT NOT NULL,
    task_repo TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'ongoing',
    updated   REAL NOT NULL,
    PRIMARY KEY (task_slug, task_repo)
);

CREATE TABLE IF NOT EXISTS lineage (
    id       INTEGER PRIMARY KEY,
    src_id   INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    dst_id   INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    rel_type TEXT NOT NULL,
    UNIQUE(src_id, dst_id, rel_type)
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    title, body, repo, rel, kind,
    content='files', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS fts_ins AFTER INSERT ON files BEGIN
  INSERT INTO fts(rowid,title,body,repo,rel,kind)
  VALUES (new.id,new.title,new.body,new.repo,new.rel,new.kind);
END;

CREATE TRIGGER IF NOT EXISTS fts_upd AFTER UPDATE ON files BEGIN
  INSERT INTO fts(fts,rowid,title,body,repo,rel,kind)
  VALUES ('delete',old.id,old.title,old.body,old.repo,old.rel,old.kind);
  INSERT INTO fts(rowid,title,body,repo,rel,kind)
  VALUES (new.id,new.title,new.body,new.repo,new.rel,new.kind);
END;

CREATE TRIGGER IF NOT EXISTS fts_del AFTER DELETE ON files BEGIN
  INSERT INTO fts(fts,rowid,title,body,repo,rel,kind)
  VALUES ('delete',old.id,old.title,old.body,old.repo,old.rel,old.kind);
END;
"""


def _write_status_sidecar(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT task_slug, task_repo, status FROM task_status").fetchall()
    data = {f"{r[1]}:{r[0]}": r[2] for r in rows}
    try:
        _STATUS_SIDECAR.parent.mkdir(parents=True, exist_ok=True)
        _STATUS_SIDECAR.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _restore_from_sidecar(conn: sqlite3.Connection) -> None:
    """Import statuses from sidecar if task_status table is empty (i.e. fresh DB)."""
    if conn.execute("SELECT task_slug FROM task_status LIMIT 1").fetchone():
        return
    if not _STATUS_SIDECAR.exists():
        return
    try:
        data = json.loads(_STATUS_SIDECAR.read_text(encoding="utf-8"))
        for key, status in data.items():
            if ":" not in key:
                continue
            task_repo, task_slug = key.split(":", 1)
            conn.execute(
                """INSERT OR IGNORE INTO task_status(task_slug,task_repo,status,updated)
                   VALUES(?,?,?,?)""",
                (task_slug, task_repo, status, time.time()),
            )
        conn.commit()
    except Exception:
        pass


def open_db(db_path: Path) -> sqlite3.Connection:
    # timeout + busy_timeout let a writer wait for a concurrent one (e.g. the
    # file-watcher and a /_set-root rebuild) instead of failing with
    # "database is locked".
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(_DDL)
    conn.commit()
    _restore_from_sidecar(conn)
    _write_status_sidecar(conn)  # keep sidecar in sync on every open
    return conn


def is_current(conn: sqlite3.Connection, abs_path: str, mtime: float) -> bool:
    row = conn.execute("SELECT mtime FROM files WHERE abs=?", (abs_path,)).fetchone()
    return row is not None and abs(row[0] - mtime) < 0.01


def _log_activity(conn: sqlite3.Connection, meta: dict, event: str) -> None:
    # Use file mtime as the event timestamp — dedup by (abs, mtime) so
    # re-scanning the same unchanged file never creates a duplicate entry.
    mtime = meta.get("mtime") or time.time()
    if conn.execute("SELECT id FROM activity_log WHERE abs=? AND ts=?",
                    (meta["abs"], mtime)).fetchone():
        return
    conn.execute(
        """INSERT INTO activity_log(abs,kind,task_slug,task_repo,rel,event,ts)
           VALUES(?,?,?,?,?,?,?)""",
        (meta["abs"], meta.get("kind"), meta.get("task_slug"),
         meta.get("task_repo"), meta["rel"], event, mtime),
    )


def upsert(conn: sqlite3.Connection, meta: dict, title: str, body: str) -> None:
    existing = conn.execute("SELECT id FROM files WHERE abs=?", (meta["abs"],)).fetchone()
    conn.execute(
        """INSERT INTO files(abs,repo,rel,ext,kind,mtime,title,body,task_slug,task_repo,updated)
           VALUES(:abs,:repo,:rel,:ext,:kind,:mtime,:title,:body,:task_slug,:task_repo,:updated)
           ON CONFLICT(abs) DO UPDATE SET
             repo=excluded.repo,rel=excluded.rel,ext=excluded.ext,kind=excluded.kind,
             mtime=excluded.mtime,title=excluded.title,body=excluded.body,
             task_slug=excluded.task_slug,task_repo=excluded.task_repo,updated=excluded.updated""",
        {**meta, "title": title, "body": body, "updated": time.time()},
    )
    _log_activity(conn, meta, "created" if existing is None else "updated")


def prune(conn: sqlite3.Connection, live_paths: set) -> None:
    """Remove rows for files that no longer exist on disk."""
    stored = {r[0] for r in conn.execute("SELECT abs FROM files").fetchall()}
    for gone in stored - live_paths:
        conn.execute("DELETE FROM files WHERE abs=?", (gone,))


def build_lineage(conn: sqlite3.Connection) -> None:
    """Link Task→Run/Artifact/Prompt/Doc edges via task_slug grouping."""
    conn.execute("DELETE FROM lineage")
    rows = conn.execute(
        "SELECT id, abs, kind, task_slug, task_repo FROM files WHERE task_slug IS NOT NULL"
    ).fetchall()

    by_task: dict = {}
    for fid, abs_, kind, slug, trepo in rows:
        key = (slug, trepo)
        g = by_task.setdefault(key, {k: [] for k in ("task", "run", "artifact", "prompt", "doc", "data")})
        bucket = kind if kind in g else "doc"
        g[bucket].append(fid)

    KIND_REL = {
        "run": "task_has_run",
        "artifact": "task_has_artifact",
        "prompt": "task_has_prompt",
        "doc": "task_has_doc",
        "data": "task_has_data",
    }
    edges: list = []
    for buckets in by_task.values():
        for tid in buckets["task"]:
            for rel_kind, rel_type in KIND_REL.items():
                for cid in buckets[rel_kind]:
                    edges.append((tid, cid, rel_type))
                    edges.append((cid, tid, "belongs_to_task"))

    conn.executemany(
        "INSERT OR IGNORE INTO lineage(src_id,dst_id,rel_type) VALUES(?,?,?)", edges
    )
    conn.commit()


def set_status(conn: sqlite3.Connection, task_slug: str, task_repo: str, status: str) -> None:
    conn.execute(
        """INSERT INTO task_status(task_slug,task_repo,status,updated)
           VALUES(?,?,?,?)
           ON CONFLICT(task_slug,task_repo) DO UPDATE SET
             status=excluded.status,updated=excluded.updated""",
        (task_slug, task_repo, status, time.time()),
    )
    conn.commit()
    _write_status_sidecar(conn)


def get_statuses_json(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT task_slug, task_repo, status FROM task_status"
    ).fetchall()
    return json.dumps(
        {f"{r[1]}:{r[0]}": r[2] for r in rows},
        separators=(",", ":"),
    )


def backfill_activity(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT id FROM activity_log LIMIT 1").fetchone():
        return
    rows = conn.execute(
        "SELECT abs,kind,task_slug,task_repo,rel,mtime FROM files ORDER BY mtime DESC LIMIT 100"
    ).fetchall()
    conn.executemany(
        "INSERT OR IGNORE INTO activity_log(abs,kind,task_slug,task_repo,rel,event,ts) VALUES(?,?,?,?,?,'updated',?)",
        [(r[0],r[1],r[2],r[3],r[4],r[5]) for r in rows],
    )
    conn.commit()


def prune_activity(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM activity_log WHERE ts<?", (time.time() - 30*86400,))
    conn.execute("DELETE FROM activity_log WHERE id NOT IN (SELECT id FROM activity_log ORDER BY ts DESC LIMIT 200)")
    conn.commit()


def get_activity_json(conn: sqlite3.Connection, scan_root: str = "") -> str:
    if scan_root:
        rows = conn.execute(
            "SELECT abs,kind,task_slug,task_repo,rel,event,ts FROM activity_log WHERE abs LIKE ? ORDER BY ts DESC LIMIT 50",
            (scan_root.rstrip("/") + "/%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT abs,kind,task_slug,task_repo,rel,event,ts FROM activity_log ORDER BY ts DESC LIMIT 50"
        ).fetchall()
    return json.dumps(
        [{"a":r[0],"k":r[1] or "","sl":r[2] or "","rp":r[3] or "","p":r[4],"ev":r[5],"ts":r[6]} for r in rows],
        separators=(",",":"),
    )


def get_timeline_data(conn: sqlite3.Connection, scan_root: str = "", days: int = 7) -> list:
    """Return per-task activity summaries for the last N days, with task status."""
    cutoff = time.time() - days * 86400
    params: list = [cutoff]
    root_filter = ""
    if scan_root:
        root_filter = "AND al.abs LIKE ?"
        params.append(scan_root.rstrip("/") + "/%")

    rows = conn.execute(
        f"""SELECT al.task_slug, al.task_repo, al.kind, al.ts,
                   COALESCE(ts.status, 'ongoing') AS status
            FROM activity_log al
            LEFT JOIN task_status ts
              ON ts.task_slug = al.task_slug AND ts.task_repo = al.task_repo
            WHERE al.ts >= ? {root_filter}
              AND al.task_slug IS NOT NULL
            ORDER BY al.ts DESC""",
        params,
    ).fetchall()

    tasks: dict = {}
    for task_slug, task_repo, kind, ts, status in rows:
        key = f"{task_repo}:{task_slug}"
        if key not in tasks:
            tasks[key] = {
                "sl": task_slug, "rp": task_repo, "status": status,
                "manifest": 0, "runs": 0, "artifacts": 0, "prompts": 0, "docs": 0,
                "ts": ts,
            }
        t = tasks[key]
        if ts > t["ts"]:
            t["ts"] = ts
        if kind == "task":      t["manifest"] += 1
        elif kind == "run":     t["runs"] += 1
        elif kind == "artifact":t["artifacts"] += 1
        elif kind == "prompt":  t["prompts"] += 1
        elif kind == "doc":     t["docs"] += 1

    return sorted(tasks.values(), key=lambda x: x["ts"], reverse=True)


def export_html_data(conn: sqlite3.Connection) -> tuple:
    """Return (fts_json, lineage_json) strings to embed in the hub HTML."""
    files = conn.execute(
        "SELECT id, abs, repo, rel, kind, title, body FROM files"
    ).fetchall()
    fts = [
        {"i": r[0], "a": r[1], "r": r[2], "p": r[3],
         "k": r[4] or "", "t": r[5] or "", "b": r[6] or ""}
        for r in files
    ]

    edges = conn.execute(
        """SELECT f1.abs, f2.abs, f2.rel, f2.kind, l.rel_type
           FROM lineage l
           JOIN files f1 ON f1.id=l.src_id
           JOIN files f2 ON f2.id=l.dst_id"""
    ).fetchall()
    lineage: dict = {}
    for src, dst_abs, dst_rel, dst_kind, rel_type in edges:
        lineage.setdefault(src, []).append(
            {"a": dst_abs, "p": dst_rel, "k": dst_kind or "", "r": rel_type}
        )

    return (
        json.dumps(fts, separators=(",", ":")),
        json.dumps(lineage, separators=(",", ":")),
    )
