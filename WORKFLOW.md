# My Workflow

## How I work

Plan before coding, keep changes small and reviewable, verify with evidence before
calling anything done, and track decisions and plans around the work so the
reasoning stays visible. When something needs visualizing I build an HTML artifact,
and when it needs sharing I publish it to a public URL.

---

## Skills I use

- **`/manifest`** — plan any non-trivial task before coding.
- **`/stacked`** — for genuinely complex, multi-layer manifests: deliver one branch/PR per layer (see below). Skip for simple changes.
- **`/kagaz`** — design system for any frontend, UI, mockup, dashboard, slide deck, report, or PDF. Use it whenever a task calls for visual design or an HTML/document artifact rather than hand-rolling markup.
- **`/dak`** — publish a local artifact (HTML report, dashboard, PDF, directory) to a shareable `https://` URL. Use it as the final step whenever I want a link back rather than a file.

---

## manifest + stacked go together for genuinely layered work

**Rule:** Stacking is for genuinely complex tasks with multiple real layers — not a
blanket requirement. When `/manifest` defines a Stack section with 2+ layers, that
table is the contract and `/stacked` branches deliver it. Simple or single-concern
changes don't need a stack.

**How to apply:**
- When the Stack section is written, name the branches: `<slug>/layer-one`, `<slug>/layer-two`, etc.
- Implement bottom-up: one branch per layer, each branching off the one below.
- Open PRs/MRs bottom-up: layer-one targets main; layer-two targets layer-one.
- Update the Stack table `Status` column (`open → in review → merged`) as PRs/MRs progress.
- Never push all stack layers to a single feature branch — it defeats independent reviewability.

**Why:** When a change genuinely spans layers, a unified multi-file diff that mixes
them can't be meaningfully reviewed — so a Stack section, once written, must be
delivered as stacked branches.
