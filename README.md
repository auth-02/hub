# Hub

![Hub — Every .md & .html, one page](assets/screenshots/banner.png)

**Every `.md` and `.html` in your projects — one searchable, previewable page.**

Hub scans a directory tree, indexes every document into SQLite with full-text search and task lineage, and serves a fast local browser at `http://localhost:8787`. No npm. No framework. Pure stdlib Python.

---

## Screenshots

### Index — grouped by repo, filtered by kind, sorted by recency

![Hub index with status badges and kind filters](assets/screenshots/index.png)

### Split-pane preview with task trace
Click any row to open a live preview. The `// trace` panel links to related runs, artifacts, and the parent task.

![Split-pane preview](assets/screenshots/preview.png)

### Markdown document page
Every file opens in a clean reading view with a `// trace` bar below the heading.

![Markdown document page](assets/screenshots/doc.png)

### HTML document page
HTML artifacts are served as-is with the `// trace` bar injected automatically.

![HTML artifact page with trace bar](assets/screenshots/doc-html.png)

---

## Features

- **Full-text search** — filter by repo, path, title, and body simultaneously. Implicit AND, `repo:name` prefix supported.
- **Kind chips** — one-click filters for TASK, RUN, ARTIFACT, CLAUDE, README, DOC, PROMPT. Stack with repo chips and search.
- **Task status badges** — every task manifest shows a clickable status pill. Cycles `ongoing → completed → paused`, persisted to SQLite without a rebuild.
- **Split-pane preview** — click any row for a live rendered preview with lineage trace. No page navigation.
- **Backlinked doc pages** — open any file in its own tab and the `// trace` bar appears below the heading, linking to all related files in both directions. Works for `.md` and `.html`.
- **Auto-rebuild** — file watcher triggers a rebuild within ~3s of any change in the scan root.
- **Keyboard-first** — navigate the full list without a mouse.

---

## Quick start

```bash
# Start the server (auto-starts at login via launchd)
python3 ~/agents/hub/server.py

# Rebuild the index
HUB_SERVER_PORT=8787 python3 ~/agents/hub/hub.py

# Open
open http://localhost:8787/
```

Two launchd agents keep everything running at login:

| Agent | Behaviour |
|-------|-----------|
| `com.user.hub-server` | HTTP server + file watcher. KeepAlive. |
| `com.user.hub` | Rebuilds index every 120s. |

```bash
# Reload after code changes
launchctl kickstart -k gui/$(id -u)/com.user.hub-server
launchctl kickstart -k gui/$(id -u)/com.user.hub
```

---

## Task structure

Hub understands this layout and builds a lineage graph automatically:

```
{repo}/tasks/{slug}/
    ├── manifest.md        ← TASK  (links to all below)
    ├── runs/YYYY-MM-DD/   ← RUN   (↑ back-link to manifest)
    ├── artifacts/         ← ARTIFACT
    └── prompts/           ← PROMPT
```

---

## Search

| Query | Finds |
|-------|-------|
| `session tokens` | files whose title or body contains both words |
| `repo:tasks manifest` | manifests in the tasks repo |
| `auth artifact` | artifacts from auth-* tasks |
| `repo:docs architecture` | docs matching "architecture" |

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search |
| `j` / `↓` | Next file |
| `k` / `↑` | Previous file |
| `Enter` | Open in new tab |
| `Esc` | Close preview |

---

## Changing the scan root

Click the scan-root path in the header → edit → **Save & Rebuild**. The server writes `.scan_root`, rebuilds, and reloads automatically.

Priority: `HUB_SCAN_ROOT` env var → `.scan_root` sidecar → `~/tifin` default.

---

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_SCAN_ROOT` | `~/tifin` | Directory to scan |
| `HUB_SERVER_PORT` | `8787` | Server port |
| `HUB_OUTPUT` | `data/docs-index.html` | Output HTML path |
| `HUB_DB` | `data/hub.db` | SQLite database |
| `HUB_DEBUG` | off | `1` enables logging to `.hub.log` |

---

## File structure

```
hub/
├── hub.py              scan, index, render
├── server.py           HTTP server · markdown renderer · file watcher
├── db.py               SQLite — files, lineage, FTS5, task_status
├── metadata.py         title + body extraction
├── templates/
│   └── template.html   single-file HTML/CSS/JS template
├── assets/
│   ├── favicon.svg
│   └── screenshots/
└── data/               generated — do not edit
    ├── hub.db
    └── docs-index.html
```
