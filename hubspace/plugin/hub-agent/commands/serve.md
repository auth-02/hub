---
description: Build and serve the Hub — a browsable page of every .md/.html, task, and skill in the current directory.
argument-hint: "[serve|build] [--port N] [--demo]"
---

Run the plugin's serve script (offline, bundled wheel). Default is
`serve --port 8787`; pass `$ARGUMENTS` through when given:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/serve.sh" $ARGUMENTS
```

When serving, tell the user to open <http://localhost:8787> — it rebuilds on
change. Leave it running.
