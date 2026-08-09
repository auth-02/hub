"""Task producer — the single writer of `tasks/<slug>/manifest.md`.

Shared by the `hub new task` CLI and the `POST /_new-task` server endpoint so
both producers emit the identical shape (see docs/HUB-LAYOUT.md §2, §4.1). A
manifest is the *only* file a producer must create; subdirs are created lazily
by whatever first writes into them. Nothing here touches the DB — the watcher
and rebuild reconcile the new file on their next tick.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..utils.paths import is_within

# A slug is the task's stable id: kebab-case, no path separators, no traversal.
# This regex is also the path-escape guard for the endpoint — it rejects `/`,
# `..`, absolute paths, and anything else that could escape `<repo>/tasks/`.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SlugError(ValueError):
    """The slug is empty or would escape `<repo>/tasks/` (bad chars, `..`, `/`)."""


class TaskExists(Exception):
    """A `manifest.md` already exists for this slug — never overwritten."""

    def __init__(self, slug: str, suggestion: str, rel: str) -> None:
        super().__init__(f"task '{slug}' already exists")
        self.slug = slug
        self.suggestion = suggestion
        self.rel = rel


def valid_slug(slug: str) -> bool:
    """True if `slug` is a safe kebab-case id that cannot escape tasks/."""
    return bool(slug) and _SLUG_RE.match(slug) is not None


def slugify_title(title: str) -> str:
    """Prettify a slug back into a Title for the manifest heading."""
    return title.replace("-", " ").replace("_", " ").title()


def manifest_path(repo_root: Path, slug: str) -> Path:
    """Where a task's manifest lands: `<repo_root>/tasks/<slug>/manifest.md`."""
    return repo_root / "tasks" / slug / "manifest.md"


def suffixed_slug(repo_root: Path, slug: str) -> str:
    """First `<slug>-N` (N≥2) whose manifest does not yet exist."""
    n = 2
    while manifest_path(repo_root, f"{slug}-{n}").exists():
        n += 1
    return f"{slug}-{n}"


def render_manifest(
    title: str,
    status: str = "ongoing",
    created: str | None = None,
    plan: list[str] | None = None,
) -> str:
    """Return the manifest.md text: frontmatter + `# Title` [+ `## Plan`].

    `created` is emitted only when given; `plan` (one string per checklist item)
    only when non-empty. With neither, the output matches `hub new task`'s
    historical minimal manifest exactly.
    """
    lines = ["---", f"status: {status}", f"title: {title}"]
    if created:
        lines.append(f"created: {created}")
    lines += ["---", "", f"# {title}"]
    if plan:
        lines += ["", "## Plan"]
        lines += [f"- [ ] {item}" for item in plan]
    return "\n".join(lines) + "\n"


def write_manifest(
    repo_root: Path,
    slug: str,
    title: str,
    status: str = "ongoing",
    created: str | None = None,
    plan: list[str] | None = None,
) -> Path:
    """Write exactly one file — `<repo_root>/tasks/<slug>/manifest.md`.

    Creates the task directory (and `tasks/` if absent) but no runs/artifacts/
    data subdirs. Raises `SlugError` on an unsafe slug, `TaskExists` on a
    collision (never overwrites), and lets `OSError` propagate on a read-only
    root. Returns the written path.
    """
    if not valid_slug(slug):
        raise SlugError(f"invalid slug: {slug!r}")
    path = manifest_path(repo_root, slug)
    # Defence in depth: the manifest must stay inside repo_root/tasks/.
    if not is_within(path.resolve(), (repo_root / "tasks").resolve()):
        raise SlugError(f"slug escapes tasks/: {slug!r}")
    if path.exists():
        rel = path.parent.relative_to(repo_root).as_posix()
        raise TaskExists(slug, suffixed_slug(repo_root, slug), rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_manifest(title, status, created or date.today().isoformat(), plan),
        encoding="utf-8",
    )
    return path
