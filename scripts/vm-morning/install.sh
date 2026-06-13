#!/usr/bin/env bash
# AWS Lightsail (yeobtoni-vm) 에서 실행
# - morning US 선물 (NQ/ES/GC) scraper 설치 + cron 등록 (매 1분)
# - Yahoo v8 chart endpoint (Lightsail IP 통과 확인됨)
# - 환경변수: ~/morning/.env 의 GITHUB_PAT
set -euo pipefail

DIR="$HOME/morning"
mkdir -p "$DIR"
cp scraper.py "$DIR/scraper.py"
chmod +x "$DIR/scraper.py"

# .env — 기존 ~/market/.env 에서 GITHUB_PAT 복사
if [ ! -f "$DIR/.env" ]; then
  if [ -f "$HOME/market/.env" ]; then
    cp "$HOME/market/.env" "$DIR/.env"
    echo "✓ ~/market/.env 그대로 복사"
  elif [ -f "$HOME/kofia/.env" ]; then
    cp "$HOME/kofia/.env" "$DIR/.env"
    echo "✓ ~/kofia/.env 복사"
  else
    cat > "$DIR/.env" <<EOF
GITHUB_PAT=
EOF
    echo "⚠️  $DIR/.env 의 GITHUB_PAT 채워주세요"
  fi
  chmod 600 "$DIR/.env"
fi

# runner
cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -e
cd "$HOME/morning"
set -a; . ./.env; set +a
python3 scraper.py 2>&1
EOF
chmod +x "$DIR/run.sh"

# cron — 매 1분 (장시간 외엔 가격 변동 거의 없어도 비용/부담 미미)
CRON_LINE="* * * * *  $HOME/morning/run.sh >> $HOME/morning/log 2>&1"
( crontab -l 2>/dev/null | grep -v "morning/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo ""
echo "✓ 설치 완료"
echo "  cron:    $CRON_LINE"
echo "  수동 테스트: bash $DIR/run.sh"
echo "  로그:    tail -f $DIR/log"
