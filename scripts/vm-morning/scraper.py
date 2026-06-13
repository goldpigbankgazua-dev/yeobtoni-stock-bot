#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — 미국 야간선물 (NQ/ES/GC).

Yahoo Finance v8 chart endpoint (Lightsail AWS IP 통과 확인됨).
매 1분 cron → modules/morning/data/us_quotes.json → GitHub push.

K200 야간선물은 별도 (KIS WebSocket — Phase 2).

env:
  GITHUB_PAT  — yeobtoni-stock-bot 리포 쓰기 권한
"""
import os
import json
import ssl
import sys
import time
import random
import urllib.parse
import urllib.request
import urllib.error
import base64
from datetime import datetime

# ============================================================
# 설정
# ============================================================
SYMBOLS = [
    {"key": "NQ", "name": "나스닥 100 선물", "yahoo": "NQ=F", "exchange": "CME"},
    {"key": "ES", "name": "S&P 500 선물",    "yahoo": "ES=F", "exchange": "CME"},
    {"key": "GC", "name": "금 선물",          "yahoo": "GC=F", "exchange": "COMEX"},
]

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/us_quotes.json"
BRANCH = "main"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SSL_CTX = ssl.create_default_context()


# ============================================================
# Yahoo Finance v8 chart endpoint
# ============================================================
def fetch_yahoo_v8(symbol):
    """Yahoo v8 chart endpoint — meta 만 사용 (실시간 가격).

    query1 → 429 시 query2 로 fallback. 브라우저 닮은 헤더 + sleep.
    """
    sym = urllib.parse.quote(symbol)
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Origin": "https://finance.yahoo.com",
        "Referer": f"https://finance.yahoo.com/quote/{sym}",
    }
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{sym}?interval=1m&range=1d"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
                raw = resp.read()
                # gzip 응답 처리
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(2 + random.random())  # backoff
                continue
            raise
    raise last_err if last_err else RuntimeError("fetch failed")


def parse_v8(data):
    """v8 chart response → 표준 dict (meta 필드 기반)."""
    try:
        result = data["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return None
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or prev is None:
        return None
    change = price - prev
    pct = (change / prev * 100) if prev else 0
    state = meta.get("marketState", "REGULAR")
    ts = meta.get("regularMarketTime", 0)
    return {
        "price": round(float(price), 2),
        "previous": round(float(prev), 2),
        "change": round(float(change), 2),
        "change_pct": round(float(pct), 2),
        "state": state,
        "market_ts": int(ts),
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

    results = []
    for idx, sym in enumerate(SYMBOLS):
        if idx > 0:
            time.sleep(1.5 + random.random())  # 요청 간 간격
        try:
            raw = fetch_yahoo_v8(sym["yahoo"])
            q = parse_v8(raw)
        except Exception as e:
            print(f"✗ {sym['name']}: {e}", file=sys.stderr)
            continue
        if not q:
            print(f"✗ {sym['name']}: 데이터 없음")
            continue
        item = {
            "key": sym["key"],
            "name": sym["name"],
            "symbol": sym["yahoo"],
            "exchange": sym["exchange"],
            **q,
            "source": "yahoo",
            "delayed": True,  # 15분 지연 표시용
        }
        results.append(item)
        sign = "+" if q["change"] >= 0 else ""
        print(f"✓ {sym['name']}: {q['price']:,.2f} "
              f"({sign}{q['change']:.2f}, {sign}{q['change_pct']:.2f}%)")

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
        sys.exit(2)


if __name__ == "__main__":
    main()
