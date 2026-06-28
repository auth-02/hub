#!/usr/bin/env bash
# scripts/setup-launchd.sh
# Creates and loads the two launchd agents that keep hub running at login.
# Run once after cloning. Re-run after changing HUB_SCAN_ROOT or HUB_OUTPUT.
#
# Usage:
#   bash scripts/setup-launchd.sh
#   HUB_SCAN_ROOT=~/work bash scripts/setup-launchd.sh   # custom scan root

set -euo pipefail

HUB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCAN_ROOT="${HUB_SCAN_ROOT:-$HOME/tifin}"
PORT="${HUB_SERVER_PORT:-8787}"
UV="$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")"
AGENTS="$HOME/Library/LaunchAgents"

mkdir -p "$AGENTS"

# ── com.user.hub — rebuild index every 120 s ──────────────────────────────
cat > "$AGENTS/com.user.hub.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.hub</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UV</string>
        <string>run</string>
        <string>--project</string>
        <string>$HUB_DIR</string>
        <string>hub</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HUB_SCAN_ROOT</key><string>$SCAN_ROOT</string>
        <key>HUB_SERVER_PORT</key><string>$PORT</string>
    </dict>
    <key>WorkingDirectory</key><string>$HUB_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>StartInterval</key><integer>120</integer>
</dict>
</plist>
EOF

# ── com.user.hub-server — HTTP server, KeepAlive ──────────────────────────
cat > "$AGENTS/com.user.hub-server.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.user.hub-server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UV</string>
        <string>run</string>
        <string>--project</string>
        <string>$HUB_DIR</string>
        <string>hub</string>
        <string>serve</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HUB_SCAN_ROOT</key><string>$SCAN_ROOT</string>
    </dict>
    <key>WorkingDirectory</key><string>$HUB_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
EOF

# ── Load (unload first if already running) ────────────────────────────────
for label in com.user.hub com.user.hub-server; do
    launchctl unload "$AGENTS/$label.plist" 2>/dev/null || true
    launchctl load "$AGENTS/$label.plist"
    echo "  loaded $label"
done

echo ""
echo "Hub running at http://localhost:$PORT"
echo "Scan root: $SCAN_ROOT"
