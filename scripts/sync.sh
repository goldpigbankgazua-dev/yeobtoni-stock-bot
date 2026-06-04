#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — 변경분 자동 동기화
# 호출 경로: launchd 워처 / 수동 실행 모두 지원
# ==========================================================

set -uo pipefail

# launchd 환경에서도 brew 경로 인식되도록
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

HUB_DIR="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"
LOG="$HUB_DIR/scripts/.sync.log"
LOCK="/tmp/yeobtoni-sync.lock"

# 동시 실행 방지
exec 9>"$LOCK"
flock -n 9 || { echo "[$(date '+%F %T')] 다른 sync 실행 중 — 스킵" >>"$LOG"; exit 0; }

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

sync_repo() {
  local dir="$1"
  local label="$2"

  [ -d "$dir/.git" ] || { log "  skip $label (no .git)"; return; }

  cd "$dir" || return

  # 변경 감지 (untracked + modified)
  local has_changes=0
  if [ -n "$(git status --porcelain)" ]; then has_changes=1; fi

  # 원격 변경 가져오기
  git fetch origin --quiet 2>>"$LOG" || true

  local local_sha remote_sha
  local_sha=$(git rev-parse HEAD 2>/dev/null || echo "none")
  remote_sha=$(git rev-parse "origin/$(git rev-parse --abbrev-ref HEAD)" 2>/dev/null || echo "none")

  # 원격이 앞서 있으면 rebase
  if [ "$local_sha" != "$remote_sha" ] && [ "$remote_sha" != "none" ]; then
    if [ "$has_changes" -eq 1 ]; then
      git stash push -u -m "autosync-temp" >/dev/null 2>>"$LOG"
      git pull --rebase --quiet 2>>"$LOG" || { log "  ✗ $label rebase failed"; git rebase --abort 2>/dev/null; git stash pop 2>/dev/null; return; }
      git stash pop >/dev/null 2>>"$LOG" || true
    else
      git pull --rebase --quiet 2>>"$LOG" || log "  ✗ $label pull failed"
    fi
  fi

  # 로컬 변경 커밋 + 푸시
  if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "auto-sync: $(date '+%F %H:%M')" --quiet 2>>"$LOG" || true
    if git push --quiet 2>>"$LOG"; then
      log "  ✓ $label pushed"
    else
      log "  ✗ $label push failed"
    fi
  fi
}

log "── sync start ──"
sync_repo "$HUB_DIR/modules/rs"    "RS"
sync_repo "$HUB_DIR/modules/chart" "CHART"
sync_repo "$HUB_DIR/modules/etf"   "ETF"
sync_repo "$HUB_DIR"               "HUB"
log "── sync end ──"
