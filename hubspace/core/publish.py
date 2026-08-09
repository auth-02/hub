#!/usr/bin/env python3
"""publish.py — the LOCAL half of "publish one asset" (roadmap 1f).

Hub's job when publishing is deliberately narrow and entirely offline: **scan**
a file for things a public reader should not see, and prepare a **sanitized
copy** on request. The actual upload lives in the bundled `dak` skill (a
separate script that reaches Cloudflare); Hub only hands off to it. Nothing in
this module — or anywhere in `hubspace/` — makes a network call.

This module is pure and unit-testable: text in, findings/text out. Both the
`hub publish` CLI verb and the `POST /_publish-scan` endpoint call the SAME
scanner here, so the privacy gate is identical on both roads.

Ruleset (small on purpose — precision over recall; a false positive is a mild
annoyance, a false negative leaks):

    path   absolute home paths — /Users/<name>/… and /home/<name>/…
    host   internal hostnames — *.internal, *.local, *.corp
    email  email addresses
    ip     private IPv4 — 10.x, 192.168.x, 172.16–31.x, 127.x (loopback)

Each finding is ``{"line": int, "kind": str, "text": str, "span": [start, end]}``
where ``span`` is a half-open character range into the ORIGINAL text. `redact()`
replaces each finding's span with a stable ``‹redacted:<kind>›`` placeholder and
leaves every other byte identical; it never touches the source file.
"""
from __future__ import annotations

import re

# ── Ruleset ──────────────────────────────────────────────────────────────────
# Kept small and named. When two patterns match overlapping text (e.g. the
# domain inside an email), the one earlier in this list wins — see scan().
_RULES: list[tuple[str, re.Pattern]] = [
    # email — before host, so bob@corp.internal is one email, not email+host.
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    # host — an internal/private hostname (one or more labels + reserved TLD).
    ("host", re.compile(
        r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
        r"(?:internal|local|corp)\b"
    )),
    # ip — RFC1918 private ranges + loopback. Full dotted quad only.
    ("ip", re.compile(
        r"\b(?:"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r"|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r")\b"
    )),
    # path — an absolute home directory path and whatever trails it, up to a
    # space or quote. /Users/<name>/… (macOS) or /home/<name>/… (Linux).
    ("path", re.compile(r"/(?:Users|home)/[^/\s'\"]+(?:/[^\s'\"]*)?")),
]

_PRIORITY = {kind: i for i, (kind, _) in enumerate(_RULES)}


def _placeholder(kind: str) -> str:
    """Stable, human-legible replacement token for a redacted finding."""
    return f"‹redacted:{kind}›"  # ‹redacted:kind›


def scan(text: str) -> list[dict]:
    """Return redaction findings for `text`, sorted by position.

    Each finding is ``{"line", "kind", "text", "span": [start, end]}``. Overlaps
    are resolved by rule priority (email > host > ip > path) and then by leftmost
    start, so no two returned findings overlap.
    """
    if not text:
        return []
    candidates: list[tuple[int, int, str, str]] = []
    for kind, pattern in _RULES:
        for m in pattern.finditer(text):
            candidates.append((m.start(), m.end(), kind, m.group()))

    # Greedy non-overlap: prefer leftmost, then higher-priority rule, then longer.
    candidates.sort(key=lambda c: (c[0], _PRIORITY[c[2]], -(c[1] - c[0])))
    findings: list[dict] = []
    consumed_to = -1
    for start, end, kind, matched in candidates:
        if start < consumed_to:
            continue
        findings.append({
            "line": text.count("\n", 0, start) + 1,
            "kind": kind,
            "text": matched,
            "span": [start, end],
        })
        consumed_to = end
    findings.sort(key=lambda f: f["span"][0])
    return findings


def redact(text: str, findings: list[dict]) -> str:
    """Return a copy of `text` with each finding's span replaced by a placeholder.

    Everything outside the finding spans is left byte-for-byte identical. Safe
    against overlapping/duplicate findings (applied right-to-left). The caller
    supplies which findings to redact — this is how the UI's per-finding toggles
    work: pass only the subset the user left enabled.
    """
    if not findings:
        return text
    ordered = sorted(findings, key=lambda f: f["span"][0], reverse=True)
    out = text
    last_start = len(text) + 1
    for f in ordered:
        start, end = f["span"]
        if end > last_start:  # overlaps a span we already replaced — skip
            continue
        out = out[:start] + _placeholder(f["kind"]) + out[end:]
        last_start = start
    return out


def scan_file(path) -> list[dict]:
    """Read a file as UTF-8 (replacing undecodable bytes) and scan it."""
    from pathlib import Path
    return scan(Path(path).read_text(encoding="utf-8", errors="replace"))


def summary(findings: list[dict]) -> str:
    """One-line comp-shaped summary: ``⚠ N findings — kind (L12), kind (L44)``.

    Empty when there are no findings (the caller decides what "clean" prints).
    """
    if not findings:
        return ""
    parts = ", ".join(f'{f["kind"]} (L{f["line"]})' for f in findings)
    n = len(findings)
    return f"⚠ {n} finding{'s' if n != 1 else ''} — {parts}"


# ── Published-state sidecar (roadmap 1g) ──────────────────────────────────────
# A tiny JSON map recording which tasks have been published, so the hub can show
# a PUBLISHED marker (URL + republish/revoke) on a task row. It lives beside the
# other generated state under state_dir() and is keyed by "<repo>\t<slug>" — the
# same tab-joined key the UI uses for O(1) lookup. Writing it makes no network
# call; it only remembers what a successful `hub publish --task` already did.
import json as _json
from pathlib import Path as _Path


def published_key(repo: str | None, slug: str) -> str:
    """The stable "<repo>\\t<slug>" sidecar key (empty repo → "(root)")."""
    return f"{repo or '(root)'}\t{slug}"


# ── Deterministic worker slugs (S26) ───────────────────────────────────────────
# Hub publishes in dak's **live** mode with a deterministic worker name so the
# resulting URL has NO random suffix and republishing the SAME task/file
# overwrites the SAME URL (idempotent). These replicate dak's slugify rules
# (lowercase, non-alnum runs → '-', trimmed, ≤63 chars, DNS-safe) so the worker
# name Hub computes equals the one dak would deploy — letting revoke later find
# and take down the exact Cloudflare worker.


def _worker_slugify(text: str) -> str:
    """dak-compatible slug: lowercase, non-alnum → '-', collapsed, trimmed, ≤63."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:63].strip("-") or "artifact"


def _is_real_repo(repo: str | None) -> bool:
    """True when `repo` names a real repo (not the ``(root)`` pseudo-repo)."""
    r = (repo or "").strip()
    return bool(r) and r != "(root)"


def task_worker_slug(repo: str | None, slug: str) -> str:
    """Deterministic dak worker name for a TASK bundle (live mode).

    Real repo → ``slug(<repo>-<taskslug>)`` (e.g. ``acme-api/hello`` →
    ``acme-api-hello``); the ``(root)`` pseudo-repo → bare ``slug(<taskslug>)``
    (e.g. ``(root)/hello`` → ``hello``). No timestamps/hashes — stable per task.
    """
    base = f"{repo.strip()}-{slug}" if _is_real_repo(repo) else slug
    return _worker_slugify(base)


def file_worker_slug(repo: str | None, rel_no_ext: str,
                     task_slug: str | None = None,
                     file_stem: str | None = None) -> str:
    """Deterministic dak worker name for a SINGLE file (live mode).

    Under a task → ``slug(<repo>-<taskslug>-<fileStem>)``; otherwise
    ``slug(<repo>-<relpathNoExt>)`` where ``rel_no_ext`` is the file's path
    (repo-relative, extension stripped). The ``(root)`` pseudo-repo drops the
    repo prefix. No timestamps/hashes — stable per file.
    """
    real = _is_real_repo(repo)
    r = (repo or "").strip()
    if task_slug and file_stem:
        base = f"{r}-{task_slug}-{file_stem}" if real else f"{task_slug}-{file_stem}"
    else:
        base = f"{r}-{rel_no_ext}" if real else rel_no_ext
    return _worker_slugify(base)


def slug_from_name(name: str | None) -> str | None:
    """Slugify a USER-PROVIDED publish name into a dak-safe worker slug (S28).

    Same rules as the deterministic worker slugs (lowercase, non-alnum runs → '-',
    collapsed, trimmed, ≤63, DNS/worker-safe) so a name the user types deploys to
    exactly the worker Hub records and dak creates. Returns ``None`` when the name
    is empty or slugifies to nothing (e.g. all punctuation) — unlike
    :func:`_worker_slugify` there is NO ``"artifact"`` fallback: an empty result
    is a SIGNAL the caller must act on (reject, or fall back to the deterministic
    default), never a silent rename.
    """
    if not name or not name.strip():
        return None
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:63].strip("-") or None


def worker_owner(data: dict, worker: str,
                 self_key: str | None = None) -> str | None:
    """Return the sidecar key of an EXISTING entry already using dak `worker`,
    excluding `self_key` (the entry we are about to (re)publish). ``None`` when no
    OTHER entry claims that worker — i.e. the name is free to use.

    The S28 custom-name collision guard: naming a publish the same as an existing
    DIFFERENT-source publish would hijack its Cloudflare worker (and a later
    unpublish would take the wrong one down), so the server refuses. Matches on
    the recorded ``worker`` field, falling back to the worker parsed from the
    stored ``url`` for pre-S26 entries that predate the field.
    """
    for key, entry in data.items():
        if key == self_key or not isinstance(entry, dict):
            continue
        w = entry.get("worker") or worker_from_url(entry.get("url"))
        if w and w == worker:
            return key
    return None


def worker_from_url(url: str | None) -> str | None:
    """Extract the dak worker name from a ``https://<worker>.<sub>.workers.dev`` URL.

    Returns the first host label (the worker) or ``None`` when `url` is empty or
    not a recognizable workers.dev URL. Used by revoke to recover the worker to
    take down when a stored entry predates the ``worker`` field.
    """
    m = re.match(r"https?://([^./]+)\.[^/]*workers\.dev\b", url or "")
    return m.group(1) if m else None


def published_path():
    """Location of the published-state sidecar (``state_dir()/published.json``)."""
    from . import config
    return config.state_dir() / "published.json"


def load_published(path=None) -> dict:
    """Read the published-state map, or ``{}`` if it is missing/unreadable."""
    p = _Path(path) if path else published_path()
    if not p.exists():
        return {}
    try:
        data = _json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_published(repo: str | None, slug: str, url: str,
                     mode: str = "snapshot", path=None,
                     worker: str | None = None) -> dict:
    """Record a successful publish and return the updated map.

    Idempotent per key: republishing overwrites the entry with a fresh
    ``{url, at, mode[, worker]}``. The ``at`` timestamp is a local ISO-ish
    string. ``worker`` (S26) is the deterministic dak worker name so a later
    revoke can take the Cloudflare worker down without recomputing it.
    """
    from datetime import datetime
    p = _Path(path) if path else published_path()
    data = load_published(p)
    entry = {
        "url": url,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": mode,
    }
    if worker:
        entry["worker"] = worker
    data[published_key(repo, slug)] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    return data


# ── Published-state for a single asset (roadmap 1f, S11) ───────────────────────
# One-click asset publish records an equivalent entry in the SAME published.json
# sidecar, keyed by the asset's absolute path (prefixed so it can never collide
# with a "<repo>\t<slug>" task key). Recording it is local-only — no network call.


def published_asset_key(path) -> str:
    """Stable sidecar key for a single published asset (``asset\\t<abspath>``).

    The stored key uses the ``resolve()``d (canonical, symlink-free) abs so a
    record is stable no matter which alias of a symlinked path the caller passed.
    Lookups reconcile this canonical form with the files-index UNRESOLVED abs via
    :func:`find_asset_key` / :func:`realign_asset_keys` — see the note there.
    """
    return f"asset\t{_Path(path).resolve()}"


import os as _os

_ASSET_PREFIX = "asset\t"


def find_asset_key(data: dict, path) -> str | None:
    """Return the ``asset\\t<abs>`` key in `data` that names the SAME file as
    `path`, comparing by ``os.path.realpath`` so a symlinked scan root does not
    hide the entry.

    The files index stores each file's abs UNRESOLVED (``scan._meta`` → ``str(path)``)
    while :func:`record_published_asset` stores the RESOLVED abs; under a symlinked
    root (e.g. macOS ``/var`` → ``/private/var``) those strings differ. Matching by
    realpath makes a lookup with EITHER form find the entry. Returns ``None`` when
    no asset entry names the same file."""
    exact = published_asset_key(path)
    if exact in data:
        return exact
    target = _os.path.realpath(str(path))
    for key in data:
        if key.startswith(_ASSET_PREFIX) and \
                _os.path.realpath(key[len(_ASSET_PREFIX):]) == target:
            return key
    return None


def realign_asset_keys(data: dict, file_abs_iter) -> dict:
    """Return a copy of `data` with every ``asset\\t<abs>`` entry re-keyed to the
    abs form used by the files index, matched by realpath.

    Called at bake time. `file_abs_iter` is the discovered files' abs strings
    (``scan._meta``'s UNRESOLVED ``str(path)``) — the exact value the UI bakes as
    each row's ``data-abs`` and passes to ``publishedForFile()``. Asset entries are
    stored under the RESOLVED abs; under a symlinked scan root the two differ, so
    without this the ``PUBLISHED_DATA`` lookup would miss and no marker would show.
    Here each asset entry is matched to a discovered file by realpath equivalence
    and re-emitted under that file's unresolved abs. Task keys and asset entries
    with no matching discovered file are passed through unchanged."""
    by_real: dict[str, str] = {}
    for abs_ in file_abs_iter:
        if abs_:
            by_real[_os.path.realpath(str(abs_))] = str(abs_)
    out: dict = {}
    for key, val in data.items():
        if key.startswith(_ASSET_PREFIX):
            ui_abs = by_real.get(_os.path.realpath(key[len(_ASSET_PREFIX):]))
            if ui_abs is not None:
                out[f"{_ASSET_PREFIX}{ui_abs}"] = val
                continue
        out[key] = val
    return out


def record_published_asset(path, url: str, mode: str = "snapshot",
                           sidecar=None, worker: str | None = None) -> dict:
    """Record a successful one-click asset publish and return the updated map.

    ``worker`` (S26) is the deterministic dak worker name so a later revoke can
    take the Cloudflare worker down without recomputing it.
    """
    from datetime import datetime
    p = _Path(sidecar) if sidecar else published_path()
    data = load_published(p)
    entry = {
        "url": url,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": mode,
    }
    if worker:
        entry["worker"] = worker
    data[published_asset_key(path)] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    return data


def revoke_published(repo: str | None, slug: str, path=None) -> bool:
    """Forget a published TASK entry locally. Returns True if an entry was removed.

    Hub only forgets the local record here (the sidecar); un-publishing the
    remote copy is dak's job and is invoked separately by the caller if desired.
    ``path`` overrides the sidecar location (used by tests) — it is NOT the
    published asset's path. To forget a single file, use
    :func:`revoke_published_asset`.
    """
    p = _Path(path) if path else published_path()
    data = load_published(p)
    key = published_key(repo, slug)
    if key not in data:
        return False
    del data[key]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    return True


def revoke_published_asset(asset_path, sidecar=None) -> bool:
    """Forget a single published ASSET entry locally. True if one was removed.

    The twin of :func:`revoke_published` for the ``asset\\t<abspath>`` keys that
    :func:`record_published_asset` writes. ``sidecar`` overrides the sidecar
    location (used by tests); ``asset_path`` is the published file itself.
    Local-only — no network call (un-publishing the remote copy is dak's job).
    """
    p = _Path(sidecar) if sidecar else published_path()
    data = load_published(p)
    # Match by realpath so a revoke by the unresolved (files-index) abs still
    # finds an entry stored under the resolved abs, and vice versa.
    key = find_asset_key(data, asset_path)
    if key is None:
        return False
    del data[key]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(data, indent=2), encoding="utf-8")
    return True
