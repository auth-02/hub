"""Text helpers: HTML escaping, slugs, and relative timestamps."""
from __future__ import annotations

import re
import time


def esc_html(s: object) -> str:
    """Escape the five characters unsafe in HTML text/attribute contexts."""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def slugify(text: str) -> str:
    """Lowercase, strip HTML tags, collapse non-alphanumeric runs to '-', trim."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def relative_time(mtime: float) -> str:
    """Human-readable 'time ago' string for a Unix mtime (e.g. '3h ago')."""
    if not mtime:
        return "—"
    delta = time.time() - mtime
    if delta < 90:
        return "just now"
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{int(delta // secs)}{unit} ago"
    return "just now"
