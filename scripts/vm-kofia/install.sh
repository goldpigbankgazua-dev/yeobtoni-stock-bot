#!/usr/bin/env bash
# =====================================================================
# VM 측 KOFIA 자동화 설치 — 한 번만 실행
# 실행 위치: Oracle VM (opc 사용자)
# 사전 조건: $GITHUB_PAT 환경변수가 .env에 저장됨
# =====================================================================
set -euo pipefail

INSTALL_DIR="$HOME/kofia"
SCRAPER="$INSTALL_DIR/scraper.py"
ENVFILE="$INSTALL_DIR/.env"
RUNNER="$INSTALL_DIR/run.sh"
LOG_DIR="$INSTALL_DIR/logs"

mkdir -p "$INSTALL_DIR" "$LOG_DIR"

# 1) Python 의존성
python3 -m pip install --user --quiet requests || python3 -m ensurepip --user --quiet

# 2) .env 검증
if [ ! -f "$ENVFILE" ]; then
  echo "ERROR: $ENVFILE 가 없습니다. GITHUB_PAT=ghp_xxx 형식으로 먼저 만드세요."
  exit 1
fi
. "$ENVFILE"
if [ -z "${GITHUB_PAT:-}" ]; then
  echo "ERROR: $ENVFILE 에 GITHUB_PAT 가 설정되지 않았습니다."
  exit 1
fi

# 3) Runner 스크립트
cat > "$RUNNER" <<'EOF'
#!/usr/bin/env bash
set -e
. "$HOME/kofia/.env"
export GITHUB_PAT
LOG="$HOME/kofia/logs/$(date +%Y-%m).log"
echo "[$(date +'%F %T')] === run ===" >> "$LOG"
python3 "$HOME/kofia/scraper.py" >> "$LOG" 2>&1
EOF
chmod +x "$RUNNER"

# 4) cron — KST 19시 매일
CRON_LINE="0 19 * * * $RUNNER"
EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(echo "$EXISTING" | grep -v "$RUNNER" || true)"
printf "%s\n%s\n" "$FILTERED" "$CRON_LINE" | grep -v '^$' | crontab -

# 5) 즉시 1회 실행 — 첫 데이터 박기
echo "→ 첫 실행..."
"$RUNNER"

echo ""
echo "✓ 설치 완료"
echo "  스크립트:  $SCRAPER"
echo "  러너:      $RUNNER"
echo "  cron:      매일 KST 19시"
echo "  로그:      $LOG_DIR/"
echo ""
echo "확인:  crontab -l"
echo "수동:  bash $RUNNER"
