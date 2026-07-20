"""Tests for config.py — hub.toml parsing and scan-root/port/view resolution."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace.core import config


class TempDirMixin(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_toml(self, text: str) -> Path:
        (self.dir / "hub.toml").write_text(text, encoding="utf-8")
        return self.dir


class TestLoadConfig(TempDirMixin):
    def test_missing_file_returns_empty(self):
        self.assertEqual(config.load_config(self.dir), {})

    def test_malformed_toml_returns_empty(self):
        self.write_toml("this is = = not valid toml [[[")
        self.assertEqual(config.load_config(self.dir), {})

    def test_hub_table_keys(self):
        self.write_toml('[hub]\nscan_root = "~/docs"\nport = 9000\n')
        cfg = config.load_config(self.dir)
        self.assertEqual(cfg["scan_root"], "~/docs")
        self.assertEqual(cfg["port"], 9000)

    def test_top_level_keys_accepted(self):
        self.write_toml('scan_root = "/data"\n')
        self.assertEqual(config.load_config(self.dir)["scan_root"], "/data")

    def test_hub_table_overrides_top_level(self):
        self.write_toml('port = 1\n[hub]\nport = 2\n')
        self.assertEqual(config.load_config(self.dir)["port"], 2)


class TestResolveScanRoot(TempDirMixin):
    def setUp(self):
        super().setUp()
        self.sidecar = self.dir / ".scan_root"

    def test_flag_wins(self):
        with patch.dict(os.environ, {"HUB_SCAN_ROOT": "/from/env"}):
            got = config.resolve_scan_root({"scan_root": "/from/cfg"}, self.sidecar, flag="~/flag")
        self.assertEqual(got, Path("~/flag").expanduser())

    def test_env_beats_config_and_sidecar(self):
        self.sidecar.write_text("/from/sidecar", encoding="utf-8")
        with patch.dict(os.environ, {"HUB_SCAN_ROOT": "/from/env"}):
            got = config.resolve_scan_root({"scan_root": "/from/cfg"}, self.sidecar)
        self.assertEqual(got, Path("/from/env"))

    def test_config_beats_sidecar(self):
        self.sidecar.write_text("/from/sidecar", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            got = config.resolve_scan_root({"scan_root": "/from/cfg"}, self.sidecar)
        self.assertEqual(got, Path("/from/cfg"))

    def test_sidecar_used_when_no_env_or_config(self):
        self.sidecar.write_text("/from/sidecar", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            got = config.resolve_scan_root({}, self.sidecar)
        self.assertEqual(got, Path("/from/sidecar"))

    def test_falls_back_to_cwd(self):
        with patch.dict(os.environ, {}, clear=True):
            got = config.resolve_scan_root({}, self.sidecar)
        self.assertEqual(got, Path.cwd())

    def test_blank_config_scan_root_ignored(self):
        with patch.dict(os.environ, {}, clear=True):
            got = config.resolve_scan_root({"scan_root": "   "}, self.sidecar)
        self.assertEqual(got, Path.cwd())


class TestResolvePort(unittest.TestCase):
    def test_env_wins(self):
        with patch.dict(os.environ, {"HUB_SERVER_PORT": "1234"}):
            self.assertEqual(config.resolve_port({"port": 9000}), "1234")

    def test_config_int(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.resolve_port({"port": 9000}), "9000")

    def test_config_numeric_string(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.resolve_port({"port": "9000"}), "9000")

    def test_empty_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.resolve_port({}), "")

    def test_non_numeric_string_ignored(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.resolve_port({"port": "abc"}), "")


class TestExcludeDirs(unittest.TestCase):
    def test_list_of_strings(self):
        self.assertEqual(config.config_exclude_dirs({"exclude_dirs": ["a", "b"]}), {"a", "b"})

    def test_non_list_ignored(self):
        self.assertEqual(config.config_exclude_dirs({"exclude_dirs": "a"}), set())

    def test_filters_non_strings_and_empties(self):
        self.assertEqual(config.config_exclude_dirs({"exclude_dirs": ["a", "", 3, None]}), {"a"})

    def test_missing_key(self):
        self.assertEqual(config.config_exclude_dirs({}), set())


class TestDefaultView(unittest.TestCase):
    def test_valid_views(self):
        for v in ("work", "list", "board", "calendar"):
            self.assertEqual(config.resolve_default_view({"default_view": v}), v)

    def test_activity_view_removed(self):
        # 'activity' was removed as a view; it should now be rejected.
        self.assertEqual(config.resolve_default_view({"default_view": "activity"}), "")

    def test_invalid_view_returns_empty(self):
        self.assertEqual(config.resolve_default_view({"default_view": "kanban"}), "")

    def test_missing_returns_empty(self):
        self.assertEqual(config.resolve_default_view({}), "")


if __name__ == "__main__":
    unittest.main()
