#!/usr/bin/env bash
# AWS Lightsail (yeobtoni-vm) — 매크로 (FRED) scraper cron
# - 매 4시간 (KST 02/06/10/14/18/22) — FRED publish 다양한 시점 catch-up
# - GitHub Action 비활성화 권장 (충돌 방지)
set -euo pipefail

DIR="$HOME/macro"
mkdir -p "$DIR"
cp fetch_macro.py "$DIR/fetch_macro.py"
chmod +x "$DIR/fetch_macro.py"

pip3 install --user --break-system-packages requests >/dev/null 2>&1 || true

# .env — 기존 ~/market/.env 에서 GITHUB_PAT 복사. FRED_API_KEY 는 별도 추가 필요.
if [ ! -f "$DIR/.env" ]; then
  if [ -f "$HOME/market/.env" ]; then
    cp "$HOME/market/.env" "$DIR/.env"
    echo "✓ ~/market/.env 복사"
  else
    echo "GITHUB_PAT=" > "$DIR/.env"
  fi
  # FRED_API_KEY 자리 표시 (사용자가 채워야 함)
  if ! grep -q "^FRED_API_KEY=" "$DIR/.env"; then
    echo "FRED_API_KEY=" >> "$DIR/.env"
  fi
  chmod 600 "$DIR/.env"
  echo "⚠️  ~/macro/.env 의 FRED_API_KEY 채워주세요"
fi

# runner
cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -e
cd "$HOME/macro"
set -a; . ./.env; set +a
python3 fetch_macro.py 2>&1
EOF
chmod +x "$DIR/run.sh"

# cron — 4시간마다 (UTC 17/21/01/05/09/13 = KST 02/06/10/14/18/22)
CRON_LINE="17 */4 * * *  $HOME/macro/run.sh >> $HOME/macro/log 2>&1"
( crontab -l 2>/dev/null | grep -v "macro/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo ""
echo "✓ 설치 완료"
echo "  cron:    $CRON_LINE"
echo "  로그:    tail -f $DIR/log"
echo "  수동:    bash $DIR/run.sh"
echo ""
echo "⚠️  GitHub Action (update-macro.yml) 비활성화 권장 — 충돌 방지"
