# Hub — CLAUDE.md

Stdlib-only Python tool that scans a directory tree, extracts metadata into
SQLite, and serves a browsable index via a local HTTP server.

## Run

```bash
python3 server.py                      # start server (port 8787, file watcher included)
HUB_SERVER_PORT=8787 python3 hub.py   # rebuild index
open http://localhost:8787/            # open hub
```

Second `hub.py` run is ~300 ms — mtime-gated, skips unchanged files.

## Run tests

```bash
python3 tests/run_tests.py       # all 128 tests
python3 tests/run_tests.py -v    # verbose output
```

## File map

```
hub/
├── hub.py              entry point — scan, DB update, render
├── server.py           HTTP server — serves index, renders .md, file watcher,
│                       /_rebuild and /_set-root endpoints
├── db.py               SQLite layer — migrations, upsert, lineage, FTS export
├── metadata.py         metadata extraction — title + body from markdown/html
├── migrations/         schema as ordered *.sql files, applied by user_version
│   ├── 001_initial_schema.sql
│   └── 002_skill_columns.sql
├── tests/
│   ├── run_tests.py    test runner entry point
│   ├── test_metadata.py
│   ├── test_db.py
│   ├── test_migrations.py
│   ├── test_hub_helpers.py
│   ├── test_server_helpers.py
│   └── test_server_http.py     integration — spins up real server
├── assets/
│   └── favicon.svg     tab icon
├── templates/
│   └── template.html   HTML/CSS/JS template (str.format()-based)
├── build/               generated — never edit directly
│   └── docs-index.html generated hub page, served at /
~/.hub-state/           persistent state — never delete
│   ├── hub.db          SQLite: files, lineage, fts, activity_log, task_status
│   └── task-status.json sidecar backup of task statuses
├── example/            fixture repos for dev/screenshots
├── .scan_root          active scan root (written by /_set-root)
└── .hub.log            debug log (only when HUB_DEBUG=1)
```

## Architecture

```
server.py
  _HubServer (ThreadingMixIn + TCPServer, dual-stack IPv4+IPv6)
  _watcher() thread        polls scan root every 3 s, triggers hub.py on change
  HubHandler.do_GET()      / → build/docs-index.html
                           /<abs-path> → render file
                           /<rel-path> → resolve vs active scan root, render
                           /_rebuild   → run hub.py subprocess
  HubHandler.do_POST()     /_set-root  → write .scan_root, run hub.py

hub.py:main()
  discover()               → dict[repo_name, list[file_meta]]
  db.open_db()             → sqlite3.Connection
  metadata.read_safe/extract_title/extract_body()
  db.upsert/prune/build_lineage/export_html_data()
  render(groups, fts_json, lineage_json)
    reads templates/template.html
    str.format() with all placeholders
    writes build/docs-index.html
```

## Server endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve `build/docs-index.html` |
| `/<abs-path>` | GET | Render file (markdown → HTML, others static) |
| `/<rel-path>` | GET | Same, resolved relative to active scan root |
| `/_rebuild` | GET | Rebuild index, return `ok` |
| `/_set-root` | POST | Body = new path. Write `.scan_root`, rebuild, return `ok` |

## SQLite schema (`build/hub.db`)

```sql
files     -- abs, repo, rel, ext, kind, mtime, title, body (2000-char), task_slug, task_repo
lineage   -- src_id → dst_id, rel_type:
          --   task_has_run | task_has_artifact | task_has_prompt | task_has_doc | belongs_to_task
fts       -- FTS5 virtual table over files(title, body, repo, rel, kind)
          --   auto-synced via INSERT/UPDATE/DELETE triggers
```

Schema lives in `migrations/*.sql`, not inline in `db.py`. Each file is named
`NNN_description.sql`; `open_db()` runs every migration whose `NNN` exceeds the
DB's `PRAGMA user_version`, then bumps the version — so each runs at most once,
in order. A DB created before migrations existed (user_version 0, schema already
current) is detected and stamped to the latest version without re-running.

**Add a schema change:** drop a new `migrations/NNN_*.sql` (next number) — no
`db.py` edit needed. Never edit an already-applied migration; add a new one.

## Template system (`templates/template.html`)

Uses Python's `str.format()`:
- `{name}` → substituted by `render()`
- `{{` / `}}` → literal `{` / `}` in CSS/JS

Placeholders: `{favicon}`, `{scan_root}`, `{scan_root_json}`, `{sidecar_json}`,
`{hubpy_json}`, `{server_origin_json}`, `{total}`, `{md_total}`, `{html_total}`,
`{repo_count}`, `{built}`, `{body}`, `{repo_chips}`, `{fts_json}`, `{lineage_json}`.

After any template change: `HUB_SERVER_PORT=8787 python3 hub.py` to catch format errors.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_SCAN_ROOT` | `~/tifin` | Root directory to scan |
| `HUB_SERVER_PORT` | *(unset)* | When set, links use `http://localhost:PORT/` |
| `HUB_OUTPUT` | `build/docs-index.html` | Output HTML path |
| `HUB_DB` | `build/hub.db` | SQLite database path |
| `HUB_FAVICON` | `assets/favicon.svg` | Tab icon |
| `HUB_DEBUG` | off | `1` enables logging to `.hub.log` |

## launchd agents

Two agents keep hub running at login. Set them up with the provided script:

```bash
bash scripts/setup-launchd.sh

# Custom scan root:
HUB_SCAN_ROOT=~/work bash scripts/setup-launchd.sh
```

The script writes both plists to `~/Library/LaunchAgents/` and loads them. Re-run it any time you change `HUB_SCAN_ROOT` or move the hub directory.

Reload after code changes (no plist edit needed):
```bash
launchctl kickstart -k gui/$(id -u)/com.user.hub
launchctl kickstart -k gui/$(id -u)/com.user.hub-server
```

## Changing the scan root

- **In browser**: click scan-root path in header → edit → **Save & Rebuild**
- **Via env**: `HUB_SCAN_ROOT=/path HUB_SERVER_PORT=8787 python3 hub.py`
- **Via sidecar**: `echo /path > ~/agents/hub/.scan_root`

Priority: `HUB_SCAN_ROOT` env > `.scan_root` sidecar > `~/tifin` default.

## Common tasks

**Re-index from scratch:**
```bash
rm build/hub.db && HUB_SERVER_PORT=8787 python3 hub.py
```

**Add a new badge/kind:**
1. Add to `KIND_DIRS` in `hub.py`
2. Add `.badge.{kind}` CSS and filter chip in `templates/template.html`
3. Add to `KIND_REL` in `db.build_lineage()` and JS `buildLineage()`

**Add an excluded directory:**
Add to `EXCLUDE_DIRS` in `hub.py` and `_WATCH_EXCLUDE` in `server.py`.

**Add a new indexed extension:**
Add to `EXTS` (always) or `PROMPT_EXTS` (prompts/ only) in `hub.py`.
Update `metadata.extract_body()` if the format needs special stripping.

## Git / PR workflow

- Personal repo on GitHub under `auth-02` (NOT work account). Identity: `name=Atharva`, `email=shindeathrv@gmail.com`.
- **Never push directly to `main`** — branch protection enforces PRs. Always branch → PR → merge.
- Feature work → new branch from `main` → PR into `main`.
- Bug fixes → `fix/<slug>` branch → PR with proof screenshot.
- Always use `GH_TOKEN` from `.git/credentials` when running `gh` CLI.

**Screenshot convention:**
- `assets/screenshots/` — feature screenshots used in README (committed to code branch)
- `screenshots` orphan branch — PR proof images only, never merged to main

**Proof screenshots for PRs — use the `screenshots` branch, not `assets/screenshots/`.**
```bash
git checkout screenshots
cp /tmp/proof.png .
git add proof.png && git commit -m "Add proof for PR #N"
git push origin screenshots
# Reference in PR body:
# ![desc](https://raw.githubusercontent.com/auth-02/hub/screenshots/proof.png)
git checkout main   # switch back when done
```

**After switching to the orphan branch and back, rebuild the index:**
```bash
mkdir -p data && HUB_SERVER_PORT=8787 python3 hub.py
```
The orphan branch wipes the working tree; `build/` is gitignored and gets deleted.

## What not to do

- Don't edit files in `build/` — regenerated on every rebuild.
- Don't add runtime dependencies — intentionally stdlib-only.
- Don't store secrets in the scan root — everything is indexed and embedded.
