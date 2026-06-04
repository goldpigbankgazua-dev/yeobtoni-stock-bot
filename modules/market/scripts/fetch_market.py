#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국내증시현황 데이터 수집기 — v3

거래대금:    Naver Stock API (인증 불필요, 안정적)
예탁금·신용잔고: KOFIA freesis JSON API 시도 (실패 시 빈 배열)

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

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15")

# ──────────────────────────────────────────────────────────
# 거래대금 — Naver Stock API
#
# Endpoint: https://api.stock.naver.com/chart/domestic/index/{code}
#   code: KOSPI, KOSDAQ
#   periodType: dayCandle
#   startDateTime, endDateTime: YYYYMMDDHHmmss
#
# 응답: { "code": "...", "priceInfos": [ {localDate, openPrice, ..., accumulatedTradingValue}, ... ] }
# ──────────────────────────────────────────────────────────
def fetch_naver_index_trading():
    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    start_str = start.strftime("%Y%m%d") + "000000"
    end_str   = today.strftime("%Y%m%d") + "235959"

    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": "https://finance.naver.com/",
        "Origin": "https://finance.naver.com",
    }

    def _series(code, label):
        url = f"https://api.stock.naver.com/chart/domestic/index/{code}"
        params = {
            "periodType": "dayCandle",
            "startDateTime": start_str,
            "endDateTime": end_str,
        }
        try:
            r = requests.get(url, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[trading] {label} 요청 실패: {e}")
            return []

        # 응답 구조 두 패턴 대응
        bars = data.get("priceInfos") or data.get("candles") or data
        if not isinstance(bars, list):
            print(f"[trading] {label}: 예상 못 한 응답 구조 = {list(data.keys())[:5] if isinstance(data, dict) else type(data)}")
            return []

        out = []
        for b in bars:
            d = b.get("localDate") or b.get("date") or b.get("localDateTime")
            v = b.get("accumulatedTradingValue") or b.get("tradingValue") or b.get("amount")
            if d is None or v is None:
                continue
            d_str = str(d)[:8]
            if len(d_str) == 8:
                d_iso = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            else:
                d_iso = str(d)[:10]
            try:
                v_int = int(v)
            except Exception:
                continue
            if v_int > 0:
                out.append({"date": d_iso, "value": v_int})
        out.sort(key=lambda x: x["date"])
        print(f"[trading] {label}: {len(out)} rows")
        return out

    kospi  = _series("KOSPI",  "KOSPI")
    time.sleep(0.4)
    kosdaq = _series("KOSDAQ", "KOSDAQ")
    return kospi, kosdaq


# ──────────────────────────────────────────────────────────
# 예탁금·신용잔고 — KOFIA freesis
# 통계 ID는 freesis에서 직접 확인 필요. 실패 시 빈 배열.
# ──────────────────────────────────────────────────────────
def fetch_kofia_macro():
    """KOFIA freesis API. 스펙이 자주 바뀌고 통계ID도 다양해서 보수적으로 빈 배열 폴백."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://freesis.kofia.or.kr",
        "Referer": "https://freesis.kofia.or.kr/",
    })

    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    fr_yyyymm = start.strftime("%Y%m")
    to_yyyymm = today.strftime("%Y%m")
    fr_ymd    = start.strftime("%Y%m%d")
    to_ymd    = today.strftime("%Y%m%d")

    BASE_URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"

    def _try(stats_id, value_field_candidates=("AMT","VAL","DAT_VAL")):
        body = {
            "statisticsId": stats_id,
            "DT_DEF_PERD": "1",
            "FROM_DT": fr_ymd,
            "TO_DT":   to_ymd,
            "DIVISION":"day",
            "OBJ_NM":  "STATSCD",
            "PAGE_TYPE": "TIME_SERIES",
        }
        try:
            r = sess.post(BASE_URL, json=body, timeout=15)
            if r.status_code != 200:
                print(f"[kofia] {stats_id}: HTTP {r.status_code}")
                return []
            try:
                data = r.json()
            except Exception:
                print(f"[kofia] {stats_id}: JSON 파싱 실패 (응답 첫 200자: {r.text[:200]!r})")
                return []
        except Exception as e:
            print(f"[kofia] {stats_id}: 요청 실패: {e}")
            return []

        rows = data.get("DATA") or data.get("rows") or data.get("result") or []
        if not isinstance(rows, list):
            print(f"[kofia] {stats_id}: 예상 못 한 구조 {list(data.keys())[:5] if isinstance(data, dict) else '?'}")
            return []

        out = []
        for r in rows:
            d = r.get("BSE_DT") or r.get("STD_DT") or r.get("date") or r.get("DT")
            v = None
            for f in value_field_candidates:
                if f in r and r[f] is not None:
                    v = r[f]; break
            if d is None or v is None:
                continue
            d_str = str(d).replace("-", "").replace("/", "")
            if len(d_str) >= 8:
                d_iso = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
            else:
                continue
            try:
                v_num = float(str(v).replace(",", "")) * 1_000_000  # 백만원 → 원
                out.append({"date": d_iso, "value": int(v_num)})
            except Exception:
                continue
        out.sort(key=lambda x: x["date"])
        return out

    # 통계 ID 후보 — 실제 freesis에서 inspect 필요
    deposit_candidates = ["FSST_03_03_00_03", "MDIS_03_03_00_03", "STAT_INVDP_DAILY"]
    credit_candidates  = ["FSST_03_03_00_05", "MDIS_03_03_00_05", "STAT_CRDT_BAL"]

    deposits = []
    for sid in deposit_candidates:
        deposits = _try(sid)
        if deposits:
            print(f"[deposits] OK via {sid}: {len(deposits)} rows")
            break
    if not deposits:
        print("[deposits] 모든 통계ID 실패 — 0 rows")

    credit_total = []
    for sid in credit_candidates:
        credit_total = _try(sid)
        if credit_total:
            print(f"[credit] OK via {sid}: {len(credit_total)} rows (시장 분리 정보 없음)")
            break
    if not credit_total:
        print("[credit] 모든 통계ID 실패 — 0 rows")

    # 시장 분리 정보 없으면 임시로 동일 시리즈를 KOSPI에 할당
    cr_kospi  = credit_total
    cr_kosdaq = []  # 분리 필요
    return deposits, cr_kospi, cr_kosdaq


# ──────────────────────────────────────────────────────────
def main():
    print(f"=== 국내증시현황 데이터 수집 ({dt.date.today()}) ===")

    tr_kospi, tr_kosdaq = fetch_naver_index_trading()
    deposits, cr_kospi, cr_kosdaq = fetch_kofia_macro()

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
