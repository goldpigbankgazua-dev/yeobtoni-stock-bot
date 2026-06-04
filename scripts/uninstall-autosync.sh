#!/usr/bin/env bash
LABEL="com.yeobtoni.autosync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "✓ 자동 sync 제거됨"
