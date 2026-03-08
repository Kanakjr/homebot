#!/bin/bash
# Sync between local workspace and HomeServer
# Only copies changed files, ignores venv/node_modules
#
# Usage:
#   ./sync-to-server.sh                # push local -> server (default)
#   ./sync-to-server.sh --pull         # pull server -> local
#   ./sync-to-server.sh --git          # include .git in sync
#   ./sync-to-server.sh --pull --git   # pull with .git

LOCAL="/Users/kanakd/Workspace/homebot/"
SERVER="/Volumes/kanakjr/HomeServer/Apps/homebot/"

SYNC_GIT=false
PULL=false
for arg in "$@"; do
  case "$arg" in
    --git)  SYNC_GIT=true ;;
    --pull) PULL=true ;;
  esac
done

if [ ! -d "$SERVER" ]; then
  echo "Error: Server path not found at $SERVER"
  echo "Make sure the volume is mounted."
  exit 1
fi

if [ "$PULL" = true ]; then
  SRC="$SERVER"
  DEST="$LOCAL"
  DIRECTION="pull (server -> local)"
else
  SRC="$LOCAL"
  DEST="$SERVER"
  DIRECTION="push (local -> server)"
fi

echo "Syncing changes:"
echo "  Direction: $DIRECTION"
echo "  Source:    $SRC"
echo "  Dest:     $DEST"
if [ "$SYNC_GIT" = true ]; then
  echo "  Git:      included"
else
  echo "  Git:      excluded (use --git to include)"
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
