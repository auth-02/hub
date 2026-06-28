# Hub — CLAUDE.md

Stdlib-only Python tool that scans a directory tree, extracts metadata into
SQLite, and serves a browsable index via a local HTTP server.

## Run

Code lives in the `hubspace/` package. Run via `-m` (no install needed) or the
console scripts (`hub`, `hub-server`) after `pip install .` / `pipx install .`.

```bash
python3 -m hubspace.server                    # start server (port 8787, watcher included)
HUB_SERVER_PORT=8787 python3 -m hubspace.hub  # rebuild index
open http://localhost:8787/                   # open hub

# After install, equivalently:
hub-server --port 8787
hub
```

Second `hub` run is ~300 ms — mtime-gated, skips unchanged files.

## Run tests

```bash
python3 tests/run_tests.py       # all 240 tests
python3 tests/run_tests.py -v    # verbose output
```

## File map

```
hub/                          repo root
├── pyproject.toml        packaging — dist name `hubspace`, console scripts, hatchling
├── LICENSE               MIT
├── README.md             stranger-facing docs (images under hubspace/assets/)
├── hubspace/             the package (importable + pip/pipx installable)
│   ├── __init__.py
│   ├── config.py         hub.toml parsing, scan-root/port/view resolution, writable paths
│   ├── hub.py            entry point — scan, DB update, render  (hub = hubspace.hub:main)
│   ├── server.py         HTTP server (hub-server = hubspace.server:main)
│   ├── db.py             SQLite layer — migrations, upsert, lineage, FTS export
│   ├── metadata.py       metadata extraction — title + body from markdown/html
│   ├── migrations/       schema as ordered *.sql files, applied by user_version
│   ├── assets/           favicon.svg, hub.css, hub.js  (screenshots/ excluded from wheel)
│   ├── templates/        template.html  (str.format()-based)
│   └── example/          fixture repos for dev + `hub --demo`
├── tests/
│   ├── run_tests.py      test runner (adds repo root → `from hubspace import …`)
│   ├── test_config.py    hub.toml + path resolution
│   └── …                 test_metadata / _db / _migrations / _hub_helpers / _server_*
~/.local/state/hub/      persistent + generated state — never delete
│   ├── build/docs-index.html   generated hub page, served at /  (was repo build/)
│   ├── hub.db            SQLite: files, lineage, fts, activity_log, task_status
│   ├── task-status.json  sidecar backup of task statuses
│   ├── .scan_root        active scan root (written by /_set-root)
│   └── hub.log           debug log (only when HUB_DEBUG=1)
```

**Layout note:** all runtime-writable output (generated index, log, DB) lives
under `state_dir()` (`$XDG_STATE_HOME/hub` or `~/.local/state/hub`), *not* the
package dir — so an installed (read-only) `hubspace` can still rebuild. Paths
are owned by `config.py` (`output_path()`, `log_path()`, `build_dir()`).

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

## SQLite schema (`~/.local/state/hub/hub.db`)

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
`{repo_count}`, `{built}`, `{body}`, `{repo_chips}`, `{fts_json}`, `{lineage_json}`,
`{default_view_json}`.

After any template change: `HUB_SERVER_PORT=8787 python3 -m hubspace.hub` to catch format errors.

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `HUB_SCAN_ROOT` | *(CWD)* | Root to scan. Priority: env > `hub.toml` > `.scan_root` sidecar > CWD |
| `HUB_SERVER_PORT` | *(unset)* | When set, links use `http://localhost:PORT/`. Falls back to `hub.toml` `port` |
| `HUB_OUTPUT` | `~/.local/state/hub/build/docs-index.html` | Output HTML path |
| `HUB_DB` | `~/.local/state/hub/hub.db` | SQLite database path |
| `HUB_FAVICON` | bundled `hubspace/assets/favicon.svg` | Tab icon |
| `HUB_DEBUG` | off | `1` enables logging to `~/.local/state/hub/hub.log` |

Config file: `hub.toml` in the run directory — keys `scan_root`, `port`,
`exclude_dirs`, `default_view` (env vars override). `hub init` writes a stub.

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
- **Via env**: `HUB_SCAN_ROOT=/path HUB_SERVER_PORT=8787 python3 -m hubspace.hub`
- **Via sidecar**: `echo /path > ~/agents/hub/.scan_root`

Priority: `HUB_SCAN_ROOT` env > `hub.toml` `scan_root` > `.scan_root` sidecar > CWD.

## Common tasks

**Re-index from scratch:**
```bash
rm ~/.local/state/hub/hub.db && HUB_SERVER_PORT=8787 python3 -m hubspace.hub
```

**Add a new badge/kind:**
1. Add to `KIND_DIRS` in `hubspace/hub.py`
2. Add `.badge.{kind}` CSS and filter chip in `hubspace/templates/template.html`
3. Add to `KIND_REL` in `db.build_lineage()` and JS `buildLineage()`

**Add an excluded directory:**
Add to `EXCLUDE_DIRS` in `hubspace/hub.py` and `_WATCH_EXCLUDE` in `hubspace/server.py`.

**Add a new indexed extension:**
Add to `EXTS` (always) or `PROMPT_EXTS` (prompts/ only) in `hubspace/hub.py`.
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
mkdir -p data && HUB_SERVER_PORT=8787 python3 -m hubspace.hub
```
The orphan branch wipes the working tree; `build/` is gitignored and gets deleted.

## What not to do

- Don't edit files in `build/` — regenerated on every rebuild.
- Don't add runtime dependencies — intentionally stdlib-only.
- Don't store secrets in the scan root — everything is indexed and embedded.
