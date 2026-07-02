# Component snippets

Copy-pasteable building blocks. These are the signature components — every project should include at least a few of them.

## Meta-row (section header)

```html
<div class="meta-row">
  <span>// 02 — Typography</span>
  <span>3 FAMILIES</span>
</div>
```

```css
.meta-row {
  display: flex; justify-content: space-between;
  border-bottom: 1px solid var(--line);
  padding-bottom: 6px;
  margin-bottom: var(--r-3);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
```

## Section title with italic accent

```html
<h2 class="sec-title">A serif for <em>voice.</em> A mono for <em>truth.</em></h2>
```

```css
.sec-title {
  font-family: var(--font-display);
  font-weight: 500;
  font-size: clamp(32px, 4.2vw, 48px);
  line-height: 1.05;
  letter-spacing: -0.025em;
  margin-bottom: var(--r-5);
  max-width: 720px;
}
.sec-title em {
  font-style: italic;
  color: var(--accent);
  font-weight: 500;
}
```

## Schematic card (with corner ticks + index)

```html
<div class="card">
  <span class="num">001</span>
  <code>grep "GDPR" ~/legal/</code>
  <h3>Legal search</h3>
  <p>Description text here.</p>
</div>
```

```css
.card {
  background: var(--bg-alt);
  border: 1px solid var(--line);
  padding: var(--r-4);
  position: relative;
}
.card::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 10px; height: 10px;
  border-top: 1px solid var(--accent);
  border-left: 1px solid var(--accent);
}
.card::after {
  content: '';
  position: absolute;
  bottom: -1px; right: -1px;
  width: 10px; height: 10px;
  border-bottom: 1px solid var(--accent);
  border-right: 1px solid var(--accent);
}
.card .num {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--accent);
  position: absolute;
  top: var(--r-3); right: var(--r-3);
}
.card code {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--bg-deep);
  color: var(--accent-deep);
  padding: 3px 8px;
  margin-bottom: var(--r-2);
}
```

## Terminal block

```html
<div class="terminal">
  <div class="term-head">
    <span><span class="dot"></span>READY</span>
    <span>INSTALL.SH</span>
  </div>
  <div><span class="prompt">$</span>curl -fsSL example.com/install | sh</div>
  <div><span class="comment"># → and you're done.</span></div>
</div>
```

```css
.terminal {
  background: var(--bg-alt);
  border: 1px solid var(--line);
  padding: var(--r-4);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
}
.terminal .term-head {
  display: flex; justify-content: space-between;
  margin-bottom: var(--r-3);
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--ink-mute);
}
.terminal .term-head .dot {
  display: inline-block;
  width: 6px; height: 6px;
  background: var(--accent);
  border-radius: 50%;
  margin-right: 6px;
}
.terminal .prompt { color: var(--accent); margin-right: 8px; }
.terminal .comment { color: var(--ink-mute); font-style: italic; }
```

## Button pair (ghost + solid)

```html
<button class="btn solid">Primary action</button>
<button class="btn">Secondary action</button>
```

```css
.btn {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  padding: 12px 20px;
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
  cursor: pointer;
  transition: all 180ms ease;
}
.btn:hover {
  background: var(--accent);
  color: var(--bg);
}
.btn.solid {
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}
.btn.solid:hover {
  background: var(--accent);
  border-color: var(--accent);
}
```

## Mono label (inline)

```html
<span class="label accent">// VIRTUAL FILE — 01</span>
```

```css
.label {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-mute);
  display: block;
}
.label.accent { color: var(--accent); }
```

## Spec-sheet grid (label + content)

```html
<div class="type-grid">
  <div class="spec-label">Display<small>Fraunces · 500</small></div>
  <div>
    <div class="spec-display">Headline <em>here.</em></div>
  </div>
</div>
```

```css
.type-grid {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--r-5) var(--r-4);
  align-items: baseline;
}
.spec-label {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-mute);
  border-top: 1px solid var(--line);
  padding-top: var(--r-2);
}
.spec-label small {
  display: block;
  text-transform: none;
  letter-spacing: 0.05em;
  margin-top: 6px;
  font-size: 10px;
}
```

## Editorial list (en-dash / bar, not round bullets)

Round bullets read juvenile next to serif editorial copy. Replace them with a short accent bar or an en-dash.

```html
<ul class="dash">
  <li>First point, set in body serif.</li>
  <li>Second point — the bar reads as editorial.</li>
</ul>
```

```css
ul.dash { list-style: none; padding-left: 0; }
ul.dash li {
  position: relative;
  padding: 8px 0 8px 18px;
  border-bottom: 1px solid var(--line);
  line-height: 1.55;
}
ul.dash li:last-child { border-bottom: none; }
ul.dash li::before {
  content: "";
  position: absolute;
  left: 0; top: 16px;
  width: 8px; height: 1.5px;
  background: var(--accent);
}
/* For plain bulleted lists that stay round, at least color the marker: */
ul li::marker { color: var(--accent); }
```

## Glance grid (key numbers)

Four key-number cells — good after a hero, a TOC, or a chapter opener.

```html
<div class="glance-grid">
  <div class="glance-cell">
    <div class="glance-label">REPORTING PERIOD</div>
    <div class="glance-value">Q1 2026</div>
    <div class="glance-note">Three core themes</div>
  </div>
  <!-- up to 4 cells -->
</div>
```

```css
.glance-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--r-3);
  margin: var(--r-4) 0;
}
.glance-cell {
  padding: 12px 0 10px 14px;
  border-left: 2px solid var(--accent);
}
.glance-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.glance-value {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 500;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  line-height: 1.1;
}
.glance-note {
  font-size: 13px;
  color: var(--ink-soft);
  line-height: 1.4;
  margin-top: 4px;
}
```

## Section header with eyebrow dot

A lightweight section opener — mono eyebrow with an accent dot, a hairline rule, then a serif title. Note the spacing rule: the gap *below* the rule must be at least double the gap above it, which anchors the title.

```html
<div class="section-header">
  <div class="eyebrow">Methodology</div>
  <div class="rule"></div>
  <h2>How the model decides.</h2>
</div>
```

```css
.section-header .eyebrow {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--ink-mute);
  margin-bottom: 14px;
}
.section-header .eyebrow::before {
  content: "";
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}
.section-header .rule {
  height: 1px;
  background: var(--line);
  margin-bottom: 36px;   /* >= 2x the 14px gap above */
}
.section-header h2 {
  font-family: var(--font-display);
  font-size: clamp(28px, 4vw, 38px);
  font-weight: 500;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--ink);
}
```

## Financial / data table

```html
<table class="data-table financial striped">
  <thead><tr><th>Category</th><th>Q1</th><th>Q2</th></tr></thead>
  <tbody>
    <tr><td>Revenue</td><td>$12.4M</td><td>$14.1M</td></tr>
    <tr class="total"><td>Total</td><td>$12.4M</td><td>$14.1M</td></tr>
  </tbody>
</table>
```

```css
.data-table {
  width: 100%; border-collapse: collapse;
  font-size: 14px; margin: var(--r-3) 0;
}
.data-table th {
  text-align: left; font-weight: 500;
  font-family: var(--font-mono);
  font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--ink-mute);
  padding: 8px 10px;
  border-bottom: 1px solid var(--line);
}
.data-table td {
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
/* Right-align numeric columns, align digits */
.data-table.financial td:not(:first-child),
.data-table.financial th:not(:first-child) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.data-table.striped tbody tr:nth-child(even) { background: var(--bg-alt); }
.data-table tr.total td {
  font-weight: 500;
  border-top: 1px solid var(--accent);
  border-bottom: none;
}
```
