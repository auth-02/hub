![Hub — Every .md & .html, one page](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/banner.png)

<div align="center">

# Hub

**Point it at a folder. Get every `.md` and `.html` inside as one searchable, previewable page.**

[![PyPI](https://img.shields.io/pypi/v/hubspaces?cacheSeconds=600)](https://pypi.org/project/hubspaces/)
[![Python](https://img.shields.io/pypi/pyversions/hubspaces?cacheSeconds=600)](https://pypi.org/project/hubspaces/)
[![tests](https://github.com/auth-02/hub/actions/workflows/tests.yml/badge.svg)](https://github.com/auth-02/hub/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**[📖 Docs & live demo →](https://auth-02.github.io/hub/)**

</div>

Hub scans a directory tree, indexes every document into SQLite with full-text search and task lineage, and serves a fast local browser at `http://localhost:8787`. No npm. No framework. No runtime dependencies — pure stdlib Python (3.11+).

---

## Install

```bash
pipx install hubspaces       # isolated, recommended
# or
pip install hubspaces
```

From a clone (no publish needed):

```bash
git clone https://github.com/auth-02/hub && cd hub
pipx install .
```

This puts the **`hub`** command on your `PATH`: `hub` builds the index, and `hub serve` serves it and watches for changes.

## Run

```bash
cd ~/my-project        # any folder you want to browse
hub serve              # serves http://localhost:8787 and rebuilds on change
```

Then open <http://localhost:8787>. That's it — Hub indexes the current directory by default.

Want to see it before pointing it at your own files? `hub serve --demo` builds and serves a bundled example repo.

```bash
hub serve --demo
```

---

### Index — grouped by repo, filtered by kind, sorted by recency
Status badges on every task manifest. Click to cycle `ongoing → completed → paused`, saved instantly.

![Hub index](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/index.png)

### Split-pane preview with task trace
Click any row to open a live preview. The `// trace` panel links to related runs, artifacts, and the parent task.

![Split-pane preview](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/preview.png)

### Hub Feed — floating activity drawer
Press `Ctrl+F` or click the `// feed` tab on the right edge. Shows the last 50 file events across the scan root — what changed, which task, when.

![Hub feed drawer](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/feed-drawer.png)

### Hub Timeline — daily work summary
Press `Ctrl+T` or click the `// timeline` tab. Answers *What have I been working on? / yesterday? / this week?* — grouped by task, with git commits, runs logged, artifacts generated, and task status inline.

![Hub timeline drawer](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/timeline.png)

### Markdown & HTML document pages
Every file opened in its own tab gets a clean reading view with a `// trace` bar below the heading. HTML artifacts are served with the hub's own CSS injected.

![Markdown document page](https://raw.githubusercontent.com/auth-02/hub/main/assets/screenshots/doc.png)

---

## Features

- **Full-text search** — filter by repo, path, title, and body simultaneously. Implicit AND, `repo:name` prefix supported.
- **Kind chips** — one-click filters for TASK, RUN, ARTIFACT, CLAUDE, README, DOC, PROMPT. Stack with repo chips and search.
- **Task status badges** — every task manifest shows a clickable status pill. Cycles `ongoing → completed → paused`. Persisted — survives DB resets, scan-root changes, and git branch switches.
- **Split-pane preview** — click any row for a live rendered preview with lineage trace. No page navigation needed.
- **Hub Feed** — floating drawer (`Ctrl+F`) showing recent file activity: what changed, which task, how long ago.
- **Hub Timeline** — drawer (`Ctrl+T`) with a synthesised daily summary grouped by *today / yesterday / this week*, pulling from the activity log + `git log` across all repos.
- **Auto-rebuild** — file watcher triggers a rebuild within ~3 s of any change in the scan root.
- **Keyboard-first** — navigate the full list without a mouse.

---

## Configuration

Everything is optional. Drop a `hub.toml` in the folder you run Hub from (or run `hub init` to scaffold one):

```toml
[hub]
scan_root    = "."                      # directory to index (default: CWD)
port         = 8787                      # local server port
exclude_dirs = ["vendor", "fixtures"]   # extra dirs to skip (added to built-ins)
default_view = "board"                   # work | list | board | calendar | activity
```

Environment variables override the file:

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_SCAN_ROOT` | *(current directory)* | Directory to scan |
| `HUB_SERVER_PORT` | `8787` | Server port |
| `HUB_OUTPUT` | `~/.local/state/hub/build/docs-index.html` | Generated HTML path |
| `HUB_DB` | `~/.local/state/hub/hub.db` | SQLite database |
| `HUB_DEBUG` | off | `1` enables logging to `~/.local/state/hub/hub.log` |

Scan-root priority: `--root` flag → `HUB_SCAN_ROOT` → `hub.toml` → `.scan_root` sidecar → current directory.
You can also change it live: click the scan-root path in the header → edit → **Save & Rebuild**.

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

`hub new task <slug>` scaffolds a valid task for you.

---

## Agent plugin (optional)

Hub is the **viewer**. If you drive work with Claude Code, the companion
`hub-agent` plugin is the **producer** — it bundles the `manifest` skill, which
creates and maintains the `tasks/<slug>/manifest.md` structure above as you
work, so the board, trace, and timeline fill themselves in.

```
/plugin marketplace add auth-02/hub
/plugin install hub-agent@hub
```

Fully opt-in — Hub needs no plugin and no agent to deliver the full
index/search/preview/trace experience.

---

## Search

| Query | Finds |
|-------|-------|
| `session tokens` | files whose title or body contains both words |
| `repo:tasks manifest` | manifests in the tasks repo |
| `repo:docs architecture` | docs matching "architecture" |

## Keyboard shortcuts

| Key | Action | | Key | Action |
|-----|--------|-|-----|--------|
| `/` | Focus search | | `Enter` | Open in new tab |
| `Ctrl+F` | Toggle feed drawer | | `j` / `↓` | Next file |
| `Ctrl+T` | Toggle timeline drawer | | `k` / `↑` | Previous file |
| `Esc` | Close preview / drawer | | | |

---

## Keep it running (macOS)

Two launchd agents start Hub at login — the server (+ watcher) and a periodic rebuild:

```bash
bash scripts/setup-launchd.sh
# custom scan root:
HUB_SCAN_ROOT=~/work bash scripts/setup-launchd.sh
```

Reload after upgrading:
```bash
launchctl kickstart -k gui/$(id -u)/com.user.hub-server
launchctl kickstart -k gui/$(id -u)/com.user.hub
```

---

## Development

```bash
git clone https://github.com/auth-02/hub && cd hub
python3 -m hubspace.cli.hub serve   # run from source, no install
python3 tests/run_tests.py          # stdlib unittest
```

Layout: code is the `hubspace/` package; all generated/writable state (index, DB, log)
lives under `~/.local/state/hub/`, never the package directory.
