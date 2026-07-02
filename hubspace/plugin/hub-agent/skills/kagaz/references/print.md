# Print & PDF specifics

When the output is a PDF (WeasyPrint, ReportLab, python-docx) rather than a screen artifact, the aesthetic stays the same but the mechanics change. Print is **tighter** than screen — web body line-heights float at pt sizes, and shadows/rgba behave differently in the renderer.

## Type scale (print, A4)

Use pt for print. Screen px ≈ pt × 1.33 (so 9pt ≈ 12px, 18pt ≈ 24px).

| Role        | Size   | Weight | Line-height | Use                              |
|-------------|--------|--------|-------------|----------------------------------|
| Display     | 36pt   | 500    | 1.10        | Cover title, one-pager hero      |
| H1 Section  | 22pt   | 500    | 1.20        | Chapter titles                   |
| H2          | 16pt   | 500    | 1.25        | Subsection                       |
| H3          | 13pt   | 500    | 1.30        | Item titles                      |
| Body Lead   | 11pt   | 400    | 1.55        | Intro paragraphs                 |
| Body        | 10pt   | 400    | 1.55        | Reading body                     |
| Body Dense  | 9.2pt  | 400    | 1.42        | Resume, one-pager dense body     |
| Caption     | 9pt    | 400    | 1.45        | Notes, figure captions           |
| Label       | 9pt    | 600    | 1.35        | Mono labels, corner tags         |

**Floors**: web text ≥ 12px, PDF text ≥ 9pt. Serif body stays at weight 400; serif headings at 500 (a real bold font file, not synthetic — WeasyPrint can't synthesize bold cleanly on a fine serif).

## Line-height tiers

Print runs tighter than English web body (which typically sits at 1.6–1.75 and floats at pt sizes).

| Tier            | Value     | Use                                |
|-----------------|-----------|------------------------------------|
| Tight headline  | 1.10–1.30 | Display, H1, H2                    |
| Dense body      | 1.40–1.45 | Resume, one-pager, dense info      |
| Reading body    | 1.50–1.55 | Long-doc chapters, letters         |
| Label / caption | 1.30–1.40 | Small labels, multi-line metadata  |

Forbidden in print: 1.60+ (loose, web rhythm) and 1.00–1.05 (lines collide except at huge display sizes).

## Letter-spacing

- Body text: **0**
- Small labels (< 10pt): **+0.2 to +0.5pt**
- All-caps overlines / mono labels: **+0.5 to +1pt** (mandatory — caps need air)
- Display headings: subtle optical tightening (-0.2 to -0.5pt), kept local, never inherited by body

## Page margins (A4)

| Document        | Top  | Right | Bottom | Left |
|-----------------|------|-------|--------|------|
| Resume (dense)  | 11mm | 13mm  | 11mm   | 13mm |
| One-Pager       | 15mm | 18mm  | 15mm   | 18mm |
| Long Doc        | 20mm | 22mm  | 22mm   | 22mm |
| Letter (formal) | 25mm | 25mm  | 25mm   | 25mm |
| Portfolio       | 12mm | 15mm  | 12mm   | 15mm |

Rule: denser document = smaller margins; more formal = larger margins.

## WeasyPrint: tags must be SOLID hex, never rgba

This is the single most important print gotcha. WeasyPrint's alpha compositing produces a visible **double rectangle** on zoom when a tag/badge background uses `rgba()`. Always convert to a solid hex equivalent.

Rust `#C0622A` over cream `#F4EFE4`, precomputed solids:

| rgba alpha | Solid hex   | Use                         |
|------------|-------------|-----------------------------|
| 0.08       | `#F0E6DA`   | Lightest tag (most restrained, default) |
| 0.14       | `#EBDBC9`   | Standard tag                |
| 0.18       | `#E7D4BF`   | Higher-contrast tag         |
| 0.30       | `#DCC0A2`   | Strong emphasis (rare)      |

Pick one step lighter than what the decoration instinct wants — pale beats saturated in iteration. `grep -F` for any `rgba(` in tag/badge CSS before shipping a PDF.

## Pagination protection

```css
/* Keep these blocks from splitting across a page break */
.card, .metric, .quote, .code-block, figure, .callout,
table.compact, .glance-cell {
  break-inside: avoid;
}

/* Headings should never sit alone at the bottom of a page */
h1, h2, h3 { break-after: avoid; }
```

## Shadows in print

Hard shadows look wrong and can render as muddy gray boxes. In PDF:
- Prefer hairline borders and tinted fills for separation.
- A featured card may use a single whisper shadow (`0 4pt 24pt rgba(0,0,0,0.05)`) — soft, singular, outline-free.
- Never use ring + whisper + border stacked together.

## Numerals in tables

Financial and metric tables should use `font-variant-numeric: tabular-nums` so digits align in columns. Right-align all columns except the first label column. A total row gets a 1pt accent top border and weight 500.

---

## Conversion procedure (HTML → PDF)

This is the reliable, repeatable way to turn an HTML artifact into a print-clean PDF. **Text cutoff and alignment bugs are caught by looking, not by rules** — WeasyPrint is deterministic, so the procedure is render → rasterize → inspect → fix. Do not skip the inspect step.

Use the bundled converter, which handles fonts, rendering, preflight, and rasterization in one call:

```bash
python scripts/html_to_pdf.py INPUT.html OUTPUT.pdf --qa-dir OUTPUT_qa
```

It will:
1. Install the brand fonts (from `assets/fonts/`, or fetch them) so the serif/mono stack embeds rather than falling back.
2. Run preflight checks (flags `rgba()` tag backgrounds, Chart.js, and `<canvas>` — all print hazards).
3. Render the PDF with WeasyPrint.
4. Rasterize every page to PNG in the QA dir.

**Then you MUST open each QA PNG and check every page for:**
- text cutoff at page edges or inside fixed-height containers
- content overflowing a card / cell / table column
- a heading stranded alone at the bottom of a page (widow)
- misaligned columns or baselines
- any element that fell back to a wrong font (serif looks like Times → fonts didn't load)

If anything is wrong, fix the HTML/CSS and re-run. Common fixes: add `break-inside: avoid`, reduce a font size one step on the print scale, shorten copy, or give a container `overflow: hidden` only after confirming nothing important is being clipped.

### Pre-flight checklist (before rendering)

- [ ] Page size and margins set via `@page` (see margin table above)
- [ ] All tag/badge backgrounds are **solid hex**, never `rgba()`
- [ ] `break-inside: avoid` on cards, cells, tables, figures, callouts
- [ ] `h1, h2, h3 { break-after: avoid; }` set
- [ ] No `<canvas>`, no Chart.js / D3 / JS-driven visuals (use inline SVG)
- [ ] Type sizes on the pt scale, body line-height ≤ 1.55
- [ ] Fixed-height containers (`.chip`, hero blocks) verified not to clip text

## Charts in PDF — use inline SVG

**WeasyPrint does not execute JavaScript.** Chart.js, D3, Plotly, and `<canvas>` all render blank. The reliable path is **inline SVG**, generated server-side before rendering. Use `scripts/charts.py`, which emits on-brand SVG (rust accent, warm ink, hairline gridlines, mono labels) for the three common cases:

```python
import sys; sys.path.insert(0, "scripts")
import charts

bars  = charts.bar_chart([("Q1", 12.4), ("Q2", 14.1), ("Q3", 9.8)], title="revenue $m")
line  = charts.line_chart(
    [{"name": "with", "values": [16, 17, 18, 18]},
     {"name": "without", "values": [12, 13, 13, 14]}],
    labels=["w1", "w2", "w3", "w4"], title="correctness")
donut = charts.donut_chart(83, 100, label="tokens saved")

# embed each returned string directly into the HTML before rendering
```

For chart shapes the helper doesn't cover, hand-author inline SVG in the same palette (`#C0622A` series, `#D9D1BC` gridlines, `JetBrains Mono` labels). SVG scales crisply in print and never needs JS.

## What renders well in PDF (and what doesn't)

| Element                              | In PDF | Notes                                            |
|--------------------------------------|--------|--------------------------------------------------|
| Tables (incl. financial / striped)   | ✓      | Full support; use `tabular-nums`, accent total   |
| Cards, terminals, glance grids, tags | ✓      | All the signature UI elements render natively    |
| Inline SVG charts                    | ✓      | Use `charts.py` or hand-authored SVG             |
| Dot-grid / CSS textures              | ✓      | Lighten the dot for print (0.5px, #CFC6AC)       |
| Corner ticks, hairlines, borders     | ✓      | Render crisply at any zoom                       |
| Whisper shadow on a featured card    | ✓      | Soft and singular only; no hard drop shadows     |
| Chart.js / D3 / Plotly / `<canvas>`  | ✗      | No JS — convert to inline SVG                    |
| `position: sticky`, scroll effects   | ✗      | No viewport in print — design for static pages   |
| Web fonts via `<link>` to Google     | ✗      | No network at render — fonts must be installed   |
