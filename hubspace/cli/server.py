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
from urllib.parse import parse_qs, quote, unquote, urlparse

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
    draw_page_html, doc_menu, DOC_PDF_ITEM, render_provenance,
    doc_publish_item, DOC_PUBLISH_SCRIPT, DOC_EMBED_SCRIPT,
)
from ..core import metadata as _metadata


def _state_dir() -> Path:
    """XDG_STATE_HOME/hub, falling back to ~/.local/state/hub."""
    return config.state_dir()


_SIDECAR = _state_dir() / ".scan_root"
_DB_PATH = _state_dir() / "hub.db"

# Serialize hub.py rebuilds so the watcher and request-triggered rebuilds
# (/_set-root, /_rebuild, /_task-status) never run two writers at once.
_REBUILD_LOCK = threading.Lock()

# Hard cap on a single /_upload request body. base64 inflates ~33%, so this
# comfortably admits several 64 MB files while refusing an absurd Content-Length
# before we read it into memory (the per-file 64 MB guard is enforced after).
_UPLOAD_REQUEST_CAP = 512 * 1024 * 1024


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

        # Settings panel (S15) — current workspace prefs + dak creds (token MASKED)
        if url_path == "/_settings":
            self._settings_get()
            return

        # Directory picker backend (read-only listing for the set-root modal)
        if url_path == "/_list-dirs":
            qs = parse_qs(urlparse(self.path).query)
            self._list_dirs((qs.get("path") or [""])[0])
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

        # A task's append-only comment log (comments/notes.jsonl) is internal
        # storage, not a document (S13). Serving it as octet-stream triggers a
        # browser download; instead bounce to the SPA so a direct URL never
        # downloads. The UI never links here — this is defense-in-depth.
        if fs_path.suffix.lower() == ".jsonl" and "comments" in fs_path.parts:
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
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
            provenance_html = render_provenance(_metadata.extract_provenance(src))
            src = _inject_into_html(src, lineage_html, _favicon_href(self.__class__.server_port),
                                    provenance_html, pub_path=self._pub_path(fs_path))
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
        elif url_path == "/_new-task":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError as e:
                self._send(400, "text/plain", str(e).encode())
                return
            self._new_task(body)
        elif url_path == "/_upload":
            self._upload()
        elif url_path == "/_note":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._note(body)
        elif url_path == "/_manifest-edit":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._manifest_edit(body)
        elif url_path == "/_publish-scan":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._publish_scan(body)
        elif url_path == "/_publish":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._publish(body)
        elif url_path == "/_publish-bundle":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._publish_bundle(body)
        elif url_path == "/_publish-revoke":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._publish_revoke(body)
        elif url_path == "/_settings":
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                self._send(400, "application/json",
                           json.dumps({"ok": False, "error": "bad_json",
                                       "detail": str(e)}).encode())
                return
            self._settings_post(body)
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

    def _new_task(self, body: dict) -> None:
        """Write exactly one file — `<repo>/tasks/<slug>/manifest.md` — then rebuild.

        The palette's one write surface (see docs/HUB-LAYOUT.md §2). No folders
        beyond the task dir, no DB row: the rebuild (same path /_set-root uses)
        reconciles the new file. Guards: unsafe slug → 400, collision → 409 with
        a suggested `-N` slug, read-only root → 403. Never overwrites a manifest.
        """
        from ..core import tasks as _tasks

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        root = _active_root.resolve()
        repo = (body.get("repo") or "").strip()
        title = (body.get("title") or "").strip()
        slug = (body.get("slug") or "").strip() or slugify(title)
        status = (body.get("status") or "ongoing").strip()
        if status not in ("ongoing", "paused", "completed"):
            status = "ongoing"
        plan_raw = body.get("plan") or []
        if isinstance(plan_raw, str):
            plan = [ln.strip() for ln in plan_raw.splitlines() if ln.strip()]
        else:
            plan = [str(x).strip() for x in plan_raw if str(x).strip()]

        if not title:
            _fail(400, {"ok": False, "error": "title required"})
            return

        # Resolve repo root under the active scan root. Empty / "(root)" → the
        # scan root itself (the "(root)" pseudo-repo in HUB-LAYOUT §1).
        if repo and repo != "(root)":
            repo_root = (root / repo).resolve()
            if not is_within(repo_root, root) or not repo_root.is_dir():
                _fail(400, {"ok": False, "error": "invalid repo"})
                return
        else:
            repo_root = root

        try:
            path = _tasks.write_manifest(repo_root, slug, title, status, plan=plan)
        except _tasks.SlugError as e:
            _fail(400, {"ok": False, "error": "invalid_slug", "detail": str(e)})
            return
        except _tasks.TaskExists as e:
            _fail(409, {"ok": False, "error": "exists",
                        "slug": e.slug, "suggestion": e.suggestion, "rel": e.rel})
            return
        except OSError as e:
            _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
            return

        rel = path.relative_to(root).as_posix()
        # Reconcile immediately so the new task appears on reload (the watcher
        # would also catch it within 3 s, but the UI reloads right after POST).
        result = self._rebuild(_active_root)
        if result.returncode != 0:
            import sys as _sys2
            print(result.stderr or result.stdout, file=_sys2.stderr)
        self._send(200, "application/json",
                   json.dumps({"ok": True, "rel": rel, "slug": slug}).encode())

    def _upload(self) -> None:
        """Write dropped files into `<repo>/tasks/<slug>/data/` — the 1d producer.

        Body is JSON: ``{repo, slug, files:[{name, dataBase64}]}`` (a stdlib-only
        multipart alternative — see the PR notes). Each file is base64-decoded
        and handed to `tasks.accept_upload`, which enforces all three guards
        server-side: the 64 MB per-file cap, the hub.toml extension allowlist,
        and a basename-only filename (no separator / `..` / absolute path). Names
        are preserved; a collision suffixes `-2`. Repo/slug reuse the same guards
        as `/_new-task`. A read-only root → 403. A rebuild runs only when at least
        one file was written; the response reports per-file accept/reject.
        """
        from ..core import tasks as _tasks
        import base64

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > _UPLOAD_REQUEST_CAP:
            _fail(413, {"ok": False, "error": "too_large"})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            _fail(400, {"ok": False, "error": "bad_json", "detail": str(e)})
            return

        root = _active_root.resolve()
        repo = (body.get("repo") or "").strip()
        slug = (body.get("slug") or "").strip()
        files = body.get("files")

        if not _tasks.valid_slug(slug):
            _fail(400, {"ok": False, "error": "invalid_slug"})
            return
        if repo and repo != "(root)":
            repo_root = (root / repo).resolve()
            if not is_within(repo_root, root) or not repo_root.is_dir():
                _fail(400, {"ok": False, "error": "invalid repo"})
                return
        else:
            repo_root = root
        task_dir = (repo_root / "tasks" / slug).resolve()
        if not is_within(task_dir, root) or not task_dir.is_dir():
            _fail(400, {"ok": False, "error": "invalid task"})
            return
        data_dir = task_dir / "data"

        allowed = config.upload_exts(config.load_config())
        results: list[dict] = []
        written = 0
        for f in files if isinstance(files, list) else []:
            name = (f.get("name") if isinstance(f, dict) else "") or ""
            b64 = (f.get("dataBase64") if isinstance(f, dict) else "") or ""
            try:
                raw = base64.b64decode(b64, validate=False)
            except Exception:
                results.append({"name": name, "ok": False, "reason": "could not decode"})
                continue
            try:
                path, reason = _tasks.accept_upload(data_dir, name, raw, allowed)
            except OSError as e:
                _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                return
            if path is not None:
                written += 1
                results.append({"name": name, "ok": True,
                                "rel": path.relative_to(root).as_posix()})
            else:
                results.append({"name": name, "ok": False, "reason": reason})

        if written:
            result = self._rebuild(_active_root)
            if result.returncode != 0:
                import sys as _sys2
                print(result.stderr or result.stdout, file=_sys2.stderr)
        self._send(200, "application/json",
                   json.dumps({"ok": True, "written": written, "results": results}).encode())

    def _note(self, body: dict) -> None:
        """Append one comment to `<repo>/tasks/<slug>/comments/notes.jsonl` (1e/S7).

        Body is JSON ``{repo, slug, target, range?, body, author?}``. Appends
        exactly one JSON line to the task's append-only comment log (see
        docs/HUB-LAYOUT.md §2), anchored to `target` (a task-relative path that
        must resolve inside the task). Reuses the same repo/slug guards as
        `/_new-task` and `/_upload`; `tasks.write_note` enforces the
        target-escape guard and never rewrites existing lines. A read-only root
        → 403. On success, rebuilds so the comment appears on reload — no DB row
        is written directly.
        """
        from ..core import tasks as _tasks

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        root = _active_root.resolve()
        repo = (body.get("repo") or "").strip()
        slug = (body.get("slug") or "").strip()
        target = (body.get("target") or "").strip()
        note_body = (body.get("body") or "").strip()
        author = (body.get("author") or "").strip() or None
        range_ = (body.get("range") or "").strip() or None

        if not _tasks.valid_slug(slug):
            _fail(400, {"ok": False, "error": "invalid_slug"})
            return
        if not target:
            _fail(400, {"ok": False, "error": "target required"})
            return
        if not note_body:
            _fail(400, {"ok": False, "error": "body required"})
            return
        if repo and repo != "(root)":
            repo_root = (root / repo).resolve()
            if not is_within(repo_root, root) or not repo_root.is_dir():
                _fail(400, {"ok": False, "error": "invalid repo"})
                return
        else:
            repo_root = root
        task_dir = (repo_root / "tasks" / slug).resolve()
        if not is_within(task_dir, root) or not task_dir.is_dir():
            _fail(400, {"ok": False, "error": "invalid task"})
            return

        try:
            path, rec = _tasks.write_note(repo_root, slug, target, note_body,
                                          author=author, range_=range_)
        except _tasks.SlugError as e:
            _fail(400, {"ok": False, "error": "invalid_target", "detail": str(e)})
            return
        except ValueError as e:
            _fail(400, {"ok": False, "error": "invalid", "detail": str(e)})
            return
        except OSError as e:
            _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
            return

        rel = path.relative_to(root).as_posix()
        result = self._rebuild(_active_root)
        if result.returncode != 0:
            import sys as _sys2
            print(result.stderr or result.stdout, file=_sys2.stderr)
        self._send(200, "application/json",
                   json.dumps({"ok": True, "rel": rel, "id": rec["id"]}).encode())

    def _manifest_edit(self, body: dict) -> None:
        """Rewrite ONLY a manifest's `status:` + `## Plan` block — the 1i producer.

        Body is JSON ``{repo, slug, status?, plan?:[{text,done}], base_mtime}``.
        The file on disk is the source of truth: `tasks.rewrite_manifest` replaces
        just those two regions, preserving prose/decisions/other frontmatter
        byte-for-byte. Conflict rule ("hub never wins a race against your
        editor"): `base_mtime` is the mtime the client last read; if the file's
        current mtime differs, the edit is DISCARDED and we return 409 so the UI
        re-reads — never a blind overwrite. On success the frontmatter status and
        the task_status table/sidecar are both updated (set_status), so file and
        sidecar stay consistent, then the index rebuilds. Read-only root → 403.
        """
        from ..core import tasks as _tasks

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        root = _active_root.resolve()
        repo = (body.get("repo") or "").strip()
        slug = (body.get("slug") or "").strip()
        status = body.get("status")
        plan = body.get("plan")
        base_mtime = body.get("base_mtime")

        if not _tasks.valid_slug(slug):
            _fail(400, {"ok": False, "error": "invalid_slug"})
            return
        if status is not None:
            status = str(status).strip()
            if status not in ("ongoing", "paused", "completed"):
                _fail(400, {"ok": False, "error": "invalid_status"})
                return
        if plan is not None:
            if not isinstance(plan, list):
                _fail(400, {"ok": False, "error": "invalid_plan"})
                return
            norm_plan = []
            for p in plan:
                if not isinstance(p, dict):
                    _fail(400, {"ok": False, "error": "invalid_plan"})
                    return
                norm_plan.append({"text": str(p.get("text", "")), "done": bool(p.get("done"))})
            plan = norm_plan
        if status is None and plan is None:
            _fail(400, {"ok": False, "error": "nothing to edit"})
            return

        # Resolve the task dir under the active root, tolerating both layouts:
        # scan root is a PARENT of the repo (root/<repo>/tasks/<slug>) or IS the
        # repo itself (root/tasks/<slug>, where task_repo == root.name).
        candidates = []
        if repo and repo != "(root)":
            candidates.append(root / repo / "tasks" / slug)
        candidates.append(root / "tasks" / slug)
        task_dir = None
        for c in candidates:
            rc = c.resolve()
            if is_within(rc, root) and rc.is_dir():
                task_dir = rc
                break
        if task_dir is None:
            _fail(400, {"ok": False, "error": "invalid task"})
            return
        manifest = task_dir / "manifest.md"
        if not manifest.is_file():
            _fail(400, {"ok": False, "error": "no manifest"})
            return

        # Conflict rule: refuse if the file changed under the user since they read it.
        try:
            cur_mtime = manifest.stat().st_mtime
        except OSError as e:
            _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
            return
        if base_mtime is not None:
            try:
                base = float(base_mtime)
            except (TypeError, ValueError):
                base = None
            if base is not None and abs(cur_mtime - base) > 0.001:
                _fail(409, {"ok": False, "error": "conflict", "mtime": cur_mtime})
                return

        try:
            text = manifest.read_text(encoding="utf-8")
        except OSError as e:
            _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
            return
        new_text = _tasks.rewrite_manifest(text, status=status, plan=plan)
        if new_text != text:
            try:
                manifest.write_text(new_text, encoding="utf-8")
            except OSError as e:
                _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                return

        # Keep the sidecar/table in step with the file. seed_status_from_frontmatter
        # only fills an EMPTY row (user toggle wins), so a status change must be
        # pushed explicitly or the sidecar would drift from the file.
        if status is not None:
            try:
                from ..core import db as _db
                conn = _db.open_db(_DB_PATH)  # ensures schema/migrations exist
                _db.set_status(conn, slug, repo, status)
                conn.close()
            except Exception as e:
                import sys as _sys2
                print(f"[manifest-edit] set_status failed: {e}", file=_sys2.stderr)

        rel = manifest.relative_to(root).as_posix()
        result = self._rebuild(_active_root)
        if result.returncode != 0:
            import sys as _sys2
            print(result.stderr or result.stdout, file=_sys2.stderr)
        try:
            new_mtime = manifest.stat().st_mtime
        except OSError:
            new_mtime = cur_mtime
        self._send(200, "application/json",
                   json.dumps({"ok": True, "rel": rel, "mtime": new_mtime}).encode())

    def _run_dak(self, publish_path, title: str, *, mode=None, slug=None,
                 dry_run: bool = False):
        """Spawn the bundled ``dak`` skill to upload ``publish_path``.

        This is the ONE place Hub crosses the network boundary — and it does so
        by handing off to a **subprocess** (dak reaches Cloudflare). Hub's own
        code opens no socket; the invariant holds at the process edge.

        Returns ``(url, dry_run, None)`` on success, or
        ``(None, dry_run, {"error", "detail"})`` on failure — ``dak_unavailable``
        when the script is missing, or ``publish_failed`` when dak exits
        non-zero / times out / prints no URL. ``dry_run`` in the return is the
        EFFECTIVE flag (S14 / #3): body flag OR ``HUB_PUBLISH_DRYRUN=1`` — so
        callers can be honest about a staged-but-not-live URL. dak writes the
        final ``https://…workers.dev`` URL as the last non-empty line of stdout.
        A dry-run passes ``--dry-run`` so dak stages a URL without uploading.
        """
        dry = bool(dry_run) or os.environ.get("HUB_PUBLISH_DRYRUN") == "1"
        dak = (_PKG_ROOT / "plugin" / "hub-agent" / "skills"
               / "dak" / "scripts" / "dak.py")
        if not dak.exists():
            return None, dry, {"error": "dak_unavailable",
                               "detail": f"dak script not found at {dak} — "
                                         f"run its one-time setup"}
        cmd = [sys.executable, str(dak), str(publish_path)]
        if mode:
            cmd += ["--mode", mode]
        if slug:
            cmd += ["--slug", slug]
        cmd += ["--title", title]
        if dry:
            cmd.append("--dry-run")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=120)
        except subprocess.TimeoutExpired:
            return None, dry, {"error": "publish_failed", "detail": "dak timed out"}
        except OSError as e:
            return None, dry, {"error": "publish_failed", "detail": str(e)}
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
            return None, dry, {"error": "publish_failed",
                               "detail": "\n".join(tail) or "dak exited non-zero"}
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines()
                 if ln.strip()]
        url = lines[-1] if lines else ""
        if not url.startswith("http"):
            return None, dry, {"error": "publish_failed",
                               "detail": "dak produced no URL"}
        return url, dry, None

    def _publish_scan(self, body: dict) -> None:
        """Run the shared redaction scanner for one path — the UI's publish gate.

        Body is JSON ``{path}`` (absolute, from a file row's data-abs, or
        scan-root-relative). The path must resolve INSIDE the active scan root
        (same containment rule as GET) — no arbitrary filesystem reads. Returns
        ``{ok, findings, private}`` using the exact same core.publish.scan the
        CLI uses, so both surfaces share ONE scanner. Hub makes no network call
        here; this only reads a local file. When the workspace is private we
        still report ``private: true`` so the UI can refuse consistently.
        """
        from ..core import publish as _publish

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        raw = (body.get("path") or "").strip()
        if not raw:
            _fail(400, {"ok": False, "error": "path required"})
            return
        root = _active_root.resolve()
        p = Path(raw)
        if not p.is_absolute():
            p = root / raw.lstrip("/")
        resolved = p.resolve()
        if not is_within(resolved, root):
            _fail(403, {"ok": False, "error": "forbidden"})
            return
        if not resolved.is_file():
            _fail(404, {"ok": False, "error": "not_found"})
            return
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            _fail(403, {"ok": False, "error": "read_failed", "detail": str(e)})
            return
        findings = _publish.scan(text)
        private = config.is_private(config.load_config())
        self._send(200, "application/json",
                   json.dumps({"ok": True, "findings": findings,
                               "private": private}).encode())

    def _publish(self, body: dict) -> None:
        """One-click asset publish (roadmap 1f, S11): prepare, run dak, return URL.

        Body is JSON ``{path, redact_indices?:[int], title?, mode?, slug?,
        dryRun?}``. Re-runs the scan server-side (the client's finding list is
        advisory only) and, for the ``redact_indices`` subset the user left
        toggled on, writes a sanitized copy to ``state_dir()/publish`` (the
        ORIGINAL is never touched) via the same core.publish.redact the CLI uses.

        Then it hands off to the bundled **dak** subprocess (see :meth:`_run_dak`)
        which performs the Cloudflare upload — Hub itself opens no socket — and
        returns ``{ok, url}``, recording the published-state under the asset's
        path. The gate is preserved: refuses when the workspace is private, and
        refuses when the scan found things the client did not opt to review
        (no ``redact_indices`` key and no ``review`` flag).
        """
        from ..core import publish as _publish

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        if config.is_private(config.load_config()):
            _fail(403, {"ok": False, "error": "private"})
            return
        raw = (body.get("path") or "").strip()
        if not raw:
            _fail(400, {"ok": False, "error": "path required"})
            return
        root = _active_root.resolve()
        p = Path(raw)
        if not p.is_absolute():
            p = root / raw.lstrip("/")
        resolved = p.resolve()
        if not is_within(resolved, root) or not resolved.is_file():
            _fail(400, {"ok": False, "error": "invalid path"})
            return
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            _fail(403, {"ok": False, "error": "read_failed", "detail": str(e)})
            return

        findings = _publish.scan(text)
        # Gate: findings must be reviewed. Presence of the redact_indices key
        # (even empty → "I looked, redact none") or a truthy `review` flag is
        # the client's acknowledgement. Unreviewed findings → refuse.
        idx = body.get("redact_indices")
        reviewed = ("redact_indices" in body) or bool(body.get("review"))
        if findings and not reviewed:
            _fail(403, {"ok": False, "error": "unreviewed_findings",
                        "findings": findings})
            return

        publish_path = resolved
        if isinstance(idx, list) and idx and findings:
            chosen = [findings[i] for i in idx
                      if isinstance(i, int) and 0 <= i < len(findings)]
            if chosen:
                redacted = _publish.redact(text, chosen)
                copy_dir = config.state_dir() / "publish"
                copy_dir.mkdir(parents=True, exist_ok=True)
                copy = copy_dir / f"{resolved.stem}.redacted{resolved.suffix}"
                try:
                    copy.write_text(redacted, encoding="utf-8")
                except OSError as e:
                    _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                    return
                publish_path = copy

        title = (body.get("title") or resolved.stem).strip() or resolved.stem
        mode = body.get("mode") if body.get("mode") in ("snapshot", "live") else None
        slug = (body.get("slug") or "").strip() or None

        # Hand off to the dak subprocess (the network edge). Hub opens no socket.
        url, dry, err = self._run_dak(publish_path, title, mode=mode, slug=slug,
                                      dry_run=bool(body.get("dryRun")))
        if err is not None:
            _fail(200 if err["error"] == "dak_unavailable" else 502,
                  {"ok": False, "dryRun": dry, **err})
            return
        # S14 / #3 — a dry-run stages a URL WITHOUT uploading, so it is not live.
        # Never record it as published-state (that drives the row's live marker).
        if not dry:
            _publish.record_published_asset(resolved, url, mode or "snapshot")
        self._send(200, "application/json", json.dumps({
            "ok": True,
            "url": url,
            "dryRun": dry,
            "copy": str(publish_path) if publish_path != resolved else None,
        }).encode())

    def _publish_bundle(self, body: dict) -> None:
        """One-click task-bundle publish (roadmap 1g, S11): render, run dak, URL.

        The UI twin of `hub publish --task`. Body is JSON
        ``{slug, repo?, include_external?, redact?, review?, dryRun?}``. Renders
        the bundle with the same pure :func:`render.bundle.render_task_bundle`
        the CLI uses, writes it under ``state_dir()/publish`` (NEVER the scan
        root), runs the SAME S5a scan over the produced HTML, then hands off to
        the bundled **dak** subprocess for the upload (:meth:`_run_dak`) — Hub
        opens no socket itself. On success it records the published-state in the
        S5b ``published.json`` sidecar, rebuilds so the row marker updates, and
        returns ``{ok, url}``. Refuses when private, and refuses when the scan
        found things and the client neither redacted nor reviewed them.
        """
        from ..core import publish as _publish
        from ..core import query
        from ..render import bundle as _bundle

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        if config.is_private(config.load_config()):
            _fail(403, {"ok": False, "error": "private"})
            return
        slug = (body.get("slug") or "").strip()
        repo = (body.get("repo") or "").strip() or None
        include_external = bool(body.get("include_external"))
        want_redact = bool(body.get("redact"))
        if not slug:
            _fail(400, {"ok": False, "error": "slug required"})
            return

        conn = query.connect()
        try:
            try:
                html = _bundle.render_task_bundle(
                    conn, repo, slug, include_external=include_external)
            except ValueError as e:
                _fail(404, {"ok": False, "error": "no_such_task", "detail": str(e)})
                return
        finally:
            if conn is not None:
                conn.close()

        out_dir = config.state_dir() / "publish"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{(repo or 'root')}-{slug}.html"
        try:
            out_path.write_text(html, encoding="utf-8")
        except OSError as e:
            _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
            return

        findings = _publish.scan(html)
        # Gate: refuse unreviewed findings (client must redact or explicitly
        # review). One-click UI sends redact:true so task secrets are sanitized.
        reviewed = want_redact or bool(body.get("review"))
        if findings and not reviewed:
            _fail(403, {"ok": False, "error": "unreviewed_findings",
                        "findings": findings})
            return

        publish_path = out_path
        if want_redact and findings:
            redacted = _publish.redact(html, findings)
            publish_path = out_path.with_suffix(".redacted.html")
            try:
                publish_path.write_text(redacted, encoding="utf-8")
            except OSError as e:
                _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                return

        # Hand off to the dak subprocess (network edge); Hub opens no socket.
        url, dry, err = self._run_dak(publish_path, slug, slug=slug,
                                      dry_run=bool(body.get("dryRun")))
        if err is not None:
            _fail(200 if err["error"] == "dak_unavailable" else 502,
                  {"ok": False, "dryRun": dry, "findings": findings, **err})
            return
        # S14 / #3 — a dry-run is not live; don't record published-state or
        # re-bake the row's PUBLISHED marker for a URL that never uploaded.
        if not dry:
            _publish.record_published(repo, slug, url, mode="snapshot")
            # Re-bake the published map into the page so the row marker updates.
            result = self._rebuild(_active_root)
            if result.returncode != 0:
                print(result.stderr or result.stdout, file=sys.stderr)
        self._send(200, "application/json", json.dumps({
            "ok": True,
            "url": url,
            "dryRun": dry,
            "bundle": str(out_path),
            "findings": findings,
        }).encode())

    def _publish_revoke(self, body: dict) -> None:
        """Forget a task's published-state entry, then rebuild so the marker clears.

        Body is JSON ``{slug, repo?}``. Local-only: Hub removes the sidecar entry
        (the UI twin of `hub publish --task <slug> --revoke`) and makes no network
        call. The rebuild re-bakes the (now smaller) published map into the page.
        """
        from ..core import publish as _publish

        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        slug = (body.get("slug") or "").strip()
        repo = (body.get("repo") or "").strip() or None
        if not slug:
            _fail(400, {"ok": False, "error": "slug required"})
            return
        removed = _publish.revoke_published(repo, slug)
        result = self._rebuild(_active_root)
        if result.returncode != 0:
            import sys as _sys2
            print(result.stderr or result.stdout, file=_sys2.stderr)
        self._send(200, "application/json",
                   json.dumps({"ok": True, "removed": removed}).encode())

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

    def _list_dirs(self, raw: str) -> None:
        """List immediate subdirectories of a path — the set-root picker backend.

        Read-only: never writes, never scans file contents, just enumerates dirs
        so the browser can navigate the server's filesystem (a native folder
        picker can't hand the server a real path). Query param ``?path=<abs>``;
        empty → the current scan root (falling back to ``$HOME`` if that isn't a
        readable dir). Returns JSON::

            {"path": "<abs, normalized>",
             "parent": "<abs or null at fs root>",
             "dirs": [{"name": "...", "path": "<abs child>"}, ...]}

        Subdirectories only, sorted case-insensitively. Skips non-dirs, hidden
        dirs (leading dot), and any entry the process can't read. A bad or
        unreadable ``path`` returns ``{"error": ..., "path": ...}`` with 400 —
        never a traceback/500.
        """
        raw = (raw or "").strip()
        if raw:
            base = Path(raw).expanduser()
        else:
            base = _active_root
            if not base.is_dir():
                base = Path.home()
        try:
            p = base.resolve()
        except OSError as e:
            self._send(400, "application/json",
                       json.dumps({"error": str(e), "path": raw}).encode())
            return
        if not p.is_dir():
            self._send(400, "application/json",
                       json.dumps({"error": "not a directory", "path": str(p)}).encode())
            return

        dirs = []
        try:
            with os.scandir(p) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    try:
                        if not entry.is_dir(follow_symlinks=True):
                            continue
                    except OSError:
                        continue
                    dirs.append({"name": entry.name, "path": str(p / entry.name)})
        except (PermissionError, OSError) as e:
            self._send(400, "application/json",
                       json.dumps({"error": str(e), "path": str(p)}).encode())
            return

        dirs.sort(key=lambda d: d["name"].lower())
        parent = None if p.parent == p else str(p.parent)
        self._send(200, "application/json",
                   json.dumps({"path": str(p), "parent": parent, "dirs": dirs}).encode())

    # ── Settings (S15) ──────────────────────────────────────────────────────
    def _settings_get(self) -> None:
        """Return current workspace prefs + dak creds — token ALWAYS masked.

        Workspace prefs come from the hub.toml the Settings panel owns
        (`config.config_path()`), so what the panel shows is what it will write.
        The dak block never carries the real token: only ``api_token_set`` (and
        the safe account_id/subdomain). See config.masked_dak_config.
        """
        cfg = config.load_config(config.config_path().parent)
        port = cfg.get("port")
        if isinstance(port, bool):
            port = None
        elif isinstance(port, int):
            pass
        elif isinstance(port, str) and port.strip().isdigit():
            port = int(port.strip())
        else:
            port = None
        hub = {
            "default_view": config.resolve_default_view(cfg),
            "port": port,
            "exclude_dirs": sorted(config.config_exclude_dirs(cfg)),
            "private": config.is_private(cfg),
            "upload_exts": sorted(config.upload_exts(cfg)),
            "scan_root": str(_active_root),
        }
        self._send(200, "application/json",
                   json.dumps({"ok": True, "hub": hub,
                               "dak": config.masked_dak_config()}).encode())

    @staticmethod
    def _split_list(raw) -> list:
        """Normalize a comma/whitespace list (or an actual list) → [str]."""
        if isinstance(raw, list):
            items = [str(x).strip() for x in raw]
        else:
            items = re.split(r"[,\s]+", str(raw or ""))
        return [x for x in (i.strip() for i in items) if x]

    def _settings_post(self, body: dict) -> None:
        """Write workspace prefs → hub.toml and dak creds → ~/.dak/config.json.

        SECURITY: the API token is written ONLY to ~/.dak/config.json, never to
        hub.toml (which is indexed and can be embedded/published). config.write_config
        enforces this at the sink via a fixed key allowlist; here we additionally
        never copy a dak field into the hub values. The token is overwritten only
        when the client sends a real new value (not the mask sentinel / not empty),
        so re-saving other fields keeps the existing token. Nothing here logs the
        token. Rebuilds after a hub.toml change; a port change is flagged in
        ``notes`` because hub.toml `port` is read at process start.
        """
        def _fail(code: int, payload: dict) -> None:
            self._send(code, "application/json", json.dumps(payload).encode())

        hub_in = body.get("hub") if isinstance(body.get("hub"), dict) else {}
        dak_in = body.get("dak") if isinstance(body.get("dak"), dict) else {}
        notes: list[str] = []

        # ── validate + normalize workspace prefs ─────────────────────────────
        hub_vals: dict = {}
        if "default_view" in hub_in:
            v = str(hub_in.get("default_view") or "").strip()
            if v:
                if v not in ("work", "list", "board", "calendar"):
                    _fail(400, {"ok": False, "error": "invalid_view"})
                    return
                hub_vals["default_view"] = v
        if "port" in hub_in:
            raw = hub_in.get("port")
            if raw not in (None, ""):
                try:
                    pi = int(raw)
                except (TypeError, ValueError):
                    _fail(400, {"ok": False, "error": "invalid_port"})
                    return
                if not (1 <= pi <= 65535):
                    _fail(400, {"ok": False, "error": "invalid_port"})
                    return
                hub_vals["port"] = pi
        if "exclude_dirs" in hub_in:
            dirs = self._split_list(hub_in.get("exclude_dirs"))
            for d in dirs:
                if "/" in d or "\\" in d or d in (".", ".."):
                    _fail(400, {"ok": False, "error": "invalid_exclude_dir",
                                "detail": d})
                    return
            hub_vals["exclude_dirs"] = dirs
        if "upload_exts" in hub_in:
            exts = []
            for e in self._split_list(hub_in.get("upload_exts")):
                e = e.lower()
                exts.append(e if e.startswith(".") else "." + e)
            hub_vals["upload_exts"] = exts
        if "private" in hub_in:
            pv = hub_in.get("private")
            if isinstance(pv, str):
                pv = pv.strip().lower() in ("1", "true", "yes", "on")
            hub_vals["private"] = bool(pv)

        # ── validate dak creds (token handled specially) ─────────────────────
        dak_vals: dict = {}
        for k in ("account_id", "subdomain"):
            if k in dak_in and dak_in.get(k) is not None:
                dak_vals[k] = str(dak_in.get(k)).strip()
        tok = dak_in.get("api_token")
        if tok is not None:
            tok = str(tok)
            if tok.strip() and tok != config.DAK_MASK:
                dak_vals["api_token"] = tok.strip()

        # ── write hub.toml (workspace prefs) + note a port change ────────────
        if hub_vals:
            cfg_path = config.config_path()
            if "port" in hub_vals:
                prev = config.resolve_port(config.load_config(cfg_path.parent))
                if str(hub_vals["port"]) != str(prev):
                    notes.append("Port change takes effect after you restart the server.")
            try:
                config.write_config(hub_vals, cfg_path)
            except OSError as e:
                _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                return
            # Re-bake the index so default_view / repo chips reflect the change.
            result = self._rebuild(_active_root)
            if result.returncode != 0:
                import sys as _sys2
                print(result.stderr or result.stdout, file=_sys2.stderr)

        # ── write dak creds (token to ~/.dak/config.json ONLY) ───────────────
        if dak_vals:
            try:
                config.write_dak_config(dak_vals)
            except OSError as e:
                _fail(403, {"ok": False, "error": "write_failed", "detail": str(e)})
                return

        self._send(200, "application/json",
                   json.dumps({"ok": True, "notes": notes}).encode())

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

    @staticmethod
    def _pub_path(path: Path) -> str:
        """Path to bake into the doc-page Publish item: scan-root-relative when
        the file lives under the active root (what /_publish prefers), else the
        absolute path (still resolved + containment-guarded server-side)."""
        try:
            return path.resolve().relative_to(_active_root.resolve()).as_posix()
        except ValueError:
            return str(path.resolve())

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

        # S6 (2a) — provenance line for agent-generated artifacts (.md/.txt),
        # read from the file's own front matter. Empty for ordinary files.
        provenance_html = ""
        if path.suffix.lower() in (".md", ".markdown", ".txt"):
            provenance_html = render_provenance(
                _metadata.extract_provenance(_metadata.read_safe(str(path)))
            )
        inject_html = lineage_html + provenance_html

        if inject_html:
            m = re.search(r"</h1>", body)
            if m:
                body = body[:m.end()] + inject_html + body[m.end():]
            else:
                body = inject_html + body

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
        # S14 / #5 — one-click Publish for any publishable doc (.md/.html). Bake
        # this file's own path into the item; a tiny inline script does the POST
        # /_publish and shows the honest published / dry-run / error state.
        pub_script = ""
        if path.suffix.lower() in (".md", ".markdown", ".html", ".htm"):
            menu_items.append(doc_publish_item(self._pub_path(path)))
            pub_script = DOC_PUBLISH_SCRIPT
        menu_items.append(DOC_PDF_ITEM)
        # S17 — keydown forwarder so the palette/composer/close shortcuts work
        # when this page is shown inside the SPA reading-view iframe. No-op for a
        # top-level tab (deep link); never present in published bundles.
        body = doc_menu(menu_items) + body + pub_script + DOC_EMBED_SCRIPT

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
