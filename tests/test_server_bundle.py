"""Tests for the 1g/S11 task-bundle endpoints — POST /_publish-bundle and
POST /_publish-revoke.

/_publish-bundle renders a task subtree to a self-contained bundle under
state_dir()/publish (NEVER the scan root), runs the same core.publish scan, then
hands off to the dak SUBPROCESS (the network edge — Hub itself opens no socket)
and returns the resulting URL, recording published-state. /_publish-revoke
forgets a task's published-state entry locally and rebuilds. These tests stub
subprocess.run so they NEVER hit the network.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.cli import server
from hubspace.core import db as _db, publish as _publish

_BUNDLE_URL = "https://auth-refactor-abc123.atharva-dak.workers.dev"


def _fake_dak(url=_BUNDLE_URL, rc=0, stderr=""):
    """Stand-in for subprocess.run covering BOTH dak and the index rebuild."""
    calls = []

    def _run(cmd, *a, **kw):
        calls.append(list(cmd))
        if any("dak.py" in str(c) for c in cmd):
            out = "" if rc else f"staged\n{url}\n"
            return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    _run.calls = calls
    return _run

_TS = time.mktime((2026, 7, 22, 12, 0, 0, 0, 0, -1))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port: int, path: str, obj, timeout: float = 10.0):
    body = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(f"http://localhost:{port}{path}", data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def _meta(abs_path, rel, kind, mtime=_TS):
    return {"abs": abs_path, "repo": "cortex", "rel": rel, "ext": "md",
            "kind": kind, "mtime": mtime, "task_slug": "auth-refactor",
            "task_repo": "cortex", "skill_slug": None, "skill_repo": None}


class TestBundleEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._port = _free_port()
        cls._scan_root = tempfile.mkdtemp()
        cls._state = tempfile.mkdtemp()
        cls._patchers = [
            patch.object(server, "_SIDECAR", Path(cls._state) / ".scan_root"),
            patch.object(server, "_DB_PATH", Path(cls._state) / "hub.db"),
            patch.object(server.config, "state_dir", lambda: Path(cls._state)),
        ]
        for p in cls._patchers:
            p.start()

        server._active_root = Path(cls._scan_root)
        server.SCAN_ROOT = Path(cls._scan_root)
        server.HubHandler.server_port = cls._port

        # A real task tree on disk under the scan root.
        def _w(rel, text):
            p = Path(cls._scan_root) / "cortex" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            os.utime(p, (_TS, _TS))
            return p

        man = _w("tasks/auth-refactor/manifest.md",
                 "---\nstatus: ongoing\ntitle: Auth Refactor\n---\nSENTINEL_MAN clean prose\n")
        art = _w("tasks/auth-refactor/artifacts/report.md", "# Report\nSENTINEL_ART\n")

        # Index it into the DB the server's query layer will read.
        conn = _db.open_db(Path(cls._state) / "hub.db")
        conn.execute("PRAGMA busy_timeout=3000")
        _db.upsert(conn, _meta(str(man), "tasks/auth-refactor/manifest.md", "task"),
                   "Auth Refactor", "prose")
        _db.upsert(conn, _meta(str(art), "tasks/auth-refactor/artifacts/report.md",
                               "artifact"), "Report", "art")
        conn.commit()
        _db.build_lineage(conn)
        conn.close()

        cls._server = server._HubServer(("::", cls._port), server.HubHandler)
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", cls._port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()
        for p in cls._patchers:
            p.stop()
        import shutil
        shutil.rmtree(cls._scan_root, ignore_errors=True)
        shutil.rmtree(cls._state, ignore_errors=True)

    def test_bundle_writes_under_state_and_runs_dak(self):
        # A REAL (mocked) bundle publish — dryRun omitted → dryRun:false and
        # published-state recorded. The mock stands in for dak (no network).
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex"})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertFalse(d["dryRun"])
        self.assertEqual(d["url"], _BUNDLE_URL)
        # dak was spawned with the produced bundle path
        dak_cmd = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertTrue(any("cortex-auth-refactor" in str(x) for x in dak_cmd))
        # published-state recorded under the S5b sidecar key
        pub = _publish.load_published(Path(self._state) / "published.json")
        self.assertEqual(pub[_publish.published_key("cortex", "auth-refactor")]["url"],
                         _BUNDLE_URL)
        produced = Path(self._state) / "publish" / "cortex-auth-refactor.html"
        self.assertTrue(produced.exists())
        html = produced.read_text(encoding="utf-8")
        self.assertIn("SENTINEL_MAN", html)
        self.assertIn("SENTINEL_ART", html)
        self.assertIn("bundle-trace", html)     # lineage baked static
        self.assertNotIn("localhost", html)     # self-contained
        # written under state, NOT the scan root
        self.assertFalse((Path(self._scan_root) / "publish").exists())

    def test_bundle_dry_run_reports_flag_and_skips_record(self):
        # S14 / #3 — a dry-run bundle carries dryRun:true and does NOT record
        # published-state (the URL never uploaded, so no live row marker).
        _publish.revoke_published("cortex", "auth-refactor")
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex",
                               "dryRun": True})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["dryRun"])
        dak_cmd = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertIn("--dry-run", dak_cmd)
        pub = _publish.load_published(Path(self._state) / "published.json")
        self.assertNotIn(_publish.published_key("cortex", "auth-refactor"), pub)

    def test_bundle_unknown_task_404(self):
        status, d = _post(self._port, "/_publish-bundle", {"slug": "nope"})
        self.assertEqual(status, 404)
        self.assertFalse(d.get("ok", False))

    def test_bundle_missing_slug_400(self):
        status, d = _post(self._port, "/_publish-bundle", {})
        self.assertEqual(status, 400)

    def test_bundle_gate_refuses_unreviewed_findings(self):
        # With findings and neither redact nor review, the gate refuses and dak
        # is never spawned. Patch the shared scanner to surface one finding.
        finding = [{"line": 1, "kind": "host",
                    "text": "box.corp.internal", "span": [0, 17]}]
        fake = _fake_dak()
        with patch.object(_publish, "scan", lambda *_a, **_k: finding), \
             patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex"})
        self.assertEqual(status, 403)
        self.assertEqual(d.get("error"), "unreviewed_findings")
        self.assertEqual(fake.calls, [])

    def test_bundle_private_refuses(self):
        with patch.object(server.config, "load_config", lambda *a, **k: {"private": True}):
            status, d = _post(self._port, "/_publish-bundle", {"slug": "auth-refactor"})
        self.assertEqual(status, 403)
        self.assertEqual(d.get("error"), "private")

    def test_bundle_live_mode_deterministic_worker(self):
        # S26 — the bundle publishes in dak LIVE mode with a DETERMINISTIC worker
        # slug (repo-slug, no random suffix), records that worker, and is
        # IDEMPOTENT: publishing the SAME task twice yields the SAME worker.
        _publish.revoke_published("cortex", "auth-refactor",
                                  path=Path(self._state) / "published.json")
        expect = _publish.task_worker_slug("cortex", "auth-refactor")
        self.assertEqual(expect, "cortex-auth-refactor")

        def _worker_of(fake):
            dak = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
            self.assertIn("--mode", dak)
            self.assertEqual(dak[dak.index("--mode") + 1], "live")
            self.assertIn("--slug", dak)
            return dak[dak.index("--slug") + 1]

        fake1 = _fake_dak()
        with patch.object(server.subprocess, "run", fake1):
            _post(self._port, "/_publish-bundle",
                  {"slug": "auth-refactor", "repo": "cortex"})
        w1 = _worker_of(fake1)
        self.assertEqual(w1, expect)
        pub = _publish.load_published(Path(self._state) / "published.json")
        self.assertEqual(pub[_publish.published_key("cortex", "auth-refactor")]["worker"],
                         expect)
        self.assertEqual(pub[_publish.published_key("cortex", "auth-refactor")]["mode"],
                         "live")

        # republish the SAME task — SAME worker slug (idempotent, same URL).
        fake2 = _fake_dak()
        with patch.object(server.subprocess, "run", fake2):
            _post(self._port, "/_publish-bundle",
                  {"slug": "auth-refactor", "repo": "cortex"})
        self.assertEqual(_worker_of(fake2), w1)
        _publish.revoke_published("cortex", "auth-refactor",
                                  path=Path(self._state) / "published.json")

    def test_revoke_removes_sidecar_entry(self):
        # S26 — revoke UNPUBLISHES: it hands the stored worker to `dak unpublish`
        # (mocked) AND forgets the local entry. Returns unpublished:true on ok.
        _publish.record_published("cortex", "auth-refactor", "https://x",
                                  path=Path(self._state) / "published.json",
                                  worker="cortex-auth-refactor")
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-revoke",
                              {"slug": "auth-refactor", "repo": "cortex"})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["removed"])
        self.assertTrue(d["unpublished"])
        # dak unpublish was spawned with the stored worker name
        unp = next(c for c in fake.calls
                   if any("dak.py" in str(x) for x in c) and "unpublish" in c)
        self.assertIn("cortex-auth-refactor", unp)
        data = _publish.load_published(Path(self._state) / "published.json")
        self.assertEqual(data, {})

    def test_revoke_forgets_locally_when_dak_fails(self):
        # S26 — a dak take-down failure NEVER hard-crashes: the local entry is
        # still forgotten and the response carries unpublished:false + a detail.
        _publish.record_published("cortex", "auth-refactor", "https://x",
                                  path=Path(self._state) / "published.json",
                                  worker="cortex-auth-refactor")

        def _run(cmd, *a, **kw):
            if any("dak.py" in str(c) for c in cmd) and "unpublish" in cmd:
                return subprocess.CompletedProcess(cmd, 1, stdout="",
                                                   stderr="worker not found\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with patch.object(server.subprocess, "run", _run):
            status, d = _post(self._port, "/_publish-revoke",
                              {"slug": "auth-refactor", "repo": "cortex"})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["removed"])
        self.assertFalse(d["unpublished"])
        self.assertIn("worker not found", d.get("detail", ""))
        self.assertEqual(_publish.load_published(Path(self._state) / "published.json"), {})

    def test_revoke_derives_worker_from_url_when_field_absent(self):
        # A pre-S26 entry has no `worker` field; revoke recovers it by parsing
        # the stored workers.dev URL and unpublishes that worker.
        _publish.record_published(
            "cortex", "auth-refactor",
            "https://cortex-auth-refactor.sub.workers.dev",
            path=Path(self._state) / "published.json")
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-revoke",
                              {"slug": "auth-refactor", "repo": "cortex"})
        self.assertTrue(d["unpublished"])
        unp = next(c for c in fake.calls
                   if any("dak.py" in str(x) for x in c) and "unpublish" in c)
        self.assertIn("cortex-auth-refactor", unp)

    def test_revoke_by_path_removes_asset_entry(self):
        # S20 — /_publish-revoke with a {path} body forgets a single-file asset
        # entry, while a co-existing task entry is left untouched.
        sidecar = Path(self._state) / "published.json"
        asset = Path(self._scan_root) / "cortex" / "tasks/auth-refactor/artifacts/report.md"
        _publish.record_published("cortex", "auth-refactor", "https://task", path=sidecar)
        _publish.record_published_asset(asset, "https://asset")
        self.assertIn(_publish.published_asset_key(asset),
                      _publish.load_published(sidecar))
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-revoke", {"path": str(asset)})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["removed"])
        data = _publish.load_published(sidecar)
        self.assertNotIn(_publish.published_asset_key(asset), data)
        # the task entry survived the by-path asset revoke
        self.assertIn(_publish.published_key("cortex", "auth-refactor"), data)
        # cleanup so other tests start clean
        _publish.revoke_published("cortex", "auth-refactor", path=sidecar)

    def test_revoke_missing_target_is_400(self):
        status, d = _post(self._port, "/_publish-revoke", {})
        self.assertEqual(status, 400)
        self.assertFalse(d.get("ok", True))

    # ── S28: optional custom publish name on the task bundle ───────────────────
    def test_bundle_custom_name_sets_slug(self):
        # A user-supplied `name` → dak --slug is that name; the recorded worker
        # matches, so a later republish/unpublish follows the ACTUAL worker.
        sidecar = Path(self._state) / "published.json"
        _publish.revoke_published("cortex", "auth-refactor", path=sidecar)
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex",
                               "name": "My Report!"})
        self.assertEqual(status, 200)
        self.assertEqual(d["worker"], "my-report")
        dak = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertEqual(dak[dak.index("--slug") + 1], "my-report")
        pub = _publish.load_published(sidecar)
        self.assertEqual(
            pub[_publish.published_key("cortex", "auth-refactor")]["worker"],
            "my-report")
        _publish.revoke_published("cortex", "auth-refactor", path=sidecar)

    def test_bundle_blank_name_uses_default(self):
        sidecar = Path(self._state) / "published.json"
        _publish.revoke_published("cortex", "auth-refactor", path=sidecar)
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex", "name": ""})
        self.assertEqual(status, 200)
        self.assertEqual(d["worker"], "cortex-auth-refactor")
        _publish.revoke_published("cortex", "auth-refactor", path=sidecar)

    def test_bundle_name_collision_rejected(self):
        # Naming a bundle the same as an existing DIFFERENT-source entry → 409
        # name_taken; dak is never spawned (no silent hijack).
        sidecar = Path(self._state) / "published.json"
        _publish.record_published("other-repo", "other-task",
                                  "https://taken.example.workers.dev",
                                  path=sidecar, worker="taken-name")
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish-bundle",
                              {"slug": "auth-refactor", "repo": "cortex",
                               "name": "taken-name"})
        self.assertEqual(status, 409)
        self.assertEqual(d.get("error"), "name_taken")
        self.assertEqual(fake.calls, [])
        _publish.revoke_published("other-repo", "other-task", path=sidecar)


if __name__ == "__main__":
    unittest.main()
