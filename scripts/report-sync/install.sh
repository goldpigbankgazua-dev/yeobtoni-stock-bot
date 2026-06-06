#!/usr/bin/env bash
# =====================================================================
# 보고서 sync launchd 설치 (Library 경로로 실행 — Sequoia 권한 우회)
# =====================================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.yeobtoni.reportsync"
SRC_SYNC="$DIR/sync.sh"
INSTALL_DIR="$HOME/Library/Application Support/$LABEL"
INSTALLED_SYNC="$INSTALL_DIR/sync.sh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

[ -f "$SRC_SYNC" ] || { echo "❌ sync.sh 없음: $SRC_SYNC"; exit 1; }

mkdir -p "$INSTALL_DIR" "$HOME/Library/LaunchAgents"

# 1) sync.sh 를 Library 로 복사 (Documents 외부 실행 가능 위치)
cp "$SRC_SYNC" "$INSTALLED_SYNC"
chmod +x "$INSTALLED_SYNC"

# 2) 기존 등록 해제
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true

# 3) plist 작성 — 실행은 Library, 감시는 Documents
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

    <!-- 보고서작성모듈 폴더 변경 감지 -->
    <key>WatchPaths</key>
    <array>
        <string>$HOME/Documents/Claude/Projects/보고서작성모듈</string>
    </array>

    <!-- 안전망: 1분마다 강제 sync -->
    <key>StartInterval</key>
    <integer>60</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/$LABEL.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/$LABEL.log</string>
</dict>
</plist>
EOF

# 4) 로드
launchctl bootstrap "gui/$UID" "$PLIST"

# 5) 즉시 1회 실행
bash "$INSTALLED_SYNC"

echo ""
echo "✓ 설치 완료 (Library 경로 모드)"
echo "  실행본:   $INSTALLED_SYNC"
echo "  plist:    $PLIST"
echo "  로그:     ~/Library/Logs/$LABEL.log"
echo "  감시:     ~/Documents/Claude/Projects/보고서작성모듈/"
echo "  주기:     60초 (변경 감지 + 1분 안전망)"
echo "  수동실행: bash '$INSTALLED_SYNC'"
echo "  해제:     launchctl bootout gui/\$UID/$LABEL"
