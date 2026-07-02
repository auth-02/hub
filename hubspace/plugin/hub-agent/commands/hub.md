---
description: Build and serve the Hub — one browsable page of every .md/.html, task, and skill in the current directory.
argument-hint: "[serve|build] [--port N] [--demo]"
---

You are launching **Hub**, the consumer half of this agent: a local page that
indexes and cross-links every `.md`/`.html` file, task manifest, run, artifact,
and skill under the current directory. The producer skills bundled with this
plugin (manifest, stacked, kagaz, dak) create that structure; Hub surfaces it.

Run it from the directory the user wants to browse. No separate install is
needed — `uvx` fetches and runs the published `hubspaces` package on demand:

```bash
# Serve (default): build the index, then serve + watch for changes on :8787
uvx --from hubspaces hub serve --port 8787

# One-shot build only (no server)
uvx --from hubspaces hub

# Try it on the bundled example repo
uvx --from hubspaces hub serve --demo
```

If `hubspaces` is already installed (`pipx install hubspaces`), use the `hub`
command directly (`hub serve`, `hub`, `hub new task <slug>`).

Steps:
1. Parse `$ARGUMENTS` — default to `serve` on port 8787 if none given.
2. Run the matching command above from the user's current working directory.
3. When serving, tell the user to open <http://localhost:8787> and that the
   server rebuilds automatically as files change. Leave it running.
