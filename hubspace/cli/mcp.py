"""Hand-rolled MCP stdio server over the read-only hub index (roadmap 1h).

MCP's stdio transport is newline-delimited JSON-RPC 2.0 — one JSON message per
line on stdin, one per line on stdout (NOT Content-Length framed). This module
implements:

  - handle(request, conn) — a pure dispatcher (unit-testable without real stdio).
  - serve(stdin, stdout)  — the read loop, guarded behind the CLI entry.

Tools are thin wrappers over hubspace.core.query (the single source of truth
shared with the `hub trace` / `hub timeline` CLI verbs). Stdlib-only; one
read-only DB connection is opened for the process lifetime.
"""
from __future__ import annotations

import json
import sys

from .. import __version__
from ..core import query

_PROTOCOL_VERSION = "2024-11-05"

# JSON-RPC 2.0 error codes.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

_TOOLS = [
    {
        "name": "search",
        "description": "Full-text search across the hub index. Returns matching "
                       "files with path, repo, kind, title and a snippet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "FTS5 search query."},
                "kind": {"type": "string",
                         "description": "Optional kind filter "
                                        "(task, run, artifact, doc, md, …)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_task",
        "description": "Fetch one task manifest: status, title, plan checklist, "
                       "notes, runs and artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Task slug (kebab-case)."},
                "repo": {"type": "string", "description": "Optional owning repo."},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "trace",
        "description": "Lineage graph around one file: its task, up/down edges "
                       "and siblings. Accepts an absolute or scan-root-relative path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "timeline",
        "description": "Task timeline as a nodes+edges graph (the 2b JSON "
                       "contract) — no layout, just structure and dates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Task slug (kebab-case)."},
                "repo": {"type": "string", "description": "Optional owning repo."},
            },
            "required": ["slug"],
        },
    },
]


def _ok(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _call_tool(name: str, args: dict, conn) -> dict | None:
    """Dispatch a tool name to its query function. None → unknown tool."""
    args = args or {}
    if name == "search":
        return query.search(conn, args.get("query", ""),
                            kind=args.get("kind"), limit=int(args.get("limit", 20)))
    if name == "get_task":
        return query.get_task(conn, args.get("slug", ""), repo=args.get("repo"))
    if name == "trace":
        return query.trace(conn, args.get("path", ""))
    if name == "timeline":
        return query.timeline(conn, args.get("slug", ""), repo=args.get("repo"))
    return None


def handle(request: dict, conn=None) -> dict | None:
    """Dispatch one JSON-RPC request. Returns a response dict, or None for
    notifications (no `id`). Never raises on bad input — returns an error object."""
    if not isinstance(request, dict):
        return _err(None, _INVALID_REQUEST, "Invalid request")

    method = request.get("method")
    req_id = request.get("id")
    is_notification = "id" not in request

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hub", "version": __version__},
        })

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _ok(req_id, {"tools": _TOOLS})

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        result = _call_tool(name, args, conn)
        if result is None:
            return _err(req_id, _INVALID_PARAMS, f"Unknown tool: {name!r}")
        return _ok(req_id, {"content": [{"type": "text",
                                         "text": json.dumps(result)}]})

    # Unknown method: a notification gets no response; a request gets an error.
    if is_notification:
        return None
    return _err(req_id, _METHOD_NOT_FOUND, f"Method not found: {method!r}")


def serve(stdin=None, stdout=None, db_path=None) -> None:
    """Run the newline-delimited JSON-RPC loop over stdio.

    Opens ONE read-only DB connection for the process lifetime. A bad input line
    yields a JSON-RPC parse error and never crashes the loop.
    """
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    conn = query.connect(db_path)

    def _write(obj: dict) -> None:
        stdout.write(json.dumps(obj) + "\n")
        stdout.flush()

    try:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                _write(_err(None, _PARSE_ERROR, "Parse error"))
                continue
            try:
                response = handle(request, conn)
            except Exception as exc:  # never let one bad request kill the server
                rid = request.get("id") if isinstance(request, dict) else None
                _write(_err(rid, _INTERNAL_ERROR, f"Internal error: {exc}"))
                continue
            if response is not None:
                _write(response)
    finally:
        if conn is not None:
            conn.close()
