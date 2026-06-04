#!/usr/bin/env bash
# ==========================================================
# chart-screener-kr + chart-screener 모두 삭제 후,
# screening_result.html을 새 chart-screener 리포로 클린 배포
# ==========================================================
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

USER="goldpigbankgazua-dev"
SRC_HTML="/Users/yeob/Desktop/클로드/클로드_일봉데이터/screening_result.html"
WORK="/tmp/chart-screener-migrate"

# 사전 체크
[ -f "$SRC_HTML" ] || { echo "❌ 소스 HTML 없음: $SRC_HTML"; exit 1; }
command -v gh >/dev/null || { echo "❌ gh 필요"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "❌ gh auth login 먼저"; exit 1; }

# gh repo delete 권한이 있는지 확인
if ! gh auth status 2>&1 | grep -q "delete_repo"; then
  echo "⚠️  gh에 delete_repo 권한이 없어요. 권한 추가합니다."
  echo "   브라우저가 열리면 Authorize 누르세요."
  gh auth refresh -h github.com -s delete_repo
fi

# ── 1) 기존 chart-* 리포 2개 삭제
echo ""
echo "── 1/3: 기존 리포 삭제 ──"
for repo in chart-screener chart-screener-kr; do
  if gh repo view "$USER/$repo" >/dev/null 2>&1; then
    echo "  삭제: $repo"
    gh repo delete "$USER/$repo" --yes
  else
    echo "  없음: $repo (스킵)"
  fi
done

# ── 2) 새 chart-screener 생성 + 푸시
echo ""
echo "── 2/3: 새 chart-screener 생성 + 푸시 ──"
rm -rf "$WORK" && mkdir -p "$WORK"
cp "$SRC_HTML" "$WORK/index.html"
cat > "$WORK/README.md" <<'EOF'
# Chart Screener — 고점 후 눌림목

한국 주식 '고점 후 눌림목' 패턴 데일리 스크리너.
TradingView 차트 연동.

자동 업데이트: 평일 저녁 9시 (KST), 데일리 스크리너 스케줄 작업.
EOF

cd "$WORK"
git init -b main >/dev/null
git add .
git -c user.email="${USER}@users.noreply.github.com" -c user.name="$USER" \
    commit -m "feat: init daily stock screener with tradingview" --quiet

gh repo create "$USER/chart-screener" \
  --public \
  --description "Daily stock screener — 고점 후 눌림목 패턴 (TradingView 연동)" \
  --source=. --remote=origin --push

# ── 3) Pages 활성화
echo ""
echo "── 3/3: Pages 활성화 ──"
sleep 2
gh api -X POST "repos/$USER/chart-screener/pages" \
  -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1 \
|| gh api -X PUT "repos/$USER/chart-screener/pages" \
  -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1 \
|| echo "  (Pages 이미 켜져 있거나 응답 변경 — 무시)"

# 정리
cd /tmp
rm -rf "$WORK"

echo ""
echo "🎉 마이그레이션 완료!"
echo ""
echo "  새 URL: https://$USER.github.io/chart-screener/"
echo "  Pages 빌드 1~2분 후 접속 가능"
echo ""
echo "허브의 CHART 탭 URL도 이미 갱신되어 있어요 (index.html)."
