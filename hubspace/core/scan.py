"""Path-based file classification and metadata extraction (pure helpers).

No module-level state: every function takes its inputs explicitly, so this
is the reusable core of hub's scanning logic (see docs/HUB-LAYOUT.md §3).
"""
from __future__ import annotations

from pathlib import Path


EXTS = {".md", ".html", ".htm"}
PROMPT_EXTS = {".txt"}
DATA_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".tsv"}
DRAW_EXTS = {".excalidraw"}  # Excalidraw diagrams — first-class vault docs, any dir


def _included(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in EXTS:
        return True
    if ext in DRAW_EXTS:  # draw anywhere in the vault
        return True
    if ext in PROMPT_EXTS and "/prompts/" in path.as_posix():
        return True
    if ext in DATA_EXTS and "/data/" in path.as_posix():
        return True
    return False


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

    # Excalidraw diagrams are always kind:draw, regardless of name or location.
    if path.suffix.lower() in DRAW_EXTS:
        return "draw"

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
