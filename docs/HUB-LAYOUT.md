# Hub Layout Specification

**Layout version:** 1
**Status:** draft

Hub infers all structure from **paths and frontmatter** — never from the tool
that created the files. Any producer that emits this shape gets the full hub
experience: kind classification, lineage trace, board, calendar, feed.

Hub is the **consumer**. Producers — the `hub new` CLI, a coding-agent skill, or
a human with a text editor — are **interchangeable**. This document is the only
coupling between them.

---

## 1. Scan root and repos

Hub scans a single **scan root** (default: the current working directory).

- Each immediate subdirectory of the scan root is a **repo**.
- Files that sit directly in the scan root belong to a pseudo-repo named `(root)`.

```
<scan-root>/
├── README.md            → repo "(root)"
├── cortex/              → repo "cortex"
├── fin/                 → repo "fin"
└── rm-orchestrator/     → repo "rm-orchestrator"
```

Hub only reads `.md` and `.html` files for the index. It always ignores:
`.git/`, `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `build/`, and its
own state directory (see §7).

---

## 2. The task unit

The differentiated structure. A task is a directory under `<repo>/tasks/<slug>/`.

```
<repo>/tasks/<slug>/
├── manifest.md          ← TASK   (required to be a task at all)
├── runs/                (optional, created on demand)
│   └── <YYYY-MM-DD>/
│       └── <name>.md    ← RUN
├── artifacts/           (optional, created on demand)
│   └── <name>.{md,html} ← ARTIFACT
├── draws/               (optional, created on demand)
│   └── <name>.excalidraw ← DRAW
├── comments/            (optional, created on demand)
│   └── <date>-<slug>.md ← NOTE
└── data/                (optional, created on demand)
    └── <name>.{xlsx,csv,json,…}  ← DATA
```

- `<slug>` is `kebab-case`. It is the task's stable id.
- `manifest.md` is what makes the directory a task, and is the **only** thing a
  producer must create. Without it, the directory's files are still indexed but
  show **no trace** (see §6, orphans).
- The `runs/`, `artifacts/`, `draws/`, `comments/`, and `data/` subdirs are
  **optional and created lazily** — only when a file first needs to land in one.
  A fresh task is
  just its `manifest.md`; empty scaffolding directories are noise. Producers must
  not pre-create them.
- `runs/` is partitioned by ISO date directories. The run's date comes from the
  directory name, not the file.
- `artifacts/`, `draws/`, and `data/` are flat (one level). Names are free.
- `draws/` is the conventional home for a task's `.excalidraw` canvases. Unlike
  the other subdirs, DRAW is resolved by extension, not by this path (§3), so a
  `.excalidraw` file anywhere is still a DRAW — `draws/` is where the UI's *New
  draw* action and the `hub draw` verb put one when scoped to a task.
- `comments/` holds **notes** — one markdown file per note, `<date>-<slug>.md`,
  flat and created on demand. Each note carries a small front-matter anchor
  (`target:` — the task-relative file it is about, may be `manifest.md`; optional
  `range:` line range) followed by the note body. A note is a real, diffable,
  git-tracked file at a predictable path — untouched by `rm hub.db`. Written by
  `hub note <path>` or the "New note" palette row; hub never scaffolds it.

> **`prompts/` is not part of the task unit.** The PROMPT kind (§3) is owned by
> any pre-existing `prompts/` folder a repo or task already keeps for its own
> reasons — it is *not* scaffolded by `hub new`, not created lazily by hub, and
> carries no required attachment to a manifest. Hub simply classifies whatever
> is already there.

---

## 3. Kind resolution

Kind is derived purely from path. First match wins, top to bottom:

| Path pattern                              | Kind     |
| ----------------------------------------- | -------- |
| `**/*.excalidraw` (by extension, any dir) | DRAW     |
| `**/CLAUDE.md`                            | CLAUDE   |
| `**/README.md`                            | README   |
| `<repo>/tasks/<slug>/manifest.md`         | TASK     |
| `<repo>/tasks/<slug>/runs/**`             | RUN      |
| `<repo>/tasks/<slug>/artifacts/**`        | ARTIFACT |
| `<repo>/tasks/<slug>/prompts/**`          | PROMPT   |
| `<repo>/tasks/<slug>/data/**`             | DATA     |
| `<repo>/tasks/<slug>/comments/**`         | NOTE     |
| `<repo>/docs/**.md`                       | DOC      |
| any other `.md` / `.html`                 | MD       |

`DRAW` is resolved by the `.excalidraw` extension and so matches first, before
any name- or path-based rule — an Excalidraw canvas is a DRAW wherever it lives
(its conventional home is a task's `draws/`, §2). `MD` is the catch-all and is
never an error — a repo of loose notes is a valid, fully searchable hub.

PROMPT is recognized only where a `prompts/` folder already exists; nothing in
hub or `hub new` creates one (see §2).

---

## 4. Frontmatter

YAML frontmatter is **optional everywhere**. Hub degrades to sensible defaults.

### 4.1 Manifest (TASK)

```yaml
---
status: ongoing        # ongoing | paused | completed
title: Auth Refactor   # optional; see title resolution below
created: 2026-05-28    # optional, ISO 8601 date
updated: 2026-06-01    # optional; falls back to file mtime
tags: [auth, security] # optional
---
```

- `status` is the **only field that affects the board.** Allowed values:
  `ongoing`, `paused`, `completed`. If absent or unrecognized, the task is
  treated as `ongoing` so it is never dropped — but explicit status is
  recommended.
- A `plan` checklist in the body (`- [x]` / `- [ ]`) is parsed for the progress
  shown in the trace panel. It is convention, not required.

### 4.2 Runs / artifacts / prompts / docs

All optional:

```yaml
---
title: 3y XIRR benchmark   # optional
created: 2026-05-28        # optional
---
```

### 4.3 Title resolution (all kinds)

1. `title:` in frontmatter, else
2. first level-1 heading (`# …`) in the body, else
3. the file/slug name, prettified.

---

## 5. Time and status semantics

These drive the calendar, feed, and "what did I work on" timeline. All derived,
no extra files:

- **A file's timestamp** = `updated` frontmatter, else filesystem mtime.
- **A run's date** = its `runs/<YYYY-MM-DD>/` directory.
- **A task's activity** = the most recent timestamp among its manifest, runs,
  artifacts, prompts, and data.
- **Feed / timeline** are reverse-chronological views over those timestamps;
  they store nothing.

---

## 6. Trace (lineage)

For any file under `tasks/<slug>/`, hub builds the trace from the directory, not
from links inside the files:

- A **TASK** manifest links down to every run, artifact, prompt, and data file
  in its directory.
- A **RUN / ARTIFACT / PROMPT / DATA** links up to its manifest (`↑ task`) and
  across to its siblings.
- **Orphans:** a `runs/`, `artifacts/`, etc. directory with no sibling
  `manifest.md` is shown under the slug with a `no manifest` marker. Never an
  error.

---

## 7. Graceful degradation (the portability contract)

Hub must be useful on a repo that knows nothing about this spec. Required
behavior:

| Repo state                                   | Hub behavior                                   |
| -------------------------------------------- | ---------------------------------------------- |
| No `tasks/` anywhere                         | Flat searchable index grouped by repo/dir.     |
| `tasks/` exists, no `status` frontmatter     | All tasks land in `ongoing`; board still works.|
| Board view, no statuses present at all       | Show empty-state hint, not three blank columns.|
| Manifest missing, runs/artifacts present     | Orphan trace (§6).                             |
| Zero `.md`/`.html` under scan root           | First-run screen explaining what hub looks for.|

No view may render blank or broken because structure is absent.

---

## 8. Versioning

A repo may declare the layout version it targets:

```toml
# hub.toml (optional, at scan root)
layout = 1
```

If absent, hub assumes the latest version it understands. Hub reads any layout
version `<=` its own and warns (does not fail) on a newer one.

---

## 9. Reserved names

Producers must not use these for content; hub owns or ignores them:

- `hub.toml`, `.scan_root`, `.hub.log` — hub config/state.
- The hub state directory (`$XDG_STATE_HOME/hub` or `~/.local/state/hub`) — never
  inside the scan root.
- `manifest.md`, `runs/`, `artifacts/`, `draws/`, `prompts/`, `data/`,
  `comments/` — structural, as defined above. (`prompts/` is reserved when
  present, but never created by hub; `comments/` is created on demand by
  `hub note`.)

---

## Appendix — minimal valid task

What `hub new task auth-refactor` emits, and the smallest thing your skill (or a
human) must write to light up the full experience — just the manifest:

```
cortex/tasks/auth-refactor/
└── manifest.md          # ---\nstatus: ongoing\ntitle: Auth Refactor\n---\n# Auth Refactor\n
```

`runs/`, `artifacts/`, and `data/` appear later, each created on demand by the
first file written into it.

To pre-create subdirs (or add them to an existing task later), pass `--with`:

```
hub new task auth-refactor --with all          # runs/ artifacts/ data/
hub new task auth-refactor --with runs --with data
hub new task auth-refactor --with artifacts    # re-run on an existing task → adds artifacts/
```

`--with` is repeatable, `all` expands to `runs,artifacts,data`, and re-running is
idempotent. `prompts/` is deliberately not accepted (§2).
