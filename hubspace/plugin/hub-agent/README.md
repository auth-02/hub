# hub — Claude Code plugin

A **self-sufficient agent** for [Hub](../../README.md): install it once and you
get both halves of the workflow — the *producers* that create structured work,
and the *consumer* (Hub) that indexes, cross-links, and serves it as one page.

## What's bundled

**Producer skills** — they create exactly the structure Hub indexes, badges,
and traces. Invoke as `/hub:<skill>` (or let Claude trigger them by context):

| Skill | Invoke | Produces |
|-------|--------|----------|
| `manifest` | `/hub:manifest` | Living `tasks/<slug>/manifest.md` (+ `data/` `artifacts/` `runs/`) for any non-trivial task. |
| `stacked` | `/hub:stacked` | Decomposes large changes into a stack of small, reviewable units. |
| `kagaz` | `/hub:kagaz` | Editorial/technical document + frontend design (HTML→PDF, slides, reports). |
| `dak` | `/hub:dak` | Publishes and shares reports / short URLs. |

**Consumer commands** — the dashboard that ties it together:

- **`/hub:serve`** — builds and serves the browsable Hub index (every `.md`/`.html`,
  task, run, artifact, skill, and **Excalidraw diagram** in the current directory)
  on <http://localhost:8787>, watching for changes. Diagrams are created in place,
  offline, and become first-class lineage nodes badged `DRAW`.
- **`/hub:daemon`** — *optional*: run that viewer as a persistent macOS launchd
  agent (from the same bundled wheel) so it survives logout/reboot. Opt-in only —
  `install` / `uninstall` / `status`.

> Everything is namespaced by the plugin name (`hub`), so it's `/hub:serve`,
> `/hub:manifest`, etc. — never a bare `/serve`.

## Offline by design

The plugin ships a **pinned `hubspaces` wheel** under `vendor/` and always runs
*that* wheel via `uv` (`uv tool run --offline --from vendor/*.whl hub serve`).
This means:

- **Fully offline from the first run** — nothing is fetched from PyPI, ever.
- **No version skew** — it never runs a separately-installed `hubspaces`; only
  ever its own bundled wheel.
- **Single source of truth** — the engine is authored only in the `hubspaces`
  package; the plugin carries a frozen build snapshot, not a second copy of the
  source. CI re-vendors the wheel automatically on every release.

The **only external requirement is `uv`** ([install](https://docs.astral.sh/uv/getting-started/installation/)).
`uv` provisions an isolated interpreter and environment, so nothing touches the
user's Python.

## Install

```
/plugin marketplace add auth-02/hub
/plugin install hub@hub
```

Then `/hub:serve` to serve the dashboard, and start any feature with a
plan-before-code loop so the producer skills scaffold structure Hub picks up
automatically.

## Note on hub-core

The `hubspaces` package delivers the full index/search/preview/trace experience
on its own (`pipx install hubspaces` → `hub serve`) with no plugin or agent
present. This plugin adds the *producer* side and a one-command launcher on top.
