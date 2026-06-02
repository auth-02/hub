#!/usr/bin/env python3
"""Build a single browsable hub of every .md / .html file under a scan root.

Stdlib-only. Re-run any time; a launchd agent does this every 120 s.

Configuration (all optional, via environment variables):
    HUB_SCAN_ROOT   directory to scan          (default: ~/tifin)
    HUB_OUTPUT      output html file           (default: data/docs-index.html)
    HUB_SERVER_PORT local server port          (default: unset — uses file:// links)
    HUB_DEBUG       "1"/"true" enables logging  (default: off)
    HUB_LOG         log file path (debug only)  (default: .hub.log)
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db
import metadata

_HERE = Path(__file__).resolve().parent


def _env_path(var: str, default: Path) -> Path:
    val = os.environ.get(var)
    return Path(val).expanduser() if val else default


SCAN_ROOT_FILE = Path.home() / "agents" / "hub" / ".scan_root"


def _resolve_scan_root() -> Path:
    """Priority: HUB_SCAN_ROOT env > .scan_root sidecar > ~/tifin default."""
    env = os.environ.get("HUB_SCAN_ROOT")
    if env:
        return Path(env).expanduser()
    try:
        text = SCAN_ROOT_FILE.read_text(encoding="utf-8").strip()
        if text:
            return Path(text).expanduser()
    except OSError:
        pass
    return Path.home() / "tifin"


# ── Configurable paths ──────────────────────────────────────────────────────
ROOT   = _resolve_scan_root()
OUTPUT = _env_path("HUB_OUTPUT", _HERE / "data" / "docs-index.html")
DEBUG  = os.environ.get("HUB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
LOG    = _env_path("HUB_LOG",    _HERE / ".hub.log")
FAVICON = _env_path("HUB_FAVICON", _HERE / "assets" / "favicon.svg")
DB     = _env_path("HUB_DB",    _HERE / "data" / "hub.db")

_SERVER_PORT   = os.environ.get("HUB_SERVER_PORT", "").strip()
_SERVER_ORIGIN = f"http://localhost:{_SERVER_PORT}" if _SERVER_PORT else ""

_TEMPLATE_PATH = _HERE / "templates" / "template.html"

EXCLUDE_DIRS = {
    ".claude", ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".next", "dist", "build", ".turbo", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", "site-packages", ".idea", ".vscode",
    ".cache", ".gradle", "target", "out", ".terraform", ".dagster",
    "graphify-out",
}
EXTS = {".md", ".html", ".htm"}
PROMPT_EXTS = {".txt"}

KIND_DIRS = (
    ("artifacts", "artifact"),
    ("runs",      "run"),
    ("tasks",     "task"),
    ("docs",      "doc"),
    ("prompts",   "prompt"),
)


def _included(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in EXTS:
        return True
    if ext in PROMPT_EXTS and "/prompts/" in path.as_posix():
        return True
    return False


def log(msg: str) -> None:
    print(msg)
    if DEBUG:
        try:
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n")
        except OSError:
            pass


def discover() -> dict[str, list[dict]]:
    """Return {repo_name: [ {abs, rel, mtime, ext, kind}, ... ]}."""
    groups: dict[str, list[dict]] = {}
    if not ROOT.exists():
        return groups
    for entry in sorted(ROOT.iterdir()):
        if entry.is_file() and _included(entry) and entry != OUTPUT:
            groups.setdefault("(root)", []).append(_meta(entry, ROOT))
        elif entry.is_dir() and entry.name not in EXCLUDE_DIRS:
            files: list[dict] = []
            for dirpath, dirnames, filenames in os.walk(entry):
                dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".venv")]
                for fn in filenames:
                    p = Path(dirpath) / fn
                    if _included(p) and p != OUTPUT:
                        files.append(_meta(p, entry))
            if files:
                groups[entry.name] = files
    return groups


def _classify(path: Path, rel: str) -> str | None:
    stem = path.stem.lower()
    if stem == "claude":
        return "claude"
    if stem == "readme":
        return "readme"
    posix = path.as_posix()
    for dirname, kind in KIND_DIRS:
        if f"/{dirname}/" in posix or rel.startswith(f"{dirname}/"):
            return kind
    return None


def _task_slug(path: Path) -> str | None:
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "tasks" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _meta(path: Path, repo_root: Path) -> dict:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    rel = path.relative_to(repo_root).as_posix()
    return {
        "abs":       str(path),
        "rel":       rel,
        "mtime":     mtime,
        "ext":       path.suffix.lower().lstrip("."),
        "kind":      _classify(path, rel),
        "task_slug": _task_slug(path),
        "task_repo": repo_root.name,
    }


def _href(abs_path: str) -> str:
    if _SERVER_PORT:
        return f"http://localhost:{_SERVER_PORT}" + quote(abs_path)
    return "file://" + quote(abs_path)


def _ago(mtime: float) -> str:
    if not mtime:
        return "—"
    delta = time.time() - mtime
    if delta < 90:
        return "just now"
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{int(delta // secs)}{unit} ago"
    return "just now"


def render(groups: dict[str, list[dict]], fts_json: str = "[]", lineage_json: str = "{}", task_status_json: str = "{}") -> str:
    total     = sum(len(v) for v in groups.values())
    md_total  = sum(1 for v in groups.values() for f in v if f["ext"] == "md")
    html_total = total - md_total
    built     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def repo_recency(item):
        name, files = item
        newest = max((f["mtime"] for f in files), default=0)
        return (name == "(root)", -newest)

    rows_html = []
    for repo, files in sorted(groups.items(), key=repo_recency):
        files.sort(key=lambda f: f["mtime"], reverse=True)
        items = []
        for f in files:
            badge     = (f["kind"] or f["ext"]).upper()
            badge_cls = f["kind"] or f["ext"]
            task_attrs = ""
            if f.get("task_slug"):
                task_attrs = (
                    f' data-task-slug="{html.escape(f["task_slug"])}"'
                    f' data-task-repo="{html.escape(f["task_repo"])}"'
                )
            items.append(
                f'<a class="row" href="{html.escape(_href(f["abs"]))}" '
                f'target="_blank" rel="noopener" '
                f'data-kind="{badge_cls}" '
                f'data-search="{html.escape((repo + " " + f["rel"]).lower())}" '
                f'data-abs="{html.escape(f["abs"])}"{task_attrs}>'
                f'<span class="badge {badge_cls}">{badge}</span>'
                f'<span class="path">{html.escape(f["rel"])}</span>'
                f'<span class="ago">{_ago(f["mtime"])}</span>'
                f"</a>"
            )
        rows_html.append(
            f'<section class="repo" data-repo="{html.escape(repo.lower())}">'
            f'<div class="repo-head">'
            f'<span class="repo-name" data-repo="{html.escape(repo.lower())}">'
            f'{html.escape(repo)}</span>'
            f'<span class="repo-count">{len(files)}</span></div>'
            f'<div class="rows">{"".join(items)}</div></section>'
        )

    repo_chips = "".join(
        f'<button class="rchip" data-repo="{html.escape(r.lower())}">{html.escape(r)}</button>'
        for r, _ in sorted(groups.items(), key=repo_recency)
    )

    return _TEMPLATE_PATH.read_text(encoding="utf-8").format(
        built=built,
        favicon=html.escape(_href(str(FAVICON))),
        scan_root=html.escape(str(ROOT)),
        scan_root_json=json.dumps(str(ROOT)),
        sidecar_json=json.dumps(str(SCAN_ROOT_FILE)),
        hubpy_json=json.dumps(str(Path(__file__).resolve())),
        total=total,
        md_total=md_total,
        html_total=html_total,
        repo_count=len(groups),
        body="".join(rows_html) or f'<p class="empty">No .md / .html files found under {html.escape(str(ROOT))}.</p>',
        repo_chips=repo_chips,
        fts_json=fts_json,
        lineage_json=lineage_json,
        task_status_json=task_status_json,
        server_origin_json=json.dumps(_SERVER_ORIGIN),
    )


def main() -> None:
    groups = discover()

    conn = db.open_db(DB)
    live_paths: set[str] = set()
    for repo, files in groups.items():
        for f in files:
            live_paths.add(f["abs"])
            if not db.is_current(conn, f["abs"], f["mtime"]):
                text  = metadata.read_safe(f["abs"])
                title = metadata.extract_title(f["abs"], text)
                body  = metadata.extract_body(f["abs"], text)
                db.upsert(conn, {**f, "repo": repo}, title, body)
    db.prune(conn, live_paths)
    db.build_lineage(conn)
    fts_json, lineage_json = db.export_html_data(conn)
    task_status_json = db.get_statuses_json(conn)
    conn.close()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(groups, fts_json, lineage_json, task_status_json), encoding="utf-8")
    total = sum(len(v) for v in groups.values())
    log(f"[hub] scanned {ROOT} -> {OUTPUT} ({total} files, {len(groups)} groups)")


if __name__ == "__main__":
    main()
