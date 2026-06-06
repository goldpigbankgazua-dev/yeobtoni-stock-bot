#!/usr/bin/env bash
# =====================================================================
# 보고서 작성모듈 폴더 → 여비또니 주식봇/modules/report/data 동기화
# - 보고서작성모듈 폴더의 *.html 을 modules/report/data 로 복사
# - 파일명 파싱해서 index.json 갱신
# - 기존 launchd auto-sync (com.yeobtoni.autosync) 가 GitHub push 처리
# =====================================================================
set -euo pipefail

SRC="$HOME/Documents/Claude/Projects/보고서작성모듈"
DST="$HOME/Documents/Claude/Projects/여비또니 주식봇/modules/report/data"
LOG="$HOME/Library/Logs/com.yeobtoni.reportsync.log"

mkdir -p "$DST"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync start" >> "$LOG"

# 1) *.html 만 sync (mtime 비교, 사양서.md 등 제외)
synced=0
shopt -s nullglob
for f in "$SRC"/*.html; do
  base=$(basename "$f")
  if [ ! -f "$DST/$base" ] || [ "$f" -nt "$DST/$base" ]; then
    cp "$f" "$DST/$base"
    synced=$((synced+1))
    echo "  + $base" >> "$LOG"
  fi
done

# 2) 삭제된 파일 정리 (보고서작성모듈에서 지워진 건 대시보드에서도 제외)
for f in "$DST"/*.html; do
  [ -f "$f" ] || continue
  base=$(basename "$f")
  if [ ! -f "$SRC/$base" ]; then
    rm -f "$f"
    synced=$((synced+1))
    echo "  - $base (removed)" >> "$LOG"
  fi
done

# 3) index.json 갱신 (페이지수 추정 포함)
python3 - "$DST" <<'PY' >> "$LOG" 2>&1
import os, json, re, sys
DST = sys.argv[1]

def estimate_pages(filepath):
    """HTML 본문 텍스트 글자 수로 A4 페이지 수 추정.
    사양서 기준: A4 14mm 마진 + 11pt + 한글 line-height 1.7
    → 한 페이지에 한글 약 1800자 (그래프/표 영역 보정 포함)."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            html = f.read()
    except Exception:
        return 1
    # <style>·<script> 블록 통째로 제거
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.S|re.I)
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S|re.I)
    # 태그 제거
    text = re.sub(r'<[^>]+>', ' ', html)
    # 엔티티/공백 정리
    text = re.sub(r'&[a-z#0-9]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    char_count = len(text)
    if char_count == 0:
        return 1
    # 표·박스가 많으므로 페이지당 1800자로 보정
    return max(1, round(char_count / 1800))

files = sorted([f for f in os.listdir(DST) if f.endswith('.html')])
arr = []
for fn in files:
    name_part = fn[:-5]
    tokens = name_part.split('_')
    is_revision = False
    if tokens and tokens[-1] == '보강판':
        is_revision = True
        tokens = tokens[:-1]
    date_str = ''
    if tokens and re.match(r'^\d{6}$', tokens[-1]):
        d = tokens[-1]
        date_str = f"20{d[:2]}-{d[2:4]}-{d[4:6]}"
        tokens = tokens[:-1]
    market = tokens[0] if tokens else ''
    name = tokens[1] if len(tokens) > 1 else ''
    themes = tokens[2:] if len(tokens) > 2 else []
    pages = estimate_pages(os.path.join(DST, fn))
    arr.append({
        'file': fn,
        'market': market,
        'name': name,
        'themes': themes,
        'date': date_str,
        'revision': is_revision,
        'pages': pages,
    })
arr.sort(key=lambda x: (x['date'] or '', x['name'] or ''), reverse=True)
with open(os.path.join(DST, 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(arr, f, ensure_ascii=False, indent=2)
print(f"  indexed {len(arr)} reports")
PY

echo "[$(date '+%Y-%m-%d %H:%M:%S')] sync done (synced=$synced)" >> "$LOG"

# 4) 변경이 있었으면 hub sync 즉시 트리거 (GitHub push까지 한 번에)
if [ "$synced" -gt 0 ]; then
  HUB_SYNC="$HOME/Library/Application Support/com.yeobtoni.autosync/sync.sh"
  if [ -x "$HUB_SYNC" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] triggering hub sync" >> "$LOG"
    bash "$HUB_SYNC" >> "$LOG" 2>&1 || true
  fi
fi
