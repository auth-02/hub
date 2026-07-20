---
description: Build and serve the Hub — one browsable page of every .md/.html, task, and skill in the current directory.
argument-hint: "[serve|build] [--port N] [--demo]"
---

You are launching **Hub**, the consumer half of this agent: a local page that
indexes and cross-links every `.md`/`.html` file, task manifest, run, artifact,
and skill under the current directory. The producer skills bundled with this
plugin (manifest, stacked, kagaz, dak) create that structure; Hub surfaces it.

This plugin is **self-sufficient and offline**: it ships a pinned `hubspaces`
wheel under `vendor/` and always runs *that* wheel via `uv`. It never fetches
from PyPI and never runs a separately-installed `hubspaces`, so there is no
version skew. The only external requirement is `uv`.

## Steps

1. **Check `uv` is installed.** Run `command -v uv`. If it is missing, STOP and
   tell the user exactly this, then wait:
   > Hub needs `uv` to run its bundled engine offline. Install it with
   > `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux) or see
   > <https://docs.astral.sh/uv/getting-started/installation/>, then re-run `/hub`.

2. **Resolve the bundled wheel.** There is exactly one wheel in the plugin's
   `vendor/` directory. Resolve its absolute path:
   ```bash
   WHEEL=$(ls "${CLAUDE_PLUGIN_ROOT}/vendor/"*.whl | head -1)
   ```
   If no wheel is found, STOP and report that the plugin install looks corrupt
   (missing `vendor/*.whl`) and should be reinstalled.

3. **Parse `$ARGUMENTS`** — default to `serve` on port 8787 when none given.
   Pass `--demo` and `--port N` through if the user supplied them.

4. **Run the bundled wheel from the user's current working directory.** Use
   `--offline` so it can never touch the network — the wheel is local:

   ```bash
   # Serve (default): build the index, then serve + watch on :8787
   uvx --offline --from "$WHEEL" hub serve --port 8787

   # One-shot build only (no server)
   uvx --offline --from "$WHEEL" hub

   # Try it on the bundled example repo
   uvx --offline --from "$WHEEL" hub serve --demo
   ```

5. **When serving,** tell the user to open <http://localhost:8787> and that the
   server rebuilds automatically as files change. Leave it running.

## Notes

- `uvx --from <wheel>` runs in an isolated, hermetic environment with a
  provisioned interpreter — nothing is installed into the user's Python.
- The bundled wheel is refreshed automatically on every `hubspaces` release
  (CI re-vendors it), so `/hub` always matches the released engine.
- A user who prefers a global install can still `pipx install hubspaces` and run
  `hub serve` directly, but the plugin does not depend on that.
