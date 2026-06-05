#!/usr/bin/env bash
# ==========================================================
# screening_result.html → modules/chart/index.html 자동 미러
#
# daily-stock-screener SKILL이 5단계(cp) 건너뛰어도
# launchd가 파일 변경 감지 시 자동 복사 → sync.sh가 GitHub push
# ==========================================================
set -euo pipefail

LABEL="com.yeobtoni.chartmirror"
INSTALL_DIR="$HOME/Library/Application Support/$LABEL"
SCRIPT="$INSTALL_DIR/mirror.sh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$INSTALL_DIR/logs"

SRC="/Users/yeob/Desktop/클로드/클로드_일봉데이터/screening_result.html"
DST="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇/modules/chart/index.html"

mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

# 기존 등록 제거
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true

# 1) mirror.sh — 실제 복사 로직
cat > "$SCRIPT" <<'EOF'
#!/usr/bin/env bash
SRC="/Users/yeob/Desktop/클로드/클로드_일봉데이터/screening_result.html"
DST="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇/modules/chart/index.html"
LOG="$HOME/Library/Application Support/com.yeobtoni.chartmirror/logs/mirror.log"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# 소스 없으면 종료
[ -f "$SRC" ] || { log "src 없음 — 스킵"; exit 0; }

# 사이즈/mtime이 같으면 변경 없음
if [ -f "$DST" ]; then
  SRC_MT=$(stat -f %m "$SRC" 2>/dev/null || echo 0)
  DST_MT=$(stat -f %m "$DST" 2>/dev/null || echo 0)
  SRC_SZ=$(stat -f %z "$SRC" 2>/dev/null || echo 0)
  DST_SZ=$(stat -f %z "$DST" 2>/dev/null || echo 0)
  if [ "$SRC_MT" = "$DST_MT" ] && [ "$SRC_SZ" = "$DST_SZ" ]; then
    log "변경 없음 — 스킵"; exit 0
  fi
fi

# 복사
if cp "$SRC" "$DST" 2>>"$LOG"; then
  log "✓ 복사: src $(stat -f %z "$SRC")B → dst"
else
  log "✗ 복사 실패"
fi
EOF
chmod +x "$SCRIPT"

# 2) plist — screening_result.html 변경 감지
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
    <string>$SCRIPT</string>
  </array>
  <key>WatchPaths</key>
  <array>
    <string>$SRC</string>
  </array>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>StartInterval</key>
  <integer>300</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>EnvironmentVariables</key>
  <dict>
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

# 3) 부트스트랩
launchctl bootstrap "gui/$UID" "$PLIST"

echo "✓ chart-mirror 설치 완료"
echo "  스크립트: $SCRIPT"
echo "  로그:     $LOG_DIR/"
echo "  플리스트: $PLIST"
echo "  감시:     $SRC"
echo "  대상:     $DST"
echo ""
echo "확인:  launchctl list | grep chartmirror"
echo "수동:  bash \"$SCRIPT\""
echo "제거:  launchctl bootout gui/\$UID/$LABEL && rm \"$PLIST\""
