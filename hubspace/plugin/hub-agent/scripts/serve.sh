#!/usr/bin/env bash
# /hub — build & serve the Hub from the plugin's vendored wheel, fully offline.
# Self-locating: resolves the wheel relative to this script, so it works whether
# invoked by the /hub command or directly. Args pass through to `hub`
# (default: `serve --port 8787`).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v uv >/dev/null || {
  echo "Hub needs 'uv': https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
}
WHEEL=$(ls "$ROOT/vendor/"*.whl 2>/dev/null | head -1 || true)
[ -n "$WHEEL" ] || { echo "hub-agent looks corrupt: no vendor/*.whl — reinstall the plugin." >&2; exit 1; }

[ "$#" -eq 0 ] && set -- serve --port 8787
exec uv tool run --offline --from "$WHEEL" hub "$@"
