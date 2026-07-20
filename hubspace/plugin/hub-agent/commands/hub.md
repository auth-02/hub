---
description: Build and serve the Hub — a browsable page of every .md/.html, task, and skill in the current directory.
argument-hint: "[serve|build] [--port N] [--demo]"
---

Run Hub from the bundled wheel (offline, no PyPI, no ambient `hubspaces`).
Default to `serve --port 8787`; pass `$ARGUMENTS` through instead when given.

```bash
command -v uv >/dev/null || { echo "Hub needs 'uv': https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
WHEEL=$(ls "${CLAUDE_PLUGIN_ROOT}/vendor/"*.whl | head -1)
uvx --offline --from "$WHEEL" hub serve --port 8787
```

When serving, tell the user to open <http://localhost:8787> — it rebuilds on
change. Leave it running.
