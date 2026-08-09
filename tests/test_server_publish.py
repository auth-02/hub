"""Tests for the 1f/S11 publish endpoints — POST /_publish-scan and /_publish.

/_publish-scan runs the SAME core.publish scanner the CLI uses and guards the
path (must resolve inside the active scan root). /_publish now performs a
ONE-CLICK publish: it prepares the local (possibly redacted) copy — original
untouched — then hands off to the bundled dak SUBPROCESS (the network edge; Hub
itself opens no socket) and returns the resulting URL. These tests stub
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

_FAKE_URL = "https://report-abc123.atharva-dak.workers.dev"


def _fake_dak(url=_FAKE_URL, rc=0, stderr=""):
    """A stand-in for subprocess.run: dak (last stdout line = URL) or rebuild.

    Routes by command so a single patch covers BOTH the dak hand-off and the
    server's own rebuild subprocess — neither ever touches the network.
    """
    calls = []

    def _run(cmd, *a, **kw):
        calls.append(list(cmd))
        if any("dak.py" in str(c) for c in cmd):
            out = "" if rc else f"staged (dry-run)\n{url}\n"
            return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=stderr)
        # anything else (e.g. the index rebuild) — succeed cheaply
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    _run.calls = calls
    return _run


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


class TestPublishEndpoints(unittest.TestCase):
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

        cls.asset = Path(cls._scan_root) / "report.md"
        cls.asset.write_text(
            "contact bob@corp.internal at 10.0.0.9\nnothing else\n", encoding="utf-8")

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

    def test_scan_returns_findings(self):
        status, d = _post(self._port, "/_publish-scan", {"path": str(self.asset)})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        kinds = {f["kind"] for f in d["findings"]}
        self.assertIn("email", kinds)
        self.assertIn("ip", kinds)

    def test_scan_relative_path(self):
        status, d = _post(self._port, "/_publish-scan", {"path": "report.md"})
        self.assertEqual(status, 200)
        self.assertTrue(d["findings"])

    def test_scan_guards_path_escape(self):
        status, d = _post(self._port, "/_publish-scan", {"path": "/etc/passwd"})
        self.assertEqual(status, 403)
        self.assertFalse(d.get("ok", False))

    def test_scan_missing_path(self):
        status, d = _post(self._port, "/_publish-scan", {})
        self.assertEqual(status, 400)

    def test_publish_runs_dak_and_returns_url(self):
        # A REAL (mocked) publish — dryRun omitted → dryRun:false, published-state
        # recorded. The mock stands in for dak so nothing hits the network.
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "redact_indices": [0, 1],
                               "title": "My Report"})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertFalse(d["dryRun"])
        self.assertEqual(d["url"], _FAKE_URL)
        # dak was invoked with the produced (redacted) copy path + the title
        dak_cmd = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertIn("--title", dak_cmd)
        self.assertIn("My Report", dak_cmd)
        self.assertIn(d["copy"], dak_cmd)
        # original file is never modified
        self.assertIn("bob@corp.internal", self.asset.read_text(encoding="utf-8"))
        # a sanitized copy was written and is what dak received
        self.assertTrue(d["copy"])
        copy_text = Path(d["copy"]).read_text(encoding="utf-8")
        self.assertNotIn("bob@corp.internal", copy_text)
        # published-state recorded for the asset, keyed by its path
        pub = _publish.load_published(Path(self._state) / "published.json")
        self.assertIn(_publish.published_asset_key(self.asset), pub)
        self.assertEqual(pub[_publish.published_asset_key(self.asset)]["url"], _FAKE_URL)

    def test_publish_live_mode_deterministic_worker(self):
        # S26 — asset publish uses dak LIVE mode with a DETERMINISTIC worker slug
        # derived from the file (no random suffix), records that worker, and is
        # idempotent (SAME file → SAME worker on republish).
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(d["mode"], "live")
        self.assertEqual(d["worker"], "report")   # loose doc at root → bare stem
        dak = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertIn("--mode", dak)
        self.assertEqual(dak[dak.index("--mode") + 1], "live")
        self.assertEqual(dak[dak.index("--slug") + 1], "report")
        # recorded published-state carries the stable worker (revoke uses it).
        pub = _publish.load_published(Path(self._state) / "published.json")
        entry = pub[_publish.published_asset_key(self.asset)]
        self.assertEqual(entry["worker"], "report")
        self.assertEqual(entry["mode"], "live")

    def test_publish_gate_refuses_unreviewed_findings(self):
        # No redact_indices key and no review flag → the findings gate refuses,
        # and dak is never spawned.
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish", {"path": "report.md"})
        self.assertEqual(status, 403)
        self.assertEqual(d.get("error"), "unreviewed_findings")
        self.assertTrue(d["findings"])
        self.assertEqual(fake.calls, [])

    def test_publish_dak_unavailable(self):
        # Point _PKG_ROOT at a tree with no bundled dak → clean JSON error.
        with patch.object(server, "_PKG_ROOT", Path(self._state)):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True})
        self.assertFalse(d.get("ok", True))
        self.assertEqual(d.get("error"), "dak_unavailable")

    def test_publish_dak_failure(self):
        fake = _fake_dak(rc=1, stderr="Not configured. Run: dak setup\n")
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True})
        self.assertFalse(d.get("ok", True))
        self.assertEqual(d.get("error"), "publish_failed")
        self.assertIn("Not configured", d.get("detail", ""))

    def test_publish_private_refuses(self):
        with patch.object(server.config, "load_config", lambda *a, **k: {"private": True}):
            status, d = _post(self._port, "/_publish", {"path": "report.md"})
        self.assertEqual(status, 403)
        self.assertEqual(d.get("error"), "private")

    def test_publish_dry_run_body_flag(self):
        # S14 / #3 — body dryRun:true → response carries dryRun:true (honest;
        # dak invoked with --dry-run, nothing uploaded).
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True, "dryRun": True})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertTrue(d["dryRun"])
        dak_cmd = next(c for c in fake.calls if any("dak.py" in str(x) for x in c))
        self.assertIn("--dry-run", dak_cmd)

    def test_publish_dry_run_env_var(self):
        # HUB_PUBLISH_DRYRUN=1 forces dryRun even without the body flag.
        fake = _fake_dak()
        with patch.dict(os.environ, {"HUB_PUBLISH_DRYRUN": "1"}), \
             patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True})
        self.assertEqual(status, 200)
        self.assertTrue(d["dryRun"])

    def test_publish_non_dry_run_reports_false(self):
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "report.md", "review": True})
        self.assertEqual(status, 200)
        self.assertFalse(d["dryRun"])

    def test_publish_non_artifact_doc(self):
        # S14 / #6 — a plain doc that is NOT a task artifact publishes fine; the
        # endpoint is path-based (+ containment-guarded), not task-scoped.
        docs = Path(self._scan_root) / "docs"
        docs.mkdir(exist_ok=True)
        doc = docs / "guide.md"
        doc.write_text("# Guide\nnothing secret here\n", encoding="utf-8")
        fake = _fake_dak()
        with patch.object(server.subprocess, "run", fake):
            status, d = _post(self._port, "/_publish",
                              {"path": "docs/guide.md", "review": True})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertEqual(d["url"], _FAKE_URL)
        self.assertIn("dryRun", d)
        # dak received a path (no task-only rejection anywhere)
        self.assertTrue(any(any("dak.py" in str(x) for x in c) for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
