#!/usr/bin/env bash
# Stop and remove the daily SimpleFIN sync launchd agent.

set -euo pipefail

TARGET="$HOME/Library/LaunchAgents/com.user.simplefin-sync.plist"

if [[ ! -f "$TARGET" ]]; then
    echo "No launchd agent installed at $TARGET"
    exit 0
fi

launchctl unload -w "$TARGET" 2>/dev/null || true
rm -f "$TARGET"
echo "Removed $TARGET. The app will no longer sync automatically."
