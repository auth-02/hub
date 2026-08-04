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
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .. import __version__
from ..core import config
from ..core import db
from ..core import metadata
from ..core.scan import _included, _meta
from ..utils.paths import env_path
from ..utils.text import relative_time

_HERE = Path(__file__).resolve().parent


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
FAVICON = env_path("HUB_FAVICON", config.static_dir() / "favicon.svg")
DB     = env_path("HUB_DB",    _state_dir() / "hub.db")

_SERVER_PORT   = config.resolve_port(CONFIG)
_SERVER_ORIGIN = f"http://localhost:{_SERVER_PORT}" if _SERVER_PORT else ""

_TEMPLATE_PATH = config.static_dir() / "hub.html"

EXCLUDE_DIRS = {
    ".claude", ".git", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".next", "dist", "build", ".turbo", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "coverage", "site-packages", ".idea", ".vscode",
    ".cache", ".gradle", "target", "out", ".terraform", ".dagster",
    "graphify-out",
}
EXCLUDE_DIRS |= config.config_exclude_dirs(CONFIG)
DEFAULT_VIEW = config.resolve_default_view(CONFIG)
UPLOAD_EXTS = config.upload_exts(CONFIG)  # allowlist mirrored to the UI (1d)

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


def _href(abs_path: str) -> str:
    if _SERVER_PORT:
        return f"http://localhost:{_SERVER_PORT}" + quote(abs_path)
    return "file://" + quote(abs_path)


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
        '<span class="first-run-comment"># scaffolds manifest.md (subdirs are created on demand)</span>'
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
                f'<span class="ago">{relative_time(f["mtime"])}</span>'
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
        upload_exts_json=json.dumps(sorted(UPLOAD_EXTS)),
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


# Manifest-owned subdirs that --with may pre-create. prompts/ is intentionally
# excluded — the PROMPT kind belongs to pre-existing prompts/ folders only and
# is not part of task scaffolding (see docs/HUB-LAYOUT.md §2).
_TASK_SUBDIRS = ("runs", "artifacts", "data")


def _resolve_with_dirs(with_dirs: list[str] | None) -> list[str]:
    """Expand repeated --with values (incl. 'all') into an ordered, de-duped list."""
    if not with_dirs:
        return []
    if "all" in with_dirs:
        return list(_TASK_SUBDIRS)
    return [d for d in _TASK_SUBDIRS if d in with_dirs]


def _cmd_new_task(slug: str, target: Path, with_dirs: list[str] | None = None) -> None:
    """hub new task <slug> [--with runs|artifacts|data|all] — scaffold a task.

    Creates manifest.md only by default; subdirs are otherwise created lazily by
    whatever first writes into them. Pass --with to pre-create chosen subdirs.
    Re-running on an existing task is safe and creates any still-missing --with
    dirs, so it doubles as the "add these later" path.
    """
    from ..core import tasks as _tasks
    if not _tasks.valid_slug(slug):
        print(f"  error: slug must be lowercase-hyphenated (got '{slug}')")
        sys.exit(1)
    task_dir = target / "tasks" / slug
    task_dir.mkdir(parents=True, exist_ok=True)
    manifest = task_dir / "manifest.md"
    if not manifest.exists():
        manifest.write_text(
            _tasks.render_manifest(_slugify_title(slug)),
            encoding="utf-8",
        )
        print(f"  created  tasks/{slug}/manifest.md")
    else:
        print(f"  exists   tasks/{slug}/manifest.md — skipped")

    for sub in _resolve_with_dirs(with_dirs):
        d = task_dir / sub
        if d.exists():
            print(f"  exists   tasks/{slug}/{sub}/ — skipped")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  created  tasks/{slug}/{sub}/")


def _cmd_note(path_arg: str, message: str, range_: str | None = None) -> None:
    """hub note <path> -m "..." [--range L41-L48] — annotate a task file.

    `<path>` is the target file the note is about. Walks up to the nearest
    `tasks/<slug>/` to find the owning task, then writes the note into that
    task's `comments/` via the shared `tasks.write_note` (same writer as
    `POST /_note`). Errors clearly when `<path>` is not under any task.
    """
    from ..core import tasks as _tasks

    target = Path(path_arg).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    ctx = _tasks.find_task_for(target)
    if ctx is None:
        print(f"  error: {path_arg} is not under a tasks/<slug>/ directory")
        sys.exit(1)
    repo_root, slug, target_rel = ctx
    try:
        author = subprocess.run(
            ["git", "-C", str(repo_root), "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or None
    except Exception:
        author = None
    try:
        note = _tasks.write_note(repo_root, slug, target_rel, message,
                                 author=author, range_=range_)
    except (_tasks.SlugError, ValueError) as e:
        print(f"  error: {e}")
        sys.exit(1)
    try:
        rel = note.relative_to(repo_root).as_posix()
    except ValueError:
        rel = str(note)
    print(f"  created  {rel}")


def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser(
        prog="hub",
        description="Build a browsable hub of every .md / .html file under a scan root. "
                    "Run with no command to (re)build the index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  hub                                rebuild the index (default action)\n"
            "  hub --demo                         rebuild against the bundled example fixture\n"
            "  hub init                           scaffold tasks/ in the current directory\n"
            "  hub new task add-sso-login         create a task (manifest.md only)\n"
            "  hub new task add-sso-login --with all   ...and pre-create runs/ artifacts/ data/\n"
            "  hub note tasks/add-sso-login/artifacts/flow.html -m \"rotation window feels short\"\n"
            "  hub serve --port 8787              serve the hub over HTTP (watches + rebuilds)\n"
        ),
    )
    ap.add_argument("--version", action="version", version=f"hub {__version__}")
    ap.add_argument("--demo", action="store_true", help="Use bundled example fixture")
    ap.add_argument("--root", help="Scan root (overrides HUB_SCAN_ROOT, hub.toml, sidecar)")

    # Subcommands: hub init, hub new task <slug>
    sub = ap.add_subparsers(dest="cmd", title="commands", metavar="<command>")
    sub.add_parser("init", help="Scaffold tasks/ in the current directory")
    serve_p = sub.add_parser("serve", help="Serve the hub over HTTP (watches + rebuilds)")
    serve_p.add_argument("--port", "-p", type=int, default=None, metavar="PORT",
                         help="Port to listen on (default: hub.toml port or 8787)")
    serve_p.add_argument("--demo", action="store_true", help="Use bundled example fixture")
    new_p = sub.add_parser("new", help="Scaffold a new task (hub new task <slug>)")
    new_p.add_argument("kind", choices=["task"], help="Object kind to create")
    new_p.add_argument("slug", help="Task slug (lowercase-hyphenated)")
    new_p.add_argument(
        "--with", dest="with_dirs", action="append", default=[],
        choices=["all", *_TASK_SUBDIRS], metavar="DIR",
        help="Pre-create subdir(s): runs, artifacts, data, or all. Repeatable. "
             "Safe to re-run on an existing task to add them later.",
    )

    # hub note <path> -m "..." — annotate a task file (roadmap 1e / 2c).
    note_p = sub.add_parser("note", help="Annotate a task file (hub note <path> -m <msg>)")
    note_p.add_argument("path", help="Target file the note is about (under a tasks/<slug>/)")
    note_p.add_argument("-m", "--message", required=True, help="The note body")
    note_p.add_argument("--range", dest="range", default=None, metavar="L..",
                        help="Optional line range the note is about, e.g. L41-L48")

    # hub agent {install|uninstall|status} — persistent launchd agent (macOS).
    # Reusable by both the package launchd script and the plugin daemon script;
    # only the launcher differs (passed via --exec). See cli/agent.py.
    agent_p = sub.add_parser("agent", help="Manage a persistent launchd agent (macOS) that runs hub")
    agent_p.add_argument("action", choices=["install", "uninstall", "status"])
    agent_p.add_argument("--label", default="com.user.hub", help="launchd label (default: com.user.hub)")
    agent_p.add_argument("--port", type=int, default=8787, help="Port to serve on (default: 8787)")
    agent_p.add_argument("--root", default=None, help="WorkingDirectory to serve (default: CWD)")
    agent_p.add_argument("--exec", dest="exec_prefix", default=None,
                         help="Launcher command prefix, e.g. 'uv tool run --offline --from <wheel> hub' "
                              "(default: resolved 'hub')")
    grp = agent_p.add_mutually_exclusive_group()
    grp.add_argument("--serve", action="store_true",
                     help="KeepAlive agent running 'hub serve' (default)")
    grp.add_argument("--rebuild-interval", dest="rebuild_interval", type=int, metavar="SECS",
                     help="StartInterval agent that rebuilds the index every SECS")

    args, _ = ap.parse_known_args()

    if args.cmd == "init":
        _cmd_init(Path.cwd())
        return
    if args.cmd == "serve":
        from .server import serve, default_port
        serve(args.port if args.port is not None else default_port(), args.demo)
        return
    if args.cmd == "new" and getattr(args, "kind", None) == "task":
        _cmd_new_task(args.slug, Path.cwd(), getattr(args, "with_dirs", None))
        return
    if args.cmd == "note":
        _cmd_note(args.path, args.message, getattr(args, "range", None))
        return
    if args.cmd == "agent":
        from .agent import run as agent_run
        agent_run(args)
        return

    if args.root:
        ROOT = config.resolve_scan_root(CONFIG, SCAN_ROOT_FILE, flag=args.root)
    if args.demo:
        ROOT = config.example_dir()

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
