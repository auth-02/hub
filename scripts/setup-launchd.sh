#!/usr/bin/env bash
# scripts/setup-launchd.sh
# Creates and loads the two launchd agents that keep hub running at login.
# Run once after cloning.
#
# Usage:
#   bash scripts/setup-launchd.sh
#   HUB_SCAN_ROOT=~/work bash scripts/setup-launchd.sh   # seed a custom scan root
#
# Scan root is stored in the .scan_root sidecar (NOT pinned as an env var in the
# plists), so the "change scan root" button in the UI persists across restarts.
# Precedence when (re)running this script:
#   explicit HUB_SCAN_ROOT env  >  existing sidecar  >  default ~/tifin

set -euo pipefail

HUB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${HUB_SERVER_PORT:-8787}"
UV="$(which uv 2>/dev/null || echo "$HOME/.local/bin/uv")"
AGENTS="$HOME/Library/LaunchAgents"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/hub"
SIDECAR="$STATE_DIR/.scan_root"

mkdir -p "$AGENTS" "$STATE_DIR"

# Seed the sidecar — the authoritative, UI-overridable scan root. Only an
# explicit HUB_SCAN_ROOT overrides an existing sidecar; otherwise keep what the
# user already chose (via the UI), falling back to ~/tifin on a fresh setup.
if [ -n "${HUB_SCAN_ROOT:-}" ]; then
    SCAN_ROOT="$HUB_SCAN_ROOT"
elif [ -s "$SIDECAR" ]; then
    SCAN_ROOT="$(cat "$SIDECAR")"
else
    SCAN_ROOT="$HOME/tifin"
fi
printf '%s\n' "$SCAN_ROOT" > "$SIDECAR"

# ── com.user.hub — rebuild index every 120 s ──────────────────────────────
# Sets HUB_SERVER_PORT only, so rebuilt links point at localhost:$PORT. No
# HUB_SCAN_ROOT — resolution falls through to the sidecar above.
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
        <key>HUB_SERVER_PORT</key><string>$PORT</string>
    </dict>
    <key>WorkingDirectory</key><string>$HUB_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>StartInterval</key><integer>120</integer>
</dict>
</plist>
EOF

# ── com.user.hub-server — HTTP server, KeepAlive ──────────────────────────
# Port is passed as a CLI arg; no env needed. No HUB_SCAN_ROOT (sidecar wins).
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
echo "Scan root: $SCAN_ROOT  (stored in $SIDECAR — change it anytime from the UI)"
