---
description: Optionally run the Hub viewer as a persistent macOS launchd agent from the bundled wheel — survives logout/reboot.
argument-hint: "install [--port N] | uninstall | status"
---

Persistent, offline Hub viewer via macOS **launchd** + the vendored wheel. Only
run when the user explicitly asks for an always-on Hub (`/hub` alone is
foreground). macOS only. `$ARGUMENTS`: `install` (default) / `uninstall` /
`status`. Serves `$PWD`.

**install** — resolve absolute paths (launchd has no `${CLAUDE_PLUGIN_ROOT}`),
write the plist, load it:

```bash
[ "$(uname)" = Darwin ] || { echo "macOS launchd only."; exit 1; }
UV=$(command -v uv) || { echo "needs uv: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
WHEEL=$(ls "${CLAUDE_PLUGIN_ROOT}/vendor/"*.whl | head -1); PORT=8787; L=com.user.hub-agent
P="$HOME/Library/LaunchAgents/$L.plist"; mkdir -p "$(dirname "$P")"
cat > "$P" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$L</string>
  <key>ProgramArguments</key><array>
    <string>$UV</string><string>tool</string><string>run</string>
    <string>--offline</string><string>--from</string><string>$WHEEL</string>
    <string>hub</string><string>serve</string><string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PLIST
launchctl bootout gui/$(id -u)/$L 2>/dev/null; launchctl bootstrap gui/$(id -u) "$P"
echo "Hub agent up at http://localhost:$PORT (serving $PWD)."
```

Pass a different `--port` if the package's own `com.user.hub-server` uses 8787.

**uninstall**
```bash
L=com.user.hub-agent; launchctl bootout gui/$(id -u)/$L 2>/dev/null; rm -f "$HOME/Library/LaunchAgents/$L.plist"; echo "removed."
```

**status**
```bash
launchctl print "gui/$(id -u)/com.user.hub-agent" 2>/dev/null | grep -E 'state =|pid =' || echo "not installed."
```
