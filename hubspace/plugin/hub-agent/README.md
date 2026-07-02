# hub-agent — Claude Code plugin

A **self-sufficient agent** for [Hub](../../README.md): install it once and you
get both halves of the workflow — the *producers* that create structured work,
and the *consumer* (Hub) that indexes, cross-links, and serves it as one page.

## What's bundled

**Producer skills** — they create exactly the structure Hub indexes, badges,
and traces:

| Skill | Produces |
|-------|----------|
| `manifest` | Living `tasks/<slug>/manifest.md` (+ `data/` `artifacts/` `runs/`) for any non-trivial task. |
| `stacked` | Decomposes large changes into a stack of small, reviewable units. |
| `kagaz` | Editorial/technical document + frontend design (HTML→PDF, slides, reports). |
| `dak` | Publishes and shares reports / short URLs. |

**Consumer command** — the dashboard that ties it together:

- **`/hub`** — builds and serves the browsable Hub index (every `.md`/`.html`,
  task, run, artifact, and skill in the current directory) on
  <http://localhost:8787>, watching for changes. Runs via `uvx --from hubspaces`,
  so no separate install is required.

## Install

```
/plugin marketplace add auth-02/hub
/plugin install hub-agent@hub
```

Then `/hub` to serve the dashboard, and start any feature with a plan-before-code
loop so the producer skills scaffold structure Hub picks up automatically.

## Note on hub-core

The `hubspaces` package delivers the full index/search/preview/trace experience
on its own (`pipx install hubspaces` → `hub serve`) with no plugin or agent
present. This plugin adds the *producer* side and a one-command launcher on top.
