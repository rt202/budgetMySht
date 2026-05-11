#!/usr/bin/env bash
# Install the daily SimpleFIN sync as a launchd agent.
#
# Usage:
#   bash scripts/install_launchd.sh           # uses the active python3 binary
#   PYTHON_BIN=/path/to/venv/bin/python bash scripts/install_launchd.sh
#
# To stop the daily sync later, run scripts/uninstall_launchd.sh.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$PROJECT_ROOT/scripts/com.user.simplefin-sync.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.user.simplefin-sync.plist"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

if [[ -z "$PYTHON_BIN" ]]; then
    echo "Could not locate python3. Set PYTHON_BIN explicitly." >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$PROJECT_ROOT/data"

sed \
    -e "s|PLACEHOLDER_PYTHON_BIN|$PYTHON_BIN|g" \
    -e "s|PLACEHOLDER_PROJECT_ROOT|$PROJECT_ROOT|g" \
    "$TEMPLATE" > "$TARGET"

launchctl unload "$TARGET" 2>/dev/null || true
launchctl load -w "$TARGET"

echo "Installed daily sync at $TARGET"
echo "Next run: tomorrow at 07:00 local time."
echo "Force run now with: launchctl start com.user.simplefin-sync"
