#!/usr/bin/env bash
# /hub:daemon — optionally run the Hub viewer as a persistent macOS launchd agent
# from the plugin's vendored wheel (offline/hermetic). Opt-in only.
# Usage: daemon.sh [install [--port N] | uninstall | status]   (default: install)
#
# Thin wrapper: the launchd plist generation + management lives once in the
# engine (`hub agent`, in the wheel). This only supplies the plugin-specific
# launcher — `uv tool run --offline --from <wheel> hub` — and a distinct label.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL=com.user.hub-agent
WHEEL=$(ls "$ROOT/vendor/"*.whl 2>/dev/null | head -1 || true)
[ -n "$WHEEL" ] || { echo "hub plugin looks corrupt: no vendor/*.whl — reinstall." >&2; exit 1; }
command -v uv >/dev/null || { echo "needs uv: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
UV=$(command -v uv)
RUN=("$UV" tool run --offline --from "$WHEEL" hub)

cmd="${1:-install}"; shift || true
case "$cmd" in
  install)
    # Bake a properly-quoted launcher so a wheel path with spaces survives shlex.
    EXEC=$(printf '%q tool run --offline --from %q hub' "$UV" "$WHEEL")
    exec "${RUN[@]}" agent install --label "$LABEL" --exec "$EXEC" "$@"
    ;;
  uninstall|status)
    exec "${RUN[@]}" agent "$cmd" --label "$LABEL"
    ;;
  *)
    echo "usage: daemon.sh [install [--port N] | uninstall | status]" >&2; exit 2 ;;
esac
