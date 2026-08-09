---
name: changelog
description: Turn a task's git diff into a human-readable changelog artifact that lands in the workspace. Use when someone asks "what changed", "write a changelog", "summarize this task's diff", "explain what this PR/branch did", or as the closing step of a task once code has landed. Reads the diff + the task's manifest (the *why*) + Hub's MCP task context, then writes ONE self-contained file into `tasks/<slug>/artifacts/`. The agent does the reading — Hub has no model. `/changelog <task-slug> [--since <ref>] [--canvas]`.
---

# changelog — the agent reads the diff, Hub reads the result

Reading a diff is the one job Hub cannot do. Hub has no model, no network, and no
API key — that is the whole point. So a changelog is **a skill your agent runs**,
not a Hub feature. You read the diff, gather the task's context, and drop ONE
self-contained file into the task's `artifacts/`. From Hub's side nothing is
special: a file appeared, the watcher indexed it, it has lineage. Hub adds only a
**provenance line** (read from the file's own front matter) and a copy-only
**"ask again"** button. *Hub stays a consumer even when the thing it consumes is
intelligence.*

```
/changelog <task-slug> [--since <ref>] [--canvas]
```

- `<task-slug>` — the task whose work you are summarizing (its folder under `tasks/`).
- `--since <ref>` — git ref to diff from (branch, tag, or commit). Default: the
  merge-base with `main` (`git merge-base main HEAD`), i.e. everything on this branch.
- `--canvas` — write an `.excalidraw` into `draws/` instead of an `.html` into
  `artifacts/` (same content, a container you can hand-annotate).

## Step 1 — read three sources (this is the work)

You are the only thing here that can read a diff. Gather:

1. **What changed** — the diff:
   ```bash
   git diff <since>..HEAD            # <since> defaults to $(git merge-base main HEAD)
   git diff --stat <since>..HEAD     # the files-touched table comes from here
   ```
2. **Why it changed** — the task's manifest, `tasks/<slug>/manifest.md`. The
   *Decisions* and *Plan* sections are where the one-line "why" for each file
   comes from. A diff says *what*; the manifest says *why*. Use both.
3. **The task's shape** — Hub's MCP read tools (from `hub mcp serve`):
   - `get_task(slug)` → status, plan, decisions, lineage counts.
   - `trace(path)` → the lineage around a file.

   **If MCP is not running, fall back** to reading the files directly:
   ```bash
   cat tasks/<slug>/manifest.md
   hub timeline <slug> --json        # the task's evolution spine
   ```

Never invent a "why". If the manifest does not explain a change, say so plainly
rather than guessing.

## Step 2 — write ONE self-contained file

Copy `templates/changelog.html` (shipped next to this skill) and fill its
placeholders. It carries the **Hub design tokens inline** so the artifact lands
looking like the workspace, not a generic white sheet:

- paper ground `#F4EFE4`, faint dot-grid — **never** a plain white background
- **Fraunces** display, **Inter** body, **JetBrains Mono** for metadata
- **oxblood `#7A2828`** = authoring/change; **deep-sea `#1E5A6B`** = navigation/links

Write it to:

```
tasks/<slug>/artifacts/changelog-<YYYY-MM-DD>.html
```

The file must be **fully self-contained and offline** — no external hosts, CDNs,
fonts, or scripts (fall back to system fonts via the stack already in the
template). This is what lets `hub publish` (1f) ship it as-is.

### Front matter — how Hub learns the provenance

Put this block at the **very top of the file**, wrapped in an HTML comment so it
never renders in the browser but Hub can still read it:

```html
<!--
---
generated_by: "claude ▸ skill:changelog"
commit_range: "<short-since>..<short-head>"
written_at: <ISO-8601 timestamp>
task: <slug>
---
-->
<!DOCTYPE html>
…
```

Hub reads exactly these four fields off the file itself and renders a small line
on the artifact page — `written by <generated_by> · <written_at> · <commit_range>`
— plus the note **"Hub did not generate this file."** The `commit_range` end also
seeds the copy-only **"ask again"** button (`/changelog <slug> --since <end>`).
Get the short hashes with `git rev-parse --short <since>` and `git rev-parse --short HEAD`.

### Content shape (from the comp)

Fill the template in this order — model it on the comp's *"Refresh tokens stopped
being reusable"* example:

1. **Title** — one line naming the change in plain language (not the branch name).
2. **Summary** — one paragraph a non-author can read: what changed and why it
   matters. No jargon dump.
3. **Before → After** — a two-column flow: the old behavior/shape on the left,
   the new one on the right.
4. **Files touched** — a table: `path` · a change note (`rewritten` / `+N lines` /
   `+N cases`) · a one-line *why* **drawn from the manifest's decisions**.
5. **Provenance footer** — visible line restating "Hub did not generate this
   file." plus the commit range and timestamp (mirrors the front matter).

Keep the footer's claim honest: the file is the agent's work; Hub only indexes
and displays it.

## `--canvas` variant

With `--canvas`, write the same content to
`tasks/<slug>/draws/<name>.excalidraw` instead — an Excalidraw scene the reviewer
can open in Hub's draw canvas and annotate by hand. Lay the same sections out as
text/rectangle elements. The default `.html` remains the publishable deliverable.

## What this skill must NOT do

- **No model / network / key in Hub.** You (the agent) do the reasoning; Hub only
  reads front matter and copies a string. Do not add generation code to Hub.
- Do not write anywhere but `tasks/<slug>/artifacts/` (or `draws/` for `--canvas`).
- Do not fabricate decisions — if the manifest is silent, the changelog says so.

## After writing

Mention the path. The watcher indexes it within ~3 s; it appears in the board
with full lineage under its task, showing the provenance line. To share it, hand
off to `hub publish` / the `dak` skill.
