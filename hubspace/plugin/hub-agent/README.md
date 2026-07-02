# hub-agent — Claude Code plugin

Opt-in companion to [Hub](../../README.md). Bundles the **`manifest`** skill: it
creates and maintains a living `tasks/<slug>/manifest.md` (plus `data/`,
`artifacts/`, `runs/`) for any non-trivial task — exactly the structure Hub
indexes, badges, and traces.

**hub-core does not depend on this.** The `hubspace` package delivers the full
index/search/preview/trace experience with no plugin and no agent present. This
plugin only adds the *producer* side for agent-driven workflows.

## Install

```
/plugin marketplace add auth-02/hub
/plugin install hub-agent@hub
```

Then start any feature with a plan-before-code loop and the skill will scaffold
and update the manifest as you go.
