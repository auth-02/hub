"""Tests for cli/mcp.py — the JSON-RPC 2.0 dispatcher and stdio loop."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hubspace import __version__
from hubspace.cli import mcp
from hubspace.core import db

_TS = time.mktime((2026, 7, 22, 12, 0, 0, 0, 0, -1))


def _seed_conn():
    tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    conn = db.open_db(Path(tf.name))
    meta = {"abs": "/r/cortex/tasks/t/manifest.md", "repo": "cortex",
            "rel": "tasks/t/manifest.md", "ext": "md", "kind": "task",
            "mtime": _TS, "task_slug": "t", "task_repo": "cortex",
            "skill_slug": None, "skill_repo": None}
    db.upsert(conn, meta, "T Title", "searchable manifest body")
    conn.commit()
    db.build_lineage(conn)
    return conn, tf.name


class TestHandle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn, cls.name = _seed_conn()

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        os.unlink(cls.name)

    def test_initialize(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(resp["result"]["protocolVersion"], "2024-11-05")
        self.assertEqual(resp["result"]["serverInfo"]["name"], "hub")
        self.assertEqual(resp["result"]["serverInfo"]["version"], __version__)
        self.assertIn("tools", resp["result"]["capabilities"])

    def test_initialized_notification_returns_none(self):
        resp = mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIsNone(resp)

    def test_tools_list(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = resp["result"]["tools"]
        self.assertGreaterEqual(len(tools), 3)
        names = {t["name"] for t in tools}
        self.assertTrue({"search", "get_task", "trace"} <= names)
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_tools_call_search(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "search",
                                      "arguments": {"query": "searchable"}}},
                          self.conn)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        self.assertTrue(any(r["title"] == "T Title" for r in data))

    def test_tools_call_get_task(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                           "params": {"name": "get_task",
                                      "arguments": {"slug": "t"}}}, self.conn)
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["slug"], "t")

    def test_tools_call_trace(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                           "params": {"name": "trace",
                                      "arguments": {"path": "tasks/t/manifest.md"}}},
                          self.conn)
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["kind"], "task")

    def test_tools_call_timeline(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                           "params": {"name": "timeline",
                                      "arguments": {"slug": "t"}}}, self.conn)
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["task"], "t")
        self.assertTrue(data["nodes"])

    def test_unknown_tool_errors(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                           "params": {"name": "nope", "arguments": {}}}, self.conn)
        self.assertEqual(resp["error"]["code"], -32602)

    def test_unknown_method_errors(self):
        resp = mcp.handle({"jsonrpc": "2.0", "id": 8, "method": "does/not/exist"})
        self.assertEqual(resp["error"]["code"], -32601)


class TestServeLoop(unittest.TestCase):
    def test_stdio_loop_and_parse_error(self):
        conn, name = _seed_conn()
        conn.close()  # serve() opens its own read-only connection
        try:
            lines = "\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                "this is not json",
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]) + "\n"
            stdin = io.StringIO(lines)
            stdout = io.StringIO()
            mcp.serve(stdin, stdout, db_path=name)
            out = [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]
            # initialize result + parse error + tools/list result
            # (the notification produces no output)
            self.assertEqual(out[0]["id"], 1)
            self.assertTrue(any(o.get("error", {}).get("code") == -32700 for o in out))
            self.assertTrue(any("tools" in o.get("result", {}) for o in out))
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main()
