#!/usr/bin/env python3
"""
server.py — serve hub's scan root, rendering .md files on request.

Usage:
    python3 server.py              # default port 8787
    python3 server.py --port 9000
    HUB_SERVER_PORT=9000 python3 server.py

Rebuild after starting so links use localhost:
    HUB_SERVER_PORT=8787 python3 hub.py
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import re
import socketserver
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote, unquote

# ── Scan root resolution (shared with hub.py via config.py) ─────────────────
_HERE = Path(__file__).resolve().parent
_PKG_ROOT = _HERE.parent  # hubspace/ (package root)
from .. import __version__
from ..core import config
from ..utils.paths import is_within
from ..utils.text import esc_html, slugify
from ..render import (
    _render_md, _render_csv, _render_xlsx, _inject_into_html,
    _render_lineage_html, _favicon_href, _CSS, _DOC_CHROME_CSS, _PAGE, _add_outline,
    draw_page_html, doc_menu, DOC_PDF_ITEM,
)


def _state_dir() -> Path:
    """XDG_STATE_HOME/hub, falling back to ~/.local/state/hub."""
    return config.state_dir()


_SIDECAR = _state_dir() / ".scan_root"
_DB_PATH = _state_dir() / "hub.db"

# Serialize hub.py rebuilds so the watcher and request-triggered rebuilds
# (/_set-root, /_rebuild, /_task-status) never run two writers at once.
_REBUILD_LOCK = threading.Lock()


def _get_lineage(abs_path: str) -> list:
    """Return lineage links for abs_path from hub.db (empty list if DB missing or file unknown)."""
    try:
        if not _DB_PATH.exists():
            return []
        conn = sqlite3.connect(f"file:{_DB_PATH}?mode=ro", uri=True)
        rows = conn.execute(
            """SELECT f2.abs, f2.rel, f2.kind, l.rel_type
               FROM lineage l
               JOIN files f1 ON f1.id = l.src_id
               JOIN files f2 ON f2.id = l.dst_id
               WHERE f1.abs = ?""",
            (abs_path,),
        ).fetchall()
        conn.close()
        return [{"a": r[0], "p": r[1], "k": r[2] or "", "r": r[3]} for r in rows]
    except Exception:
        return []



def _resolve_scan_root() -> Path:
    """flag > HUB_SCAN_ROOT env > hub.toml > .scan_root sidecar > CWD (see config.py)."""
    return config.resolve_scan_root(config.load_config(), _SIDECAR)


SCAN_ROOT = _resolve_scan_root()
_active_root: Path = SCAN_ROOT  # updated by _set_root(); used by rebuild + watcher


def _safe_draw_stem(name) -> str:
    """Sanitize a user-supplied diagram name into a safe filename stem.

    Drops path separators and a trailing ``.excalidraw``, keeps only
    alphanumerics/space/dash/underscore, caps length, and falls back to a
    timestamp slug when the result is empty.
    """
    if name:
        name = str(name).strip()
        if name.lower().endswith(".excalidraw"):
            name = name[: -len(".excalidraw")]
        name = "".join(c for c in name if c.isalnum() or c in " -_").strip()[:80]
        if name:
            return name
    return "drawing-" + time.strftime("%Y%m%d-%H%M%S")


class HubHandler(http.server.BaseHTTPRequestHandler):
    server_port: int = 8787

    def do_GET(self) -> None:
        url_path = unquote(self.path.split("?")[0])

        # Rebuild trigger
        if url_path == "/_rebuild":
            self._run_rebuild()
            return

        # Blank Excalidraw canvas (new, unsaved diagram)
        if url_path == "/draw":
            html_page = draw_page_html(None, None, self.__class__.server_port)
            self._send(200, "text/html; charset=utf-8", html_page.encode("utf-8"))
            return

        # Root → hub index
        if url_path in ("/", ""):
            docs = config.output_path()
            if docs.exists():
                self._send(200, "text/html; charset=utf-8", docs.read_bytes())
            else:
                self._send(404, "text/plain", b"docs-index.html not found - run hub first.")
            return

        # Static hub assets (CSS, JS, favicon, etc.)
        if url_path.startswith("/static/"):
            static_root = config.static_dir().resolve()
            asset = (static_root / url_path[len("/static/"):]).resolve()
            if not is_within(asset, static_root):
                self._send(403, "text/plain", b"Forbidden")
                return
            if not asset.exists():
                self._send(404, "text/plain", b"Not found")
                return
            ext = asset.suffix.lower()
            mime = {"css": "text/css", "js": "application/javascript",
                    "svg": "image/svg+xml"}.get(ext.lstrip("."), "application/octet-stream")
            self._send(200, mime, asset.read_bytes())
            return

        fs_path = Path(url_path)

        # Absolute path from hub _href() → use directly.
        # Relative/short path (e.g. after replaceState rewrites URL) →
        # resolve against active scan root.
        if not fs_path.is_absolute() or not fs_path.exists():
            candidate = _active_root / url_path.lstrip("/")
            if candidate.exists():
                fs_path = candidate

        # Security: must be within scan root or hub directory
        resolved = fs_path.resolve()
        if not (
            is_within(resolved, _active_root.resolve())
            or is_within(resolved, _PKG_ROOT.resolve())
        ):
            self._send(403, "text/plain", b"Forbidden")
            return

        if not fs_path.exists():
            self._send(404, "text/plain", f"Not found: {fs_path}".encode())
            return

        if fs_path.is_dir():
            self._serve_dir(fs_path, url_path)
        elif fs_path.suffix.lower() == ".excalidraw":
            # Open the vault's .excalidraw file in the Excalidraw canvas.
            try:
                rel = str(fs_path.resolve().relative_to(_active_root.resolve()).as_posix())
            except ValueError:
                rel = str(fs_path)
            scene_text = fs_path.read_text(encoding="utf-8", errors="replace")
            html_page = draw_page_html(rel, scene_text, self.__class__.server_port)
            self._send(200, "text/html; charset=utf-8", html_page.encode("utf-8"))
        elif fs_path.suffix.lower() == ".md":
            self._serve_md(fs_path)
        elif fs_path.suffix.lower() in (".html", ".htm"):
            src = fs_path.read_text(encoding="utf-8", errors="replace")
            links = _get_lineage(str(fs_path.resolve()))
            lineage_html = _render_lineage_html(links, self.__class__.server_port) if links else ""
            src = _inject_into_html(src, lineage_html, _favicon_href(self.__class__.server_port))
            self._send(200, "text/html; charset=utf-8", src.encode("utf-8"))
        elif fs_path.suffix.lower() == ".txt":
            src = fs_path.read_text(encoding="utf-8", errors="replace")
            escaped = src.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            self._serve_page(fs_path.name, fs_path, f"<pre><code>{escaped}</code></pre>")
        elif fs_path.suffix.lower() in (".csv", ".tsv"):
            self._serve_page(fs_path.name, fs_path, _render_csv(fs_path))
        elif fs_path.suffix.lower() == ".xlsx":
            self._serve_page(fs_path.name, fs_path, _render_xlsx(fs_path))
        elif fs_path.suffix.lower() == ".pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", "inline")
            body = fs_path.read_bytes()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            ct, _ = mimetypes.guess_type(str(fs_path))
            self._send(200, ct or "application/octet-stream", fs_path.read_bytes())

    def do_POST(self) -> None:
        url_path = unquote(self.path.split("?")[0])
        if url_path == "/_set-root":
            length = int(self.headers.get("Content-Length", 0))
            new_root = self.rfile.read(length).decode("utf-8").strip()
            self._set_root(new_root)
        elif url_path == "/draw/save":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                self._save_draw(body.get("rel"), body.get("scene"), body.get("dir"), body.get("name"))
            except (ValueError, KeyError) as e:
                self._send(400, "text/plain", str(e).encode())
        elif url_path == "/_task-status":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                task_slug = body["task_slug"]
                task_repo = body["task_repo"]
                status = body["status"]
                if status not in ("ongoing", "completed", "paused"):
                    self._send(400, "text/plain", b"invalid status")
                    return
                from ..core import db as _db
                conn = sqlite3.connect(str(_DB_PATH), timeout=30)
                _db.set_status(conn, task_slug, task_repo, status)
                conn.close()
                # Regenerate the HTML so TASKS_DATA baked into the page reflects
                # the new status immediately when the client reloads.
                result = self._rebuild(_active_root)
                if result.returncode != 0:
                    # DB write succeeded; log the rebuild error but still return ok
                    # so the client reloads and at least shows the sidecar status.
                    import sys as _sys2
                    print(result.stderr or result.stdout, file=_sys2.stderr)
                self._send(200, "text/plain", b"ok")
            except Exception as e:
                self._send(400, "text/plain", str(e).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def _set_root(self, new_root: str) -> None:
        global _active_root
        p = Path(new_root).expanduser().resolve()
        if not p.is_dir():
            self._send(400, "text/plain", b"Not a directory")
            return
        try:
            _SIDECAR.write_text(str(p), encoding="utf-8")
        except OSError as e:
            self._send(500, "text/plain", str(e).encode())
            return
        _active_root = p
        result = self._rebuild(p)
        if result.returncode == 0:
            self._send(200, "text/plain", b"ok")
        else:
            self._send(500, "text/plain", result.stderr.encode())

    def _save_draw(self, rel, scene, dir_=None, name=None) -> None:
        """Persist an Excalidraw scene into the vault.

        rel   — vault-relative path of an existing file to overwrite (falsy → a new
                file). Must carry the .excalidraw ext.
        scene — the scene object (JSON-serializable) to write.
        dir_  — for a NEW file, the vault-relative directory to create it in (e.g.
                a task's ``tasks/<slug>/draws``). Falsy → the scan root. Created if
                missing. Ignored when ``rel`` is given.
        name  — for a NEW file, the user-chosen base name (sanitized to a safe
                filename; falls back to a timestamp slug). A colliding name gets a
                ``-N`` suffix so we never clobber an existing diagram.

        Everything must stay inside the active scan root. The file lands there, so
        the watcher reindexes it on its next tick — no explicit rebuild here.
        """
        if scene is None:
            self._send(400, "text/plain", b"missing scene")
            return
        root = _active_root.resolve()
        if rel:
            target = (root / rel).resolve()
            if target.suffix.lower() != ".excalidraw":
                self._send(400, "text/plain", b"not an .excalidraw path")
                return
            if not is_within(target, root):
                self._send(403, "text/plain", b"Forbidden")
                return
        else:
            base = root
            if dir_:
                base = (root / dir_).resolve()
                if not is_within(base, root):
                    self._send(403, "text/plain", b"Forbidden")
                    return
            stem = _safe_draw_stem(name)
            target = (base / f"{stem}.excalidraw").resolve()
            n = 2
            while target.exists():  # don't overwrite a different diagram
                target = (base / f"{stem}-{n}.excalidraw").resolve()
                n += 1
            if not is_within(target, root):
                self._send(403, "text/plain", b"Forbidden")
                return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(scene), encoding="utf-8")
        except OSError as e:
            self._send(500, "text/plain", str(e).encode())
            return
        out_rel = target.relative_to(root).as_posix()
        self._send(200, "application/json", json.dumps({"ok": True, "rel": out_rel}).encode())

    def _run_rebuild(self) -> None:
        result = self._rebuild(_active_root)
        if result.returncode == 0:
            self._send(200, "text/plain", b"ok")
        else:
            self._send(500, "text/plain", result.stderr.encode())

    @staticmethod
    def _rebuild(root: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["HUB_SERVER_PORT"] = str(HubHandler.server_port)
        env["HUB_SCAN_ROOT"] = str(root)
        # Ensure `-m hubspace.cli.hub` resolves regardless of the child's CWD
        # (installed: already importable; dev: package parent on PYTHONPATH).
        _pkg_parent = str(_PKG_ROOT.parent)
        env["PYTHONPATH"] = (
            _pkg_parent + os.pathsep + env["PYTHONPATH"]
            if env.get("PYTHONPATH") else _pkg_parent
        )
        with _REBUILD_LOCK:
            try:
                return subprocess.run(
                    [sys.executable, "-m", "hubspace.cli.hub"],
                    env=env, capture_output=True, text=True,
                    timeout=600,
                )
            except subprocess.TimeoutExpired as exc:
                exc.kill()
                return subprocess.CompletedProcess(exc.args, 1, "", "hub timed out after 600 s")

    def _serve_md(self, path: Path) -> None:
        src = path.read_text(encoding="utf-8", errors="replace")
        body = _render_md(src)
        self._serve_page(path.name, path, body)

    def _serve_dir(self, path: Path, url_path: str) -> None:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        rows: list[str] = []

        parent = str(Path(url_path).parent)
        if url_path != str(SCAN_ROOT):
            rows.append(f'<li><a href="{parent}">↑ ../</a></li>')

        for entry in entries:
            if entry.is_dir():
                icon, href = "📁", str(Path(url_path) / entry.name) + "/"
                ext_html = ""
            else:
                icon = "📝" if entry.suffix.lower() in (".md", ".txt") else "📄"
                href = str(Path(url_path) / entry.name)
                ext_html = f'<span class="ext">{entry.suffix}</span>' if entry.suffix else ""
            rows.append(
                f'<li><a href="{href}">{icon} {entry.name}{ext_html}</a></li>'
            )

        body = f"<ul class='dir-list'>{''.join(rows)}</ul>"
        self._serve_page(url_path, path, body)

    def _serve_page(self, title: str, path: Path, body: str) -> None:
        try:
            rel = path.resolve().relative_to(_active_root.resolve())
            parts = [_active_root.name] + list(rel.parts)
            nav_html = f'<nav>{" / ".join(parts)}</nav>'
        except ValueError:
            nav_html = ""

        # Outline is a sibling of .page (a direct child of <body>) so the
        # wide-screen grid (body.with-outline) can place it in its own column.
        # Nesting it inside .page made it overlap the document text.
        body, outline = _add_outline(body)

        links = _get_lineage(str(path.resolve()))
        lineage_html = _render_lineage_html(links, self.__class__.server_port)

        if lineage_html:
            m = re.search(r"</h1>", body)
            if m:
                body = body[:m.end()] + lineage_html + body[m.end():]
            else:
                body = lineage_html + body

        # Floating ⋯ actions menu (top-right). Task manifests also get a "New draw"
        # item that opens a blank canvas scoped to this task's draws/ folder.
        menu_items = []
        if path.name.lower() == "manifest.md" and path.parent.parent.name == "tasks":
            try:
                draws_rel = (path.parent / "draws").resolve().relative_to(
                    _active_root.resolve()
                ).as_posix()
                href = "/draw?dir=" + quote(draws_rel, safe="/")
                menu_items.append(
                    f'<a class="doc-menu-item" href="{esc_html(href)}" target="_blank" '
                    f'rel="noopener" title="New Excalidraw diagram in this task">'
                    f'<span class="pencil">✏︎</span> New draw</a>'
                )
            except ValueError:
                pass
        menu_items.append(DOC_PDF_ITEM)
        body = doc_menu(menu_items) + body

        html = _PAGE.format(
            title=title,
            css=_CSS + _DOC_CHROME_CSS,
            nav=nav_html,
            body=body,
            outline=outline,
            body_class="with-outline" if outline else "",
            favicon=_favicon_href(self.__class__.server_port),
        ).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", html)

    def _send(self, code: int, ct: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"  {fmt % args}")


# ── File watcher ────────────────────────────────────────────────────────────

_WATCH_EXCLUDE = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".next", "dist", "build", ".turbo", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", ".idea", ".vscode", ".cache",
}


def _scan_mtime() -> float:
    """Return the latest mtime of any file under _active_root."""
    best = 0.0
    try:
        for dirpath, dirnames, filenames in os.walk(_active_root):
            dirnames[:] = [d for d in dirnames if d not in _WATCH_EXCLUDE]
            for fn in filenames:
                try:
                    m = (Path(dirpath) / fn).stat().st_mtime
                    if m > best:
                        best = m
                except OSError:
                    pass
    except OSError:
        pass
    return best


def _watcher(port: int, interval: float = 3.0) -> None:
    last = _scan_mtime()
    while True:
        time.sleep(interval)
        cur = _scan_mtime()
        if cur != last:
            last = cur
            HubHandler._rebuild(_active_root)
            print(f"  [watcher] rebuilt ({_active_root.name})")


# ── Server (dual-stack IPv4+IPv6, threaded) ─────────────────────────────────

import socket as _socket


class _HubServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    address_family = _socket.AF_INET6
    allow_reuse_address = True
    daemon_threads = True

    def server_bind(self) -> None:
        # Dual-stack only applies to IPv6 sockets; guard so the IPv4 fallback
        # (and platforms lacking IPV6_V6ONLY) don't raise.
        if self.address_family == _socket.AF_INET6:
            try:
                self.socket.setsockopt(_socket.IPPROTO_IPV6, _socket.IPV6_V6ONLY, 0)
            except (AttributeError, OSError):
                pass
        super().server_bind()


def _make_server(port: int, handler: type) -> _HubServer:
    """Bind a dual-stack IPv6 socket, falling back to IPv4 on hosts without an
    IPv6 stack (many containers, restricted CI, some corporate networks)."""
    try:
        _HubServer.address_family = _socket.AF_INET6
        return _HubServer(("::", port), handler)
    except OSError:
        _HubServer.address_family = _socket.AF_INET
        return _HubServer(("0.0.0.0", port), handler)


# ── Entry point ─────────────────────────────────────────────────────────────

def default_port() -> int:
    """Configured port, or 8787."""
    return int(config.resolve_port(config.load_config()) or "8787")


def serve(port: int, demo: bool = False) -> None:
    """Run the hub HTTP server (the implementation behind `hub serve`)."""
    global _active_root
    if demo:
        _active_root = config.example_dir()

    HubHandler.server_port = port

    # Trigger an initial build so the index is fresh on first load.
    HubHandler._rebuild(_active_root)

    threading.Thread(target=_watcher, args=(port,), daemon=True).start()

    with _make_server(port, HubHandler) as srv:
        print(f"  Scan root : {_active_root}")
        print(f"  Listening : http://localhost:{port}")
        print()
        print("  Ctrl+C to stop")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


def main() -> None:
    """Direct entry point for `python -m hubspace.cli.server` (use `hub serve`)."""
    ap = argparse.ArgumentParser(description="hub markdown server (prefer `hub serve`)")
    ap.add_argument("--version", action="version", version=f"hub {__version__}")
    ap.add_argument("--port", "-p", type=int, default=default_port(), metavar="PORT")
    ap.add_argument("--demo", action="store_true", help="Use bundled example fixture")
    args = ap.parse_args()
    serve(args.port, args.demo)


if __name__ == "__main__":
    main()
