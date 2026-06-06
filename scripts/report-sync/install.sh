#!/usr/bin/env bash
# =====================================================================
# 보고서 sync launchd 설치 (한 번만 실행)
# =====================================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$DIR/com.yeobtoni.reportsync.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.yeobtoni.reportsync.plist"

# 1) sync.sh 실행권한
chmod +x "$DIR/sync.sh"

# 2) 기존 등록 해제 (있으면)
launchctl bootout "gui/$(id -u)/com.yeobtoni.reportsync" 2>/dev/null || true

# 3) plist 복사 + 로드
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

# 4) 즉시 1회 실행 (초기 sync)
bash "$DIR/sync.sh"

echo ""
echo "✓ 설치 완료"
echo "  plist:   $PLIST_DST"
echo "  로그:    ~/Library/Logs/com.yeobtoni.reportsync.log"
echo "  수동실행: bash '$DIR/sync.sh'"
echo "  해제:    launchctl bootout gui/\$(id -u)/com.yeobtoni.reportsync"
