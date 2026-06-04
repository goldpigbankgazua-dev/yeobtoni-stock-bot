#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국내증시현황 데이터 수집기
- 투자자예탁금 / 신용융자잔고: 금융투자협회(KOFIA freesis) — 2거래일 지연
- 거래대금: pykrx (KRX KOSPI/KOSDAQ 일별 거래대금)

산출물: data/market.json  (시계열, 최대 400일)
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

# ──────────────────────────────────────────────────────────
# 거래대금 (pykrx)
# ──────────────────────────────────────────────────────────
def fetch_trading_values():
    try:
        from pykrx import stock
    except ImportError:
        print("[trading] pykrx 미설치 — 스킵")
        return [], []
    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    fr, to = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    def _series(code, label):
        try:
            df = stock.get_index_ohlcv_by_date(fr, to, code)  # 1001 코스피, 2001 코스닥
            if df is None or df.empty:
                return []
            # 거래대금 컬럼: "거래대금"
            col = "거래대금" if "거래대금" in df.columns else df.columns[-1]
            out = []
            for idx, row in df.iterrows():
                d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                v = float(row[col]) if row[col] is not None else None
                if v is None:
                    continue
                out.append({"date": d, "value": int(v)})
            print(f"[trading] {label}: {len(out)} rows")
            return out
        except Exception as e:
            print(f"[trading] {label} 실패: {e}")
            return []

    kospi  = _series("1001", "KOSPI")
    time.sleep(0.5)
    kosdaq = _series("2001", "KOSDAQ")
    return kospi, kosdaq


# ──────────────────────────────────────────────────────────
# 투자자예탁금 / 신용융자잔고 (KOFIA freesis)
#
# freesis는 statisticsId 별 POST API 제공.
# 안정성 위해 pykrx의 bond / 또는 직접 호출.
# 여기선 pykrx에 일부 있고 없으면 KOFIA 직접 호출 fallback.
# ──────────────────────────────────────────────────────────
def fetch_kofia_deposit_and_credit():
    """
    pykrx.bond 에 일부 KOFIA 데이터 wrapper가 있으나 버전 호환 이슈가 있어
    직접 KOFIA freesis HTTP API 호출.
    """
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15",
        "Accept": "application/json",
    })

    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    fr, to = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

    # KOFIA freesis 통계 ID (공개 데이터)
    # statisticsId:
    #   - 투자자예탁금:   STATSCD_DEPOSIT  → MDIS_03_03_00_03
    #   - 신용공여 잔고:  STATSCD_CREDIT   → MDIS_03_03_00_05 (시장별)
    URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"

    def _call(stats_id, extra=None):
        body = {
            "statisticsId":   stats_id,
            "DT_DEF_PERD":    "1",
            "FROM_DT":        fr,
            "TO_DT":          to,
            "DIVISION":       "month",
            "OBJ_NM":         "STATSCD",
            "PAGE_TYPE":      "TIME_SERIES",
        }
        if extra:
            body.update(extra)
        try:
            r = sess.post(URL, json=body, timeout=20)
            r.raise_for_status()
            data = r.json()
            return data
        except Exception as e:
            print(f"[kofia] call 실패 (stats_id={stats_id}): {e}")
            return None

    # KOFIA API 스펙이 자주 바뀌어서 일단 시도하고 실패하면 빈 결과 반환.
    # 실제 stats_id는 KOFIA freesis 사이트의 통계ID에서 확인 필요.
    deposit_data    = _call("MDIS_03_03_00_03")  # 예탁금
    credit_data     = _call("MDIS_03_03_00_05")  # 신용잔고

    def _parse(data, market_filter=None):
        if not data:
            return []
        # KOFIA 응답 구조는 통계마다 다름. 일반적으로 "rows" 또는 "DATA" 키.
        rows = data.get("DATA") or data.get("rows") or []
        out = []
        for r in rows:
            d = r.get("BSE_DT") or r.get("date") or r.get("STD_DT")
            v = r.get("AMT") or r.get("value") or r.get("VAL")
            if not d or v is None:
                continue
            try:
                d_str = str(d)
                if len(d_str) == 8:
                    d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                v_num = float(str(v).replace(",", ""))
                # KOFIA는 보통 백만원 단위 — 원 단위로 환산
                v_num = v_num * 1_000_000
                if market_filter:
                    mkt = (r.get("MKT_NM") or r.get("MKT") or "").upper()
                    if market_filter.upper() not in mkt:
                        continue
                out.append({"date": d_str, "value": int(v_num)})
            except Exception:
                continue
        out.sort(key=lambda x: x["date"])
        return out

    deposits     = _parse(deposit_data)
    credit_kospi = _parse(credit_data, "KOSPI") or _parse(credit_data, "유가증권")
    credit_kosdaq= _parse(credit_data, "KOSDAQ")

    print(f"[kofia] deposits={len(deposits)} credit_kospi={len(credit_kospi)} credit_kosdaq={len(credit_kosdaq)}")
    return deposits, credit_kospi, credit_kosdaq


# ──────────────────────────────────────────────────────────
def main():
    print(f"=== 국내증시현황 데이터 수집 ({dt.date.today()}) ===")

    # 1) 거래대금
    tr_kospi, tr_kosdaq = fetch_trading_values()

    # 2) 예탁금 / 신용잔고
    deposits, cr_kospi, cr_kosdaq = fetch_kofia_deposit_and_credit()

    # 기존 데이터 병합 (KOFIA 일부 실패해도 직전 일자 유지)
    prev = {}
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    def _merge(existing, new):
        if not new and existing:
            return existing
        if not existing:
            return new
        seen = {p["date"] for p in new}
        merged = list(new) + [p for p in existing if p["date"] not in seen]
        merged.sort(key=lambda x: x["date"])
        # DAYS 일치까지만
        cutoff = (dt.date.today() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%d")
        return [p for p in merged if p["date"] >= cutoff]

    out = {
        "updated_at":    dt.date.today().strftime("%Y-%m-%d"),
        "deposits":      _merge(prev.get("deposits"),      deposits),
        "credit_kospi":  _merge(prev.get("credit_kospi"),  cr_kospi),
        "credit_kosdaq": _merge(prev.get("credit_kosdaq"), cr_kosdaq),
        "trading_kospi": _merge(prev.get("trading_kospi"), tr_kospi),
        "trading_kosdaq":_merge(prev.get("trading_kosdaq"),tr_kosdaq),
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
