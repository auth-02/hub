#!/usr/bin/env python3
"""
charts.py — Generate on-brand inline SVG charts for kagaz PDFs.

WeasyPrint does not run JavaScript, so Chart.js / D3 / <canvas> render blank.
These functions return SVG strings you embed directly in the HTML before
rendering. They use the design tokens (rust accent, warm ink, hairlines, mono
labels) so charts match the rest of the system.

All functions return a string of `<svg>...</svg>`. Drop it straight into the
HTML. Numbers are formatted with tabular figures via the surrounding CSS.

  bar_chart(data, ...)    vertical bars, one rust series
  line_chart(series, ...) one or more line series, rust + muted
  donut_chart(data, ...)  single-value ring / proportion

Palette (matches tokens.md):
  ink #1A1A1A · ink-mute #8A8377 · line #D9D1BC · accent #C0622A · soft #E89A6B
"""
from __future__ import annotations
from typing import Sequence
import html as _html

INK = "#1A1A1A"
INK_MUTE = "#8A8377"
LINE = "#D9D1BC"
ACCENT = "#C0622A"
SOFT = "#E89A6B"
PANEL = "#ECE5D2"
MONO = "'JetBrains Mono', monospace"
SERIF = "'Fraunces', Georgia, serif"


def _esc(s) -> str:
    return _html.escape(str(s))


def bar_chart(data: Sequence[tuple], width: int = 520, height: int = 240,
              pad: int = 36, title: str | None = None) -> str:
    """data: sequence of (label, value). Single rust series, hairline baseline."""
    labels = [d[0] for d in data]
    values = [float(d[1]) for d in data]
    vmax = max(values) or 1
    n = len(values)
    plot_w = width - pad * 2
    plot_h = height - pad * 2
    gap = plot_w / n * 0.32
    bw = (plot_w - gap * (n - 1)) / n if n else plot_w

    bars, xlabels = [], []
    for i, (lab, val) in enumerate(zip(labels, values)):
        x = pad + i * (bw + gap)
        bh = (val / vmax) * plot_h
        y = pad + plot_h - bh
        vlabel = int(val) if val == int(val) else round(val, 1)
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="{ACCENT}"/>'
            f'<text x="{x + bw/2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="10" fill="{INK}">{_esc(vlabel)}</text>'
        )
        xlabels.append(
            f'<text x="{x + bw/2:.1f}" y="{pad + plot_h + 16:.1f}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="9" fill="{INK_MUTE}" '
            f'letter-spacing="0.04em">{_esc(lab)}</text>'
        )
    baseline = (f'<line x1="{pad}" y1="{pad+plot_h}" x2="{width-pad}" y2="{pad+plot_h}" '
                f'stroke="{LINE}" stroke-width="1"/>')
    ttl = (f'<text x="{pad}" y="20" font-family="{MONO}" font-size="9" '
           f'letter-spacing="0.12em" fill="{INK_MUTE}">{_esc(title.upper())}</text>') if title else ""
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">{ttl}{baseline}'
            f'{"".join(bars)}{"".join(xlabels)}</svg>')


def line_chart(series: Sequence[dict], labels: Sequence[str] | None = None,
               width: int = 520, height: int = 240, pad: int = 40,
               title: str | None = None) -> str:
    """series: list of {'name': str, 'values': [..], 'color': hex?}.
    First series defaults to rust, others to muted ink."""
    all_vals = [v for s in series for v in s["values"]]
    vmax = max(all_vals) or 1
    vmin = min(all_vals + [0])
    span = (vmax - vmin) or 1
    npts = max(len(s["values"]) for s in series)
    plot_w = width - pad * 2
    plot_h = height - pad * 2

    def pt(i, v):
        x = pad + (plot_w * (i / (npts - 1))) if npts > 1 else pad
        y = pad + plot_h - ((v - vmin) / span) * plot_h
        return x, y

    # horizontal gridlines (hairline)
    grid = "".join(
        f'<line x1="{pad}" y1="{pad + plot_h*g/3:.1f}" x2="{width-pad}" '
        f'y2="{pad + plot_h*g/3:.1f}" stroke="{LINE}" stroke-width="0.6"/>'
        for g in range(4)
    )
    paths, dots = [], []
    default_colors = [ACCENT, INK_MUTE, SOFT]
    for si, s in enumerate(series):
        color = s.get("color", default_colors[si % len(default_colors)])
        pts = [pt(i, v) for i, v in enumerate(s["values"])]
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        paths.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{color}"/>')
    xlabels = ""
    if labels:
        xlabels = "".join(
            f'<text x="{pt(i,vmin)[0]:.1f}" y="{pad+plot_h+16:.1f}" text-anchor="middle" '
            f'font-family="{MONO}" font-size="9" fill="{INK_MUTE}">{_esc(l)}</text>'
            for i, l in enumerate(labels)
        )
    ttl = (f'<text x="{pad}" y="20" font-family="{MONO}" font-size="9" '
           f'letter-spacing="0.12em" fill="{INK_MUTE}">{_esc(title.upper())}</text>') if title else ""
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">{ttl}{grid}'
            f'{"".join(paths)}{"".join(dots)}{xlabels}</svg>')


def donut_chart(value: float, total: float = 100, label: str | None = None,
                size: int = 180, stroke: int = 18) -> str:
    """Single-proportion ring. value/total filled in rust, remainder hairline."""
    import math
    r = (size - stroke) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    frac = max(0.0, min(1.0, value / total if total else 0))
    filled = circ * frac
    pct = round(frac * 100)
    track = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
             f'stroke="{LINE}" stroke-width="{stroke}"/>')
    arc = (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ACCENT}" '
           f'stroke-width="{stroke}" stroke-dasharray="{filled:.1f} {circ:.1f}" '
           f'stroke-linecap="butt" transform="rotate(-90 {cx} {cy})"/>')
    center = (f'<text x="{cx}" y="{cy-2}" text-anchor="middle" font-family="{SERIF}" '
              f'font-size="34" font-weight="500" fill="{INK}">{pct}%</text>')
    sub = (f'<text x="{cx}" y="{cy+20}" text-anchor="middle" font-family="{MONO}" '
           f'font-size="9" letter-spacing="0.1em" fill="{INK_MUTE}">{_esc(label.upper())}</text>') if label else ""
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">{track}{arc}{center}{sub}</svg>')


if __name__ == "__main__":
    # quick self-test: write a sample page
    bars = bar_chart([("Q1", 12.4), ("Q2", 14.1), ("Q3", 9.8), ("Q4", 16.2)], title="revenue $m")
    line = line_chart([{"name": "with", "values": [16, 17, 18, 18]},
                       {"name": "without", "values": [12, 13, 13, 14]}],
                      labels=["w1", "w2", "w3", "w4"], title="correctness")
    donut = donut_chart(83, 100, label="tokens saved")
    print("<div style='display:flex;gap:24px;flex-wrap:wrap'>"
          + bars + line + donut + "</div>")
