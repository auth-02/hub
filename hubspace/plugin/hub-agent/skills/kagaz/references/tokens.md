# Design tokens — copy-paste reference

Default CSS variables for any new project. Drop this block into `:root` and start building.

```css
:root {
  /* ── SURFACES ─────────────────────────────────────────── */
  --bg:           #F4EFE4;   /* warm cream canvas */
  --bg-alt:       #ECE5D2;   /* tinted panel */
  --bg-deep:      #E4DCC4;   /* nested panel */

  /* ── INK ──────────────────────────────────────────────── */
  --ink:          #1A1A1A;   /* primary body */
  --ink-soft:     #3A352D;   /* secondary text */
  --ink-mute:     #8A8377;   /* labels, captions */
  --line:         #D9D1BC;   /* hairline rules */

  /* ── ACCENT (default: rust) ───────────────────────────── */
  --accent:       #C0622A;
  --accent-soft:  #E89A6B;
  --accent-deep:  #8A4218;

  /* ── TYPE ─────────────────────────────────────────────── */
  --font-display: 'Fraunces', 'Times New Roman', serif;
  --font-body:    'Inter', system-ui, sans-serif;
  --font-mono:    'JetBrains Mono', 'SF Mono', Menlo, monospace;

  /* ── RHYTHM (4-based) ─────────────────────────────────── */
  --r-1: 4px;   --r-2: 8px;   --r-3: 16px;
  --r-4: 24px;  --r-5: 40px;  --r-6: 64px;  --r-7: 96px;
}

body {
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.55;
  /* Signature dot-grid */
  background-image: radial-gradient(circle, #C9BFA3 0.7px, transparent 0.7px);
  background-size: 22px 22px;
}
```

## Google Fonts import

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

## Accent mood swaps

If rust is wrong for the project, replace `--accent` / `--accent-soft` / `--accent-deep` with one of:

| Mood       | Primary   | Soft      | Deep      | Use for                          |
|------------|-----------|-----------|-----------|----------------------------------|
| Rust       | `#C0622A` | `#E89A6B` | `#8A4218` | Default — editorial, technical   |
| Deep sea   | `#1E5A6B` | `#3D8A9E` | `#0F3340` | Healthcare, research, calm tools |
| Oxblood    | `#7A2828` | `#B85454` | `#4D1414` | Financial, serious, archival     |
| Moss       | `#4A6B3D` | `#7A9E5E` | `#2D4520` | Sustainability, organic, natural |
| Indigo ink | `#2D3866` | `#5468A8` | `#161E40` | Developer tools, infrastructure  |

Never mix moods. Pick one per project.
