#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — launchd 자동 sync 설치
# ==========================================================
set -euo pipefail

HUB_DIR="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"
SYNC_SH="$HUB_DIR/scripts/sync.sh"
LABEL="com.yeobtoni.autosync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -f "$SYNC_SH" ] || { echo "❌ sync.sh 없음: $SYNC_SH"; exit 1; }
chmod +x "$SYNC_SH"
mkdir -p "$HOME/Library/LaunchAgents"

# 기존 등록 제거
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SYNC_SH</string>
  </array>
  <key>WatchPaths</key>
  <array>
    <string>$HUB_DIR/index.html</string>
    <string>$HUB_DIR/README.md</string>
    <string>$HUB_DIR/modules/rs</string>
    <string>$HUB_DIR/modules/chart</string>
    <string>$HUB_DIR/modules/etf</string>
  </array>
  <key>ThrottleInterval</key>
  <integer>20</integer>
  <key>RunAtLoad</key>
  <false/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$HUB_DIR/scripts/.launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$HUB_DIR/scripts/.launchd.err</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$UID" "$PLIST"
echo "✓ 자동 sync 설치 완료. ${LABEL} 등록됨."
echo "  → 이 폴더 아래 무언가 바뀌면 약 20초 이내 GitHub로 push됩니다."
echo ""
echo "확인:  launchctl list | grep yeobtoni"
echo "제거:  bash scripts/uninstall-autosync.sh"
echo "수동:  bash scripts/sync.sh"
