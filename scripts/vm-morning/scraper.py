#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — Yahoo Finance Quote + KIS API (선택).

매 30분 cron 실행 → modules/morning/data/quotes.json 갱신 → GitHub push.

env:
  GITHUB_PAT  — yeobtoni-stock-bot 리포 쓰기 권한
  KIS_APP_KEY / KIS_APP_SECRET — (선택) K200 야간선물 정확 시세
"""
import os
import json
import ssl
import sys
import urllib.parse
import urllib.request
import urllib.error
import base64
from datetime import datetime

# ============================================================
# 설정
# ============================================================
SYMBOLS = [
    # K200 야간선물 — KIS API 가능시 그쪽, 아니면 KOSPI 종합 대체
    {"key": "K200",  "name": "K200 야간선물",     "yahoo": "^KS11", "exchange": "KRX Night",   "use_kis": True},
    {"key": "NQ",    "name": "나스닥 100 선물",    "yahoo": "NQ=F",  "exchange": "CME",         "use_kis": False},
    {"key": "ES",    "name": "S&P 500 선물",      "yahoo": "ES=F",  "exchange": "CME",         "use_kis": False},
    {"key": "GC",    "name": "금 선물",            "yahoo": "GC=F",  "exchange": "COMEX",       "use_kis": False},
]

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/morning/data/quotes.json"
BRANCH = "main"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ============================================================
# Yahoo Finance Quote API
# ============================================================
def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
        return json.loads(resp.read())


def parse_yahoo(data):
    res = data["chart"]["result"][0]
    meta = res["meta"]
    current = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if current is None or prev is None:
        return None
    change = current - prev
    pct = (change / prev * 100) if prev else 0
    state = meta.get("marketState", "")  # REGULAR / CLOSED / PRE / POST
    return {
        "price": round(current, 2),
        "previous": round(prev, 2),
        "change": round(change, 2),
        "change_pct": round(pct, 2),
        "state": state,
    }


# ============================================================
# KIS API (K200 야간선물 — 선택)
# ============================================================
KIS_BASE = "https://openapi.koreainvestment.com:9443"

def kis_token():
    key = os.environ.get("KIS_APP_KEY", "").strip()
    secret = os.environ.get("KIS_APP_SECRET", "").strip()
    if not key or not secret:
        return None
    url = f"{KIS_BASE}/oauth2/tokenP"
    body = json.dumps({"grant_type": "client_credentials", "appkey": key, "appsecret": secret}).encode()
    req = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return json.loads(resp.read())["access_token"]
    except Exception as e:
        print(f"[KIS] token 실패: {e}")
        return None


def fetch_k200_night(token):
    """KIS API: K200 야간선물 시세."""
    if not token:
        return None
    # K200 야간선물 종목코드 (월물에 따라 다름 — 활성 월물 자동 선택은 복잡)
    # 일단 plain endpoint 로 시도. 실패시 None 반환 → Yahoo fallback.
    # TODO: 정확한 endpoint 사용자 확인 후 보완
    return None  # 일단 Yahoo fallback


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
        "message": f"data: morning quotes ({datetime.now().strftime('%Y-%m-%d %H:%M')} KST)",
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

    kis_t = kis_token()  # 있으면 KIS 활용
    if kis_t:
        print("✓ KIS token OK")

    results = []
    for sym in SYMBOLS:
        quote = None
        # 1) KIS 우선 (K200 야간선물 등)
        if sym["use_kis"] and kis_t:
            quote = fetch_k200_night(kis_t)
            if quote:
                quote["source"] = "kis"
        # 2) Yahoo fallback
        if not quote:
            try:
                data = fetch_yahoo(sym["yahoo"])
                quote = parse_yahoo(data)
                if quote:
                    quote["source"] = "yahoo"
            except Exception as e:
                print(f"✗ {sym['name']}: {e}")
                continue

        if not quote:
            print(f"✗ {sym['name']}: 데이터 없음")
            continue

        item = {
            "key": sym["key"],
            "name": sym["name"],
            "symbol": sym["yahoo"],
            "exchange": sym["exchange"],
            **quote,
        }
        results.append(item)
        sign = "+" if quote["change"] >= 0 else ""
        print(f"✓ {sym['name']}: {quote['price']:,.2f} ({sign}{quote['change']:.2f}, {sign}{quote['change_pct']:.2f}%)")

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
