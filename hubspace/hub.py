#!/usr/bin/env python3
"""Build a single browsable hub of every .md / .html file under a scan root.

Stdlib-only. Re-run any time; an optional background watcher does this on change.

Configuration (all optional, via environment variables):
    HUB_SCAN_ROOT   directory to scan          (default: current working directory)
    HUB_OUTPUT      output html file           (default: build/docs-index.html)
    HUB_SERVER_PORT local server port          (default: unset — uses file:// links)
    HUB_DEBUG       "1"/"true" enables logging  (default: off)
    HUB_LOG         log file path (debug only)  (default: .hub.log)

State directory (db, sidecar):
    $XDG_STATE_HOME/hub  or  ~/.local/state/hub
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from . import config
from . import db
from . import metadata

_HERE = Path(__file__).resolve().parent


def _env_path(var: str, default: Path) -> Path:
    val = os.environ.get(var)
    return Path(val).expanduser() if val else default


def _state_dir() -> Path:
    """XDG_STATE_HOME/hub, falling back to ~/.local/state/hub."""
    return config.state_dir()


CONFIG = config.load_config()
SCAN_ROOT_FILE = _state_dir() / ".scan_root"


def _resolve_scan_root() -> Path:
    """flag > HUB_SCAN_ROOT env > hub.toml > .scan_root sidecar > CWD (see config.py)."""
    return config.resolve_scan_root(CONFIG, SCAN_ROOT_FILE)


# ── Configurable paths ──────────────────────────────────────────────────────
ROOT   = _resolve_scan_root()
OUTPUT = config.output_path()
DEBUG  = os.environ.get("HUB_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
LOG    = config.log_path()
FAVICON = _env_path("HUB_FAVICON", _HERE / "assets" / "favicon.svg")
DB     = _env_path("HUB_DB",    _state_dir() / "hub.db")

_SERVER_PORT   = config.resolve_port(CONFIG)
_SERVER_ORIGIN = f"http://localhost:{_SERVER_PORT}" if _SERVER_PORT else ""

_TEMPLATE_PATH = _HERE / "templates" / "template.html"

EXCLUDE_DIRS = {
    ".claude", ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".next", "dist", "build", ".turbo", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", "site-packages", ".idea", ".vscode",
    ".cache", ".gradle", "target", "out", ".terraform", ".dagster",
    "graphify-out",
}
EXCLUDE_DIRS |= config.config_exclude_dirs(CONFIG)
DEFAULT_VIEW = config.resolve_default_view(CONFIG)
EXTS = {".md", ".html", ".htm"}
PROMPT_EXTS = {".txt"}
DATA_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".tsv"}

def _included(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in EXTS:
        return True
    if ext in PROMPT_EXTS and "/prompts/" in path.as_posix():
        return True
    if ext in DATA_EXTS and "/data/" in path.as_posix():
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


def _classify(path: Path, rel: str, repo_name: str = "") -> str | None:
    """Kind resolution per HUB-LAYOUT.md §3. First match wins.

    repo_name is the immediate parent directory name (the "repo"). When the repo
    dir is itself named "tasks", the rel is already one level inside tasks/, so
    we prefix it so the structural patterns still fire correctly.
    """
    stem = path.stem.lower()
    # When the containing repo is named "tasks", the file is already inside
    # tasks/<slug>/... — prepend so classification patterns match.
    effective_rel = f"tasks/{rel}" if repo_name.lower() == "tasks" else rel
    parts = effective_rel.split("/")

    if stem == "claude":
        return "claude"
    if stem == "readme":
        return "readme"

    # Task family — tasks/ at repo root; order matters: sub-dirs before task itself
    if parts[0] == "tasks" and len(parts) >= 3:
        sub = parts[2]
        if sub == "runs":        return "run"
        if sub == "artifacts":   return "artifact"
        if sub == "prompts":     return "prompt"
        if sub == "data":        return "data"
        if len(parts) == 3 and stem == "manifest":
            return "task"

    if parts[0] == "docs":
        return "doc"

    # Skills — hub extension; skills/ may be nested at any depth
    if stem == "skill" and "/skills/" in path.as_posix():
        return "skill"

    # MD catch-all per spec §3 — any .md/.html that didn't match above
    if path.suffix.lower() in (".md", ".html", ".htm"):
        return "md"
    return None


def _task_slug(path: Path) -> str | None:
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "tasks" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _task_repo(path: Path, repo_root: Path) -> str:
    """Return the directory that owns the tasks/ folder, regardless of scan root depth.

    ~/tifin/cortex/tasks/slug/...  →  cortex   (scan root ~/tifin OR ~/tifin/cortex)
    """
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "tasks" and i > 0:
            return parts[i - 1]
    return repo_root.name


def _skill_slug(path: Path) -> str | None:
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "skills" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _skill_repo(path: Path, repo_root: Path) -> str:
    parts = path.parts
    for i, part in enumerate(parts):
        if part == "skills" and i > 0:
            return parts[i - 1]
    return repo_root.name


def _meta(path: Path, repo_root: Path) -> dict:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    rel = path.relative_to(repo_root).as_posix()
    return {
        "abs":        str(path),
        "rel":        rel,
        "mtime":      mtime,
        "ext":        path.suffix.lower().lstrip("."),
        "kind":       _classify(path, rel, repo_root.name),
        "task_slug":  _task_slug(path),
        "task_repo":  _task_repo(path, repo_root),
        "skill_slug": _skill_slug(path),
        "skill_repo": _skill_repo(path, repo_root),
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


def _collect_git(scan_root: Path, since_days: int = 7) -> list[dict]:
    """Return git commits from all repos under scan_root authored in the last N days."""
    commits: list[dict] = []
    try:
        repos = [p for p in scan_root.iterdir() if p.is_dir() and (p / ".git").exists()]
    except OSError:
        return commits
    for repo in repos:
        try:
            author = subprocess.run(
                ["git", "-C", str(repo), "config", "user.name"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if not author:
                continue
            out = subprocess.run(
                ["git", "-C", str(repo), "log", "--all",
                 f"--since={since_days} days ago",
                 f"--author={author}",
                 "--format=%at\t%s"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            for line in out.splitlines():
                if "\t" not in line:
                    continue
                ts_str, subject = line.split("\t", 1)
                commits.append({"rp": repo.name, "msg": subject.strip(), "ts": int(ts_str)})
        except Exception:
            continue
    return commits


def _first_run_html(root: Path) -> str:
    r = html.escape(str(root))
    return (
        '<div class="first-run">'
        '<div class="first-run-eyebrow">// nothing to index yet</div>'
        f'<div class="first-run-title">Hub looks for <em>.md</em> &amp; <em>.html</em> under <code>{r}</code>.</div>'
        '<p class="first-run-body">Drop docs anywhere and they\'ll appear. '
        'To unlock lineage, tasks live under '
        '<code>tasks/&lt;slug&gt;/</code> with a manifest.</p>'
        '<pre class="first-run-cmd">'
        '<span class="first-run-prompt">$</span> hub new task my-first-task\n'
        '<span class="first-run-comment"># scaffolds manifest + runs/ artifacts/ prompts/ data/</span>'
        '</pre>'
        '</div>'
    )


def render(groups: dict[str, list[dict]], fts_json: str = "[]", lineage_json: str = "{}", task_status_json: str = "{}", activity_json: str = "[]", timeline_json: str = "{}", tasks_json: str = "[]") -> str:
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
            if f.get("skill_slug"):
                task_attrs += (
                    f' data-skill-slug="{html.escape(f["skill_slug"])}"'
                    f' data-skill-repo="{html.escape(f["skill_repo"])}"'
                )
            items.append(
                f'<a class="row" href="{html.escape(_href(f["abs"]))}" '
                f'target="_blank" rel="noopener" '
                f'data-kind="{badge_cls}" '
                f'data-mtime="{int(f["mtime"])}" '
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
        body="".join(rows_html) or _first_run_html(ROOT),
        repo_chips=repo_chips,
        fts_json=fts_json,
        lineage_json=lineage_json,
        task_status_json=task_status_json,
        activity_json=activity_json,
        timeline_json=timeline_json,
        tasks_json=tasks_json,
        server_origin_json=json.dumps(_SERVER_ORIGIN),
        default_view_json=json.dumps(DEFAULT_VIEW),
    )


def _cmd_init(target: Path) -> None:
    """hub init — scaffold tasks/ and hub.toml stub in target directory."""
    tasks_dir = target / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    gitignore = target / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if "tasks/" not in content:
            with gitignore.open("a", encoding="utf-8") as fh:
                if not content.endswith("\n"):
                    fh.write("\n")
                fh.write("tasks/\n")
            print(f"  updated  {gitignore.relative_to(target)}")
    print(f"  created  {tasks_dir.relative_to(target)}/")
    hub_toml = target / "hub.toml"
    if not hub_toml.exists():
        hub_toml.write_text(_HUB_TOML_STUB, encoding="utf-8")
        print(f"  created  {hub_toml.relative_to(target)}")
    else:
        print(f"  exists   {hub_toml.relative_to(target)} — skipped")
    print("  hub init done — run 'hub new task <slug>' to scaffold your first task.")


_HUB_TOML_STUB = """\
# hub configuration — all keys optional. Environment variables override these.
[hub]
# scan_root    = "."                      # directory to index (default: CWD)
# port         = 8787                      # local server port
# exclude_dirs = ["vendor", "fixtures"]   # extra dirs to skip (added to built-ins)
# default_view = "list"                    # work | list | board | calendar | activity
"""


def _slugify_title(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _cmd_new_task(slug: str, target: Path) -> None:
    """hub new task <slug> — scaffold a minimal valid task per HUB-LAYOUT.md Appendix."""
    import re
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
        print(f"  error: slug must be lowercase-hyphenated (got '{slug}')")
        sys.exit(1)
    task_dir = target / "tasks" / slug
    task_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("runs", "artifacts", "prompts", "data"):
        (task_dir / sub).mkdir(exist_ok=True)
    manifest = task_dir / "manifest.md"
    if not manifest.exists():
        title = _slugify_title(slug)
        manifest.write_text(
            f"---\nstatus: ongoing\ntitle: {title}\n---\n\n# {title}\n",
            encoding="utf-8",
        )
        print(f"  created  tasks/{slug}/manifest.md")
        for sub in ("runs", "artifacts", "prompts", "data"):
            print(f"  created  tasks/{slug}/{sub}/")
    else:
        print(f"  exists   tasks/{slug}/manifest.md — skipped")


def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser(description="Hub index builder")
    ap.add_argument("--demo", action="store_true", help="Use bundled example fixture")
    ap.add_argument("--root", help="Scan root (overrides HUB_SCAN_ROOT, hub.toml, sidecar)")

    # Subcommands: hub init, hub new task <slug>
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("init", help="Scaffold tasks/ in the current directory")
    new_p = sub.add_parser("new", help="Scaffold a new task")
    new_p.add_argument("kind", choices=["task"], help="Object kind to create")
    new_p.add_argument("slug", help="Task slug (lowercase-hyphenated)")

    args, _ = ap.parse_known_args()

    if args.cmd == "init":
        _cmd_init(Path.cwd())
        return
    if args.cmd == "new" and getattr(args, "kind", None) == "task":
        _cmd_new_task(args.slug, Path.cwd())
        return

    if args.root:
        ROOT = config.resolve_scan_root(CONFIG, SCAN_ROOT_FILE, flag=args.root)
    if args.demo:
        ROOT = _HERE / "example"

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
                if f.get("kind") == "task" and f.get("task_slug"):
                    status = metadata.extract_status(text)
                    db.seed_status_from_frontmatter(conn, f["task_slug"], f["task_repo"], status)
    db.prune(conn, live_paths)
    db.build_lineage(conn)
    db.backfill_activity(conn)
    db.prune_activity(conn)
    fts_json, lineage_json = db.export_html_data(conn)
    task_status_json = db.get_statuses_json(conn)
    activity_json = db.get_activity_json(conn, str(ROOT))
    timeline_tasks = db.get_timeline_data(conn, str(ROOT))
    all_tasks = db.get_all_tasks(conn, str(ROOT))
    orphan_tasks = db.get_orphan_tasks(conn, str(ROOT))
    existing_keys = {(t["sl"], t["rp"]) for t in all_tasks}
    for ot in orphan_tasks:
        if (ot["sl"], ot["rp"]) not in existing_keys:
            all_tasks.append(ot)
    conn.close()

    for t in all_tasks:
        if t.get("abs"):
            _text = metadata.read_safe(t["abs"])
            t["plan"] = metadata.extract_plan(_text)
            t["decisions"] = metadata.extract_decisions(_text)

    tasks_json = json.dumps(all_tasks, separators=(",", ":"))

    git_commits = _collect_git(ROOT)
    timeline_json = json.dumps(
        {"tasks": timeline_tasks, "commits": git_commits},
        separators=(",", ":"),
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(groups, fts_json, lineage_json, task_status_json, activity_json, timeline_json, tasks_json), encoding="utf-8")
    total = sum(len(v) for v in groups.values())
    log(f"[hub] scanned {ROOT} -> {OUTPUT} ({total} files, {len(groups)} groups, {len(all_tasks)} tasks)")


if __name__ == "__main__":
    main()
