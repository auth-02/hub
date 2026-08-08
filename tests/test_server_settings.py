"""Tests for the S15 Settings endpoints — GET/POST /_settings.

Workspace prefs are written to hub.toml (config.config_path, redirected to a
temp file here); Cloudflare creds go ONLY to ~/.dak/config.json (redirected via
HUB_DAK_CONFIG). The API token is MASKED on GET and must never land in hub.toml.
subprocess.run is stubbed so a POST's rebuild never spawns a real hub build.
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
from hubspace.core import config


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(port: int, path: str, timeout: float = 10.0):
    req = urllib.request.Request(f"http://localhost:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


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


def _fake_run(cmd, *a, **kw):
    # Stand in for the index rebuild — never spawn a real build / hit the net.
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


class TestSettingsEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._port = _free_port()
        cls._scan_root = tempfile.mkdtemp()
        cls._state = tempfile.mkdtemp()
        cls._cfgdir = tempfile.mkdtemp()
        cls._dakdir = tempfile.mkdtemp()
        cls._toml = Path(cls._cfgdir) / "hub.toml"
        cls._dak = Path(cls._dakdir) / ".dak" / "config.json"

        cls._patchers = [
            patch.object(server, "_SIDECAR", Path(cls._state) / ".scan_root"),
            patch.object(server, "_DB_PATH", Path(cls._state) / "hub.db"),
            patch.object(server.config, "state_dir", lambda: Path(cls._state)),
            # Redirect the two write sinks off the real filesystem locations.
            patch.object(server.config, "config_path", lambda: cls._toml),
            patch.object(server.config, "dak_config_path", lambda: cls._dak),
            patch.object(server.subprocess, "run", _fake_run),
        ]
        for p in cls._patchers:
            p.start()

        server._active_root = Path(cls._scan_root)
        server.SCAN_ROOT = Path(cls._scan_root)
        server.HubHandler.server_port = cls._port

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
        for d in (cls._scan_root, cls._state, cls._cfgdir, cls._dakdir):
            shutil.rmtree(d, ignore_errors=True)

    def setUp(self):
        # Fresh config files per test.
        if self._toml.exists():
            self._toml.unlink()
        if self._dak.exists():
            self._dak.unlink()

    # ── GET ──────────────────────────────────────────────────────────────────
    def test_get_shape_and_scan_root(self):
        status, d = _get(self._port, "/_settings")
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        self.assertIn("default_view", d["hub"])
        self.assertEqual(d["hub"]["scan_root"], str(server._active_root))
        self.assertIn("api_token_set", d["dak"])
        self.assertNotIn("api_token", d["dak"])

    def test_get_masks_token(self):
        config.write_dak_config({"api_token": "super-secret-value",
                                 "account_id": "acc"})
        status, d = _get(self._port, "/_settings")
        self.assertEqual(status, 200)
        self.assertIs(d["dak"]["api_token_set"], True)
        self.assertEqual(d["dak"]["account_id"], "acc")
        # The real token value never crosses the wire.
        self.assertNotIn("super-secret-value", json.dumps(d))

    # ── POST hub.toml ─────────────────────────────────────────────────────────
    def test_post_writes_hub_prefs(self):
        status, d = _post(self._port, "/_settings", {"hub": {
            "default_view": "board", "port": 8181,
            "exclude_dirs": "vendor, fixtures", "upload_exts": ".pdf .csv",
            "private": True,
        }})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])
        cfg = config.load_config(self._toml.parent)
        self.assertEqual(config.resolve_default_view(cfg), "board")
        self.assertEqual(cfg["port"], 8181)
        self.assertEqual(config.config_exclude_dirs(cfg), {"vendor", "fixtures"})
        self.assertTrue(config.is_private(cfg))

    def test_post_rejects_bad_view(self):
        status, d = _post(self._port, "/_settings", {"hub": {"default_view": "kanban"}})
        self.assertEqual(status, 400)
        self.assertEqual(d["error"], "invalid_view")

    def test_post_rejects_bad_port(self):
        status, d = _post(self._port, "/_settings", {"hub": {"port": "not-a-number"}})
        self.assertEqual(status, 400)
        self.assertEqual(d["error"], "invalid_port")

    def test_port_change_flags_restart_note(self):
        status, d = _post(self._port, "/_settings", {"hub": {"port": 9099}})
        self.assertEqual(status, 200)
        self.assertTrue(any("restart" in n.lower() for n in d["notes"]))

    # ── POST dak creds ─────────────────────────────────────────────────────────
    def test_post_dak_goes_to_dak_only_not_hub(self):
        status, d = _post(self._port, "/_settings", {
            "hub": {"port": 8282},
            "dak": {"api_token": "TOKEN-XYZ", "account_id": "acct1",
                    "subdomain": "atharva-dak"},
        })
        self.assertEqual(status, 200)
        # Token landed in ~/.dak/config.json ...
        dak = config.read_dak_config()
        self.assertEqual(dak["api_token"], "TOKEN-XYZ")
        self.assertEqual(dak["subdomain"], "atharva-dak")
        # ... and NEVER in hub.toml.
        self.assertTrue(self._toml.exists())
        toml_text = self._toml.read_text(encoding="utf-8")
        self.assertNotIn("TOKEN-XYZ", toml_text)
        self.assertNotIn("api_token", toml_text)

    def test_masked_submit_keeps_existing_token(self):
        config.write_dak_config({"api_token": "original-token", "account_id": "a1"})
        # Re-save with the mask sentinel + a new account id.
        status, d = _post(self._port, "/_settings", {
            "dak": {"api_token": config.DAK_MASK, "account_id": "a2"},
        })
        self.assertEqual(status, 200)
        dak = config.read_dak_config()
        self.assertEqual(dak["api_token"], "original-token")  # untouched
        self.assertEqual(dak["account_id"], "a2")             # updated

    def test_empty_submit_keeps_existing_token(self):
        config.write_dak_config({"api_token": "original-token"})
        status, d = _post(self._port, "/_settings", {"dak": {"api_token": "",
                                                             "account_id": "b"}})
        self.assertEqual(status, 200)
        self.assertEqual(config.read_dak_config()["api_token"], "original-token")


if __name__ == "__main__":
    unittest.main()
