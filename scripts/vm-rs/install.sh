#!/usr/bin/env bash
# Oracle VM (opc@168.110.125.122) 에서 실행
#  - rs-screener-kr 리포 clone
#  - cron 등록 (평일 21시 KST = 12 UTC)
#  - 환경변수: ~/rs/.env 에 GITHUB_PAT 만 있으면 됨
#  - 의존성: rs 리포의 scripts/requirements.txt 그대로 사용
set -euo pipefail

DIR="$HOME/rs"
REPO_URL="https://github.com/goldpigbankgazua-dev/rs-screener-kr.git"

# git 없으면 설치 (Oracle Linux)
if ! command -v git >/dev/null 2>&1; then
  echo "→ git 설치 중 (sudo dnf install -y git)…"
  sudo dnf install -y git
fi

mkdir -p "$DIR"
cd "$DIR"

if [ ! -d repo/.git ]; then
  git clone "$REPO_URL" repo
fi

# .env — 기존 ~/kofia/.env 에서 GITHUB_PAT 자동 복사
if [ ! -f "$DIR/.env" ]; then
  KOFIA_PAT=""
  if [ -f "$HOME/kofia/.env" ]; then
    KOFIA_PAT="$(grep -E '^GITHUB_PAT=' "$HOME/kofia/.env" | head -1 | cut -d= -f2-)"
  fi
  cat > "$DIR/.env" <<EOF
GITHUB_PAT=${KOFIA_PAT}
EOF
  chmod 600 "$DIR/.env"
  if [ -n "$KOFIA_PAT" ]; then
    echo "✓ GITHUB_PAT 자동 복사됨 (~/kofia/.env)"
  else
    echo "⚠️  $DIR/.env 파일에 GITHUB_PAT 채워주세요"
  fi
fi

# 의존성
cd repo
pip3 install --user -r scripts/requirements.txt >/dev/null 2>&1 \
  || sudo pip3 install -r scripts/requirements.txt
cd ..

# runner
cat > "$DIR/run.sh" <<'EOF'
#!/usr/bin/env bash
set -e
cd "$HOME/rs"
set -a; . ./.env; set +a
cd repo

# 최신 main 받기
git fetch origin main --quiet
git reset --hard origin/main --quiet

# 데이터 생성
python3 scripts/update_data.py

# 변경분 push (git 인증은 PAT 사용)
if git diff --quiet data/stocks.json; then
  echo "변경 없음"
  exit 0
fi
git config user.name  "vm-rs-bot"
git config user.email "vm-rs@yeobtoni.local"
git add data/stocks.json
git commit -m "data: rs $(date -u +%Y-%m-%d)"
git push "https://x-access-token:${GITHUB_PAT}@github.com/goldpigbankgazua-dev/rs-screener-kr.git" main
EOF
chmod +x "$DIR/run.sh"

# cron: 평일 21시 KST = 12 UTC
CRON_LINE="0 12 * * 1-5  $HOME/rs/run.sh >> $HOME/rs/log 2>&1"
( crontab -l 2>/dev/null | grep -v "rs/run.sh" ; echo "$CRON_LINE" ) | crontab -

echo "✓ 설치 완료"
echo "  cron: $CRON_LINE"
echo "  수동 테스트: bash $DIR/run.sh"
