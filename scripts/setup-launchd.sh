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
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/hub"
SIDECAR="$STATE_DIR/.scan_root"

mkdir -p "$STATE_DIR"   # ~/Library/LaunchAgents is created by `hub agent`

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

# Plist generation + launchctl load now live once in the engine (`hub agent`);
# this script only supplies the dev launcher (`uv run --project $HUB_DIR hub`)
# and its two agents. HUB_SCAN_ROOT is intentionally NOT pinned in the plists —
# resolution falls through to the sidecar seeded above, so the UI's "change scan
# root" button persists across restarts.
EXEC=$(printf '%q run --project %q hub' "$UV" "$HUB_DIR")
HUB_RUN=("$UV" run --project "$HUB_DIR" hub)

# com.user.hub        — rebuild the index every 120 s (StartInterval)
# com.user.hub-server — HTTP server, KeepAlive
"${HUB_RUN[@]}" agent install --label com.user.hub \
    --exec "$EXEC" --rebuild-interval 120 --port "$PORT" --root "$HUB_DIR"
"${HUB_RUN[@]}" agent install --label com.user.hub-server \
    --exec "$EXEC" --serve --port "$PORT" --root "$HUB_DIR"

echo ""
echo "Hub running at http://localhost:$PORT"
echo "Scan root: $SCAN_ROOT  (stored in $SIDECAR — change it anytime from the UI)"
