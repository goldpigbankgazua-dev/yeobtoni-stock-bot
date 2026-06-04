#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — launchd 자동 sync 설치
# ----------------------------------------------------------
# macOS Sequoia+ 가 Documents 폴더 안의 스크립트 실행을 막기 때문에,
# 실행되는 sync.sh 는 ~/Library/Application Support/com.yeobtoni.autosync/
# 로 복사하고, 거기서 Documents 폴더의 작업트리를 sync 합니다.
# ==========================================================
set -euo pipefail

HUB_DIR="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"
SRC_SYNC="$HUB_DIR/scripts/sync.sh"
LABEL="com.yeobtoni.autosync"
INSTALL_DIR="$HOME/Library/Application Support/$LABEL"
INSTALLED_SYNC="$INSTALL_DIR/sync.sh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$INSTALL_DIR/logs"

[ -f "$SRC_SYNC" ] || { echo "❌ sync.sh 없음: $SRC_SYNC"; exit 1; }

mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

# 1) sync.sh 를 Library 로 복사 (Documents 외부 실행 가능 위치)
cp "$SRC_SYNC" "$INSTALLED_SYNC"
chmod +x "$INSTALLED_SYNC"

# 2) 기존 등록 제거
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true

# 3) plist 작성 — 실행 파일은 Library, 감시는 Documents
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
    <string>$INSTALLED_SYNC</string>
  </array>
  <key>WatchPaths</key>
  <array>
    <string>$HUB_DIR/index.html</string>
    <string>$HUB_DIR/README.md</string>
    <string>$HUB_DIR/modules/rs/index.html</string>
    <string>$HUB_DIR/modules/chart/index.html</string>
    <string>$HUB_DIR/modules/etf/index.html</string>
  </array>
  <key>ThrottleInterval</key>
  <integer>20</integer>
  <key>StartInterval</key>
  <integer>45</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/launchd.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/launchd.err</string>
</dict>
</plist>
EOF

# 4) 부트스트랩
launchctl bootstrap "gui/$UID" "$PLIST"

echo "✓ 자동 sync 재설치 완료"
echo ""
echo "  실행 파일: $INSTALLED_SYNC"
echo "  로그:      $LOG_DIR/"
echo "  플리스트:  $PLIST"
echo ""
echo "확인:  launchctl list | grep yeobtoni"
echo "수동:  bash \"$INSTALLED_SYNC\""
echo "제거:  bash \"$HUB_DIR/scripts/uninstall-autosync.sh\""
echo ""
echo "※ sync.sh 를 수정했다면 다시 이 스크립트 실행으로 복사·재등록."
