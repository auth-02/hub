"""SQLite persistence for hub: file metadata, lineage graph, FTS5 full-text index."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

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


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_DDL)
    conn.commit()
    return conn


def is_current(conn: sqlite3.Connection, abs_path: str, mtime: float) -> bool:
    row = conn.execute("SELECT mtime FROM files WHERE abs=?", (abs_path,)).fetchone()
    return row is not None and abs(row[0] - mtime) < 0.01


def upsert(conn: sqlite3.Connection, meta: dict, title: str, body: str) -> None:
    conn.execute(
        """INSERT INTO files(abs,repo,rel,ext,kind,mtime,title,body,task_slug,task_repo,updated)
           VALUES(:abs,:repo,:rel,:ext,:kind,:mtime,:title,:body,:task_slug,:task_repo,:updated)
           ON CONFLICT(abs) DO UPDATE SET
             repo=excluded.repo,rel=excluded.rel,ext=excluded.ext,kind=excluded.kind,
             mtime=excluded.mtime,title=excluded.title,body=excluded.body,
             task_slug=excluded.task_slug,task_repo=excluded.task_repo,updated=excluded.updated""",
        {**meta, "title": title, "body": body, "updated": time.time()},
    )


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
        g = by_task.setdefault(key, {k: [] for k in ("task", "run", "artifact", "prompt", "doc")})
        bucket = kind if kind in g else "doc"
        g[bucket].append(fid)

    KIND_REL = {
        "run": "task_has_run",
        "artifact": "task_has_artifact",
        "prompt": "task_has_prompt",
        "doc": "task_has_doc",
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
