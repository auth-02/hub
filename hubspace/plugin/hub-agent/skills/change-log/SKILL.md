---
name: change-log
description: Map a task's changes as an interactive change-map — nodes are functional CHANGES (a capability that moved), arrows are dependencies, and clicking a change deep-dives into its file / function / test detail in a side inspector. Use when someone asks "what changed", "map this change", "diagram this PR/branch", "show how the changes connect", or as the closing step of a task once code has landed. Reads the diff + the task's manifest (the *why*) + Hub's MCP task context, then writes ONE self-contained HTML page into `tasks/<slug>/artifacts/`. The agent does the reading — Hub has no model. `/change-log <task-slug> [--since <ref>] [--canvas] [--doc]`.
---

# change-log — the agent reads the diff, Hub renders an explorable map

The point of a change-log here is **a picture you can interrogate, not prose**:
each **node is a functional change** — a *capability that moved* ("delete a
comment", "publish reach"), NOT a file — and each **arrow is a dependency**
("calls" / "feeds" / "renames"). A reviewer glances at the flow to see the shape
of the change, then **clicks any node to deep-dive** into that change's files,
functions/symbols, and tests in a side inspector. (Modeled on workflow-map tools
like HQFlow: the agent authors the graph, the page renders it + the inspector.)

Reading a diff and deciding what the *functional changes* are is the one job Hub
cannot do. Hub has no model, no network, no API key — that is the whole point. So
change-log is **a skill your agent runs**: you read the diff, gather the task's
context, reason out the change-graph (each node carrying its own deep-dive
detail), and drop ONE self-contained HTML page into the task's `artifacts/`. From
Hub's side nothing is special — a file appeared, the watcher indexed it, it has
lineage, it opens in the workspace. *Hub stays a consumer even when the thing it
consumes is intelligence.*

```
/change-log <task-slug> [--since <ref>] [--canvas] [--doc]
```

- `<task-slug>` — the task whose work you are mapping (its folder under `tasks/`).
- `--since <ref>` — git ref to diff from (branch, tag, or commit). Default: the
  merge-base with `main` (`git merge-base main HEAD`), i.e. everything on this branch.
- `--canvas` — ALSO write an Excalidraw scene (`changelog.to_scene`) into
  `draws/` — the same flow as a hand-annotatable canvas on Hub's draw surface
  (no inspector; static).
- `--doc` — ALSO write the prose HTML write-up (`templates/change-log.html`) into
  `artifacts/` when someone wants a linear narrative.

The **interactive change-map is always the primary deliverable**; `--canvas` and
`--doc` are optional companions.

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
of **functional changes** — NOT one node per file. A node is a *capability that
moved*: "delete a comment", "publish reach", "settings panel". Aim for **5–12
nodes**; if you have more, you are mapping code, not the change. Then draw the
**dependency arrows** between them ("A calls B", "B feeds A") — the path a
reviewer traces to understand the PR.

The file/function/test detail does **not** go in the node — it goes in the
node's **`details`**, surfaced when the reviewer clicks to deep-dive. Node
(change-oriented on top, file-oriented underneath):

```json
{ "id": "endpoint",
  "kind": "task",                       // category → accent colour (see palette)
  "title": "Delete a comment",          // the CHANGE, a short noun phrase
  "verb": "new",                        // new | changed | rewritten | removed
  "summary": "Remove one comment by id, mirroring the add path.",
  "files":     [{"path":"hubspace/cli/server.py","change":"+handler"}],
  "functions": [{"symbol":"_note_delete()","note":"guards + rebuild"}],
  "tests":     ["TestNoteDeleteEndpoint"],
  "note": "mirrors /_note" }
```

`title` + `summary` are what shows on the card; `files` / `functions` / `tests`
/ `note` are the **deep-dive**, shown in the inspector on click. Draw them from
the diff (files/symbols) and the manifest (the *why*); leave a list empty rather
than inventing. Each edge is `{ "from", "to", "rel"? }` — an arrow *from* the
dependent *to* what it depends on; `rel` is a short relationship word drawn on
the arrow.

**Kind → accent colour** (reuse Hub's palette; any other kind renders neutral):
`task` oxblood · `artifact` violet · `script` slate · `doc` deep-sea ·
`data` teal · `run` green · `draw` amber · `note` rust · `prompt` gold.
Pick the kind that fits the change (endpoint/feature → `task`, helper/module →
`script`, UI/asset/page → `artifact`, spec/docs → `doc`).

## Step 3 — render the interactive change-map (the default)

Hand your nodes/edges to Hub's **deterministic** renderer
(`hubspace.core.changemap.render_html`) — it lays out a left→right dependency
flow and emits ONE **self-contained, offline HTML page**: numbered cards with a
left colour-accent bar, curved labelled arrows, a kinds legend, a clean paper
ground (no grid), and a **click-to-deep-dive inspector** (Purpose · Files ·
Functions/symbols · Tests · Note). No model involved — just layout. Write:

```
tasks/<slug>/artifacts/change-log-<YYYY-MM-DD>.html
```

```bash
python3 - <<'PY'
import json
from hubspace.core import changemap
meta = {
  "title": "Change-log — delete a comment", "slug": "<slug>",
  "subtitle": "<short-since>..<short-head> · 2 changes",
  # provenance (an HTML comment Hub reads for the "written by …" line + "ask again"):
  "generated_by": "claude ▸ skill:change-log",
  "commit_range": "<short-since>..<short-head>",
  "written_at": "<ISO-8601 timestamp>",
}
nodes = [
  {"id":"endpoint","kind":"task","title":"Delete a comment","verb":"new",
   "summary":"Remove one comment by id, mirroring the add path.",
   "files":[{"path":"hubspace/cli/server.py","change":"+handler"}],
   "functions":[{"symbol":"_note_delete()","note":"guards + rebuild"}],
   "tests":["TestNoteDeleteEndpoint"],"note":"mirrors /_note"},
  {"id":"store","kind":"script","title":"Notes store","verb":"new",
   "summary":"Byte-preserving line removal from notes.jsonl.",
   "files":[{"path":"hubspace/core/tasks.py","change":"+delete_note"}],
   "functions":[{"symbol":"delete_note()","note":"idempotent"}],
   "tests":["TestDeleteNote"]},
]
edges = [ {"from":"endpoint","to":"store","rel":"calls"} ]
open("tasks/<slug>/artifacts/change-log-<YYYY-MM-DD>.html","w").write(
    changemap.render_html(meta, nodes, edges))
PY
```

The page is fully self-contained (inline CSS+JS, no CDNs/fonts) so `hub publish`
ships it as-is; the provenance front matter (top-of-file HTML comment) lets Hub
show the "written by …" line + copy-only "ask again" button. Get the short
hashes with `git rev-parse --short <since>` and `git rev-parse --short HEAD`.

Keep the **cards** high level (the change, its summary); push files, symbols and
tests into `details` for the deep-dive. A reviewer skims the flow, then clicks in.

## `--canvas` — the Excalidraw companion (optional)

With `--canvas`, ALSO render the same flow as a hand-annotatable Excalidraw scene
via `hubspace.core.changelog.to_scene(nodes, edges, title=…, subtitle=…)` (uses
`path`/`at`/`note` in place of `title`/`verb`/`summary`), writing to
`tasks/<slug>/draws/change-log-<YYYY-MM-DD>.excalidraw`. Same clean paper ground,
numbered accent cards + labelled arrows, but static (no inspector) — it opens in
Hub's draw canvas for hand mark-up. `templates/change-log.excalidraw` is that
emitter's output for the worked example.

## `--doc` — the prose companion (optional)

With `--doc`, ALSO copy `templates/change-log.html` and fill it (Title → Summary
→ Before → After → Files touched → Provenance), writing to
`tasks/<slug>/artifacts/change-log-<YYYY-MM-DD>-notes.html`. A linear narrative
for when someone wants to read rather than explore. Same self-contained/offline
rule so `hub publish` can ship it.

### Provenance — how Hub learns who made it

The interactive map (`changemap.render_html`) emits the provenance front matter
for you from the `meta` `generated_by` / `commit_range` / `written_at` / `slug`
fields (a top-of-file HTML comment). For the `--doc` template, put the same block
at the **very top** by hand:

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

Hub reads those four fields and renders `written by <generated_by> · <written_at>
· <commit_range>` plus **"Hub did not generate this file."**, and seeds the
copy-only **"ask again"** button (`/change-log <slug> --since <end>`).

## What this skill must NOT do

- **No model / network / key in Hub.** You (the agent) do the reasoning — reading
  the diff, choosing the functional changes, their dependencies, and each change's
  file/function/test detail. Hub only lays out the graph you hand it (deterministic)
  , indexes the file, and reads front matter. Do not add generation code to Hub.
- Map the **change**, not the code — 5–12 functional-change nodes; the file/symbol
  detail belongs in each node's `details` (the deep-dive), not as its own node.
  One-node-per-file is the failure mode.
- Write only into `tasks/<slug>/artifacts/` (and `draws/` for `--canvas`).
- Do not fabricate — if the manifest is silent on a "why", leave the note/summary
  spare rather than inventing one.

## After writing

Mention the path. The watcher indexes it within ~3 s; the page appears under its
task with full lineage and opens in the workspace — click a change to deep-dive.
To share it, hand off to `hub publish` / the `dak` skill.
