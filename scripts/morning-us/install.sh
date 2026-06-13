#!/usr/bin/env bash
# =====================================================================
# 미국 선물 (NQ/ES/GC) 15분 지연 cron — 맥 launchd
# 1분마다 Yahoo Finance fetch → modules/morning/data/us_quotes.json
# autosync launchd 가 자동으로 git push 함
# =====================================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SCRAPER="$DIR/scraper.py"
PLIST_NAME="com.yeobtoni.morning-us.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
LOG_DIR="$HOME/Library/Logs/yeobtoni"
LOG_OUT="$LOG_DIR/morning-us.log"
LOG_ERR="$LOG_DIR/morning-us.err"

mkdir -p "$LOG_DIR"

PY3="$(command -v python3 || echo /usr/bin/python3)"

# plist 생성 — 1분 간격
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.yeobtoni.morning-us</string>

  <key>ProgramArguments</key>
  <array>
    <string>$PY3</string>
    <string>$SCRAPER</string>
  </array>

  <key>StartInterval</key>
  <integer>60</integer>

  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$LOG_OUT</string>

  <key>StandardErrorPath</key>
  <string>$LOG_ERR</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF

# 기존 등록 제거 후 재등록
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo "✓ launchd 등록 완료"
echo "  plist:  $PLIST_PATH"
echo "  스크립트: $SCRAPER"
echo "  로그:   $LOG_OUT"
echo "  간격:   60초 (1분마다)"
echo ""
echo "수동 실행 테스트:"
echo "  $PY3 $SCRAPER"
echo ""
echo "로그 보기:"
echo "  tail -f $LOG_OUT"
echo ""
echo "제거:"
echo "  launchctl unload $PLIST_PATH && rm $PLIST_PATH"
