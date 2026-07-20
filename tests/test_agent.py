"""Tests for the shared `hub agent` launchd plist generation (cli/agent.py).

Only the pure plist rendering + exec resolution is unit-tested here; the
launchctl bootstrap/bootout path is exercised end-to-end by the distribution
e2e scripts (macOS only), not in CI.
"""
import unittest

from hubspace.cli import agent


class RenderPlistTest(unittest.TestCase):
    def test_serve_agent_is_keepalive_no_interval(self):
        xml = agent._render_plist(
            "com.user.hub-agent",
            ["/abs/uv", "tool", "run", "--from", "/w.whl", "hub", "serve", "--port", "8787"],
            "/scan",
            keepalive=True, interval=None, env={},
        )
        self.assertIn("<key>KeepAlive</key><true/>", xml)
        self.assertNotIn("StartInterval", xml)
        self.assertIn("<string>com.user.hub-agent</string>", xml)
        self.assertIn("<key>WorkingDirectory</key><string>/scan</string>", xml)
        # every launcher token becomes its own <string>
        self.assertIn("<string>serve</string>", xml)
        self.assertIn("<string>--port</string>", xml)

    def test_rebuild_agent_is_interval_with_env(self):
        xml = agent._render_plist(
            "com.user.hub",
            ["/abs/hub"],
            "/proj",
            keepalive=False, interval=120, env={"HUB_SERVER_PORT": "8787"},
        )
        self.assertIn("<key>StartInterval</key><integer>120</integer>", xml)
        self.assertNotIn("KeepAlive", xml)
        self.assertIn("<key>EnvironmentVariables</key>", xml)
        self.assertIn("<key>HUB_SERVER_PORT</key><string>8787</string>", xml)

    def test_paths_and_labels_are_xml_escaped(self):
        xml = agent._render_plist(
            "com.a&b",
            ["/x/uv", "--from", "/weird & dir/w.whl"],
            "/w & d",
            keepalive=True, interval=None, env={},
        )
        self.assertIn("com.a&amp;b", xml)
        self.assertIn("/weird &amp; dir/w.whl", xml)
        self.assertNotIn("& dir", xml.replace("&amp;", ""))  # no raw ampersands

    def test_default_exec_resolves_to_hub_or_module(self):
        toks = agent._default_exec()
        self.assertTrue(toks)
        # either a resolved `hub` on PATH, or `<python> -m hubspace.cli.hub`
        resolved_hub = len(toks) == 1 and toks[0].endswith("hub")
        module_form = toks[1:] == ["-m", "hubspace.cli.hub"]
        self.assertTrue(resolved_hub or module_form, toks)


if __name__ == "__main__":
    unittest.main()
