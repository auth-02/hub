---
name: stacked
description: >
  Decompose large, complex, or risky changes into a stack of small, dependent, independently reviewable units. Use this skill whenever a user asks to implement a feature, refactor, pipeline, system, or workflow that spans multiple architectural layers — or whenever the resulting change would be hard to review as a single unit. Trigger on requests like "build X", "implement Y", "add Z to my system", "refactor W", especially when the task touches models, storage, business logic, tools, workflows, API, or UI in combination. Also trigger when the user says "stacked", "stacked PRs", "stacked diffs", "stack this", or asks how to break down a large change. If the task is non-trivial and involves more than one concern, use this skill — even if the user didn't explicitly ask for a stack.
---

# Stacked

Decompose work into a stack of small, dependent, reviewable changes. Each change has a single responsibility and builds on the one below it.

---

## When to Use

- A feature spans multiple architectural layers
- The implementation requires several logical steps
- The resulting change would be difficult to review
- Multiple concerns are modified simultaneously
- The implementation can be delivered incrementally

Do not use for trivial or isolated changes.

---

## Core Principle

Prefer a stack of small changes over one massive change.

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

When uncertain whether to split a change: **split it.**

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
