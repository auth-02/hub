"""Excalidraw canvas host page (Phase 02).

`.excalidraw` files are first-class vault docs: this module renders the full-page
HTML shell that boots the Excalidraw canvas (built from hubspace/ui/src/draw.tsx →
static/draw.js). The scene JSON is injected as ``window.DRAW_STATE`` for draw.tsx
to hydrate; the client POSTs edits back to ``/draw/save``.

The heavy React/Excalidraw bundle is code-split and lazy-loaded by draw.js, so this
shell stays tiny — just the mount point, vendored CSS, and the injected state.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from ..core import config


def _favicon_href(port: int) -> str:
    return f"http://localhost:{port}" + quote(
        str(config.static_dir() / "favicon.svg"), safe="/:@"
    )


def _safe_json(obj) -> str:
    """json.dumps hardened for embedding inside a <script> element.

    Escapes ``</`` (so a literal ``</script>`` in the scene can't close the tag)
    and the line-separator code points that are illegal in JS string literals.
    """
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


def _parse_scene(scene_text: str | None):
    """Parse a .excalidraw file's text into a scene object, or None if blank/invalid."""
    if not scene_text or not scene_text.strip():
        return None
    try:
        return json.loads(scene_text)
    except (ValueError, TypeError):
        # Malformed scene → boot a blank canvas rather than 500.
        return None


def draw_page_html(rel: str | None, scene_text: str | None, port: int) -> str:
    """Full-page Excalidraw host.

    rel        — vault-relative path of the file (None for a new, unsaved diagram).
    scene_text — the .excalidraw file's raw JSON (None/empty for a blank canvas).
    """
    title = Path(rel).stem if rel else "Draw"
    state = {"rel": rel, "data": _parse_scene(scene_text)}
    return _PAGE.format(
        title=_escape_title(title),
        favicon=_favicon_href(port),
        state_json=_safe_json(state),
    )


def _escape_title(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" type="image/svg+xml" href="{favicon}">
<link rel="stylesheet" href="/static/draw.css">
</head>
<body>
<div id="app"><div class="draw-skeleton">loading canvas…</div></div>
<script>window.DRAW_STATE = {state_json};</script>
<script type="module" src="/static/draw.js"></script>
</body>
</html>
"""
