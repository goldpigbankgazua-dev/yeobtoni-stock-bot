#!/usr/bin/env bash
# =====================================================================
# ETF CHECK 스크래퍼 설치 — Mac
# 1. Node.js 확인 (없으면 안내)
# 2. npm install playwright
# 3. Chromium 다운로드 (Playwright)
# 4. 첫 스크랩 1회 (수익률만 검증)
# =====================================================================
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 1) Node.js
if ! command -v node >/dev/null 2>&1; then
  echo "❌ Node.js가 없습니다."
  echo "   설치: https://nodejs.org/ 또는 'brew install node'"
  exit 1
fi
echo "✓ Node.js $(node -v)"

# 2) npm install
echo "→ npm install playwright (~30초)..."
npm install --silent

# 3) Chromium 다운로드 (~200MB, 한 번만)
echo "→ Playwright Chromium 다운로드..."
npx playwright install chromium

# 4) 수익률 검증 스크랩 1회
echo ""
echo "→ 첫 스크랩 시도 (수익률 1개 카테고리)..."
node scraper.js yield || { echo "❌ 스크랩 실패"; exit 1; }

echo ""
echo "✓ 설치 완료"
echo "  스크립트:  $DIR/scraper.js"
echo "  결과:      $DIR/../../modules/etfstatus/data/yield.json"
echo ""
echo "수동 실행:"
echo "  cd '$DIR' && node scraper.js          # 전체"
echo "  cd '$DIR' && node scraper.js yield    # 수익률만"
