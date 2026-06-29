---
name: kagaz
description: Kagaz (कागज़) — a personal frontend and document design system — an editorial, technical, archival aesthetic combining serif display type, monospace metadata, warm paper-toned palettes, a single rust accent, dot-grid textures, and schematic-style component framing. Use this skill whenever the user asks for any kind of frontend, UI, web page, landing page, dashboard, artifact, component, mockup, poster, slide deck or presentation, report, or PDF/document design, when converting an HTML artifact to a clean PDF, when building a slide deck as a PDF (one slide per page), or for any "make this look good" / "style this" / "design this" / "turn this into a PDF" / "make slides" request — even without explicitly invoking this skill or mention design preferences. The skill defines a specific aesthetic point of view (paper not screen, one accent under five percent of surface, warm neutrals only, mono-as-metadata, italic-not-bold, hairlines and soft depth not hard shadows, number everything, one decoration density), ships a reliable HTML-to-PDF converter with visual QA plus on-brand SVG charts, and should override generic defaults like Inter-on-white, purple gradients, cool grays, or cookie-cutter dashboard layouts.
---

# Kagaz — Kagaz Design System

A reference aesthetic for any frontend work. The look is editorial-technical: warm paper canvas, surgical rust accent, literary serif display paired with mono metadata, hairline-bounded schematic cards. It reads like a well-typeset technical manual or an archival spec sheet, not a SaaS landing page.

This skill describes the **taste**, not a fixed template. Apply it to whatever you're building — a landing page, a dashboard, a docs site, an internal tool, a presentation — and adapt the principles to fit. The example in `examples/kagaz-showcase.html` shows one full execution; reference it for proportions, spacing, and detail handling, but don't copy it wholesale.

## When to use

Apply this skill any time the user asks for:
- A web page, landing page, marketing site, or portfolio
- A dashboard, internal tool, or admin interface
- A React/HTML/CSS component or full artifact
- A "design", "mockup", "style", "theme", or "look and feel" request
- Slides or a poster where visual design matters
- Anything where you'd otherwise reach for generic AI defaults

If the request is purely functional (e.g. "fix this bug in my React state logic") and appearance isn't involved, skip this skill. But if any styling decision is involved, default to this aesthetic.

## The invariants

These are the spine of the aesthetic. Each one has a real cost — they're not arbitrary, so think before overriding any of them. If you break one, do it deliberately and know what you're trading.

### 1. Paper, not screen
The canvas is **warm cream** (`#F4EFE4`), never pure white. Subtle texture — a radial dot-grid or fine noise — sits behind everything to evoke archival print. Use tinted paper layers (cream → tinted panel → deeper panel) for depth instead of elevation. *Cost of breaking it: the work immediately reads as a generic SaaS page.*

### 2. One accent, ≤ 5% of surface area
A single chromatic accent (rust orange `#C0622A` by default) does all the emotional work, and it should cover **no more than ~5% of the visible surface**. More than that is ornament, not restraint. It appears on:
- Italic emphasis in display headlines
- Section numbers and indices
- Corner ticks on cards
- Links and CTAs
- Small status indicators and `::marker` bullets

Never use a second saturated color. Never spread the accent across large fills. If a design "needs more color," resist — reach for typographic contrast (size, italic, mono) instead. *Cost of breaking it: the accent stops feeling intentional and starts feeling like a brand color slapped on.*

### 3. Warm neutrals only, four levels
Every gray carries a **yellow-brown undertone** — never a cool blue-gray. The mnemonic: in `rgb()`, warm gray is **R ≥ G > B**; cool gray is R ≤ G ≤ B or fully neutral. Use exactly four ink levels — primary → secondary → subtext → tertiary — and no fifth. *Cost of breaking it: one cool `#6b7280` gray contaminates the whole warm palette and the page feels cheap.*

### 4. Mono as metadata
Every label, code reference, index number, system state, version string, and "// SECTION" marker runs in monospace. The serif speaks; the mono annotates. This is the signature spec-sheet feel.

### 5. Italic as emphasis
Replace bold with **serif italic** in the accent color. Headlines read like a magazine pull-quote, not a marketing banner. `<em>` does what `<strong>` would in a generic design. Serif weight stays locked at **500** — never synthetic 700/900 bold. *Cost of breaking it: synthetic bold on a fine serif looks muddy and undercuts the editorial tone.*

### 6. Hairlines and soft depth, never hard shadows
Containers are bounded by **1px borders** on tinted backgrounds. Corners stay sharp (0–4px radius). Add accent-colored corner ticks (10px L-brackets at top-left + bottom-right) on featured cards for schematic framing. When depth is genuinely needed, use one of two soft moves — never a hard drop shadow:
- **Ring shadow** (`box-shadow: 0 0 0 1px <color>`) — a border replacement for button focus/hover. Don't stack it over an existing border.
- **Whisper shadow** (`box-shadow: 0 4px 24px rgba(0,0,0,0.05)`) — a barely-visible lift for a featured card, mimicking paper raised off the table.

*Forbidden: `box-shadow: 0 2px 8px rgba(0,0,0,0.3)` and relatives. Cost of breaking it: hard shadows read as digital, not paper.*

### 7. Number everything
Sections get `// 01 — SECTION NAME` headers. Cards get `001`, `002` indices. Principles get `PRINCIPLE 04`. Numbering implies authorship, version, intentionality — it makes the work feel deliberate.

### 8. Pick one decoration density and hold it
A layout is either **editorial** or **structured** — never both, never neither overdone.
- **Editorial** (default): no decorative lines. The accent appears only in text — chapter numbers, emphasis, `<strong>`, digits, labels. Containers use tinted fill + soft radius. Reads as "content speaks."
- **Structured**: top hairlines (0.6–0.8px accent) on cards, glance cells, and callouts — roughly 5–8 accent lines per page. Reads as "structure helps."

The failure mode is the third option: accent lines *plus* fills *plus* radius *plus* borders all at once, which signals over-packaging. When unsure, default to editorial.

## Default token palette

Use these CSS variables as the starting point. Adjust hues if context demands (a dashboard for a finance product might warrant a deeper paper; a docs site might lean cooler), but keep the **structure** — three paper tones, three accent depths, three ink levels.

```css
:root {
  /* Surfaces — warm cream, layered */
  --bg:       #F4EFE4;  /* canvas */
  --bg-alt:   #ECE5D2;  /* panel */
  --bg-deep:  #E4DCC4;  /* nested */

  /* Ink — never pure black */
  --ink:       #1A1A1A;  /* primary body */
  --ink-soft:  #3A352D;  /* secondary */
  --ink-mute:  #8A8377;  /* labels, captions */
  --line:      #D9D1BC;  /* hairline rules */

  /* Accent — the one chromatic note */
  --accent:       #C0622A;  /* rust — primary */
  --accent-soft:  #E89A6B;  /* highlight tint */
  --accent-deep:  #8A4218;  /* pressed/serious */
}
```

**Alternative accent moods** if rust doesn't fit the project:
- Deep sea: `#1E5A6B` / `#3D8A9E` / `#0F3340`
- Oxblood: `#7A2828` / `#B85454` / `#4D1414`
- Moss: `#4A6B3D` / `#7A9E5E` / `#2D4520`
- Indigo ink: `#2D3866` / `#5468A8` / `#161E40`

Pick one and stick to it. Never combine accent moods.

## Default type stack

```css
--font-display: 'Fraunces', 'Times New Roman', serif;
--font-body:    'Inter', system-ui, sans-serif;
--font-mono:    'JetBrains Mono', 'SF Mono', Menlo, monospace;
```

**Fraunces** is the signature — use weight 500 (not 700), tight letter-spacing (-0.025 to -0.035em), and lean on the italics. **Inter** handles body copy at 15–16px with 1.55 line-height. **JetBrains Mono** at 10–13px, UPPERCASE for labels, letter-spacing +0.12 to +0.18em.

**Acceptable display swaps** if Fraunces is wrong for the project:
- More editorial: `Tiempos`, `Source Serif Pro`
- More architectural: `PP Editorial New`, `Domaine Display`
- More archival: `EB Garamond`, `Cormorant Garamond`

**Never use** for display: Inter, Roboto, Arial, Poppins, Montserrat, Space Grotesk, Plus Jakarta Sans, or any other AI-default font.

## Layout patterns

**Sections** are tall (96px vertical padding on desktop), separated by 1px top borders. Each opens with a mono-set meta-row:

```html
<div class="meta-row">
  <span>// 02 — Typography</span>
  <span>3 FAMILIES</span>
</div>
<h2 class="sec-title">A serif for <em>voice.</em> A mono for <em>truth.</em></h2>
```

**Cards** sit on `--bg-alt` with hairline borders. Featured cards get accent corner ticks via `::before` (top-left) and `::after` (bottom-right) pseudo-elements. Index number sits absolute top-right in mono.

**Terminal blocks** use mono on `--bg-alt` with a status header (red dot · READY · filename right-aligned in mono caps).

**Grids** prefer asymmetric column splits (e.g., 200px label column + flexible content column for spec sheets) over symmetric grids. Generous gap (24–40px).

## Motion

Keep motion **restrained**. The aesthetic is paper, and paper doesn't bounce. Use:
- 160–200ms ease transitions on hover (color shifts, border color, text underline)
- Subtle reveal on scroll for hero sections only (10–15px translate, 400ms)
- No parallax, no large-scale movement, no autoplay video

## Don'ts (hard rules)

- ❌ Pure white (`#FFF`) backgrounds or any cool-gray surface (`#f8f9fa`, `#f3f4f6`)
- ❌ Pure black (`#000`) text — deepest ink is `#1A1A1A` with a warm undertone
- ❌ Cool blue-gray neutrals (any gray where B ≥ G ≥ R)
- ❌ Hard drop shadows (`0 2px 8px rgba(0,0,0,0.3)` and relatives) — use ring or whisper only
- ❌ Rounded corners over 4px (hero containers may reach 8px, rarely more)
- ❌ Gradient fills (linear or radial, except the dot-grid texture)
- ❌ Multiple saturated colors
- ❌ `rgba()` backgrounds on tags/badges in **print/PDF** output — WeasyPrint renders a visible double-rectangle on zoom; always convert to a solid hex
- ❌ Emoji as functional UI elements (decorative use sparingly OK)
- ❌ Inter (or Roboto, Arial, Poppins, Space Grotesk) as a display font
- ❌ Synthetic bold (700/900) as emphasis — use serif italic + accent color; serif weight locked at 500
- ❌ Loose line-heights (1.60+) in dense or print contexts — reads as web rhythm, not print
- ❌ Centered body copy in long-form sections
- ❌ Hero sections with stock-photo backgrounds or AI-generated imagery

## Workflow when generating a design

1. **Read the request and identify the form** — landing page? dashboard? component? Adapt the principles to the form; don't force every design to look like the showcase example.
2. **Pick the accent mood** — rust by default. Only swap if the project context strongly suggests otherwise (e.g., a healthcare tool might lean moss or sea).
3. **Confirm the type stack** — Fraunces by default unless a serif swap is more appropriate.
4. **Sketch the section structure with mono meta-rows and numbered indices** — this is what makes the work feel intentional, not generic.
5. **Build with the invariants as a checklist** — before finishing, verify each of the eight is honored (or that any break was deliberate).
6. **Reference `examples/kagaz-showcase.html`** for proportions, spacing rhythm, component patterns, and detail-handling — but don't lift content or structure wholesale. It's an example, not a template.

## Bundled references

- **`references/tokens.md`** — Copy-paste CSS variables, Google Fonts import line, and accent mood swap table. Read this first when starting a new project.
- **`references/components.md`** — Copy-paste HTML+CSS snippets for the signature components (meta-row, schematic card, terminal block, button pair, spec-sheet grid, glance grid, editorial list, data table, mono labels). Read when you need to drop in any of these.
- **`references/print.md`** — Print/PDF specifics: pt-based type scale, line-height tiers, page margins, pagination rules, the WeasyPrint solid-tag conversion table, **the full HTML→PDF conversion procedure with its mandatory visual-QA loop**, inline-SVG chart guidance, and a what-renders-in-PDF support matrix. **Read this whenever the output is a PDF.**
- **`references/slides.md`** — Slide-deck → PDF specifics: landscape page geometry, the fixed-size-slide-with-`overflow:hidden` rule that keeps one slide on one page, the continuity check (page count must equal slide count), slide-scale type, and a table of common continuity bugs. **Read this whenever the output is a slide deck / presentation as PDF.**
- **`examples/kagaz-showcase.html`** + **`kagaz-showcase.pdf`** — The canonical design system showcase: "Editorial precision, terminal warmth." Demonstrates the full palette, type specimens, schematic cards, glance grid, editorial list, data table, and invariants grid. **Primary calibration reference** — use it first when in doubt about how anything should look. For slide-deck layout, the HTML→PDF slide patterns live in `references/slides.md`.

## Bundled scripts and assets

- **`scripts/html_to_pdf.py`** — Converts an HTML artifact to a print-clean PDF. Installs the brand fonts, runs preflight checks, renders with WeasyPrint, and rasterizes every page to PNG for visual QA. Always use this (not a raw WeasyPrint call) so cutoff/alignment bugs get caught. Usage: `python scripts/html_to_pdf.py INPUT.html OUTPUT.pdf --qa-dir OUTPUT_qa`, then **open each QA PNG and inspect before delivering**. For a slide deck, add `--slides` and it asserts that the PDF page count equals the number of `.slide` elements — i.e. that every slide is exactly one page and continuity held.
- **`scripts/charts.py`** — Generates on-brand inline SVG charts (`bar_chart`, `line_chart`, `donut_chart`) in the rust palette. Use these whenever a PDF needs a chart, because WeasyPrint can't run JavaScript charting libraries.
- **`assets/fonts/`** — Fraunces, Inter, and JetBrains Mono (all OFL-licensed), bundled so PDFs embed the real type stack offline. `html_to_pdf.py` installs these automatically.

### Quick note on PDF capability

This skill produces PDFs that fully support **tables** (financial/striped, with tabular figures and accent total rows), **all the signature UI elements** (cards, terminals, glance grids, badges, corner ticks), and **charts via inline SVG**. It does **not** support JavaScript-driven charts (Chart.js, D3, `<canvas>`) — convert those to inline SVG with `charts.py`. See the support matrix at the end of `print.md`.

It also produces **slide decks as PDF** — one slide per page, 16:9 landscape, presenter-ready. The mechanics differ from documents (fixed-size slides, not flowing content), so read `references/slides.md` for the full slide-as-page geometry. Render with `--slides` to verify continuity. Note this is a *fixed* PDF deck, not an editable `.pptx`; for editable slides use the pptx skill while keeping this design system's palette and type.

## A note on adapting to context

This skill encodes a strong aesthetic point of view. That's the point. The system spans many domains — financial tooling, AI infrastructure, developer tools, internal dashboards — and the design should always feel **appropriate** to the subject, not pasted on. A portfolio diagnostics dashboard for institutional clients should feel more reserved and data-dense (lean structured, tighter line-heights); a developer-tool landing page can lean more playful in its mono-typography choices (lean editorial). The invariants hold; the expression flexes.
