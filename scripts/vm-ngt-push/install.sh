#!/usr/bin/env bash
# K200 야간선물 polling push — 매 1분 cron
set -euo pipefail

DIR="$HOME/ngt-push"
mkdir -p "$DIR"
cp push.py "$DIR/push.py"
chmod +x "$DIR/push.py"

# .env (GITHUB_PAT)
if [ ! -f "$DIR/.env" ] && [ -f "$HOME/morning/.env" ]; then
  cp "$HOME/morning/.env" "$DIR/.env"
  chmod 600 "$DIR/.env"
  echo "✓ ~/morning/.env 복사"
fi

# runner
cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -e
cd "$HOME/ngt-push"
set -a; . ./.env; set +a
python3 push.py 2>&1
EOF
chmod +x "$DIR/run.sh"

# cron 매 1분
CRON_LINE="* * * * *  $HOME/ngt-push/run.sh >> $HOME/ngt-push/log 2>&1"
( crontab -l 2>/dev/null | grep -v "ngt-push/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo ""
echo "✓ 설치 완료"
echo "  cron:    $CRON_LINE"
echo "  로그:    tail -f $DIR/log"
echo "  수동:    bash $DIR/run.sh"
