#!/usr/bin/env bash
# ==========================================================
# 여비또니 주식봇 — 자동 동기화 (좀비 lock 박멸 모드)
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

# ─── 시작 즉시 좀비 git lock 박멸 (조건 없이 무조건) ───
# 이게 핵심: 어떤 이유로든 .git/index.lock이 남아 있으면 무조건 제거.
# 동시 git 실행은 아래 mkdir 락이 막아주므로 안전.
rm -f "$HUB_DIR/.git/index.lock" 2>/dev/null
rm -f "$HUB_DIR"/modules/*/.git/index.lock 2>/dev/null
rm -f "$HUB_DIR"/modules/*/.git/refs/heads/*.lock 2>/dev/null
rm -f "$HUB_DIR"/modules/*/.git/HEAD.lock 2>/dev/null

# ─── 동시 실행 방지 (sync.sh 자체) ───
if ! mkdir "$LOCK" 2>/dev/null; then
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) ))
  if [ "$AGE" -gt 120 ]; then
    rm -rf "$LOCK"; mkdir "$LOCK"
  else
    log "다른 sync 실행 중 (${AGE}초 경과) — 스킵"
    exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT INT TERM HUP

sync_repo() {
  local dir="$1" label="$2"
  [ -d "$dir/.git" ] || { log "  $label: .git 없음 — 스킵"; return; }

  cd "$dir" || { log "  $label: cd 실패"; return; }

  # 진입 시점에도 한 번 더 lock 청소 (이중 안전망)
  rm -f .git/index.lock .git/HEAD.lock 2>/dev/null

  # 로컬 변경 여부
  local has_changes=0
  [ -n "$(git status --porcelain 2>/dev/null)" ] && has_changes=1

  # 원격 동기화 — autostash로 로컬 변경 자동 보존
  if [ "$has_changes" -eq 1 ]; then
    git pull --rebase --autostash --quiet 2>/dev/null
  else
    git pull --rebase --quiet 2>/dev/null
  fi

  # 1) uncommitted 변경 → 커밋
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    git add -A 2>/dev/null
    git -c user.email="$EMAIL" -c user.name="$NAME" \
        commit -m "auto-sync: $(date '+%F %H:%M')" --quiet 2>/dev/null
  fi

  # 2) origin보다 앞선 commit(방금 만들었든 이전 것이든) 있으면 무조건 push
  local ahead
  ahead=$(git rev-list --count @{u}..HEAD 2>/dev/null || echo 0)
  if [ "$ahead" -gt 0 ]; then
    if git push --quiet origin HEAD 2>>"$LOG_FILE"; then
      log "  ✓ $label pushed ($ahead commit)"
    else
      log "  ✗ $label push 실패"
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
