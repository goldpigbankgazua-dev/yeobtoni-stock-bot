#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — Twelve Data API (NQ/ES/GC/DXY).

Twelve Data 무료 등급: 800 calls/day, multi-symbol single call 지원.
1 호출 = 4종목 → 5분 cron 으로 288 호출/day (한도 800 안에 여유).
Yahoo IP throttle 회피 — 토큰 인증으로 안정적.

env:
  GITHUB_PAT       — yeobtoni-stock-bot 리포 쓰기 권한
  TWELVEDATA_KEY   — twelvedata.com Dashboard 의 API Key
"""
import os
import json
import ssl
import sys
import subprocess
import urllib.parse
import urllib.request
import urllib.error
import base64
from datetime import datetime

# ============================================================
# 설정
# ============================================================
SYMBOLS = [
    {"key": "NQ",  "name": "나스닥 100 선물", "td": "NQ",  "exchange": "CME"},
    {"key": "ES",  "name": "S&P 500 선물",   "td": "ES",  "exchange": "CME"},
    {"key": "GC",  "name": "금 선물",         "td": "GC",  "exchange": "COMEX"},
    {"key": "DXY", "name": "달러 지수",       "td": "DXY", "exchange": "ICE"},
]

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/us_quotes.json"
BRANCH = "main"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SSL_CTX = ssl.create_default_context()


# ============================================================
# Twelve Data quote — multi-symbol single call
# ============================================================
def fetch_twelvedata(api_key, symbols):
    """https://api.twelvedata.com/quote?symbol=NQ,ES,GC,DXY&apikey=...

    Response (multi-symbol):
      {"NQ": {...quote...}, "ES": {...}, "GC": {...}, "DXY": {...}}
    Response (single symbol):
      {...quote fields...} (top-level)
    """
    symbols_csv = ",".join(symbols)
    url = (f"https://api.twelvedata.com/quote"
           f"?symbol={urllib.parse.quote(symbols_csv)}"
           f"&apikey={urllib.parse.quote(api_key)}")
    result = subprocess.run(
        ["curl", "-s", "-S", "--fail-with-body",
         "-A", UA,
         "--connect-timeout", "10",
         "--max-time", "20",
         url],
        capture_output=True, text=True, timeout=25
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"curl exit {result.returncode}: {result.stderr.strip()[:200]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON decode: {result.stdout[:300]}")


def parse_td_quote(obj):
    """Twelve Data quote → 표준 dict."""
    if not isinstance(obj, dict):
        return None
    # Twelve Data 에러 응답: {"code": 4xx, "message": "..."}
    if "code" in obj and obj.get("code") not in (None, 200):
        return None
    try:
        price = float(obj["close"])
        prev = float(obj["previous_close"])
    except (KeyError, TypeError, ValueError):
        return None
    change = price - prev
    pct = (change / prev * 100) if prev else 0
    # is_market_open → state
    state = "REGULAR" if obj.get("is_market_open") else "CLOSED"
    ts = 0
    try:
        ts = int(obj.get("timestamp") or 0)
    except (TypeError, ValueError):
        pass
    return {
        "price": round(price, 2),
        "previous": round(prev, 2),
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "state": state,
        "market_ts": ts,
    }


# ============================================================
# GitHub Contents API — push
# ============================================================
def github_get_sha(pat):
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def github_put(pat, content_str, sha=None):
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}"
    payload = {
        "message": f"data: morning US quotes ({datetime.now().strftime('%Y-%m-%d %H:%M')} KST)",
        "content": base64.b64encode(content_str.encode("utf-8")).decode(),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return resp.status


# ============================================================
# 메인
# ============================================================
def main():
    pat = os.environ.get("GITHUB_PAT", "").strip()
    if not pat:
        print("✗ GITHUB_PAT 없음", file=sys.stderr)
        sys.exit(1)

    td_key = os.environ.get("TWELVEDATA_KEY", "").strip()
    if not td_key:
        print("✗ TWELVEDATA_KEY 없음 (.env 에 추가)", file=sys.stderr)
        sys.exit(1)

    td_symbols = [s["td"] for s in SYMBOLS]
    try:
        raw = fetch_twelvedata(td_key, td_symbols)
    except Exception as e:
        print(f"✗ Twelve Data fetch 실패: {e}", file=sys.stderr)
        sys.exit(2)

    # multi-symbol 응답: dict by symbol. single symbol: top-level quote.
    # SYMBOLS 가 1개일 때만 top-level, 우리는 항상 2+ 라 항상 dict.
    if not isinstance(raw, dict):
        print(f"✗ 예상 못한 응답 형식: {str(raw)[:200]}", file=sys.stderr)
        sys.exit(3)

    # 에러 응답 — top-level "code" 가 있고 200 아님
    if "code" in raw and raw.get("code") not in (None, 200):
        print(f"✗ Twelve Data 에러: {raw.get('message', raw)}", file=sys.stderr)
        sys.exit(4)

    # SYMBOLS=1 인 케이스 — top-level 이 quote 자체. 우리는 multi 이지만 방어.
    is_multi = all(s in raw for s in td_symbols)

    results = []
    for sym in SYMBOLS:
        if is_multi:
            obj = raw.get(sym["td"])
        else:
            obj = raw if sym["td"] == raw.get("symbol") else None
        q = parse_td_quote(obj)
        if not q:
            err = (obj or {}).get("message") if isinstance(obj, dict) else None
            print(f"✗ {sym['name']}: 데이터 없음 ({err or 'parse 실패'})")
            continue
        item = {
            "key": sym["key"],
            "name": sym["name"],
            "symbol": sym["td"],
            "exchange": sym["exchange"],
            **q,
            "source": "twelvedata",
            "delayed": True,  # 15분 지연 표시용
        }
        results.append(item)
        sign = "+" if q["change"] >= 0 else ""
        print(f"✓ {sym['name']}: {q['price']:,.2f} "
              f"({sign}{q['change']:.2f}, {sign}{q['change_pct']:.2f}%)")

    if not results:
        print("✗ 결과 0건", file=sys.stderr)
        sys.exit(5)

    payload = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "quotes": results,
    }
    content_str = json.dumps(payload, ensure_ascii=False, indent=2)

    # GitHub push
    try:
        sha = github_get_sha(pat)
        status = github_put(pat, content_str, sha=sha)
        print(f"[gh] PUT OK HTTP {status}")
    except Exception as e:
        print(f"[gh] PUT 실패: {e}", file=sys.stderr)
        sys.exit(6)


if __name__ == "__main__":
    main()
