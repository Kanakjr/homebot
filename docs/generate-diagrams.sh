#!/usr/bin/env bash
#
# Generate architecture diagram PNG from Mermaid source.
# Re-run this script after editing docs/architecture.mmd.
#
# Usage:
#   ./docs/generate-diagrams.sh            # default: docs/architecture.png
#   ./docs/generate-diagrams.sh out.png    # custom output path
#
# Requirements:
#   npm install -g @mermaid-js/mermaid-cli
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INPUT="$SCRIPT_DIR/architecture.mmd"
OUTPUT="${1:-$SCRIPT_DIR/architecture.png}"
CONFIG="$SCRIPT_DIR/mermaid-config.json"

if ! command -v mmdc &>/dev/null; then
  echo "Error: mmdc (mermaid-cli) not found."
  echo "Install with: npm install -g @mermaid-js/mermaid-cli"
  exit 1
fi

if [[ ! -f "$INPUT" ]]; then
  echo "Error: $INPUT not found."
  exit 1
fi

cat > "$CONFIG" << 'CONF'
{
  "theme": "default",
  "backgroundColor": "#ffffff"
}
CONF

echo "Generating: $INPUT -> $OUTPUT"
mmdc -i "$INPUT" -o "$OUTPUT" -b "#ffffff" -w 2400 -s 2 --configFile "$CONFIG"

rm -f "$CONFIG"

echo "Done: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
