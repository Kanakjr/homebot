#!/bin/bash
# Sync differences from local workspace to HomeServer
# Only copies changed files, ignores venv/node_modules
#
# Usage:
#   ./sync-to-server.sh           # excludes .git (default)
#   ./sync-to-server.sh --git     # includes .git in sync

SRC="/Users/kanakd/Workspace/homebot/"
DEST="/Volumes/kanakjr/HomeServer/Apps/homebot/"

SYNC_GIT=false
for arg in "$@"; do
  if [ "$arg" = "--git" ]; then
    SYNC_GIT=true
  fi
done

# Check if destination is reachable
if [ ! -d "$DEST" ]; then
  echo "Error: Destination not found at $DEST"
  echo "Make sure the volume is mounted."
  exit 1
fi

echo "Syncing changes from:"
echo "  Source: $SRC"
echo "  Dest:   $DEST"
if [ "$SYNC_GIT" = true ]; then
  echo "  Git:    included"
else
  echo "  Git:    excluded (use --git to include)"
fi
echo ""

EXCLUDES=(
  --exclude 'node_modules'
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '.smbdelete*'
)

if [ "$SYNC_GIT" = false ]; then
  EXCLUDES+=(--exclude '.git')
fi

rsync -av --delete \
  "${EXCLUDES[@]}" \
  "$SRC" "$DEST"

echo ""
echo "Sync complete."
