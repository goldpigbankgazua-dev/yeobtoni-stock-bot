#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — 통합관리 구조 초기 셋업
# ----------------------------------------------------------
# 무엇을 하나:
#  1) 여비또니 주식봇/ 자체를 yeobtoni-stock-bot 리포로 git 연결
#  2) modules/{rs,chart,etf}/ 에 3개 모듈 클론
#  3) .gitignore 정리
#  4) launchd 자동 sync 설치
# ----------------------------------------------------------
# 한 번만 실행:
#   bash "/Users/yeob/Documents/Claude/Projects/여비또니 주식봇/scripts/bootstrap.sh"
# ==========================================================
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

USER="goldpigbankgazua-dev"
HUB_DIR="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"

# ---------- 사전 체크 ----------
command -v gh  >/dev/null || { echo "❌ gh 필요"; exit 1; }
command -v git >/dev/null || { echo "❌ git 필요"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "❌ gh auth login 먼저"; exit 1; }

cd "$HUB_DIR"

# ---------- 1) 허브 폴더 git 연결 (로컬 변경 보존) ----------
echo "── 1/5: 허브 git 연결 ──"
if [ ! -d .git ]; then
  git init -b main >/dev/null
  git remote add origin "https://github.com/$USER/yeobtoni-stock-bot.git"
  git fetch origin main --quiet
  # --mixed: HEAD만 origin/main으로, 작업트리는 로컬 그대로 유지
  git reset --mixed origin/main 2>/dev/null || true
  echo "  ✓ git init + 원격 연결 (로컬 파일 보존)"
else
  echo "  ✓ 이미 git 폴더"
fi

# ---------- 2) .gitignore + 잔재 정리 ----------
echo "── 2/5: .gitignore + 정리 ──"
cat > .gitignore <<'EOF'
# 모듈은 각자 자기 리포로 별도 push (이 리포에는 포함하지 않음)
modules/
# 잔재
patches/
setup.sh
# 스크립트 로그·캐시
scripts/.sync.log
scripts/.launchd.log
scripts/.launchd.err
scripts/.repos.json
# 시스템
.DS_Store
EOF
# 더 이상 안 쓰는 잔재 삭제 (있는 것만)
rm -f setup.sh 2>/dev/null || true
rm -rf patches 2>/dev/null || true
echo "  ✓ .gitignore 작성 + 잔재 제거"

# ---------- 3) 허브 로컬 변경분 push ----------
echo "── 3/5: 허브 로컬 변경분 push ──"
git add -A
if git diff --cached --quiet 2>/dev/null; then
  echo "  변경 없음"
else
  git -c user.email="${USER}@users.noreply.github.com" \
      -c user.name="$USER" \
      commit -m "feat: hub theme system + tab rename" --quiet
  git push origin main && echo "  ✓ 허브 push 완료" || echo "  ⚠️  push 실패 (수동 확인 필요)"
fi

# ---------- 4) 3개 모듈 클론 ----------
echo "── 4/5: 모듈 3개 클론 ──"
mkdir -p modules

clone_or_pull () {
  local repo="$1" path="modules/$2"
  if [ -d "$path/.git" ]; then
    (cd "$path" && git pull --rebase --quiet 2>/dev/null) && echo "  ✓ $repo 최신화"
  else
    rm -rf "$path"
    gh repo clone "$USER/$repo" "$path" -- -q && echo "  ✓ $repo 클론"
  fi
}

clone_or_pull rs-screener-kr     rs
clone_or_pull chart-screener    chart
clone_or_pull kr-new-listed-etf etf

# ---------- 5) launchd 자동 sync ----------
echo "── 5/5: 자동 sync 설치 ──"
bash "$HUB_DIR/scripts/install-autosync.sh"

# ---------- 마무리 ----------
echo ""
echo "🎉 통합관리 구조 셋업 완료!"
echo ""
echo "구조:"
echo "  여비또니 주식봇/"
echo "  ├── index.html          ← 허브 (→ yeobtoni-stock-bot)"
echo "  ├── modules/"
echo "  │   ├── rs/             ← rs-screener-kr"
echo "  │   ├── chart/          ← chart-screener"
echo "  │   └── etf/            ← kr-new-listed-etf"
echo "  └── scripts/sync.sh     (launchd 자동 호출됨)"
echo ""
echo "이제 이 폴더 아무 파일이나 수정하면 ~20초 안에 알아서 GitHub로 push됩니다."
