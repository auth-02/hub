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
from datetime import date, datetime
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
    """Return the manifest.md text: `# Title` [+ `## Plan`].

    Hub no longer writes YAML frontmatter (S22): a new manifest is just the
    `# Title` H1 (title resolution falls back to it — HUB-LAYOUT §4.3) plus a
    `## Plan` checklist when `plan` items are given. Status is tracked in the
    DB/sidecar (default `ongoing`), never seeded from a produced file, so the
    `status`/`created` params are accepted for signature compatibility but not
    emitted. Frontmatter authored by a human/agent is still read if present.
    """
    lines = [f"# {title}"]
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


# ── comments / notes (roadmap 1e — Comments & annotations, S7 revision) ──────
# Comments are an append-only JSONL log: ONE file per task at
# `<repo>/tasks/<slug>/comments/notes.jsonl`, one JSON object per line, one line
# per comment (see docs/HUB-LAYOUT.md §2). Adding a comment appends exactly one
# line and never rewrites or reorders existing lines — the file is the source of
# truth (`rm hub.db` loses nothing). The writer below is shared by the `hub
# note` CLI verb and the `POST /_note` endpoint so both emit the identical shape
# (verb-parity, roadmap 2c). Like write_manifest() it touches no DB — the
# watcher/rebuild reconcile the file on their tick.

NOTES_FILE = "notes.jsonl"


def notes_path(repo_root: Path, slug: str) -> Path:
    """Where a task's comment log lives: `<slug>/comments/notes.jsonl`."""
    return repo_root / "tasks" / slug / "comments" / NOTES_FILE


def note_id(target: str, body: str, created: str, range_: str | None = None,
            existing: set[str] | None = None) -> str:
    """A short, stable, deterministic id for one comment line.

    Derived from a content hash of the note's fields (NOT time/random) so a given
    comment always hashes to the same id and tests stay stable. Disambiguated
    with a ``-N`` suffix only if that hash already appears in `existing` (the ids
    already present in the file), which keeps ids unique per file.
    """
    import hashlib

    base = "\x1f".join([created or "", target or "", range_ or "", body or ""])
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    existing = existing or set()
    nid, n = h, 2
    while nid in existing:
        nid = f"{h}-{n}"
        n += 1
    return nid


def read_notes(task_dir: Path) -> list[dict]:
    """Parse a task's `comments/notes.jsonl` into a list of comment dicts.

    Reads `<task_dir>/comments/notes.jsonl`, one JSON object per line. A missing
    file yields ``[]``; a malformed or non-object line is skipped rather than
    raising, so a partially-corrupt log still reads. Order is preserved (append
    order = chronological).
    """
    import json

    path = Path(task_dir) / "comments" / NOTES_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue  # skip a malformed line without crashing
        if isinstance(rec, dict):
            out.append(rec)
    return out


def write_note(
    repo_root: Path,
    slug: str,
    target: str,
    body: str,
    author: str | None = None,
    range_: str | None = None,
    created: str | None = None,
) -> tuple[Path, dict]:
    """Append exactly one comment line to `<slug>/comments/notes.jsonl`.

    The single comment writer shared by `hub note` and `POST /_note`. Appends ONE
    JSON object (`{id,target,range?,author,created,body}`) as a new line; it never
    rewrites or reorders existing lines, so prior comments stay byte-identical.
    `comments/notes.jsonl` is created lazily on the first comment. `target` is
    task-relative (defaults to the manifest for a general comment) and must
    resolve inside the task. Raises `SlugError` on an unsafe slug or an escaping
    `target`, `ValueError` on an empty target/body, and lets `OSError` propagate
    on a read-only root. Returns ``(notes_path, appended_record)``.
    """
    import json

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

    created = created or datetime.now().isoformat(timespec="seconds")
    range_ = (range_ or "").strip() or None
    existing = {r.get("id") for r in read_notes(task_dir) if isinstance(r, dict)}
    rec: dict = {"id": note_id(target, body, created, range_, existing),
                 "target": target}
    if range_:
        rec["range"] = range_
    rec["author"] = (author or "").strip() or "you"
    rec["created"] = created
    rec["body"] = body

    path = task_dir / "comments" / NOTES_FILE
    # Defence in depth: the resolved write must stay inside the task dir.
    if not is_within(path.resolve(), task_dir):
        raise SlugError("note path escapes task")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(rec, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:  # append-only: never rewrites
        fh.write(line + "\n")
    return path, rec


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


# ── inline manifest editing (roadmap 1i — plan + status only) ────────────────
# The manifest file on disk is the source of truth. `rewrite_manifest` is the
# single pure, testable rewriter behind the `POST /_manifest-edit` endpoint: it
# replaces ONLY the frontmatter `status:` line and the `## Plan` checklist block,
# preserving prose, decisions, other frontmatter, and lineage byte-for-byte.
# Kept deliberately narrow (see the 1i comp) — no general asset editing.

_FM_BLOCK    = re.compile(r"\A(---[ \t]*\n)(.*?\n)(---[ \t]*\n)", re.DOTALL)
_FM_STATUS_LINE = re.compile(r"(?m)^status:.*$")
_PLAN_HEADING   = re.compile(r"(?im)^#{1,6}[ \t]+plan[ \t]*$")
_NEXT_HEADING   = re.compile(r"(?m)^#{1,6}[ \t]+\S")
_CHECKLIST_LINE = re.compile(r"(?m)^- \[[ xX]\] .*$")


def _fmt_plan(plan: list[dict]) -> str:
    """Serialize plan items ``[{text, done}]`` into a `- [ ]`/`- [x]` checklist."""
    lines = []
    for p in plan:
        text = str((p or {}).get("text", "")).strip()
        mark = "x" if (p or {}).get("done") else " "
        lines.append(f"- [{mark}] {text}")
    return "\n".join(lines)


def _rewrite_status(text: str, status: str) -> str:
    """Replace the frontmatter `status:` line in place, if a block exists.

    S22: Hub no longer injects frontmatter. When the manifest already has a
    frontmatter block we update its `status:` line (or add one inside the block)
    so a human-authored manifest stays consistent; when there is NO frontmatter
    (the new default shape) this is a no-op — status is persisted to the
    DB/sidecar by the caller (`set_status`), not written into the file.
    """
    m = _FM_BLOCK.match(text)
    if not m:
        return text  # no frontmatter — status lives in the sidecar/DB, not the file
    open_, fm_body, close = m.group(1), m.group(2), m.group(3)
    new_body, n = _FM_STATUS_LINE.subn(f"status: {status}", fm_body, count=1)
    if n == 0:  # frontmatter present but no status line — add one at the top
        new_body = f"status: {status}\n" + fm_body
    return open_ + new_body + close + text[m.end():]


def _rewrite_plan(text: str, plan: list[dict]) -> str:
    """Replace the `## Plan` checklist block (append the section if absent).

    Only the contiguous run of `- [ ]`/`- [x]` lines inside the Plan section is
    rewritten; the heading, surrounding blank lines, and any prose elsewhere in
    the section are preserved. A manifest with no `## Plan` gets one appended.
    """
    checklist = _fmt_plan(plan)
    m = _PLAN_HEADING.search(text)
    if not m:
        if not checklist:
            return text
        sep = "" if text == "" else ("\n" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n"))
        block = "## Plan\n" + checklist + "\n"
        return text + sep + block
    # The Plan section runs from the heading to the next heading (or EOF).
    nxt = _NEXT_HEADING.search(text, m.end())
    section_end = nxt.start() if nxt else len(text)
    section = text[m.end():section_end]  # begins with the newline after the heading
    matches = list(_CHECKLIST_LINE.finditer(section))
    if matches:
        new_section = section[:matches[0].start()] + checklist + section[matches[-1].end():]
    elif checklist:
        new_section = "\n" + checklist + section
    else:
        new_section = section
    return text[:m.end()] + new_section + text[section_end:]


def rewrite_manifest(
    text: str,
    *,
    status: str | None = None,
    plan: list[dict] | None = None,
) -> str:
    """Rewrite ONLY the frontmatter `status:` line and/or the `## Plan` block.

    `status` (if given) replaces the frontmatter status value; `plan` (a list of
    ``{text, done}`` items, if given) replaces the Plan checklist. Everything
    else — prose, decisions, other frontmatter, lineage — is preserved
    byte-for-byte. A pure function: the endpoint reads the file, calls this, and
    writes the result back. Passing neither returns `text` unchanged.
    """
    if status is not None:
        text = _rewrite_status(text, status)
    if plan is not None:
        text = _rewrite_plan(text, plan)
    return text


# ── general inline doc editing (roadmap S18 — edit ANY hub document) ─────────
# Unlike rewrite_manifest (which surgically edits ONLY a manifest's status/plan),
# this is a whole-file replace for arbitrary TEXT documents. It shares the S3c
# conflict rule ("hub never wins a race against your editor") via a base_mtime
# guard, and the same "text only" allowlist the reading view enforces. HTML is
# deliberately excluded (raw HTML editing would break rendered artifacts) and
# internal storage (a task's comments/ log) is never editable. The single pure,
# testable writer behind `POST /_edit-doc`. Containment to the scan root is the
# caller's job (it owns the active root) — this only guards ext + conflict.

from .scan import SCRIPT_EXTS as _SCRIPT_EXTS

# Text/markdown docs a user may edit inline: prose formats + the S16 script/probe
# text files. HTML (.html/.htm) is intentionally absent.
EDITABLE_EXTS = {".md", ".markdown", ".txt"} | set(_SCRIPT_EXTS)


class DocConflict(Exception):
    """The file changed on disk since the client read it (stale base_mtime)."""

    def __init__(self, mtime: float) -> None:
        super().__init__("file changed on disk")
        self.mtime = mtime


def editable_doc_reason(path: Path) -> str | None:
    """Return None if `path` is an editable text doc, else a rejection reason.

    Rejections: ``html_unsupported`` for .html/.htm (out of scope — raw HTML
    editing would break rendered artifacts), ``internal`` for a task's comments/
    storage (append-only log, never a document), and ``unsupported`` for any
    other extension. Purely path-based; the caller still enforces scan-root
    containment.
    """
    ext = path.suffix.lower()
    if ext in (".html", ".htm"):
        return "html_unsupported"
    # A task's comment log is internal storage, not a document (S13/S7).
    if "comments" in path.parts:
        return "internal"
    if ext not in EDITABLE_EXTS:
        return "unsupported"
    return None


def write_doc(path: Path, content: str, base_mtime=None) -> float:
    """Whole-file overwrite of an editable text doc, honouring the conflict rule.

    `path` must already exist and be an editable text doc (see
    `editable_doc_reason`) — the caller is responsible for scan-root containment.
    The conflict rule: `base_mtime` is the mtime the client last read; if the
    file's current mtime differs (beyond the S3c 1 ms tolerance) the write is
    DISCARDED and `DocConflict` is raised so the caller can 409 and the UI can
    re-read. Otherwise `content` is written UTF-8 and the new mtime is returned.
    Raises `ValueError` on a non-editable target or non-string content; lets
    `OSError` propagate (e.g. a read-only root → the caller maps it to 403).
    """
    reason = editable_doc_reason(path)
    if reason is not None:
        raise ValueError(reason)
    if not isinstance(content, str):
        raise ValueError("content must be a string")
    cur = path.stat().st_mtime  # OSError if missing → caller maps to 404/403
    if base_mtime is not None:
        try:
            base = float(base_mtime)
        except (TypeError, ValueError):
            base = None
        if base is not None and abs(cur - base) > 0.001:
            raise DocConflict(cur)
    path.write_text(content, encoding="utf-8")
    return path.stat().st_mtime


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
