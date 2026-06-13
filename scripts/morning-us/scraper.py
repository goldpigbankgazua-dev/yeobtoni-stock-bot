#!/usr/bin/env python3
"""아침에 보는 글로벌증시 — 미국 선물 (NQ/ES/GC) 1분 cron — 맥 launchd 전용

Yahoo Finance Quote API → modules/morning/data/us_quotes.json
(Lightsail VM 은 AWS IP 차단으로 Yahoo 못 씀 → 맥에서만 실행)
"""
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ============================================================
# 설정
# ============================================================
SYMBOLS = [
    {"key": "NQ", "name": "나스닥 100 선물", "yahoo": "NQ=F", "exchange": "CME"},
    {"key": "ES", "name": "S&P 500 선물",    "yahoo": "ES=F", "exchange": "CME"},
    {"key": "GC", "name": "금 선물",          "yahoo": "GC=F", "exchange": "COMEX"},
]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_ROOT / "modules" / "morning" / "data" / "us_quotes.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

SSL_CTX = ssl.create_default_context()


# ============================================================
# Yahoo Finance Quote API
# ============================================================
def fetch_yahoo_quotes(yahoo_symbols):
    """한 번에 여러 심볼 fetch."""
    symbols_csv = ",".join(urllib.parse.quote(s) for s in yahoo_symbols)
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols_csv}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
        return json.loads(resp.read())


def parse_quote(item):
    """Yahoo Finance Quote result → 표준 dict"""
    price = item.get("regularMarketPrice")
    prev = item.get("regularMarketPreviousClose")
    change = item.get("regularMarketChange")
    pct = item.get("regularMarketChangePercent")
    state = item.get("marketState", "REGULAR")  # REGULAR / PRE / POST / CLOSED
    ts = item.get("regularMarketTime", 0)
    if price is None:
        return None
    return {
        "price": round(float(price), 2),
        "previous": round(float(prev), 2) if prev is not None else None,
        "change": round(float(change), 2) if change is not None else None,
        "change_pct": round(float(pct), 2) if pct is not None else None,
        "state": state,
        "market_ts": int(ts),
    }


# ============================================================
# 메인
# ============================================================
def main():
    yahoo_to_sym = {s["yahoo"]: s for s in SYMBOLS}
    yahoo_symbols = [s["yahoo"] for s in SYMBOLS]

    try:
        resp = fetch_yahoo_quotes(yahoo_symbols)
    except Exception as e:
        print(f"✗ Yahoo fetch 실패: {e}", file=sys.stderr)
        sys.exit(1)

    results = []
    qr = resp.get("quoteResponse", {})
    for item in qr.get("result", []):
        ysym = item.get("symbol")
        sym = yahoo_to_sym.get(ysym)
        if not sym:
            continue
        q = parse_quote(item)
        if not q:
            print(f"✗ {sym['name']}: 데이터 없음")
            continue
        results.append({
            "key": sym["key"],
            "name": sym["name"],
            "symbol": sym["yahoo"],
            "exchange": sym["exchange"],
            **q,
            "source": "yahoo",
            "delayed": True,  # 15분 지연 라벨용
        })
        sign = "+" if (q["change"] or 0) >= 0 else ""
        print(f"✓ {sym['name']}: {q['price']:,.2f} "
              f"({sign}{q['change']:.2f}, {sign}{q['change_pct']:.2f}%)")

    if not results:
        print("✗ 결과 0건", file=sys.stderr)
        sys.exit(2)

    payload = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "quotes": results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"[ok] {OUT_PATH.relative_to(REPO_ROOT)} 갱신 ({len(results)}건)")


if __name__ == "__main__":
    main()
