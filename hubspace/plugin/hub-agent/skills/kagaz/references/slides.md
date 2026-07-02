# Slides → PDF

A slide deck is **not** a flowing document. Each slide must be exactly one page,
in landscape, fixed-size, with nothing spilling onto a phantom next page. That
spilling is what "breaks continuity" — a slide bleeds onto a second page and the
1-slide-1-page mapping is lost.

The whole problem reduces to one rule:

> **Every slide is a fixed-size box equal to the page, with `overflow: hidden`.**
> Then a too-tall slide gets *clipped* (visible in QA) instead of *spilling* (a
> phantom page). Page count therefore always equals slide count — and that
> equality is the test that proves continuity held.

## Page geometry

Use 16:9 widescreen (PowerPoint default) unless asked otherwise:

```css
@page { size: 13.333in 7.5in; margin: 0; }   /* 960 x 540 pt — 16:9 */
```

Other ratios: 4:3 → `10in 7.5in`; A4 landscape → `297mm 210mm`.
Set `margin: 0` on `@page` and do the padding inside each `.slide`, so the slide
fills the page edge to edge (the dot-grid and full-bleed panels need this).

## The slide box

```css
.slide {
  width: 13.333in; height: 7.5in;   /* exactly the page */
  overflow: hidden;                  /* clip, never spill */
  break-after: page;
  position: relative;
  padding: 0.72in 0.86in;
  display: flex; flex-direction: column;
  background: var(--bg);
}
.slide:last-child { break-after: auto; }   /* no trailing blank page */
```

Two things make or break this:
- `height: 7.5in` (the exact page height) + `overflow: hidden` is what prevents
  the phantom page. Do not use `min-height` — that lets content push taller.
- `.slide:last-child { break-after: auto; }` stops a blank final page.

## Layout inside a slide

Use `flex-direction: column` and push content with `margin-top: auto` or a
`.spacer` so footers sit at the bottom and hero content centers. Anchor the
brandmark and page number absolutely:

```css
.pageno    { position: absolute; bottom: 0.5in; right: 0.86in;
             font-family: var(--mono); font-size: 9pt; color: var(--ink-mute); }
.brandmark { position: absolute; bottom: 0.5in; left: 0.86in;
             font-family: var(--mono); font-size: 9pt; color: var(--ink-mute); }
```

Slide type runs larger than print-document type: cover h1 ~54pt, section h2
~34pt, body ~15pt, bullets ~15pt. Keep line-heights tight (1.0–1.3 on titles).
A slide should hold **one idea** — if it needs more than ~6 bullet lines or two
stacked blocks, split it into two slides rather than shrinking type.

## Conversion + the continuity check

Render in slide mode, which asserts page count equals slide count:

```bash
python scripts/html_to_pdf.py deck.html deck.pdf --slides --qa-dir deck_qa
```

- `CONTINUITY OK — N slides = N pages` → mapping held.
- `CONTINUITY BROKEN — N slides but N+1 pages` → a slide overflowed. **Fix it**,
  don't ship it. The slide whose content is too tall is the culprit; find it in
  the QA PNGs (it'll be the one clipped at the bottom), then shorten copy, scale
  type down one step, or split the slide.

Then still open the QA PNGs: the continuity check guarantees 1 slide = 1 page,
but only your eyes confirm nothing important got *clipped* by `overflow: hidden`.

## Common continuity bugs

| Symptom                         | Cause                                  | Fix                                            |
|---------------------------------|----------------------------------------|------------------------------------------------|
| N slides → N+1 pages            | a slide's content exceeds page height  | shorten / scale / split that slide             |
| blank page after every slide    | slide height slightly > page, or stray `break-after` on last | use exact height; `:last-child{break-after:auto}` |
| footer/page-no drifts up        | content pushed it instead of anchoring | `position: absolute` the footer to the slide   |
| text clipped at slide bottom    | too much content for one slide         | split into two slides; never just clip         |
| whole deck on one page          | missing `break-after: page` on `.slide`| add it                                         |

## Editable decks (PPTX)

This path produces a **PDF** deck — fixed, print-perfect, presenter-ready, but
not editable in PowerPoint/Keynote. If the user needs an editable `.pptx`, that's
a different tool (the pptx skill / python-pptx); this design system still governs
the palette, type, and layout, but the slide-as-page mechanics above are
PDF-specific.
