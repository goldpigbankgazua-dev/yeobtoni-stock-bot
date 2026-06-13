#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — 미국 야간선물 + 금 + 달러 지수.

Yahoo Finance spark endpoint (multi-symbol single call).
1 호출 = 4종목 → 5분 cron 으로 288 호출/day. IP throttle 가능성 최소화.

env:
  GITHUB_PAT  — yeobtoni-stock-bot 리포 쓰기 권한
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
    {"key": "NQ",  "name": "나스닥 100 선물", "yahoo": "NQ=F", "exchange": "CME"},
    {"key": "ES",  "name": "S&P 500 선물",   "yahoo": "ES=F", "exchange": "CME"},
    {"key": "GC",  "name": "금 선물",         "yahoo": "GC=F", "exchange": "COMEX"},
    {"key": "DXY", "name": "달러 지수",       "yahoo": "DX=F", "exchange": "ICE"},
]

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/us_quotes.json"
BRANCH = "main"

# UA: Linux 서버는 Linux UA 가 정직. Mac UA 면 Yahoo 봇 의심.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SSL_CTX = ssl.create_default_context()


# ============================================================
# Yahoo spark — multi-symbol 단일 호출
# ============================================================
def fetch_yahoo_spark(yahoo_symbols):
    """https://query1.finance.yahoo.com/v7/finance/spark?symbols=...&range=1d&interval=1m

    한 호출에 multiple symbols. raw URL (URL encoding 없이 직접) 사용 —
    %3D 인코딩되면 Yahoo 가 받아들이긴 함.
    """
    symbols_csv = ",".join(yahoo_symbols)  # raw, encode 안 함
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = (f"https://{host}/v7/finance/spark"
               f"?symbols={symbols_csv}&range=1d&interval=1m")
        try:
            result = subprocess.run(
                ["curl", "-s", "-S", "--fail-with-body",
                 "-A", UA,
                 "--connect-timeout", "10",
                 "--max-time", "20",
                 url],
                capture_output=True, text=True, timeout=25
            )
            if result.returncode != 0:
                last_err = RuntimeError(
                    f"curl exit {result.returncode}: {result.stderr.strip()[:200]}")
                continue
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired as e:
            last_err = e
            continue
        except json.JSONDecodeError:
            last_err = RuntimeError(f"JSON decode: {result.stdout[:200]}")
            continue
    raise last_err if last_err else RuntimeError("spark fetch failed")


def parse_spark_meta(meta):
    """spark response 의 각 종목 meta → 표준 dict."""
    if not meta:
        return None
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


def extract_meta_by_symbol(spark_data):
    """spark response 의 두 가지 포맷 모두 지원.

    1) {"spark": {"result": [{"symbol": "NQ=F", "response": [{"meta": ...}]}, ...]}}
    2) {"NQ=F": [{"meta": ...}], "ES=F": [...], ...}
    """
    by_sym = {}
    spark = spark_data.get("spark", {}) if isinstance(spark_data, dict) else {}
    for item in spark.get("result", []):
        sym = item.get("symbol")
        resp = (item.get("response") or [{}])[0]
        if sym and resp.get("meta"):
            by_sym[sym] = resp["meta"]
    if by_sym:
        return by_sym
    if isinstance(spark_data, dict):
        for sym, val in spark_data.items():
            if isinstance(val, list) and val and isinstance(val[0], dict) and val[0].get("meta"):
                by_sym[sym] = val[0]["meta"]
    return by_sym


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

    yahoo_symbols = [s["yahoo"] for s in SYMBOLS]
    try:
        raw = fetch_yahoo_spark(yahoo_symbols)
    except Exception as e:
        print(f"✗ spark fetch 실패: {e}", file=sys.stderr)
        sys.exit(2)

    metas = extract_meta_by_symbol(raw)
    if not metas:
        print(f"✗ spark 응답 파싱 실패: {json.dumps(raw)[:300]}", file=sys.stderr)
        sys.exit(3)

    results = []
    for sym in SYMBOLS:
        meta = metas.get(sym["yahoo"])
        q = parse_spark_meta(meta)
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

    if not results:
        print("✗ 결과 0건", file=sys.stderr)
        sys.exit(4)

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
        sys.exit(5)


if __name__ == "__main__":
    main()
