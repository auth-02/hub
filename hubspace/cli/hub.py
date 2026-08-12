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
from ..core import query
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
PRIVATE = config.is_private(CONFIG)       # baked → JS PRIVATE; drops Publish row (1f)

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


def render(groups: dict[str, list[dict]], fts_json: str = "[]", lineage_json: str = "{}", task_status_json: str = "{}", activity_json: str = "[]", timeline_json: str = "{}", tasks_json: str = "[]", task_timeline_json: str = "{}", published_json: str = "{}", provenance_json: str = "{}", notes_json: str = "{}") -> str:
    # `note`-kind files are the per-task append-only comment log
    # (comments/notes.jsonl). They stay indexed (FTS + task_has_note lineage +
    # the // NOTES cards read them), but they are internal storage, not a
    # document to click into — so they never appear as plain list rows, kind
    # chips, or counts. See _classify() in scan.py: kind 'note' is exclusively
    # a comments/*.jsonl file.
    def _listable(f) -> bool:
        return f.get("kind") != "note"

    vis_groups = {
        repo: [f for f in files if _listable(f)]
        for repo, files in groups.items()
    }
    vis_groups = {repo: files for repo, files in vis_groups.items() if files}

    total     = sum(len(v) for v in vis_groups.values())
    md_total  = sum(1 for v in vis_groups.values() for f in v if f["ext"] == "md")
    html_total = total - md_total
    built     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def repo_recency(item):
        name, files = item
        newest = max((f["mtime"] for f in files), default=0)
        return (name == "(root)", -newest)

    rows_html = []
    for repo, files in sorted(vis_groups.items(), key=repo_recency):
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
        for r, _ in sorted(vis_groups.items(), key=repo_recency)
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
        repo_count=len(vis_groups),
        body="".join(rows_html) or _first_run_html(ROOT),
        repo_chips=repo_chips,
        fts_json=fts_json,
        lineage_json=lineage_json,
        task_status_json=task_status_json,
        activity_json=activity_json,
        timeline_json=timeline_json,
        tasks_json=tasks_json,
        task_timeline_json=task_timeline_json,
        server_origin_json=json.dumps(_SERVER_ORIGIN),
        default_view_json=json.dumps(DEFAULT_VIEW),
        upload_exts_json=json.dumps(sorted(UPLOAD_EXTS)),
        private_json=json.dumps(PRIVATE),
        published_json=published_json,
        provenance_json=provenance_json,
        notes_json=notes_json,
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


def _cmd_note(path_arg: str, message: str, range_: str | None = None,
              delete: str | None = None) -> None:
    """hub note <path> -m "..." [--range L41-L48] | --delete <id> — annotate/uncomment.

    `<path>` is the target file the note is about. Walks up to the nearest
    `tasks/<slug>/` to find the owning task, then either writes a note into that
    task's `comments/` via the shared `tasks.write_note` (same writer as
    `POST /_note`), or — with `--delete <id>` — removes the comment with that id
    via `tasks.delete_note` (the inverse of `POST /_note-delete`, verb-parity
    2c). Errors clearly when `<path>` is not under any task.
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

    if delete:
        try:
            note_file, removed = _tasks.delete_note(repo_root, slug, delete)
        except (_tasks.SlugError, ValueError) as e:
            print(f"  error: {e}")
            sys.exit(1)
        if removed is None:
            print(f"  no comment with id {delete} in {slug}")
            sys.exit(1)
        try:
            rel = note_file.relative_to(repo_root).as_posix()
        except ValueError:
            rel = str(note_file)
        print(f"  deleted   {rel}  (comment {delete})")
        return

    if not message:
        print("  error: pass -m <message> to add a comment, or --delete <id> to remove one")
        sys.exit(1)
    try:
        author = subprocess.run(
            ["git", "-C", str(repo_root), "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or None
    except Exception:
        author = None
    try:
        note_file, rec = _tasks.write_note(repo_root, slug, target_rel, message,
                                           author=author, range_=range_)
    except (_tasks.SlugError, ValueError) as e:
        print(f"  error: {e}")
        sys.exit(1)
    try:
        rel = note_file.relative_to(repo_root).as_posix()
    except ValueError:
        rel = str(note_file)
    # One line appended to the task's append-only comment log.
    print(f"  appended  {rel}  (comment {rec['id']} → {rec['target']})")


def _cmd_trace(path: str, as_json: bool) -> None:
    """hub trace <path> — print the lineage graph around a file (query.trace)."""
    from ..core import query
    conn = query.connect()
    try:
        result = query.trace(conn, path)
    finally:
        if conn is not None:
            conn.close()
    if as_json:
        print(json.dumps(result, indent=2))
        return
    if result["kind"] is None:
        print(f"  not indexed: {path}")
        return
    print(f"{result['path']}  [{result['kind']}]"
          + (f"  task: {result['task']}" if result["task"] else ""))
    for e in result["up"]:
        print(f"  ↑ {e['rel_type']}: {e['rel']} [{e['kind']}]")
    for e in result["down"]:
        print(f"  ↓ {e['rel_type']}: {e['rel']} [{e['kind']}]")
    if result["siblings"]:
        print(f"  ↔ {len(result['siblings'])} sibling(s):")
        for s in result["siblings"]:
            print(f"      {s['rel']} [{s['kind']}]")


def _cmd_timeline(slug: str, as_json: bool, as_graph: bool, repo: str | None) -> None:
    """hub timeline <slug> — the 2b timeline: chronological list, JSON, or graph.

    `--graph` emits the same nodes/edges contract as `--json` (they describe the
    same graph — layout and colours are the canvas's business, per 2b) and, when
    a server port is configured, also prints the canvas URL that opens the
    graph-order canvas for this task.
    """
    from ..core import query
    conn = query.connect()
    try:
        result = query.timeline(conn, slug, repo=repo)
    finally:
        if conn is not None:
            conn.close()
    if as_json or as_graph:
        print(json.dumps(result))
        if as_graph:
            port = config.resolve_port(CONFIG)
            if port and result["nodes"]:
                url = f"http://localhost:{port}/?graph={quote(slug)}"
                if result.get("task") and repo:
                    url += f"&repo={quote(repo)}"
                print(f"# canvas: {url}", file=sys.stderr)
        return
    nodes = sorted(result["nodes"], key=lambda n: (n["at"], n["path"]))
    if not nodes:
        print(f"  no task found: {slug}")
        return
    print(f"timeline: {result['task']}  ({len(nodes)} events)")
    for n in nodes:
        print(f"  {n['at']}  {n['kind']:9} {n['path']}")


def _cmd_draw(name: str | None, task: str | None, repo: str | None) -> None:
    """hub draw [--task <slug>] [--repo R] [name] — create a blank .excalidraw scene.

    With `--task`, the scene lands in that task's `draws/` (created lazily) at
    `tasks/<slug>/draws/<name>.excalidraw`; otherwise it is a top-level draw in
    the scan root. Shares the slug guard with `hub new task` and the draw-stem
    sanitiser with the server, and never clobbers an existing diagram (a colliding
    name suffixes `-N`). This is the `D` palette row's CLI equivalent.
    """
    from ..core import tasks as _tasks, graph as _graph
    from .server import _safe_draw_stem

    root = ROOT
    if repo:
        if not _tasks.valid_slug(repo):
            print(f"  error: bad repo '{repo}'")
            sys.exit(1)
        root = root / repo
    if task is not None:
        if not _tasks.valid_slug(task):
            print(f"  error: task slug must be lowercase-hyphenated (got '{task}')")
            sys.exit(1)
        manifest = root / "tasks" / task / "manifest.md"
        if not manifest.exists():
            print(f"  error: not a task — no tasks/{task}/manifest.md under {root}")
            sys.exit(1)
        base = root / "tasks" / task / "draws"
    else:
        base = root
    stem = _safe_draw_stem(name)
    target = base / f"{stem}.excalidraw"
    n = 2
    while target.exists():
        target = base / f"{stem}-{n}.excalidraw"
        n += 1
    base.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_graph.blank_scene()), encoding="utf-8")
    try:
        shown = target.relative_to(ROOT).as_posix()
    except ValueError:
        shown = str(target)
    print(f"  created  {shown}")


def _dak_script() -> Path:
    """Path to the bundled dak skill script (may not exist in an installed wheel).

    The hub-agent plugin — dak included — is excluded from the wheel, so in a
    pip/pipx install this file is absent and we fall back to printing the exact
    command for the user to run. In a source checkout it is present and we shell
    out to it. Hub NEVER imports dak; the subprocess boundary is the only link.
    """
    return (_HERE.parent / "plugin" / "hub-agent" / "skills"
            / "dak" / "scripts" / "dak.py")


def _cmd_publish(path_arg: str, *, reviewed: bool, do_redact: bool,
                 dry_run: bool, title: str | None, mode: str | None,
                 slug: str | None) -> None:
    """hub publish <path> — the privacy gate + handoff to dak (roadmap 1f).

    Hub does the LOCAL work only: run the redaction scan and (with --redact)
    prepare a sanitized copy. The actual upload is dak's job — Hub either shells
    out to the bundled dak script or, if it is absent, prints the exact command.
    Hub itself makes no network call.

    Gate: findings block publishing unless --i-have-reviewed (publish as-is) or
    --redact (publish a sanitized copy). With neither flag it is a scan only and
    exits non-zero when findings exist. `[hub] private = true` refuses entirely.
    """
    from ..core import publish as _publish

    if config.is_private(CONFIG):
        print("  refusing: this workspace is private ([hub] private = true)")
        sys.exit(2)

    target = Path(path_arg).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    if not target.is_file():
        print(f"  error: not a file: {path_arg}")
        sys.exit(1)

    text = metadata.read_safe(str(target))
    findings = _publish.scan(text)

    if findings:
        print(f"  {_publish.summary(findings)}")
    else:
        print("  ✓ scan clean — no findings")

    publishing = reviewed or do_redact
    if not publishing:
        # scan-only mode (--redact-scan or no gate flag)
        sys.exit(1 if findings else 0)

    # An approved publish. Decide what file dak receives.
    if do_redact and findings:
        redacted = _publish.redact(text, findings)
        copy_dir = config.state_dir() / "publish"
        copy_dir.mkdir(parents=True, exist_ok=True)
        copy = copy_dir / f"{target.stem}.redacted{target.suffix}"
        copy.write_text(redacted, encoding="utf-8")
        print(f"  redacted copy → {copy}  (original untouched)")
        publish_path = copy
    else:
        publish_path = target

    dak = _dak_script()
    cmd = ["python3", str(dak), str(publish_path)]
    if mode:
        cmd += ["--mode", mode]
    if slug:
        cmd += ["--slug", slug]
    cmd += ["--title", title or target.stem]
    if dry_run:
        cmd += ["--dry-run"]

    if not dak.exists():
        print("  dak not bundled here — run this to publish:")
        print("    " + " ".join(cmd))
        return
    print("  handing off to dak:")
    print("    " + " ".join(cmd))
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def _cmd_publish_task(slug: str, *, repo: str | None, include_external: bool,
                      out: str | None, reviewed: bool, do_redact: bool,
                      dry_run: bool, title: str | None, mode: str | None) -> None:
    """hub publish --task <slug> — freeze a task subtree to self-contained HTML,
    run the SAME S5a redaction gate over it, then hand off to dak (roadmap 1g).

    Hub's work is pure local rendering (:mod:`render.bundle`) + the shared
    privacy scan (:mod:`core.publish`); the upload is dak's job. The bundle is
    written under ``state_dir()/publish/`` — NEVER into the scan root. On a real
    (non-dry-run) publish that dak accepts, the published-state sidecar records
    ``{url, at, mode}`` so the hub can show a PUBLISHED marker. ``[hub] private``
    refuses entirely.
    """
    from ..core import publish as _publish
    from ..core import query
    from ..render import bundle as _bundle

    if config.is_private(CONFIG):
        print("  refusing: this workspace is private ([hub] private = true)")
        sys.exit(2)

    conn = query.connect()
    try:
        try:
            html = _bundle.render_task_bundle(
                conn, repo, slug, include_external=include_external)
        except ValueError as e:
            print(f"  error: {e}")
            sys.exit(1)
    finally:
        if conn is not None:
            conn.close()

    # Write the bundle under state_dir()/publish — never into the scan root.
    if out:
        out_path = Path(out).expanduser()
        if not out_path.is_absolute():
            out_path = Path.cwd() / out_path
    else:
        stem = f"{(repo or 'root')}-{slug}"
        out_path = config.state_dir() / "publish" / f"{stem}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"  bundle → {out_path}")

    # Same gate as `hub publish <path>`: scan the PRODUCED HTML.
    findings = _publish.scan(html)
    if findings:
        print(f"  {_publish.summary(findings)}")
    else:
        print("  ✓ scan clean — no findings")

    publishing = reviewed or do_redact
    if not publishing:
        sys.exit(1 if findings else 0)

    publish_path = out_path
    if do_redact and findings:
        redacted = _publish.redact(html, findings)
        publish_path = out_path.with_suffix(".redacted.html")
        publish_path.write_text(redacted, encoding="utf-8")
        print(f"  redacted copy → {publish_path}  (bundle untouched)")

    dak = _dak_script()
    cmd = ["python3", str(dak), str(publish_path)]
    if mode:
        cmd += ["--mode", mode]
    cmd += ["--slug", slug, "--title", title or slug]
    if dry_run:
        cmd += ["--dry-run"]

    if not dak.exists():
        print("  dak not bundled here — run this to publish:")
        print("    " + " ".join(cmd))
        return
    print("  handing off to dak:")
    print("    " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    # Record published-state only on a real, accepted publish (not dry-run).
    if result.returncode == 0 and not dry_run:
        import re
        url = ""
        for line in (result.stdout or "").splitlines():
            m = re.search(r"https?://\S+", line)
            if m:
                url = m.group(0)
                break
        _publish.record_published(repo, slug, url, mode=mode or "snapshot")
        print(f"  recorded published-state ({_publish.published_path()})")
    sys.exit(result.returncode)


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

    # hub note <path> -m "..." | --delete <id> — annotate/uncomment (roadmap 1e / 2c).
    note_p = sub.add_parser("note", help="Annotate a task file (hub note <path> -m <msg> | --delete <id>)")
    note_p.add_argument("path", help="Target file the note is about (under a tasks/<slug>/)")
    note_p.add_argument("-m", "--message", default=None, help="The note body (to add a comment)")
    note_p.add_argument("--range", dest="range", default=None, metavar="L..",
                        help="Optional line range the note is about, e.g. L41-L48")
    note_p.add_argument("--delete", dest="delete", default=None, metavar="ID",
                        help="Remove the comment with this id instead of adding one")

    # hub mcp serve — MCP stdio server (JSON-RPC 2.0 over newline-delimited
    # stdin/stdout). A daemon, so it has no palette/UI row (roadmap note on 1h).
    mcp_p = sub.add_parser("mcp", help="Run the read-only MCP stdio server (hub mcp serve)")
    mcp_p.add_argument("action", choices=["serve"], help="MCP action")

    # hub trace <path> [--json] — lineage graph around one file (query.trace).
    trace_p = sub.add_parser("trace", help="Show the lineage around a file (query.trace)")
    trace_p.add_argument("path", help="Absolute or scan-root-relative file path")
    trace_p.add_argument("--json", action="store_true", help="Emit raw JSON")

    # hub timeline <slug> [--json] [--repo R] — the 2b task timeline contract.
    timeline_p = sub.add_parser("timeline", help="Show a task timeline (query.timeline)")
    timeline_p.add_argument("slug", help="Task slug (lowercase-hyphenated)")
    timeline_p.add_argument("--json", action="store_true", help="Emit the raw 2b JSON contract")
    timeline_p.add_argument("--graph", action="store_true",
                            help="Emit the 2b graph contract (nodes/edges) + canvas URL")
    timeline_p.add_argument("--repo", default=None, help="Owning repo (disambiguates a slug)")

    # hub draw [--task <slug>] [--repo R] [name] — create a blank .excalidraw scene.
    draw_p = sub.add_parser("draw", help="Create a blank Excalidraw scene (hub draw [--task <slug>] [name])")
    draw_p.add_argument("name", nargs="?", default=None, help="Diagram name (default: timestamp slug)")
    draw_p.add_argument("--task", default=None, help="Scope the draw to a task's draws/ folder")
    draw_p.add_argument("--repo", default=None, help="Owning repo (a subdir of the scan root)")

    # hub publish <path> — privacy gate (scan → review/redact) + handoff to dak.
    # Hub does the local scan only; dak (a separate script) does the upload.
    pub_p = sub.add_parser("publish", help="Scan + publish an asset or a whole task via dak (hub publish <path> | --task <slug>)")
    pub_p.add_argument("path", nargs="?", default=None,
                       help="File to publish (absolute or CWD-relative). Omit with --task.")
    # 1g — freeze a whole task subtree to a self-contained bundle and publish it.
    pub_p.add_argument("--task", default=None,
                       help="Publish a whole task subtree as one self-contained HTML bundle")
    pub_p.add_argument("--include-external", dest="include_external", action="store_true",
                       help="Inline cross-task lineage refs (default: mark them excluded)")
    pub_p.add_argument("--out", default=None,
                       help="Bundle output path (default: state_dir()/publish/<repo>-<slug>.html)")
    pub_p.add_argument("--revoke", action="store_true",
                       help="With --task: forget the local published-state entry and exit")
    gate = pub_p.add_mutually_exclusive_group()
    gate.add_argument("--redact-scan", action="store_true",
                      help="Only run the scan and exit non-zero if findings exist (default)")
    gate.add_argument("--i-have-reviewed", dest="reviewed", action="store_true",
                      help="Publish the file as-is despite findings (you reviewed them)")
    gate.add_argument("--redact", dest="do_redact", action="store_true",
                      help="Publish a sanitized copy with findings redacted (original untouched)")
    pub_p.add_argument("--dry-run", action="store_true", help="Pass --dry-run through to dak")
    pub_p.add_argument("--title", default=None, help="Title for the published page")
    pub_p.add_argument("--mode", choices=["snapshot", "live"], default=None, help="dak publish mode")
    pub_p.add_argument("--slug", default=None, help="dak URL slug")
    pub_p.add_argument("--repo", default=None, help="With --task: owning repo (disambiguates a slug)")

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
        _cmd_note(args.path, args.message, getattr(args, "range", None),
                  getattr(args, "delete", None))
        return
    if args.cmd == "agent":
        from .agent import run as agent_run
        agent_run(args)
        return
    if args.cmd == "mcp":
        from . import mcp
        mcp.serve()
        return
    if args.cmd == "trace":
        _cmd_trace(args.path, args.json)
        return
    if args.cmd == "timeline":
        _cmd_timeline(args.slug, args.json, args.graph, args.repo)
        return
    if args.cmd == "draw":
        _cmd_draw(args.name, args.task, args.repo)
        return
    if args.cmd == "publish":
        if args.task:
            if args.revoke:
                from ..core import publish as _publish
                removed = _publish.revoke_published(args.repo, args.task)
                print("  revoked" if removed else "  no published-state entry to revoke")
                return
            _cmd_publish_task(
                args.task,
                repo=args.repo,
                include_external=args.include_external,
                out=args.out,
                reviewed=args.reviewed,
                do_redact=args.do_redact,
                dry_run=args.dry_run,
                title=args.title,
                mode=args.mode,
            )
            return
        if not args.path:
            print("  error: give a file path or --task <slug>")
            sys.exit(1)
        _cmd_publish(
            args.path,
            reviewed=args.reviewed,
            do_redact=args.do_redact,
            dry_run=args.dry_run,
            title=args.title,
            mode=args.mode,
            slug=args.slug,
        )
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

    # S4a — per-task timeline (the "how this evolved" spine in Trace). Reuse the
    # 2b contract (query.timeline) so the client renders already-indexed lineage
    # with no new endpoint. Keyed by "<repo>\t<slug>" for O(1) client lookup.
    # Bake the full 2b contract ({nodes, edges}) — S4a lists the nodes by date,
    # S4b (2b) re-renders the same events + edges in graph order on the canvas.
    task_timelines: dict = {}
    for t in all_tasks:
        tl = query.timeline(conn, t["sl"], repo=t["rp"])
        if tl.get("nodes"):
            task_timelines[f'{t["rp"]}\t{t["sl"]}'] = {"nodes": tl["nodes"], "edges": tl.get("edges", [])}
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
    task_timeline_json = json.dumps(task_timelines, separators=(",", ":"))

    # S12 — bake each task's stored comments so the Trace overlay can render the
    # // NOTES cards (author · time · body). Comments live in an append-only
    # JSONL at tasks/<slug>/comments/notes.jsonl; read_notes() returns [] when the
    # file is absent, so a task with no comments is simply omitted. Keyed by
    # "<repo>\t<slug>" to match TASK_TIMELINE_DATA. Bodies stay raw data — the UI
    # escapes them on render.
    from ..core import tasks as _tasks
    notes_map: dict = {}
    for t in all_tasks:
        if not t.get("abs"):
            continue
        task_dir = Path(t["abs"]).parent
        comments = _tasks.read_notes(task_dir)
        if not comments:
            continue
        notes_map[f'{t["rp"]}\t{t["sl"]}'] = [
            {"id": c.get("id"), "author": c.get("author"),
             "created": c.get("created"), "body": c.get("body"),
             "target": c.get("target"), "range": c.get("range")}
            for c in comments
        ]
    notes_json = json.dumps(notes_map, separators=(",", ":"))

    # 1g — bake the published-state sidecar so a published task row can show a
    # PUBLISHED marker (URL + republish/revoke). Read-only; a missing file → {}.
    from ..core import publish as _publish
    # Re-key single-file asset entries to the files-index abs form (unresolved,
    # what each row bakes as data-abs) so the UI's PUBLISHED_DATA lookup hits even
    # when the scan root is symlinked (e.g. /var → /private/var). See
    # publish.realign_asset_keys.
    _all_abs = [f["abs"] for files in groups.values() for f in files if f.get("abs")]
    _pub_data = _publish.realign_asset_keys(_publish.load_published(), _all_abs)
    published_json = json.dumps(_pub_data, separators=(",", ":"))

    # S6 (2a) — bake per-artifact provenance so the UI can show an "ask again"
    # affordance (copy-only) on agent-generated artifacts. Read straight from
    # each file's own front matter; only artifacts carry it, so the map is tiny.
    provenance: dict = {}
    for repo, files in groups.items():
        for f in files:
            if f.get("kind") == "artifact" and Path(f["abs"]).suffix.lower() in (
                ".html", ".htm", ".md", ".markdown"
            ):
                prov = metadata.extract_provenance(metadata.read_safe(f["abs"]))
                if prov:
                    provenance[f["abs"]] = prov
    provenance_json = json.dumps(provenance, separators=(",", ":"))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(groups, fts_json, lineage_json, task_status_json, activity_json, timeline_json, tasks_json, task_timeline_json, published_json, provenance_json, notes_json), encoding="utf-8")
    total = sum(len(v) for v in groups.values())
    log(f"[hub] scanned {ROOT} -> {OUTPUT} ({total} files, {len(groups)} groups, {len(all_tasks)} tasks)")


if __name__ == "__main__":
    main()
