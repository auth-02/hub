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
    default_view = "board"                  # work | list | board | calendar | activity

Environment variables always override the file. Stdlib-only (tomllib, Py 3.11+).
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

_VALID_VIEWS = {"work", "list", "board", "calendar", "activity"}


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


def resolve_default_view(config: dict) -> str:
    """Configured default view, or "" if unset/invalid (JS falls back to its own default)."""
    v = config.get("default_view")
    if isinstance(v, str) and v in _VALID_VIEWS:
        return v
    return ""


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
