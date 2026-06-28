# <Feature / Task Title>

## Context
<one-paragraph paraphrase of the ask, plus any business or technical background. Not the plan — the problem.>

### Decisions
1. <decision> — captured <date or "from session">.

## Exploration Results
_(populate after grep / read / probe — `file:line` cross-links for every claim)_

### Consumers / callers

### Data shape / schema

### Related subsystems

### Out of scope

### Not found

## Stack
_(skip for single-layer or single-PR changes — populate whenever the task spans 2+ architectural layers)_

```
<feature>/layer-one       ← implement first
      ↑
<feature>/layer-two
      ↑
<feature>/layer-three     ← implement last
```

| Layer | What it does | Depends on | Reviewable question | Status |
|-------|-------------|------------|---------------------|--------|
| `<feature>/layer-one` | … | — | Does X look correct? | open |
| `<feature>/layer-two` | … | layer-one | Does Y look correct? | open |

## Plan
_(when a Stack exists, organize steps under each layer as a heading)_

- [ ] **Step 1 — <name>** `<path/to/file>`
  - What to change
  - Why / what it unblocks

## Open questions
1.

## Confirmed findings
_(fill after running exploration probes — distinguish "assumed" from "confirmed"; ⚠️ for surprises that invalidate the plan)_

## Testing plan
_(parity baselines, canary, fallback tests, scheduled runs, exit gate)_

## Rollout plan
_(stages, rollback procedure, coordination notes, gotchas)_

## Review
_(fill at end: files changed with one-line summaries, how to cut over, follow-ups, out-of-scope items)_
