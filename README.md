# Hub

One browsable page linking every `.md` / `.html` file under a scan root
(default `~/tifin`) — grouped by repo, sorted by most-recently-modified, with
split-pane preview, full-text search, and task lineage tracing.

## Open

```
http://localhost:8787/
```

## Quick start

```bash
# Start the server (auto-starts at login via launchd)
python3 ~/agents/hub/server.py

# Manual rebuild
python3 ~/agents/hub/hub.py

# Rebuild with debug logging
HUB_DEBUG=1 python3 ~/agents/hub/hub.py
```

The server watches the scan root and rebuilds automatically on file changes (~3s).
Click **↻ rebuild hub** in the header for an immediate rebuild.

## File structure

```
hub/
├── hub.py              entry point — scan, DB update, render
├── server.py           HTTP server — renders .md, file watcher, rebuild endpoints
├── db.py               SQLite layer — schema, upsert, lineage, FTS export
├── metadata.py         metadata extraction — title and body from markdown/html
├── assets/
│   └── favicon.svg     tab icon
├── templates/
│   └── template.html   HTML/CSS/JS template filled by render()
├── data/               generated — do not edit directly
│   ├── hub.db          SQLite database
│   └── docs-index.html generated hub page
├── README.md
└── CLAUDE.md
```

Hidden files:
- `.scan_root` — active scan root path (written by the "Save & Rebuild" modal)
- `.hub.log` — debug log (only written when `HUB_DEBUG=1`)

## Features

### Split-pane preview
Click any row to open a full-height preview pane (40% width). Every file is
rendered via the server — full markdown, HTML, or plain text — with the hub's
theme. The pane scrolls independently.

Press `Enter` or click **Open** to open the file in a new tab. Press `Esc` to close.

### Search
Implicit AND across repo name, path, title, and body text.

| Query | Finds |
|-------|-------|
| `entity extraction` | files containing both words |
| `fix artifact` | artifacts from fix-* tasks |
| `repo:ai task` | tasks in ai-chatbot |
| `repo:co prompts` | prompts in cortex |

### Kind & repo chips
Sticky filter chips at the top. Multi-select repos. All filters stack as AND.

### Task lineage trace
Files under `tasks/<slug>/` show a **// trace** panel:
- **TASK** manifest → lists all runs, artifacts, prompts, docs.
- **RUN / ARTIFACT / PROMPT** → `↑ task` back-link + siblings.

```
{repo}/tasks/{slug}/
    ├── manifest.md        ← TASK
    ├── runs/YYYY-MM-DD/   ← RUN
    ├── artifacts/         ← ARTIFACT
    └── prompts/           ← PROMPT
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `j` / `↓` | Next file |
| `k` / `↑` | Previous file |
| `Enter` | Open file in new tab |
| `Esc` | Close preview |
| `/` | Focus search |

## Changing the scan root

Click the scan-root path in the header → edit the directory → **Save & Rebuild**.
The server writes `.scan_root`, rebuilds, and reloads the page automatically.

Priority: `HUB_SCAN_ROOT` env var → `.scan_root` sidecar → `~/tifin` default.

## Configuration

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_SCAN_ROOT` | `~/tifin` | Root directory to scan |
| `HUB_SERVER_PORT` | `8787` | Port for `server.py` |
| `HUB_OUTPUT` | `data/docs-index.html` | Output HTML path |
| `HUB_DB` | `data/hub.db` | SQLite database path |
| `HUB_FAVICON` | `assets/favicon.svg` | Tab icon |
| `HUB_DEBUG` | off | `1` enables logging to `.hub.log` |

## launchd agents

Two agents start at login:

| Label | Script | Behaviour |
|-------|--------|-----------|
| `com.user.hub` | `hub.py` | Rebuilds index every 120 s |
| `com.user.hub-server` | `server.py` | HTTP server, KeepAlive |

```bash
# Reload after plist or script changes
launchctl kickstart -k gui/$(id -u)/com.user.hub
launchctl kickstart -k gui/$(id -u)/com.user.hub-server
```

## Server endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve `data/docs-index.html` |
| `/<abs-path>` | GET | Render file (markdown → HTML, others static) |
| `/<rel-path>` | GET | Same, resolved relative to active scan root |
| `/_rebuild` | GET | Trigger immediate rebuild |
| `/_set-root` | POST | Body = new path. Write `.scan_root`, rebuild |
