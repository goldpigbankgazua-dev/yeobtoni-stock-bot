#!/usr/bin/env bash
LABEL="com.yeobtoni.autosync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INSTALL_DIR="$HOME/Library/Application Support/$LABEL"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
rm -rf "$INSTALL_DIR"
echo "✓ 자동 sync 제거됨 (plist + Library 사본 + 로그)"
