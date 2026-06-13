#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — Cloudflare Worker proxy 통해 Yahoo fetch.

CF Worker (yeobtoni-yahoo-proxy.sylee0137.workers.dev) 가 CF IP 통해
Yahoo v8 chart endpoint 호출 (Lightsail AWS IP 차단 우회).
4종 (NQ/ES/GC/DXY) → us_quotes.json → GitHub push.

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
WORKER_URL = "https://yeobtoni-yahoo-proxy.sylee0137.workers.dev"

SYMBOLS = [
    {"key": "NQ",  "name": "나스닥 100 선물", "yahoo": "NQ=F",     "exchange": "CME"},
    {"key": "ES",  "name": "S&P 500 선물",   "yahoo": "ES=F",     "exchange": "CME"},
    {"key": "GC",  "name": "금 선물",         "yahoo": "GC=F",     "exchange": "COMEX"},
    {"key": "DXY", "name": "달러 지수",       "yahoo": "DX-Y.NYB", "exchange": "ICE"},
]

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/us_quotes.json"
BRANCH = "main"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SSL_CTX = ssl.create_default_context()


# ============================================================
# Cloudflare Worker 호출 (multi-symbol 단일 호출)
# ============================================================
def fetch_worker(yahoo_symbols):
    csv = ",".join(yahoo_symbols)
    url = f"{WORKER_URL}/?symbols={urllib.parse.quote(csv)}"
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
    return json.loads(result.stdout)


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
        worker_data = fetch_worker(yahoo_symbols)
    except Exception as e:
        print(f"✗ Worker fetch 실패: {e}", file=sys.stderr)
        sys.exit(2)

    by_sym = worker_data.get("symbols", {})
    results = []
    for sym in SYMBOLS:
        d = by_sym.get(sym["yahoo"])
        if not d or d.get("error"):
            err = (d or {}).get("error", "데이터 없음")
            print(f"✗ {sym['name']}: {err}")
            continue
        price = d.get("price")
        prev = d.get("previous")
        change = d.get("change")
        pct = d.get("change_pct")
        if price is None:
            print(f"✗ {sym['name']}: price 없음")
            continue
        item = {
            "key": sym["key"],
            "name": sym["name"],
            "symbol": sym["yahoo"],
            "exchange": sym["exchange"],
            "price": round(float(price), 2),
            "previous": round(float(prev), 2) if prev is not None else None,
            "change": round(float(change), 2) if change is not None else None,
            "change_pct": round(float(pct), 2) if pct is not None else None,
            "state": d.get("state") or "REGULAR",
            "market_ts": int(d.get("ts") or 0),
            "source": "yahoo (via CF Worker)",
            "delayed": True,
        }
        results.append(item)
        sign = "+" if (change or 0) >= 0 else ""
        print(f"✓ {sym['name']}: {item['price']:,.2f} "
              f"({sign}{item['change']:.2f}, {sign}{item['change_pct']:.2f}%)")

    if not results:
        print("✗ 결과 0건", file=sys.stderr)
        sys.exit(3)

    payload = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "quotes": results,
    }
    content_str = json.dumps(payload, ensure_ascii=False, indent=2)

    try:
        sha = github_get_sha(pat)
        status = github_put(pat, content_str, sha=sha)
        print(f"[gh] PUT OK HTTP {status}")
    except Exception as e:
        print(f"[gh] PUT 실패: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
