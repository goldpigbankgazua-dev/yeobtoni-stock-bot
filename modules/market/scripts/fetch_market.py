#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국내증시현황 데이터 수집기 — v2

거래대금:    pykrx (KOSPI/KOSDAQ 지수 일별)
예탁금·신용잔고: Naver Finance (KOFIA가 source. Naver가 정리해서 노출)

산출물: data/market.json
"""

import os
import sys
import json
import time
import datetime as dt
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "market.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

DAYS = 400

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                   "Version/16.5 Safari/605.1.15"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}

# ──────────────────────────────────────────────────────────
# 거래대금 — pykrx (지수 OHLCV에서 "거래대금" 컬럼)
# ──────────────────────────────────────────────────────────
def fetch_trading_values():
    try:
        from pykrx import stock
    except ImportError as e:
        print(f"[trading] pykrx 미설치: {e}")
        return [], []

    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    fr, to = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    def _series(code, label):
        df = None
        # pykrx 버전별 함수명이 달라서 둘 다 시도
        for fn_name in ("get_index_ohlcv", "get_index_ohlcv_by_date"):
            try:
                fn = getattr(stock, fn_name, None)
                if fn is None:
                    continue
                df = fn(fr, to, code)
                if df is not None and not df.empty:
                    print(f"[trading] {label}: {fn_name} OK ({len(df)} rows)")
                    break
            except Exception as e:
                print(f"[trading] {label} {fn_name} 실패: {e}")
        if df is None or df.empty:
            print(f"[trading] {label}: 데이터 없음")
            return []

        col = "거래대금" if "거래대금" in df.columns else None
        if col is None:
            print(f"[trading] {label}: 거래대금 컬럼 없음 — 컬럼들: {list(df.columns)}")
            return []
        out = []
        for idx, row in df.iterrows():
            d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            try:
                v = int(row[col])
            except Exception:
                continue
            if v > 0:
                out.append({"date": d, "value": v})
        return out

    kospi  = _series("1001", "KOSPI")
    time.sleep(0.5)
    kosdaq = _series("2001", "KOSDAQ")
    return kospi, kosdaq


# ──────────────────────────────────────────────────────────
# 투자자예탁금 — Naver Finance: /sise/sise_deposit.naver
# 신용잔고     — Naver Finance: /sise/sise_credit.naver (간접)
#
# Naver는 표 형태로 일별 데이터를 페이지네이션으로 제공.
# ──────────────────────────────────────────────────────────
def _parse_naver_deposit_page(html):
    """예탁금 페이지 파싱 — table.type_1 에 일별 데이터."""
    import re
    rows = []
    # tr 안에서 td 추출
    tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    for tr in tr_matches:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 2:
            continue
        date_raw = re.sub(r'<[^>]+>', '', tds[0]).strip()
        val_raw  = re.sub(r'<[^>]+>', '', tds[1]).strip()
        # date: "2026.06.04" → "2026-06-04"
        if not re.match(r'^\d{4}\.\d{2}\.\d{2}', date_raw):
            continue
        date_iso = date_raw[:10].replace(".", "-")
        # value: 콤마 제거, 단위는 백만원 (Naver 기본)
        v_clean = val_raw.replace(",", "").replace(" ", "")
        try:
            v = float(v_clean) * 1_000_000  # 백만원 → 원
            rows.append({"date": date_iso, "value": int(v)})
        except Exception:
            continue
    return rows


def fetch_naver_deposits():
    """Naver Finance에서 투자자예탁금 페이지네이션 수집."""
    sess = requests.Session()
    sess.headers.update(HEADERS)
    out = []
    for page in range(1, 12):  # 페이지당 약 20일 × 12 = 240일
        url = f"https://finance.naver.com/sise/sise_deposit.naver?&page={page}"
        try:
            r = sess.get(url, timeout=15)
            r.encoding = "euc-kr"  # Naver finance 인코딩
            rows = _parse_naver_deposit_page(r.text)
            if not rows:
                break
            out.extend(rows)
            time.sleep(0.4)
        except Exception as e:
            print(f"[deposits] page {page} 실패: {e}")
            break
    # 중복 제거 + 날짜순
    seen = set()
    dedup = []
    for r in out:
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        dedup.append(r)
    dedup.sort(key=lambda x: x["date"])
    print(f"[deposits] {len(dedup)} rows")
    return dedup


def fetch_naver_credit():
    """
    Naver Finance의 신용잔고 페이지.
    Naver는 일자별 시장별(거래소/코스닥) 신용공여 잔고를 제공.
    """
    sess = requests.Session()
    sess.headers.update(HEADERS)
    kospi_out, kosdaq_out = [], []
    for page in range(1, 12):
        url = f"https://finance.naver.com/sise/sise_credit.naver?&page={page}"
        try:
            r = sess.get(url, timeout=15)
            r.encoding = "euc-kr"
            import re
            tr_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', r.text, re.S)
            found = 0
            for tr in tr_matches:
                tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
                if len(tds) < 3:
                    continue
                date_raw = re.sub(r'<[^>]+>', '', tds[0]).strip()
                kospi_raw  = re.sub(r'<[^>]+>', '', tds[1]).strip()
                kosdaq_raw = re.sub(r'<[^>]+>', '', tds[2]).strip()
                if not re.match(r'^\d{4}\.\d{2}\.\d{2}', date_raw):
                    continue
                date_iso = date_raw[:10].replace(".", "-")
                def _to_won(s):
                    s = s.replace(",", "").replace(" ", "")
                    try:
                        return int(float(s) * 1_000_000)  # 백만원 → 원
                    except Exception:
                        return None
                k = _to_won(kospi_raw); q = _to_won(kosdaq_raw)
                if k is not None:
                    kospi_out.append({"date": date_iso, "value": k})
                if q is not None:
                    kosdaq_out.append({"date": date_iso, "value": q})
                found += 1
            if found == 0:
                break
            time.sleep(0.4)
        except Exception as e:
            print(f"[credit] page {page} 실패: {e}")
            break

    def _dedup(lst):
        seen = set(); out = []
        for r in lst:
            if r["date"] in seen: continue
            seen.add(r["date"]); out.append(r)
        out.sort(key=lambda x: x["date"])
        return out

    kospi_out = _dedup(kospi_out)
    kosdaq_out = _dedup(kosdaq_out)
    print(f"[credit] kospi={len(kospi_out)} kosdaq={len(kosdaq_out)}")
    return kospi_out, kosdaq_out


# ──────────────────────────────────────────────────────────
def main():
    print(f"=== 국내증시현황 데이터 수집 ({dt.date.today()}) ===")

    tr_kospi, tr_kosdaq = fetch_trading_values()
    deposits = fetch_naver_deposits()
    cr_kospi, cr_kosdaq = fetch_naver_credit()

    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    def _merge(existing, new):
        if not new and existing: return existing
        if not existing: return new
        seen = {p["date"] for p in new}
        merged = list(new) + [p for p in existing if p["date"] not in seen]
        merged.sort(key=lambda x: x["date"])
        cutoff = (dt.date.today() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%d")
        return [p for p in merged if p["date"] >= cutoff]

    out = {
        "updated_at":     dt.date.today().strftime("%Y-%m-%d"),
        "deposits":       _merge(prev.get("deposits"),      deposits),
        "credit_kospi":   _merge(prev.get("credit_kospi"),  cr_kospi),
        "credit_kosdaq":  _merge(prev.get("credit_kosdaq"), cr_kosdaq),
        "trading_kospi":  _merge(prev.get("trading_kospi"), tr_kospi),
        "trading_kosdaq": _merge(prev.get("trading_kosdaq"),tr_kosdaq),
    }

    OUT.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"\n→ {OUT}")
    for k in ("deposits", "credit_kospi", "credit_kosdaq", "trading_kospi", "trading_kosdaq"):
        print(f"  {k}: {len(out[k])} rows")


if __name__ == "__main__":
    main()
