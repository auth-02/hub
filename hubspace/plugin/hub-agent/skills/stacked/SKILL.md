---
name: stacked
description: >
  Decompose LARGE, complex, or risky changes into a stack of small, dependent, independently reviewable units. Use this skill only when the change is genuinely big: it spans multiple architectural layers with functionally distinct concerns (models + storage + logic + API + UI in combination), or the resulting diff would be too large to review as a single unit. Trigger when the user says "stacked", "stacked PRs", "stacked diffs", "stack this", or asks how to break down a large change — or when a "build X" / "implement Y" / "refactor W" request is clearly multi-layer and large in scope. Do NOT use for small or moderate changes: bug fixes, tweaks, config changes, single-file or single-layer changes, or anything reviewable in one sitting belongs on ONE branch as ONE change — creating a stack of tiny branches for these adds overhead without value.
---

# Stacked

Decompose work into a stack of small, dependent, reviewable changes. Each change has a single responsibility and builds on the one below it.

---

## When to Use

Stack only when **all** of these hold:

- The change is large — too big to review comfortably as a single unit
- It spans multiple architectural layers with **functionally distinct** concerns
- Each layer would carry substantial, self-contained work worth its own review

## When NOT to Use

Default to a **single branch, single change** for:

- Bug fixes, tweaks, styling adjustments, config or copy changes
- Single-file or single-layer changes, however "multi-step" the edit feels
- Small features a reviewer can absorb in one sitting
- Related small changes — batch them into one coherent change rather than one branch each

A stack of tiny branches is worse than one clear change: it multiplies review, CI, and merge overhead without improving reviewability. The size of the change decides, not the number of steps it took to write.

---

## Core Principle

Prefer a stack of small changes over one massive change — and prefer one plain change over an unnecessary stack. Stacking is a tool for taming size, not a default workflow.

```
Small Change   ← top (depends on everything below)
    ↑
Small Change
    ↑
Small Change
    ↑
Small Change   ← bottom (no dependencies)
```

Implement from the **bottom up**. Review from the **bottom up**.

---

## Decomposition Strategy

Before writing any code:

1. Understand the complete scope
2. Identify architectural boundaries
3. Separate concerns
4. Build a proposed stack
5. Validate each layer has a single responsibility

Think in terms of:

- **Data structures** — types, models, schemas
- **Persistence** — storage, migrations, indexes
- **Domain logic** — business rules, transformations
- **Tools / Services** — utilities, clients, adapters
- **Workflows** — orchestration, pipelines, agents
- **API** — interfaces, contracts, endpoints
- **UI** — presentation, interaction

Not every feature requires every layer.

---

## Preferred Layering Order

```
Types / Models
      ↓
  Persistence
      ↓
 Domain Logic
      ↓
Tools / Services
      ↓
  Workflows
      ↓
     API
      ↓
      UI
```

Higher layers depend on lower layers. Lower layers must not depend on higher layers.

---

## Naming

Name each change by **capability and responsibility** — not sequence.

**Good:**
```
search/indexing
search/retrieval
search/ranking
search/api

doc-parser/core
doc-parser/chunking
doc-parser/indexing
doc-parser/workflow

chat/session-model
chat/history-store
chat/context-builder
chat/agent
```

**Avoid:**
```
part-1
part-2
final
misc
changes
```

Names should explain what a change does without requiring additional context.

---

## Reviewability Rule

Each change should answer **a single question**:

> Does [this specific thing] look correct?

Examples:
- "Does the indexing model look correct?"
- "Does the retrieval implementation look correct?"
- "Does the workflow orchestration look correct?"

If a reviewer must answer multiple unrelated questions, the change is too large. Split it.

---

## Agent Behavior

1. **Plan the full stack first** — propose it before writing any code
2. **Explain the proposed stack** — show names, dependencies, and responsibilities
3. **Implement bottom-up** — start with the lowest-dependency layer
4. **Keep responsibilities isolated** — no mixing of architectural layers within a change
5. **Avoid unrelated refactors** — scope each change tightly
6. **Prefer incremental progress** — don't bundle work to seem efficient
7. **Write into the manifest** — when a manifest exists for this task (`tasks/<slug>/manifest.md`), write the stack into its `## Stack` section rather than presenting it only in chat. The manifest is the canonical record; chat is ephemeral. Update layer `Status` cells as PRs open and merge.

When uncertain whether the change is big enough to warrant a stack: **don't stack it — ship it as one change.** Only once you're inside a genuinely large stack and uncertain whether a layer is doing two jobs: split that layer.

Sizing floor: never create a layer that a reviewer would read in under a couple of minutes and think "why is this its own PR?" Merge such fragments into the adjacent layer they belong to.

---

## Output Format

When proposing a stack, present it clearly:

```
feature-name/layer-one       ← implement first
      ↑
feature-name/layer-two
      ↑
feature-name/layer-three
      ↑
feature-name/layer-four      ← implement last
```

For each layer, briefly state:
- **What it does** (one sentence)
- **What it depends on** (prior layers, if any)
- **Why it's its own change** (the single reviewable question)

---

## Example

**User request:** Build a document intelligence pipeline that can parse, chunk, index, and search documents.

**Proposed stack:**

```
doc-intelligence/models          ← types and schemas
        ↑
doc-intelligence/parser          ← raw document ingestion
        ↑
doc-intelligence/chunking        ← splitting and segmentation logic
        ↑
doc-intelligence/indexing        ← storage and index construction
        ↑
doc-intelligence/search          ← retrieval and ranking
        ↑
doc-intelligence/workflow        ← end-to-end orchestration
```

Each layer has one job. Each layer can be reviewed independently. The story is clear from bottom to top.

---

## Success Criteria

A stack is successful when:

- Each change has one responsibility
- Dependencies are obvious from the names and order
- Changes are independently reviewable
- The implementation story is clear from bottom to top
- Testing can happen incrementally
- Merging can happen incrementally
- A reviewer can understand the full stack without confusion

---

## Worked example (in `examples/`)

`examples/notifications-system.md` is a worked example showing how a **complex** feature — an in-app notifications system spanning schema, storage, delivery, API, and UI — decomposes into one tight bottom-up stack. Only the Stack section is shown: each layer's responsibility, its dependency on the layer below, the single reviewable question it answers, and its status. Note how even a large, multi-concern feature reduces to a short ladder where each layer is independently reviewable and nothing above can be built until the layer below it is tested.
