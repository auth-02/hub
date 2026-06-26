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
