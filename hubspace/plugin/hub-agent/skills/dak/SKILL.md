---
name: dak
description: Turn any local artifact — an HTML report, Markdown notes, an interactive dashboard, a generated PDF, a directory of files — into a shareable https:// URL with one command, using free Cloudflare Workers hosting. Use this skill whenever the user wants to SHARE or SEND a file or generated output rather than hand it over as an attachment. Triggers include "send me a link", "publish this", "share this report/dashboard/page", "host this", "put this online", "give me a URL for this", "make this shareable", or any agent workflow that ends in "...and send me a link". Also use it as the final step after generating a report, dashboard, or visualization when the user expects a link back. Covers two modes — snapshot (frozen, immutable) and live (updates on re-publish). Do NOT use for deploying full applications, CI/CD, or git-based hosting workflows.
---

# Dak — local artifact → shareable URL

Dak turns a generated file into a link. An agent produces something — a report, a
dashboard, notes, a diagram — and instead of handing over a file, it publishes and
returns a URL.

*Generate → Publish → Share link.*

## First-time setup

```bash
python3 scripts/dak.py setup
```

Interactive prompts — walks through three values and saves them to `~/.dak/config.json`:

1. **Cloudflare API token** — create at `dash.cloudflare.com/profile/api-tokens`
   with permission: **Workers Scripts: Edit**
2. **Account ID** — visible in the Cloudflare dashboard sidebar under Workers & Pages
3. **workers.dev subdomain** — convention is `<username>-dak` (e.g. `atharva-dak`)
   Check/set yours at: `dash.cloudflare.com → Workers & Pages → Your subdomain`

After setup, the URL is constructed locally as `https://<name>.<subdomain>.workers.dev`
— no parsing of wrangler output needed.

## Publishing

```bash
# snapshot (default) — frozen, unique URL per publish
python3 scripts/dak.py report.html

# live — stable URL, updates on redeploy
python3 scripts/dak.py dashboard/ --mode live --slug portfolio
```

Prints only the URL to stdout. Composes cleanly in agent pipelines.

### Input types

- **`.html`** → served as-is.
- **`.md` / `.markdown`** → rendered to a clean HTML page (code, tables, links).
- **directory** → deployed as-is; generates an index if none exists.
- **`.pdf` / image** → embedded in a minimal viewer page.
- **any other file** → served with a download index.

### Options

| Flag | Purpose |
|------|---------|
| `--mode snapshot\|live` | default `snapshot` |
| `--slug NAME` | worker name for live mode; also base for snapshot names |
| `--title T` | page `<title>` |
| `--dry-run` | show URL + wrangler command without deploying |

## Other commands

```bash
python3 scripts/dak.py doctor       # check config + credentials
python3 scripts/dak.py list         # all published artifacts
python3 scripts/dak.py unpublish <worker-name>
```

## URL format

```
https://<worker-name>.<subdomain>.workers.dev

# snapshot:  https://report-a1b2c3.atharva-dak.workers.dev
# live:      https://portfolio.atharva-dak.workers.dev
```

## Config file

`~/.dak/config.json` — stores token, account ID, and subdomain.
`~/.dak/manifest.json` — local record of all published artifacts.

Credentials are read from config first, falling back to `CLOUDFLARE_API_TOKEN` /
`CLOUDFLARE_ACCOUNT_ID` env vars if config isn't set up yet.

## Notes

- Free Cloudflare Workers: unlimited requests, no bandwidth cap.
- Nothing leaves the machine until a deploy command runs.
- The `wrangler.jsonc` is written into a temp dir and deleted after deploy.
