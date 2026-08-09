#!/usr/bin/env python3
"""Shared configuration for hub.py and server.py.

Single source of truth for:
  - the state directory ($XDG_STATE_HOME/hub or ~/.local/state/hub),
  - `hub.toml` parsing, and
  - scan-root resolution.

Scan-root priority (PRD §7.9), highest first:
    explicit flag  →  HUB_SCAN_ROOT env  →  hub.toml [hub].scan_root  →
    .scan_root sidecar  →  current working directory

`hub.toml` lives in the directory you run hub from (CWD). Recognised keys live
under a `[hub]` table; top-level keys are also accepted for convenience:

    [hub]
    scan_root    = "~/work/docs"
    port         = 8787
    exclude_dirs = ["vendor", "fixtures"]   # added to the built-in excludes
    default_view = "board"                  # work | list | board | calendar

Environment variables always override the file. Stdlib-only (tomllib, Py 3.11+).
"""
from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path

_VALID_VIEWS = {"work", "list", "board", "calendar"}

# Mask sentinel returned for a set-but-hidden secret (GET /_settings) and
# recognised on write-back: a POST carrying exactly this string (or empty)
# means "keep the existing token", never "set the token to these dots".
DAK_MASK = "••••••"  # ••••••

# hub.toml keys the Settings panel is allowed to write. Deliberately a fixed
# allowlist: even if a caller smuggles an `api_token` into the values dict, it
# can NEVER reach hub.toml (which lives in the indexed scan root) — secrets go
# to ~/.dak/config.json only. See write_config / write_dak_config below.
_WRITABLE_HUB_KEYS = (
    "scan_root", "default_view", "port", "exclude_dirs", "private", "upload_exts",
)

# Keys accepted for the dak (Cloudflare) config at ~/.dak/config.json.
_DAK_KEYS = ("api_token", "account_id", "subdomain")

# Default extension allowlist for uploaded data files (roadmap 1d — Add data).
# Mirrors scan.py DATA_EXTS (pdf/xlsx/xls/csv/tsv) plus the plain-text and
# structured formats a task commonly attaches. Override via hub.toml
# `upload_exts` (a list of extensions, with or without a leading dot).
DEFAULT_UPLOAD_EXTS = {".pdf", ".xlsx", ".xls", ".csv", ".tsv", ".json", ".txt", ".md"}


def state_dir() -> Path:
    """$XDG_STATE_HOME/hub, falling back to ~/.local/state/hub (created if absent)."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    d = base / "hub"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_dir() -> Path:
    """Writable directory holding the generated index — `state_dir()/build`.

    Lives outside the (read-only when installed) package directory so a `pipx`
    install can still rebuild. Created on access.
    """
    d = state_dir() / "build"
    d.mkdir(parents=True, exist_ok=True)
    return d


def output_path() -> Path:
    """Generated index path: HUB_OUTPUT env > `state_dir()/build/docs-index.html`."""
    env = os.environ.get("HUB_OUTPUT")
    if env:
        return Path(env).expanduser()
    return build_dir() / "docs-index.html"


def log_path() -> Path:
    """Debug log path: HUB_LOG env > `state_dir()/hub.log`."""
    env = os.environ.get("HUB_LOG")
    if env:
        return Path(env).expanduser()
    return state_dir() / "hub.log"


def load_config(start: Path | None = None) -> dict:
    """Parse `hub.toml` from `start` (default: CWD). Return {} if absent or invalid.

    Keys under a `[hub]` table take precedence over top-level keys of the same
    name. A malformed file is ignored (returns {}) rather than crashing startup.
    """
    base = start if start is not None else Path.cwd()
    path = base / "hub.toml"
    try:
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    merged = {k: v for k, v in raw.items() if not isinstance(v, dict)}
    section = raw.get("hub")
    if isinstance(section, dict):
        merged.update(section)
    return merged


def resolve_scan_root(
    config: dict,
    sidecar_file: Path,
    flag: str | None = None,
) -> Path:
    """Resolve the scan root following the §7.9 priority chain."""
    if flag:
        return Path(flag).expanduser()
    env = os.environ.get("HUB_SCAN_ROOT")
    if env:
        return Path(env).expanduser()
    cfg_root = config.get("scan_root")
    if isinstance(cfg_root, str) and cfg_root.strip():
        return Path(cfg_root).expanduser()
    try:
        text = sidecar_file.read_text(encoding="utf-8").strip()
        if text:
            return Path(text).expanduser()
    except OSError:
        pass
    return Path.cwd()


def resolve_port(config: dict) -> str:
    """Server port: HUB_SERVER_PORT env > hub.toml `port` > "" (file:// links)."""
    env = os.environ.get("HUB_SERVER_PORT", "").strip()
    if env:
        return env
    port = config.get("port")
    if isinstance(port, int):
        return str(port)
    if isinstance(port, str) and port.strip().isdigit():
        return port.strip()
    return ""


def config_exclude_dirs(config: dict) -> set[str]:
    """Extra excluded directory names from hub.toml `exclude_dirs` (list of str)."""
    raw = config.get("exclude_dirs")
    if isinstance(raw, list):
        return {d for d in raw if isinstance(d, str) and d}
    return set()


def upload_exts(config: dict) -> set[str]:
    """Allowed upload extensions (lowercased, dot-prefixed) for `POST /_upload`.

    From hub.toml `upload_exts` (a list of str, each with or without a leading
    dot); falls back to DEFAULT_UPLOAD_EXTS when the key is unset, not a list,
    or yields no usable entries. This is the server-side allowlist enforced by
    the upload guard — the UI mirrors it only for pre-check UX.
    """
    raw = config.get("upload_exts")
    if isinstance(raw, list):
        exts = set()
        for e in raw:
            if isinstance(e, str) and e.strip():
                e = e.strip().lower()
                exts.add(e if e.startswith(".") else "." + e)
        if exts:
            return exts
    return set(DEFAULT_UPLOAD_EXTS)


def is_private(config: dict) -> bool:
    """Whether this workspace is marked private via hub.toml `[hub] private`.

    A private workspace refuses to publish at all (roadmap 1f): the CLI `hub
    publish` verb bails and the palette drops its Publish row. Accepts a TOML
    boolean (`private = true`) or a truthy string, mirroring how the other
    scalar keys are read. Anything else (unset / falsy) → not private.
    """
    v = config.get("private")
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return False


def resolve_default_view(config: dict) -> str:
    """Configured default view, or "" if unset/invalid (JS falls back to its own default)."""
    v = config.get("default_view")
    if isinstance(v, str) and v in _VALID_VIEWS:
        return v
    return ""


def config_path() -> Path:
    """Path to the hub.toml the Settings panel reads and writes.

    HUB_CONFIG env (an explicit file) > ``<CWD>/hub.toml`` — the same directory
    ``load_config()`` reads from by default (the run directory). Kept as one
    resolver so GET and POST /_settings agree on which file they touch.
    """
    env = os.environ.get("HUB_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.cwd() / "hub.toml"


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _toml_value(v) -> str:
    """Serialize a Python scalar/list into a TOML value (stdlib has no writer)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join('"' + _toml_escape(str(x)) + '"' for x in v) + "]"
    return '"' + _toml_escape(str(v)) + '"'


def write_config(values: dict, path: Path) -> None:
    """Write/merge the known ``[hub]`` keys into the hub.toml at ``path``.

    Hand-rolled, stdlib-only (there is no ``tomli-w``). Only the fixed
    ``_WRITABLE_HUB_KEYS`` allowlist is ever emitted — so a stray secret in
    ``values`` can never land in hub.toml (which lives in the indexed scan
    root). Existing values for keys you don't pass are preserved; the emitted
    file is a clean ``[hub]`` table (any non-``[hub]`` top-level content is not
    round-tripped — Settings owns the ``[hub]`` table).

    Types round-trip: ``port`` → int, ``private`` → bool, ``exclude_dirs`` /
    ``upload_exts`` → TOML arrays, ``default_view`` / ``scan_root`` → strings.
    """
    path = Path(path)
    existing = load_config(path.parent)
    merged: dict = {}
    for k in _WRITABLE_HUB_KEYS:
        if k in values and values[k] is not None:
            merged[k] = values[k]
        elif k in existing and existing[k] is not None:
            merged[k] = existing[k]
    lines = ["[hub]"]
    for k in _WRITABLE_HUB_KEYS:
        if k in merged:
            lines.append(f"{k} = {_toml_value(merged[k])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def dak_config_path() -> Path:
    """Location of the dak (Cloudflare) creds: HUB_DAK_CONFIG env > ~/.dak/config.json.

    The env override exists so tests never touch the user's real credentials.
    This file — NOT hub.toml — is the ONLY place the API token is stored.
    """
    env = os.environ.get("HUB_DAK_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".dak" / "config.json"


def read_dak_config() -> dict:
    """Read ~/.dak/config.json → dict (``{}`` if missing/unreadable/not an object)."""
    try:
        with open(dak_config_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_dak_config(values: dict) -> None:
    """Merge ``values`` into ~/.dak/config.json, creating ~/.dak/ if needed.

    Only ``_DAK_KEYS`` are merged; keys already present that you don't pass are
    kept (re-saving account_id must not wipe the token). Written 0600 so the
    token isn't world-readable. The caller is responsible for never sending the
    mask sentinel / empty string as ``api_token`` (see server /_settings).
    """
    p = dak_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    cur = read_dak_config()
    for k in _DAK_KEYS:
        if k in values and values[k] is not None:
            cur[k] = values[k]
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2, sort_keys=True)
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def masked_dak_config() -> dict:
    """dak config for GET /_settings — the token is NEVER returned, only its
    set/unset state (``api_token_set``). account_id/subdomain are safe to show."""
    cfg = read_dak_config()
    return {
        "account_id": str(cfg.get("account_id") or ""),
        "subdomain": str(cfg.get("subdomain") or ""),
        "api_token_set": bool(cfg.get("api_token")),
    }


def example_dir() -> Path:
    """Locate the bundled demo fixture used by `hub --demo`.

    Installed wheels carry it at ``hubspace/example`` (force-included at build
    time); in a source checkout it lives at the repo root, outside the package.
    """
    pkg = Path(__file__).resolve().parent.parent  # hubspace/
    bundled = pkg / "example"
    return bundled if bundled.exists() else pkg.parent / "example"


def static_dir() -> Path:
    """Runtime static web assets (favicon.svg, hub.css, hub.js).

    These live inside the package at ``hubspace/static`` so they ship in the
    wheel automatically. (Docs-only screenshots/illustrations live in the
    repo-root assets/ instead and are never packaged.)
    """
    return Path(__file__).resolve().parent.parent / "static"  # hubspace/static
