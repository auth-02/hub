# Hub — AGENTS.md

Stdlib-only Python tool that scans a directory tree, extracts metadata into
SQLite, and serves a browsable index via a local HTTP server.

## Run

Code lives in the `hubspace/` package. Run via `-m` (no install needed) or the
single `hub` console script after `pip install .` / `pipx install .`.

```bash
python3 -m hubspace.cli.hub serve                 # start server (port 8787, watcher included)
HUB_SERVER_PORT=8787 python3 -m hubspace.cli.hub  # rebuild index
open http://localhost:8787/                   # open hub

# After install, equivalently:
hub serve --port 8787
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
├── docs/                 specs — HUB-LAYOUT.md (the producer/consumer contract)
├── site/                 GitHub Pages landing page source (deployed to gh-pages on release)
├── example/              demo fixture repos — `hub --demo` (force-included in wheel)
├── assets/               docs-only: screenshots/ + hub-illustrations/ (never packaged)
├── hubspace/             the package (importable + pip/pipx installable)
│   ├── __init__.py       __version__ (single source; pyproject reads it)
│   ├── core/             core logic — no CLI/HTTP concerns
│   │   ├── config.py     hub.toml parsing; example_dir()/static_dir() resolvers
│   │   ├── db.py         SQLite layer — migrations, upsert, lineage, FTS export
│   │   ├── metadata.py   metadata extraction — title + body from markdown/html
│   │   ├── scan.py       pure path → kind/metadata classification (_classify, _meta)
│   │   └── migrations/   schema as ordered *.sql files, applied by user_version
│   ├── cli/              the `hub` command (hub = hubspace.cli.hub:main)
│   │   ├── hub.py        scan, DB update, index render; subcommands init/new/serve
│   │   └── server.py     HTTP server + watcher; `hub serve` calls server.serve()
│   ├── render/           file → HTML: columns.py, markdown.py, tabular.py, page.py
│   ├── utils/            generic helpers — text.py (slug/escape/time), paths.py
│   ├── static/          served assets + str.format template: favicon.svg, hub.css/js,
│   │                     hub.html, doc-page CSS (page/backlinks/chrome.css, loaded by render/page.py)
│   └── plugin/           hub-agent Claude plugin (manifest skill; excluded from wheel)
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
cli/server.py
  _HubServer (ThreadingMixIn + TCPServer, dual-stack IPv4+IPv6)
  _watcher() thread        polls scan root every 3 s, triggers hub.py on change
  HubHandler.do_GET()      / → build/docs-index.html
                           /<abs-path> → render file
                           /<rel-path> → resolve vs active scan root, render
                           /_rebuild   → run hub.py subprocess
  HubHandler.do_POST()     /_set-root  → write .scan_root, run hub.py

cli/hub.py:main()
  discover()               → dict[repo_name, list[file_meta]]
  db.open_db()             → sqlite3.Connection
  metadata.read_safe/extract_title/extract_body()
  db.upsert/prune/build_lineage/export_html_data()
  render(groups, fts_json, lineage_json)
    reads static/hub.html
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

## Template system (`static/hub.html`)

Uses Python's `str.format()`:
- `{name}` → substituted by `render()`
- `{{` / `}}` → literal `{` / `}` in CSS/JS

Placeholders: `{favicon}`, `{scan_root}`, `{scan_root_json}`, `{sidecar_json}`,
`{hubpy_json}`, `{server_origin_json}`, `{total}`, `{md_total}`, `{html_total}`,
`{repo_count}`, `{built}`, `{body}`, `{repo_chips}`, `{fts_json}`, `{lineage_json}`,
`{default_view_json}`, `{task_timeline_json}`, `{upload_exts_json}`, `{private_json}`,
`{published_json}`, `{provenance_json}`, `{notes_json}`.

After any template change: `HUB_SERVER_PORT=8787 python3 -m hubspace.cli.hub` to catch format errors.

## UI layering (z-index) contract

Hub has **two front-ends**: the SPA workspace (`ui/src/hub.css`, served on `/`)
and the standalone doc page (`ui/public/chrome.css`, served per file). Both
define the **same** ordered z-index scale as `:root` tokens — keep them in sync:

| token | value | for |
|-------|-------|-----|
| `--z-sticky` | 5 | in-flow sticky chrome (search bar, in-pane menus) |
| `--z-chrome` | 45 | persistent page chrome (settings gear, doc ⋯ menu) |
| `--z-overlay` | 90 | full-view overlays: preview, trace (graph = `+2`) |
| `--z-palette` | 100 | command palette |
| `--z-transient` | 1000 | **summoned surfaces**: modals, name inputs, composers, help |
| `--z-toast` | 1100 | **notifications** — the very top, never occluded |

**The rule (why a popup must never land "on the home page"):** anything a user
*summons* — a modal, the dak publish-name input, the comment composer, a confirm
— uses `--z-transient`; any toast/notification uses `--z-toast`. Both sit ABOVE
every view overlay and the palette, so they always appear on the page/overlay
they were invoked from, not hidden behind it. **When you add ANY new popup,
toast, sheet, or input, give it a token — never a bare z-index number.** A bare
number is how this regressed once per feature (S26/S27/S29): a new `z-index:60`
looks fine on the bare index but renders behind the open trace/graph/palette.

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
- **Via env**: `HUB_SCAN_ROOT=/path HUB_SERVER_PORT=8787 python3 -m hubspace.cli.hub`
- **Via sidecar**: `echo /path > ~/agents/hub/.scan_root`

Priority: `HUB_SCAN_ROOT` env > `hub.toml` `scan_root` > `.scan_root` sidecar > CWD.

## Common tasks

**Re-index from scratch:**
```bash
rm ~/.local/state/hub/hub.db && HUB_SERVER_PORT=8787 python3 -m hubspace.cli.hub
```

**Add a new badge/kind:**
1. Add the path rule to `_classify()` in `hubspace/core/scan.py`
2. Add `.badge.{kind}` CSS and filter chip in `hubspace/static/hub.html`
3. Add to `KIND_REL` in `db.build_lineage()` and JS `buildLineage()`

**Add an excluded directory:**
Add to `EXCLUDE_DIRS` in `hubspace/cli/hub.py` and `_WATCH_EXCLUDE` in `hubspace/cli/server.py`.

**Add a new indexed extension:**
Add to `EXTS` (always) or `PROMPT_EXTS` (prompts/ only) in `hubspace/core/scan.py`.
Update `metadata.extract_body()` if the format needs special stripping.

## Releases

Version is single-sourced in `hubspace/__init__.py` (`pyproject` reads it dynamically).

**To ship: bump `__version__` and merge to `main` — that's the only manual step.**
The rest is automated:
- `release.yml` — on a push to `main` that touches `hubspace/__init__.py`, cuts a
  GitHub Release `v<version>` (if it doesn't already exist). Uses the `RELEASE_PAT`
  secret, *not* `GITHUB_TOKEN`, because releases made with `GITHUB_TOKEN` don't
  trigger other workflows.
- `publish.yml` (on `release: published`) → builds + uploads wheel/sdist to PyPI (`hubspaces`).
- `pages.yml`  (on `release: published`) → stamps the tag into `site/index.html` and
  force-pushes `site/` to `gh-pages` (landing page at auth-02.github.io/hub).

Edit the landing page by editing `site/`; it redeploys on the next release (or via
`workflow_dispatch`). `RELEASE_PAT` must be a PAT with `repo` + `workflow` scope.

## Git / PR workflow

- Personal repo on GitHub under `auth-02` (NOT work account). Identity: `name=Atharva`, `email=shindeathrv@gmail.com`.
- **Never push directly to `main`** — branch protection enforces PRs. Always branch → PR → merge.
- Feature work → new branch from `main` → PR into `main`.
- Bug fixes → `fix/<slug>` branch → PR with proof screenshot.
- Always use `GH_TOKEN` from `.git/credentials` when running `gh` CLI.

**Local testing, demos & screenshots — dogfood, never the work hub:**
For any manual run, demo, or screenshot, point hub at **the hub repo itself**
(`cd ~/agents/hub && hub serve`) or the bundled fixture (`hub serve --demo`).
**Never** run it against — or capture — the real work hub at `/tifin`: it holds
private data. The committed `banner.png` is shot from hub's own dogfood hub.

**Screenshot convention:**
- `assets/screenshots/` — holds **only `banner.png`** (branding, ages slowly). We
  deliberately do *not* keep literal per-feature UI screenshots: they drift as the
  UI changes. Feature visuals come from the live demo instead —
  `uvx --from hubspaces hub serve --demo` — which the README and landing page point to.
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
mkdir -p data && HUB_SERVER_PORT=8787 python3 -m hubspace.cli.hub
```
The orphan branch wipes the working tree; `build/` is gitignored and gets deleted.

## What not to do

- Don't edit files in `build/` — regenerated on every rebuild.
- Don't add runtime dependencies — intentionally stdlib-only.
- Don't store secrets in the scan root — everything is indexed and embedded.
