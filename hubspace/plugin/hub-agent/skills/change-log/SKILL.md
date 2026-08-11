---
name: change-log
description: Draw a task's changes as a high-level connected wireframe on Hub's draw canvas — change-units as nodes, dependencies as arrows, so a reviewer *sees* what moved and how it hangs together (no code). Use when someone asks "what changed", "map this change", "diagram this PR/branch", "show how the changes connect", or as the closing step of a task once code has landed. Reads the diff + the task's manifest (the *why*) + Hub's MCP task context, then writes ONE `.excalidraw` scene into `tasks/<slug>/draws/`. The agent does the reading — Hub has no model. `/change-log <task-slug> [--since <ref>] [--doc]`.
---

# change-log — the agent reads the diff, Hub draws the result as a map

The point of a change-log here is **a picture, not prose**: a connected wireframe
on the draw canvas Hub already has, where each **node is a unit of change** (an
area/module/feature that moved) and each **arrow is a dependency** ("depends on"
/ "feeds" / "calls"). A reviewer glances at it and *sees* the shape of the change
— what's new, what changed, and how the pieces hang together — without reading a
line of code. (Inspired by workflow-map tools like HQFlow: the agent authors the
graph, the canvas renders it.)

Reading a diff and deciding what the *units of change* are is the one job Hub
cannot do. Hub has no model, no network, no API key — that is the whole point. So
change-log is **a skill your agent runs**: you read the diff, gather the task's
context, reason out the change-graph, and drop ONE `.excalidraw` scene into the
task's `draws/`. From Hub's side nothing is special — a file appeared, the watcher
indexed it, it has lineage, it opens in the draw canvas and is hand-annotatable.
*Hub stays a consumer even when the thing it consumes is intelligence.*

```
/change-log <task-slug> [--since <ref>] [--doc]
```

- `<task-slug>` — the task whose work you are mapping (its folder under `tasks/`).
- `--since <ref>` — git ref to diff from (branch, tag, or commit). Default: the
  merge-base with `main` (`git merge-base main HEAD`), i.e. everything on this branch.
- `--doc` — ALSO write the prose HTML changelog (`templates/change-log.html`) into
  `artifacts/`. The diagram is always the primary deliverable; `--doc` adds the
  companion write-up when someone wants a shareable narrative too.

## Step 1 — read three sources (this is the work)

You are the only thing here that can read a diff. Gather:

1. **What changed** — the diff:
   ```bash
   git diff <since>..HEAD            # <since> defaults to $(git merge-base main HEAD)
   git diff --stat <since>..HEAD     # the files-touched table + rough sizes
   ```
2. **Why it changed** — the task's manifest, `tasks/<slug>/manifest.md`. The
   *Decisions* and *Plan* sections are where the one-line "why" for each change
   comes from. A diff says *what*; the manifest says *why*. Use both.
3. **The task's shape** — Hub's MCP read tools (from `hub mcp serve`):
   - `get_task(slug)` → status, plan, decisions, lineage counts.
   - `trace(path)` → the lineage around a file.

   **If MCP is not running, fall back** to reading the files directly:
   ```bash
   cat tasks/<slug>/manifest.md
   hub timeline <slug> --json        # the task's evolution spine
   ```

Never invent a "why". If the manifest does not explain a change, leave that
node's note blank rather than guessing.

## Step 2 — reason out the change-graph (nodes + edges)

This is the judgement call, and it is yours. Collapse the raw diff into a handful
of **high-level change-units** — NOT one node per file. A unit is a coherent thing
that changed: "delete-comment endpoint", "notes store", "trace + doc-page UI",
"z-index layering". Aim for **5–12 nodes**; if you have more, you are mapping code,
not the change. Then draw the **dependency arrows** between them ("A calls B",
"B feeds A"), the same success-path a reviewer would trace to understand the PR.

Each node is:

```json
{ "id": "n1",                       // short unique id
  "kind": "task",                   // category → colour + top label (see palette)
  "path": "delete-comment endpoint",// the human label (short noun phrase)
  "at": "new" }                     // the change verb: new | changed | rewritten | removed
```

Each edge is `{ "from": "<id>", "to": "<id>" }` — an arrow *from* the dependent
*to* what it depends on.

**Kind → colour** (reuse Hub's palette so the map reads in the workspace; any
other kind renders neutral grey, which is fine for a wireframe):
`task` oxblood · `artifact` violet · `script` slate · `doc` deep-sea ·
`data` teal · `run` green · `draw` amber · `note` rust · `prompt` gold.
Pick the kind that best fits each change-unit (e.g. an endpoint/feature → `task`,
a helper/module → `script`, a UI/asset → `artifact`, a spec/doc → `doc`).

## Step 3 — render the scene into `draws/`

Hand your nodes/edges to Hub's **deterministic** layout+Excalidraw emitter
(`hubspace.core.graph.to_excalidraw`) — it does the geometry (kind columns,
bound labels, arrows on paper ground), no model involved. Write ONE file:

```
tasks/<slug>/draws/change-log-<YYYY-MM-DD>.excalidraw
```

```bash
python3 - <<'PY'
import json
from hubspace.core import graph
nodes = [
  {"id":"n1","kind":"task","path":"delete-comment endpoint","at":"new"},
  {"id":"n2","kind":"script","path":"notes store · delete_note","at":"new"},
  {"id":"n3","kind":"artifact","path":"trace + doc-page ✕ UI","at":"changed"},
]
edges = [ {"from":"n1","to":"n2"}, {"from":"n3","to":"n1"} ]
scene = graph.to_excalidraw(nodes, edges, source="hub-change-log")
open("tasks/<slug>/draws/change-log-<YYYY-MM-DD>.excalidraw","w").write(
    json.dumps(scene, ensure_ascii=False, indent=2))
PY
```

`templates/change-log.excalidraw` next to this skill is the same emitter's output
for the worked example above — open it to see the target shape, or copy it and
hand-edit the labels if you prefer building the scene by hand. Either way the
result is a plain Excalidraw scene (`type:"excalidraw"`, `elements`, paper-ground
`appState`) that opens in Hub's draw canvas and can be annotated.

Keep it **high level**: node labels are short noun phrases, not file paths or
symbols; arrows are dependencies, not call stacks. If a reviewer needs the code,
they open the files — this map is for the *understanding*.

## `--doc` — the optional prose companion

With `--doc`, ALSO copy `templates/change-log.html` and fill it, writing to
`tasks/<slug>/artifacts/change-log-<YYYY-MM-DD>.html`. It carries the Hub design
tokens inline (paper ground `#F4EFE4` + dot-grid, Fraunces/Inter/JetBrains Mono,
oxblood `#7A2828` = change, deep-sea `#1E5A6B` = links) and is **fully
self-contained/offline** (no CDNs/fonts/scripts) so `hub publish` can ship it
as-is. Fill it in this order: **Title** (plain language) → **Summary** (one
paragraph a non-author can read) → **Before → After** (two-column flow) →
**Files touched** (path · change note · one-line *why* from the manifest) →
**Provenance footer**. The diagram is still the headline; the doc is the narrative.

### Front matter — how Hub learns the provenance

Put this at the **very top** of the `--doc` HTML, in an HTML comment so it never
renders but Hub can read it:

```html
<!--
---
generated_by: "claude ▸ skill:change-log"
commit_range: "<short-since>..<short-head>"
written_at: <ISO-8601 timestamp>
task: <slug>
---
-->
<!DOCTYPE html>
…
```

Hub reads exactly these four fields off the file and renders a small line —
`written by <generated_by> · <written_at> · <commit_range>` — plus the note
**"Hub did not generate this file."** The `commit_range` end also seeds the
copy-only **"ask again"** button (`/change-log <slug> --since <end>`). Get the
short hashes with `git rev-parse --short <since>` and `git rev-parse --short HEAD`.

## What this skill must NOT do

- **No model / network / key in Hub.** You (the agent) do the reasoning — reading
  the diff, choosing the change-units and their dependencies. Hub only lays out
  the graph you hand it (deterministic geometry), indexes the file, and reads
  front matter. Do not add generation code to Hub.
- Draw the **change**, not the code — 5–12 high-level nodes, dependency arrows.
  One-node-per-file is the failure mode.
- Write only into `tasks/<slug>/draws/` (and `tasks/<slug>/artifacts/` for `--doc`).
- Do not fabricate a "why" — if the manifest is silent, the node's note stays blank.

## After writing

Mention the path. The watcher indexes it within ~3 s; the `.excalidraw` appears
under its task as a DRAW with full lineage and opens in the draw canvas. To share
the `--doc` HTML, hand off to `hub publish` / the `dak` skill.
