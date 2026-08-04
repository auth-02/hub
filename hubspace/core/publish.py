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
