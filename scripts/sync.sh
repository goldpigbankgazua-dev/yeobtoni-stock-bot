#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — 변경분 자동 동기화
# launchd 워처 / 수동 실행 모두 지원
# ==========================================================
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

HUB_DIR="/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"
LOG_DIR="$HOME/Library/Application Support/com.yeobtoni.autosync/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG_FILE="$LOG_DIR/sync.log"
LOCK="/tmp/yeobtoni-sync.lock"
EMAIL="goldpigbankgazua@users.noreply.github.com"
NAME="goldpigbankgazua-dev"

log() {
  local msg="[$(date '+%F %T')] $*"
  echo "$msg"
  echo "$msg" >> "$LOG_FILE" 2>/dev/null || true
}

# 동시 실행 방지 (macOS 호환 mkdir 락)
if ! mkdir "$LOCK" 2>/dev/null; then
  AGE_MIN=$(( ( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ) / 60 ))
  if [ "$AGE_MIN" -gt 1 ]; then
    rm -rf "$LOCK"; mkdir "$LOCK"
  else
    log "다른 sync 실행 중 (${AGE_MIN}분 경과) — 스킵"
    exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT INT TERM

sync_repo() {
  local dir="$1" label="$2"

  if [ ! -d "$dir/.git" ]; then
    log "  $label: .git 없음 — 스킵"
    return
  fi

  cd "$dir" || { log "  $label: cd 실패"; return; }

  # 원격 동기화 시도
  git fetch origin --quiet 2>/dev/null || log "  $label: fetch 실패 (네트워크?)"

  local branch local_sha remote_sha
  branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
  local_sha=$(git rev-parse HEAD 2>/dev/null)
  remote_sha=$(git rev-parse "origin/$branch" 2>/dev/null)

  local has_changes=0
  [ -n "$(git status --porcelain 2>/dev/null)" ] && has_changes=1

  # 원격이 앞서 있으면 rebase (로컬 변경은 stash로 보존)
  if [ -n "$remote_sha" ] && [ "$local_sha" != "$remote_sha" ]; then
    if [ "$has_changes" -eq 1 ]; then
      git stash push -u -m "autosync-tmp" --quiet 2>/dev/null
      git pull --rebase --quiet 2>/dev/null || { log "  $label: rebase 실패"; git rebase --abort 2>/dev/null; git stash pop --quiet 2>/dev/null; return; }
      git stash pop --quiet 2>/dev/null
    else
      git pull --rebase --quiet 2>/dev/null
    fi
  fi

  # 로컬 변경분 커밋·푸시
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    git add -A
    git -c user.email="$EMAIL" -c user.name="$NAME" \
        commit -m "auto-sync: $(date '+%F %H:%M')" --quiet
    if git push --quiet origin "$branch" 2>>"$LOG_FILE"; then
      log "  ✓ $label pushed"
    else
      log "  ✗ $label push 실패 (자격증명/네트워크 확인)"
    fi
  else
    log "  · $label: 변경 없음"
  fi
}

log "── sync 시작 ──"
sync_repo "$HUB_DIR/modules/rs"    "RS"
sync_repo "$HUB_DIR/modules/chart" "CHART"
sync_repo "$HUB_DIR/modules/etf"   "ETF"
sync_repo "$HUB_DIR"               "HUB"
log "── sync 끝 ──"
