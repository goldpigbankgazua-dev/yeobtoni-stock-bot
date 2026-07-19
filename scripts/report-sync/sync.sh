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

# 실제 렌더 페이지수 캐시 (파일명 -> {pages, size}). 크기가 같으면 재렌더 안 함.
CACHE_PATH = os.path.join(DST, '.pages_cache.json')
try:
    with open(CACHE_PATH, encoding='utf-8') as f:
        PAGES_CACHE = json.load(f)
except Exception:
    PAGES_CACHE = {}

def _render_pages(filepath):
    """weasyprint 실제 A4 렌더 페이지수. 없거나 실패하면 None."""
    try:
        from weasyprint import HTML
        return len(HTML(filepath).render().pages)
    except Exception:
        return None

def _heuristic_pages(filepath):
    """폴백: 본문 글자수 기반 추정 (표·박스 많은 양식 보정)."""
    try:
        with open(filepath, encoding='utf-8', errors='replace') as f:
            html = f.read()
    except Exception:
        return 1
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.S|re.I)
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S|re.I)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-z#0-9]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return max(1, round(len(text) / 1100)) if text else 1

def estimate_pages(filepath):
    """실제 렌더 페이지수 우선. 캐시(크기 일치) → weasyprint → 휴리스틱 순."""
    fn = os.path.basename(filepath)
    try:
        size = os.path.getsize(filepath)
    except Exception:
        size = -1
    hit = PAGES_CACHE.get(fn)
    if hit and hit.get('size') == size and hit.get('pages'):
        return hit['pages']
    pages = _render_pages(filepath)
    if pages is None:
        pages = _heuristic_pages(filepath)
    else:
        PAGES_CACHE[fn] = {'pages': pages, 'size': size}
    return pages

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
# 캐시 저장 (삭제된 파일 정리 후)
existing = set(files)
PAGES_CACHE = {k: v for k, v in PAGES_CACHE.items() if k in existing}
try:
    with open(CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(PAGES_CACHE, f, ensure_ascii=False)
except Exception:
    pass
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
