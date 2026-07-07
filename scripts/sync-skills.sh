#!/usr/bin/env bash
# scripts/sync-skills.sh
# Syncs the hub-agent plugin's bundled skills from the canonical git-backed
# skills repo (~/skills). Copies — never symlinks — because the plugin is
# distributed via git and symlinks to local paths would break on install.
#
# Usage:
#   bash scripts/sync-skills.sh          # sync + show diff
#   bash scripts/sync-skills.sh --check  # exit 1 if plugin skills are stale
set -euo pipefail

SRC="${HUB_SKILLS_SRC:-$HOME/skills}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/hubspace/plugin/hub-agent/skills"
SKILLS=(dak kagaz manifest stacked)

if [[ "${1:-}" == "--check" ]]; then
  stale=0
  for s in "${SKILLS[@]}"; do
    if ! diff -rq --exclude=.DS_Store --exclude=__pycache__ "$SRC/$s" "$DEST/$s" >/dev/null 2>&1; then
      echo "stale: $s"
      stale=1
    fi
  done
  exit $stale
fi

for s in "${SKILLS[@]}"; do
  rsync -a --delete --exclude=.DS_Store --exclude=__pycache__ "$SRC/$s/" "$DEST/$s/"
  echo "synced: $s"
done

cd "$(dirname "$DEST")" && git -C "$DEST" status --short -- . || true
