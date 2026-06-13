#!/usr/bin/env bash
# AWS Lightsail (yeobtoni-vm) 에서 실행
# - morning scraper 설치 + cron 등록 (매 30분)
# - 환경변수: ~/morning/.env 의 GITHUB_PAT + (선택) KIS_APP_KEY/KIS_APP_SECRET
set -euo pipefail

DIR="$HOME/morning"
mkdir -p "$DIR"
cp scraper.py "$DIR/scraper.py"
chmod +x "$DIR/scraper.py"

pip3 install --user requests >/dev/null 2>&1 || true

# .env — 기존 ~/market/.env (또는 ~/kofia/.env) 에서 자동 복사
if [ ! -f "$DIR/.env" ]; then
  if [ -f "$HOME/market/.env" ]; then
    cp "$HOME/market/.env" "$DIR/.env"
    echo "✓ ~/market/.env 그대로 복사"
  elif [ -f "$HOME/kofia/.env" ]; then
    cp "$HOME/kofia/.env" "$DIR/.env"
    echo "✓ ~/kofia/.env 복사 (KIS 키 없으면 K200 야간은 Yahoo fallback)"
  else
    cat > "$DIR/.env" <<EOF
GITHUB_PAT=
KIS_APP_KEY=
KIS_APP_SECRET=
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

# cron — 매 30분 (KST 거의 항상 야간/해외 거래 시간이라 자주)
CRON_LINE="*/30 * * * *  $HOME/morning/run.sh >> $HOME/morning/log 2>&1"
( crontab -l 2>/dev/null | grep -v "morning/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo ""
echo "✓ 설치 완료"
echo "  cron: $CRON_LINE"
echo "  수동 테스트: bash $DIR/run.sh"
