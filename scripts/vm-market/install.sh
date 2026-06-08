#!/usr/bin/env bash
# Oracle VM (opc@168.110.125.122) 에서 실행
#  - market scraper 설치 + cron 등록
#  - 환경변수 KIS_APP_KEY / KIS_APP_SECRET / GITHUB_PAT 은 ~/market/.env 에서 로드
set -euo pipefail

DIR="$HOME/market"
mkdir -p "$DIR"
cp scraper.py "$DIR/scraper.py"
chmod +x "$DIR/scraper.py"

# 의존성
pip3 install --user requests >/dev/null 2>&1 || sudo pip3 install requests

# .env 템플릿 (이미 있으면 안 건드림)
if [ ! -f "$DIR/.env" ]; then
  cat > "$DIR/.env" <<'EOF'
KIS_APP_KEY=
KIS_APP_SECRET=
GITHUB_PAT=
EOF
  chmod 600 "$DIR/.env"
  echo "⚠️  $DIR/.env 파일에 키 3개 채워주세요"
fi

# runner 스크립트 (.env 로드 + 로그 기록)
cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -e
cd "$HOME/market"
set -a; . ./.env; set +a
python3 scraper.py 2>&1
EOF
chmod +x "$DIR/run.sh"

# cron 등록 (KST 18:00 = UTC 09:00, 평일)
CRON_LINE="0 9 * * 1-5  $HOME/market/run.sh >> $HOME/market/log 2>&1"
( crontab -l 2>/dev/null | grep -v "market/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo "✓ 설치 완료"
echo "  cron: $CRON_LINE"
echo "  수동 테스트: bash $DIR/run.sh"
