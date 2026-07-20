---
description: Optionally run the Hub viewer as a persistent macOS launchd agent from the bundled wheel — survives logout/reboot.
argument-hint: "install [--port N] | uninstall | status"
---

Run the plugin's daemon script. Opt-in only — use when the user explicitly wants
an always-on Hub (`/hub` alone is foreground). macOS only. Serves `$PWD`.
Default action is `install`; pass `$ARGUMENTS` through:

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/daemon.sh" $ARGUMENTS
```
