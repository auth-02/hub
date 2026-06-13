# Hub Illustrations — Prompt Shot List

> Prompts generated using the [ian-xiaohei-illustrations](https://github.com/helloianneo/ian-xiaohei-illustrations) Claude Code skill — Xiaohei (小黑) illustration system by Ian Neo. Feed these prompts into any image generation tool (Midjourney, DALL-E, Stable Diffusion).

## Shot list
1. [The Single Page Promise] — every scattered doc funneled into one place — Conceptual metaphor
2. [Task Lineage Tree] — manifest → runs → artifacts connected — System cross-section
3. [Hub Feed Pulse] — activity surfacing in real time — Character state
4. [The Timeline Question] — "what did I work on?" answered — Map/route

---

### Illustration 1: The Single Page Promise

**Cognitive anchor:** Hundreds of `.md` and `.html` files across many repos collapse into one browsable page
**Structure type:** Conceptual metaphor
**Metaphor:** A funnel — files pour in from all sides, one clean sheet falls out the bottom

**Image generation prompt:**
```
Pure white background. Minimalist black hand-drawn line art. Large empty white space (at least 35% of canvas as a quiet zone).

Central character: small solid-black creature (Xiaohei) with white dot eyes, tiny thin legs, blank deadpan serious expression — standing at the bottom of a giant hand-drawn funnel, holding a single flat sheet of paper and looking at it with total calm. Not decorative. Not cute. Not a mascot.

Scene: A wide funnel drawn in thick black lines dominates the upper-center. From the top rim, dozens of small scraps labeled ".md" and ".html" tumble downward in disarray — overlapping, rotated, chaotic. Below the funnel spout, Xiaohei holds one neat rectangular sheet. To the left and right of the funnel, empty white space breathes. The funnel is slightly crooked, hand-drawn imperfect.

Sparse English handwritten-style annotations (max 6 labels):
- "17 repos" (near funnel top, scattered side)
- "318 files" (near funnel mid, orange)
- "one page" (near the clean sheet, red)
- ".md .html .htm" (small, near falling scraps)
- "sorted by recency" (small, near bottom sheet)
- "just open it" (far right quiet zone, small blue)

Color rules: orange for the funnel mouth arrow flow; red for "one page" label; blue for the quiet annotation; black for all linework.

No gradients. No shadows. No background texture. No realistic UI. No PPT infographic style. No title label in top-left corner. No Chinese text.

Format: 16:9 horizontal. Style: sketch, eccentric, memorable, hand-drawn product diagram feel.
```

---

### Illustration 2: Task Lineage Tree

**Cognitive anchor:** Every file under `tasks/<slug>/` is automatically linked — manifest to runs to artifacts — without any manual configuration
**Structure type:** System cross-section
**Metaphor:** An archaeological dig cross-section — the manifest is bedrock, runs and artifacts are strata above it

**Image generation prompt:**
```
Pure white background. Minimalist black hand-drawn line art. Large empty white space (at least 35% on the right side as quiet zone).

Central character: small solid-black creature (Xiaohei) with white dot eyes, tiny thin legs, blank deadpan serious expression — mid-dig, holding a tiny shovel, standing inside a cross-section cut into the ground. Not decorative. Not cute. Not a mascot.

Scene: Left half of the canvas shows a vertical cross-section of earth, drawn with rough horizontal strata lines. Bottom layer (thickest, most solid) labeled "manifest.md" — Xiaohei stands here with shovel. Middle stratum labeled "runs/" with small date stamps sketched in. Top stratum labeled "artifacts/" with a small folded-corner document shape. Orange connecting lines run vertically between the strata like veins. A small "// trace" annotation floats above the cross-section with an orange upward arrow. Right half: pure white empty space.

Sparse English handwritten-style annotations (max 6 labels):
- "manifest.md" (bottom stratum, red)
- "runs/2026-05-18" (middle stratum)
- "artifacts/" (top stratum)
- "// trace" (floating above, orange)
- "auto-linked" (blue, small, far right quiet zone)
- "no config needed" (blue, small, below "auto-linked")

Color rules: orange for the vertical connective veins and trace arrow; red for manifest label; blue for the quiet zone notes; black for all stratum lines and Xiaohei.

No gradients. No shadows. No realistic UI. No PPT style. No Chinese text. No title label.

Format: 16:9 horizontal. Style: sketch, eccentric, hand-drawn cross-section diagram.
```

---

### Illustration 3: Hub Feed Pulse

**Cognitive anchor:** The `// feed` drawer surfaces what changed, which task, how long ago — the workspace feels alive
**Structure type:** Character state
**Metaphor:** Xiaohei pressing an ear to the wall of the hub, listening to signals pulse through it

**Image generation prompt:**
```
Pure white background. Minimalist black hand-drawn line art. Large empty white space (at least 40% — upper right corner is completely empty).

Central character: small solid-black creature (Xiaohei) with white dot eyes, tiny thin legs, blank deadpan serious expression — pressing one ear flat against a tall vertical rectangle (the drawer panel), holding perfectly still, listening intently. Posture: side-on, one arm braced against the panel. Not cute. Deadpan.

Scene: The drawer panel is a tall thin rectangle on the right side of canvas, drawn with slightly uneven lines. Inside the panel, three or four short horizontal pulses are visible — like an ECG trace — in orange. Each pulse has a small handwritten label floating beside it. Xiaohei is pressed against the left face of the panel. Far left and upper right: completely empty white space.

Sparse English handwritten-style annotations (max 7 labels):
- "3h ago" (near top pulse, small)
- "Canonical logging" (italic feel, near top pulse, blue)
- "run logged" (small, near top pulse)
- "1d ago" (near lower pulse)
- "Artifact revised" (blue, near lower pulse)
- "// feed" (red, top of the drawer panel, small header)
- "ctrl+F" (small, black, bottom corner of panel)

Color rules: orange for ECG pulses inside the panel; red for "// feed" header label; blue for task name annotations; black for all linework and Xiaohei.

No gradients. No shadows. No realistic UI. No PPT style. No Chinese text. No title label.

Format: 16:9 horizontal. Style: sketch, deadpan, hand-drawn.
```

---

### Illustration 4: The Timeline Question

**Cognitive anchor:** The `// timeline` drawer answers "What did I work on yesterday?" — synthesising git commits, manifests, runs into a daily narrative
**Structure type:** Map/route
**Metaphor:** Xiaohei unrolling a very long receipt from a tiny machine, reading yesterday's work printed on it

**Image generation prompt:**
```
Pure white background. Minimalist black hand-drawn line art. Large empty white space (left side, at least 40%).

Central character: small solid-black creature (Xiaohei) with white dot eyes, tiny thin legs, blank deadpan serious expression — standing to the right of canvas, holding a long curling paper receipt that spills onto the floor. One hand feeds it through a small boxy receipt printer on a table. Reading the receipt with total calm. Not cute. Not mascot.

Scene: The receipt printer is a small boxy machine, slightly imperfect lines. The receipt paper curls out and down, long and narrow. On the receipt, three sections are printed in small handwritten text — each a mini task summary: task name, a bullet or two, a small upward arrow (git commit). The receipt coils loosely on the floor below. Left half of canvas: empty white space. The question "what did I work on?" floats in the top-left quiet zone in small hand-drawn text.

Sparse English handwritten-style annotations (max 7 labels):
- "what did I work on?" (top-left quiet zone, red)
- "Canonical logging" (on receipt, blue italic)
- "· 1 run logged" (on receipt, small black)
- "↑ fix(sandbox): pre-bind..." (on receipt, small orange)
- "Perf open closed" (lower on receipt, blue italic)
- "// timeline" (on printer face, small black)
- "ctrl+T" (small, below printer, black)

Color rules: orange for the git commit arrow lines on receipt; red for the question annotation; blue for task name labels; black for all linework, printer, Xiaohei.

No gradients. No shadows. No realistic UI. No PPT style. No Chinese text. No title label.

Format: 16:9 horizontal. Style: sketch, eccentric, deadpan, hand-drawn.
```
