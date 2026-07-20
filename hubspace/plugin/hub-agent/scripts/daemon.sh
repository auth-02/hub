#!/usr/bin/env bash
# /hub-daemon — optionally run the Hub viewer as a persistent macOS launchd agent
# from the plugin's vendored wheel (offline/hermetic). Opt-in only.
# Usage: daemon.sh [install [--port N] | uninstall | status]   (default: install)
# Serves the current working directory ($PWD).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=com.user.hub-agent
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
GUI="gui/$(id -u)"

cmd="${1:-install}"; shift || true

case "$cmd" in
  install)
    [ "$(uname)" = Darwin ] || { echo "Persistent agent supports macOS launchd only." >&2; exit 1; }
    UV=$(command -v uv) || { echo "needs uv: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
    WHEEL=$(ls "$ROOT/vendor/"*.whl 2>/dev/null | head -1 || true)
    [ -n "$WHEEL" ] || { echo "hub-agent looks corrupt: no vendor/*.whl." >&2; exit 1; }
    PORT=8787
    while [ "$#" -gt 0 ]; do case "$1" in --port) PORT="${2:?}"; shift 2;; *) shift;; esac; done
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$UV</string><string>tool</string><string>run</string>
    <string>--offline</string><string>--from</string><string>$WHEEL</string>
    <string>hub</string><string>serve</string><string>--port</string><string>$PORT</string>
  </array>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
</dict></plist>
PLIST
    launchctl bootout "$GUI/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$GUI" "$PLIST"
    echo "Hub agent up at http://localhost:$PORT (serving $PWD). Manage with: /hub-daemon status | uninstall"
    ;;
  uninstall)
    launchctl bootout "$GUI/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Hub agent stopped and removed."
    ;;
  status)
    launchctl print "$GUI/$LABEL" 2>/dev/null | grep -E 'state =|pid =' \
      || echo "Hub agent is not installed. Run /hub-daemon install to start one."
    ;;
  *)
    echo "usage: daemon.sh [install [--port N] | uninstall | status]" >&2; exit 2 ;;
esac
