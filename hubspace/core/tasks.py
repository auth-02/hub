"""Task producer — the single writer of `tasks/<slug>/manifest.md`.

Shared by the `hub new task` CLI and the `POST /_new-task` server endpoint so
both producers emit the identical shape (see docs/HUB-LAYOUT.md §2, §4.1). A
manifest is the *only* file a producer must create; subdirs are created lazily
by whatever first writes into them. Nothing here touches the DB — the watcher
and rebuild reconcile the new file on their next tick.
"""
from __future__ import annotations

import os
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


# ── data upload (roadmap 1d — Add data) ─────────────────────────────────────
# A task's attachments land in `<repo>/tasks/<slug>/data/`. The writer below is
# the single testable guard: given a dest data/ dir + a client-supplied filename
# + bytes, it either writes the file (names preserved, collisions suffixed) or
# returns a rejection reason. Nothing here touches the DB — the watcher/rebuild
# reconcile the new file, exactly like write_manifest().

UPLOAD_MAX_BYTES = 64 * 1024 * 1024  # 64 MB per-file guard.


def safe_basename(name: str) -> str | None:
    """Reduce a client-supplied upload name to a bare filename, or None if unsafe.

    Rejects anything carrying a path separator (`/` or `\\`), a NUL byte, an
    absolute path, a `.`/`..` traversal segment, or an empty result — so a
    crafted upload filename can never escape the task's own data/ dir. This is
    the filename analogue of `valid_slug`.
    """
    if not name or not isinstance(name, str):
        return None
    if "/" in name or "\\" in name or "\x00" in name:
        return None
    base = name.strip()
    if base in ("", ".", ".."):
        return None
    # Defence in depth: with separators already rejected these agree, but a
    # mismatch (e.g. an odd platform basename) means we drop it.
    if os.path.basename(base) != base:
        return None
    return base


def _suffixed_name(base: str, n: int) -> str:
    """`report.pdf` → `report-2.pdf`; a name with no extension → `report-2`."""
    stem, dot, ext = base.rpartition(".")
    return f"{stem}-{n}.{ext}" if dot else f"{base}-{n}"


def accept_upload(
    data_dir: Path,
    filename: str,
    data: bytes,
    allowed_exts: set[str],
    max_bytes: int = UPLOAD_MAX_BYTES,
) -> tuple[Path | None, str | None]:
    """Validate one upload and, if accepted, write it into `data_dir`.

    Returns ``(written_path, None)`` on success or ``(None, reason)`` on
    rejection. Guards, in order:
      1. safe basename — no path separator, `..`, or absolute path,
      2. extension allowlist (`allowed_exts`, lowercased/dot-prefixed),
      3. per-file size cap (`max_bytes`, default 64 MB).
    `data_dir` (a task's data/) is created lazily. A name collision suffixes
    `-2`, `-3`, … — an existing file is never overwritten. Lets `OSError`
    propagate (e.g. a read-only root) so the caller can map it to a 403.
    """
    base = safe_basename(filename)
    if base is None:
        return None, "unsafe filename"
    ext = ("." + base.rsplit(".", 1)[1].lower()) if "." in base else ""
    allowed = {e.lower() for e in allowed_exts}
    if ext not in allowed:
        return None, f"{ext or 'no extension'} not in the allowlist"
    if len(data) > max_bytes:
        return None, "over the 64 MB guard"
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / base
    n = 2
    while target.exists():  # never clobber an existing file
        target = data_dir / _suffixed_name(base, n)
        n += 1
    # Defence in depth: the resolved write must stay inside data_dir.
    if not is_within(target.resolve(), data_dir.resolve()):
        return None, "unsafe filename"
    target.write_bytes(data)
    return target, None


# ── comments / notes (roadmap 1e — Comments & annotations) ──────────────────
# A note is ONE markdown file at `<repo>/tasks/<slug>/comments/<date>-<slug>.md`
# with a small front-matter anchor pointing at the file it is about. The writer
# below is shared by the `hub note` CLI verb and the `POST /_note` endpoint so
# both emit the identical shape (verb-parity, roadmap 2c). Like write_manifest()
# it touches no DB — the watcher/rebuild reconcile the new file on their tick.


def note_stem(body: str, target: str = "", max_words: int = 6) -> str:
    """A short kebab slug for a note filename, from the body then the target.

    Takes the first few words of the note body; if that yields nothing usable,
    falls back to the target file's stem, then to a bare ``note``. Capped so the
    filename stays short.
    """
    from ..utils.text import slugify

    base = slugify(" ".join((body or "").split()[:max_words]))
    if not base and target:
        base = slugify(Path(target).stem)
    return (base[:60].strip("-")) or "note"


def render_note(
    target: str,
    body: str,
    author: str | None = None,
    range_: str | None = None,
    created: str | None = None,
) -> str:
    """Return a note's markdown: a small front-matter anchor + the body.

    `range` and `author` are emitted only when given; `target` and `created`
    always appear. See docs/HUB-LAYOUT.md §2 (comments/).
    """
    lines = ["---", f"target: {target}"]
    if range_:
        lines.append(f"range: {range_}")
    if author:
        lines.append(f"author: {author}")
    lines.append(f"created: {created or date.today().isoformat()}")
    lines += ["---", "", (body or "").strip()]
    return "\n".join(lines) + "\n"


def write_note(
    repo_root: Path,
    slug: str,
    target: str,
    body: str,
    author: str | None = None,
    range_: str | None = None,
    created: str | None = None,
) -> Path:
    """Write exactly one note into `<repo_root>/tasks/<slug>/comments/`.

    The single note writer shared by `hub note` and `POST /_note`. The file is
    `comments/<date>-<note-slug>.md` — markdown whose front matter anchors it to
    `target` (the task-relative path the note is about) with an optional line
    `range`. `comments/` is created lazily; a colliding filename suffixes `-N`
    and an existing note is never overwritten. Raises `SlugError` on an unsafe
    slug or a `target` that escapes the task, `ValueError` on an empty
    target/body, and lets `OSError` propagate on a read-only root. Returns the
    written path.
    """
    if not valid_slug(slug):
        raise SlugError(f"invalid slug: {slug!r}")
    task_dir = (repo_root / "tasks" / slug).resolve()
    if not is_within(task_dir, (repo_root / "tasks").resolve()):
        raise SlugError(f"slug escapes tasks/: {slug!r}")
    target = (target or "").strip()
    if not target:
        raise ValueError("target required")
    body = (body or "").strip()
    if not body:
        raise ValueError("body required")
    # `target` is task-relative and must resolve inside the task dir — no absolute
    # path, no `..` traversal escaping the task.
    if target.startswith("/") or "\x00" in target:
        raise SlugError(f"target escapes task: {target!r}")
    if not is_within((task_dir / target).resolve(), task_dir):
        raise SlugError(f"target escapes task: {target!r}")
    created = created or date.today().isoformat()
    stem = note_stem(body, target)
    comments_dir = task_dir / "comments"
    path = comments_dir / f"{created}-{stem}.md"
    n = 2
    while path.exists():  # never clobber an existing note
        path = comments_dir / f"{created}-{stem}-{n}.md"
        n += 1
    # Defence in depth: the resolved write must stay inside the task dir.
    if not is_within(path.resolve(), task_dir):
        raise SlugError("note path escapes task")
    comments_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_note(target, body, author, range_, created), encoding="utf-8"
    )
    return path


def find_task_for(path: Path) -> tuple[Path, str, str] | None:
    """Walk up from `path` to the nearest `tasks/<slug>/`; return its context.

    Returns ``(repo_root, slug, target_rel)`` where `repo_root` owns the `tasks/`
    dir, `slug` is the task, and `target_rel` is `path` expressed relative to the
    task dir (the note's `target:` anchor). Returns None when `path` is not under
    any `tasks/<slug>/`. Used by the `hub note <path>` CLI verb.
    """
    p = path.resolve()
    parts = p.parts
    for i in range(len(parts) - 1):
        if parts[i] == "tasks" and i > 0:
            slug = parts[i + 1] if i + 1 < len(parts) else ""
            if not valid_slug(slug):
                continue
            repo_root = Path(*parts[:i])
            task_dir = repo_root / "tasks" / slug
            try:
                target_rel = p.relative_to(task_dir.resolve()).as_posix()
            except ValueError:
                continue
            return repo_root, slug, target_rel
    return None


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
