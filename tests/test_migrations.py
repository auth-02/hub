"""Tests for db.py's file-based migration system (migrations/*.sql + user_version)."""
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import db


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


class TestMigrationFiles(unittest.TestCase):
    def test_migrations_dir_exists(self):
        self.assertTrue(db._MIGRATIONS_DIR.is_dir())

    def test_every_file_has_numeric_prefix(self):
        files = list(db._MIGRATIONS_DIR.glob("*.sql"))
        self.assertTrue(files, "expected at least one migration file")
        for p in files:
            self.assertRegex(p.name, r"^\d+_.+\.sql$", f"bad name: {p.name}")

    def test_version_prefixes_are_unique(self):
        nums = [v for v, _ in db._discover_migrations()]
        self.assertEqual(len(nums), len(set(nums)), "duplicate migration numbers")

    def test_discover_returns_ascending_order(self):
        nums = [v for v, _ in db._discover_migrations()]
        self.assertEqual(nums, sorted(nums))


class TestFreshDb(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tf.close()
        self.path = Path(self.tf.name)

    def tearDown(self):
        os.unlink(self.tf.name)

    def test_all_tables_created(self):
        conn = db.open_db(self.path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for expected in ("files", "lineage", "task_status", "activity_log", "fts"):
            self.assertIn(expected, tables)
        conn.close()

    def test_version_equals_latest_migration(self):
        latest = db._discover_migrations()[-1][0]
        conn = db.open_db(self.path)
        self.assertEqual(_version(conn), latest)
        conn.close()

    def test_skill_columns_present(self):
        conn = db.open_db(self.path)
        cols = _cols(conn, "files")
        self.assertIn("skill_slug", cols)
        self.assertIn("skill_repo", cols)
        conn.close()

    def test_idempotent_reopen(self):
        conn = db.open_db(self.path)
        v1 = _version(conn)
        conn.close()
        # Re-open the same DB — must not raise (e.g. "duplicate column") and
        # must leave the version untouched.
        conn = db.open_db(self.path)
        self.assertEqual(_version(conn), v1)
        conn.close()

    def test_upsert_and_set_status_no_schema_errors(self):
        # Guards the schema-drift regression: a fresh DB must support the real
        # write paths without "no such table" / "no such column".
        conn = db.open_db(self.path)
        meta = {
            "abs": "/x/manifest.md", "repo": "r", "rel": "tasks/s/manifest.md",
            "ext": "md", "kind": "task", "mtime": 1.0,
            "task_slug": "s", "task_repo": "r",
            "skill_slug": None, "skill_repo": None,
        }
        db.upsert(conn, meta, "Title", "body")
        db.set_status(conn, "s", "r", "completed")
        conn.commit()
        row = conn.execute(
            "SELECT status FROM task_status WHERE task_slug='s' AND task_repo='r'"
        ).fetchone()
        self.assertEqual(row[0], "completed")
        conn.close()


class TestBaselineDetection(unittest.TestCase):
    """A DB created before migrations existed: user_version=0 but schema current."""

    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tf.close()
        self.path = Path(self.tf.name)

    def tearDown(self):
        os.unlink(self.tf.name)

    def _simulate_pre_migrations_db(self):
        # Apply 001 + the skill-column ALTERs by hand, leaving user_version=0,
        # exactly mirroring how the old _DDL + _migrate() left a DB.
        conn = sqlite3.connect(str(self.path))
        sql_001 = (db._MIGRATIONS_DIR / "001_initial_schema.sql").read_text()
        conn.executescript(sql_001)
        conn.execute("ALTER TABLE files ADD COLUMN skill_slug TEXT")
        conn.execute("ALTER TABLE files ADD COLUMN skill_repo TEXT")
        conn.commit()
        self.assertEqual(_version(conn), 0)
        conn.close()

    def test_baseline_db_gets_stamped_without_error(self):
        self._simulate_pre_migrations_db()
        latest = db._discover_migrations()[-1][0]
        # open_db must NOT re-run 002 (which would throw "duplicate column").
        conn = db.open_db(self.path)
        self.assertEqual(_version(conn), latest)
        cols = _cols(conn, "files")
        self.assertIn("skill_slug", cols)
        self.assertIn("skill_repo", cols)
        conn.close()


if __name__ == "__main__":
    unittest.main()
