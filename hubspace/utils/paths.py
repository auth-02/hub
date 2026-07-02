"""Filesystem path helpers."""
from __future__ import annotations

import os
from pathlib import Path


def env_path(var: str, default: Path) -> Path:
    """Read an env var as an expanded Path, falling back to `default` if unset."""
    val = os.environ.get(var)
    return Path(val).expanduser() if val else default


def is_within(child: Path, parent: Path) -> bool:
    """True if `child` is `parent` or nested under it (no symlink resolution)."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
