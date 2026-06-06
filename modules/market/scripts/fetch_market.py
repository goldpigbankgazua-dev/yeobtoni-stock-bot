#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
국내증시현황 데이터 수집기 — v5 (KIS API + debug)

거래대금: 한국투자증권 KIS REST API (inquire-index-daily-price)
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

KIS_BASE = "https://openapi.koreainvestment.com:9443"
APP_KEY    = os.environ.get("KIS_APP_KEY", "").strip()
APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip()

# ── 환경변수 가시화 ──
print(f"[env] KIS_APP_KEY: {'SET (len=' + str(len(APP_KEY)) + ')' if APP_KEY else '*** NOT SET ***'}")
print(f"[env] KIS_APP_SECRET: {'SET (len=' + str(len(APP_SECRET)) + ')' if APP_SECRET else '*** NOT SET ***'}")


def kis_token():
    if not APP_KEY or not APP_SECRET:
        print("[KIS] 환경변수 없음 — 토큰 발급 스킵")
        return None
    try:
        r = requests.post(
            f"{KIS_BASE}/oauth2/tokenP",
            headers={"Content-Type": "application/json"},
            json={"grant_type": "client_credentials",
                  "appkey": APP_KEY, "appsecret": APP_SECRET},
            timeout=20,
        )
    except Exception as e:
        print(f"[KIS] 토큰 요청 예외: {e}")
        return None

    print(f"[KIS] 토큰 응답 HTTP {r.status_code}")
    print(f"[KIS] 응답 첫 300자: {r.text[:300]!r}")
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except Exception as e:
        print(f"[KIS] 토큰 JSON 파싱 실패: {e}")
        return None
    tok = data.get("access_token")
    if not tok:
        print(f"[KIS] access_token 없음 — keys: {list(data.keys())}")
        return None
    print(f"[KIS] 토큰 발급 OK (expires_in={data.get('expires_in')})")
    return tok


def fetch_kis_index(token, iscd, label, debug=False):
    """
    국내업종 일별지수 — inquire-index-daily-price
    TR_ID: FHPUP02120000
    한 번에 최근 ~30영업일 반환. FID_INPUT_DATE_1 을 점진적으로 과거로 옮기며 반복.
    """
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey":    APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id":     "FHPUP02120000",
        "custtype":  "P",
    }
    url = f"{KIS_BASE}/uapi/domestic-stock/v1/quotations/inquire-index-daily-price"

    out = []
    seen = set()
    today = dt.date.today()
    target_start = today - dt.timedelta(days=DAYS)
    cur = today
    safety = 25  # 30영업일 × 25 = 750+ 거래일, 충분

    first = True
    while cur > target_start and safety > 0:
        safety -= 1
        params = {
            "FID_COND_MRKT_DIV_CODE": "U",
            "FID_INPUT_ISCD":          iscd,
            "FID_INPUT_DATE_1":        cur.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE":     "D",
        }
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
        except Exception as e:
            print(f"[trading] {label} 요청 예외: {e}")
            break

        if r.status_code != 200:
            print(f"[trading] {label} HTTP {r.status_code}: {r.text[:300]}")
            break

        try:
            data = r.json()
        except Exception as e:
            print(f"[trading] {label} JSON 파싱 실패: {e} (응답 첫 300자: {r.text[:300]!r})")
            break

        if first:
            first = False
            # 첫 호출만 응답 구조 dump (디버그)
            print(f"[trading] {label} 첫 응답 키: {list(data.keys())}")
            print(f"[trading] {label} rt_cd={data.get('rt_cd')} msg={data.get('msg1','')[:200]}")
            out1 = data.get("output1")
            out2 = data.get("output2") or data.get("output")
            if out1:
                if isinstance(out1, list) and out1:
                    print(f"[trading] {label} output1[0] 키: {list(out1[0].keys())[:10]}")
                elif isinstance(out1, dict):
                    print(f"[trading] {label} output1 키: {list(out1.keys())[:10]}")
            if isinstance(out2, list) and out2:
                print(f"[trading] {label} output2[0] 키: {list(out2[0].keys())[:10]}")
                print(f"[trading] {label} output2[0] 샘플: {dict(list(out2[0].items())[:6])}")

        if data.get("rt_cd") != "0":
            print(f"[trading] {label} rt_cd={data.get('rt_cd')} msg={data.get('msg1','')[:200]} — 중단")
            break

        bars = data.get("output2") or data.get("output") or []
        if not bars:
            print(f"[trading] {label}: 빈 응답 → 종료")
            break

        added = 0
        earliest = cur
        for b in bars:
            d_str = b.get("stck_bsop_date") or b.get("bsop_date") or ""
            if len(d_str) != 8:
                continue
            d_iso = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            if d_iso in seen:
                continue
            # 거래대금 필드 후보
            amt = (b.get("acml_tr_pbmn")
                   or b.get("acml_tr_pbm")
                   or b.get("acc_trd_value")
                   or b.get("tr_pbmn"))
            if not amt:
                continue
            try:
                # KIS acml_tr_pbmn 단위는 백만원 → 원으로 변환
                v = int(str(amt).replace(",", "")) * 1_000_000
            except Exception:
                continue
            if v <= 0:
                continue
            # 지수 종가 (선택) — bstp_nmix_prpr
            close = b.get("bstp_nmix_prpr") or b.get("bstp_nmix_close") or b.get("nmix_prpr")
            try:
                close_val = float(str(close).replace(",", "")) if close else None
            except Exception:
                close_val = None
            row = {"date": d_iso, "value": v}
            if close_val is not None and close_val > 0:
                row["close"] = close_val
            out.append(row)
            seen.add(d_iso)
            added += 1
            try:
                d_date = dt.date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:]))
                if d_date < earliest:
                    earliest = d_date
            except Exception:
                pass

        print(f"[trading] {label}: +{added} (누계 {len(out)}), 최오래 {earliest}")

        if added == 0 or earliest >= cur:
            break
        cur = earliest - dt.timedelta(days=1)
        time.sleep(0.3)

    out.sort(key=lambda x: x["date"])
    return out


def fetch_kofia_macro_daily():
    """
    KOFIA freesis 메인페이지(stat/main.do)에서 어제 발표분 한 줄 추출.
    매일 1줄씩 누적되도록 main()에서 prev에 append.
    """
    import re
    url = "https://freesis.kofia.or.kr/stat/main.do"
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15"),
        })
        if r.status_code != 200:
            print(f"[kofia] HTTP {r.status_code}")
            return None, None
        html = r.text
    except Exception as e:
        print(f"[kofia] 요청 실패: {e}")
        return None, None

    def _extract(label):
        m = re.search(label + r'[\s\S]{0,200}?(\d{2}\/\d{2})[\s\S]{0,80}?([\d,]{7,})', html)
        if not m:
            print(f"[kofia] '{label}' 패턴 못 찾음")
            return None
        mmdd = m.group(1)        # "06/04"
        val  = m.group(2).replace(",", "")
        try:
            # 백만원 단위 → 원
            v_won = int(val) * 1_000_000
        except Exception:
            return None
        # MM/DD를 올해 ISO 날짜로 (KOFIA는 거래일 기준 그 해 데이터)
        try:
            mm, dd = mmdd.split("/")
            year = dt.date.today().year
            # 12월이 1월보다 늦으면 작년 데이터
            today = dt.date.today()
            cand = dt.date(year, int(mm), int(dd))
            if cand > today + dt.timedelta(days=1):
                cand = dt.date(year - 1, int(mm), int(dd))
            return {"date": cand.strftime("%Y-%m-%d"), "value": v_won}
        except Exception as e:
            print(f"[kofia] 날짜 파싱 실패: {e}")
            return None

    dep = _extract("투자자예탁금")
    cre = _extract("신용융자")
    if dep:    print(f"[kofia] 투자자예탁금: {dep['date']} = {dep['value']:,}원")
    if cre:    print(f"[kofia] 신용융자:     {cre['date']} = {cre['value']:,}원")
    return dep, cre


def main():
    print(f"=== 국내증시현황 데이터 수집 ({dt.date.today()}) ===")

    tr_kospi, tr_kosdaq = [], []
    idx_kospi, idx_kosdaq = [], []  # 지수 종가 시계열
    token = kis_token()
    if token:
        raw_kospi  = fetch_kis_index(token, "0001", "KOSPI")
        time.sleep(0.3)
        raw_kosdaq = fetch_kis_index(token, "1001", "KOSDAQ")
        # 거래대금/지수 분리
        tr_kospi  = [{"date": r["date"], "value": r["value"]} for r in raw_kospi]
        tr_kosdaq = [{"date": r["date"], "value": r["value"]} for r in raw_kosdaq]
        idx_kospi  = [{"date": r["date"], "value": r["close"]} for r in raw_kospi  if "close" in r]
        idx_kosdaq = [{"date": r["date"], "value": r["close"]} for r in raw_kosdaq if "close" in r]
        print(f"[index] KOSPI 종가 {len(idx_kospi)}일치, KOSDAQ 종가 {len(idx_kosdaq)}일치")
    else:
        print("토큰 없음 — 거래대금/지수 빈 배열 유지")

    # KOFIA 어제 발표분 1줄 (누적용)
    kofia_dep, kofia_cre = fetch_kofia_macro_daily()
    deposits = [kofia_dep] if kofia_dep else []
    cr_kospi = [kofia_cre] if kofia_cre else []  # 통합 신용 (KOSPI 컬럼으로 표시)
    cr_kosdaq = []

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
        "index_kospi":    _merge(prev.get("index_kospi"),   idx_kospi),
        "index_kosdaq":   _merge(prev.get("index_kosdaq"),  idx_kosdaq),
    }

    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n→ {OUT}")
    for k in ("deposits", "credit_kospi", "credit_kosdaq", "trading_kospi", "trading_kosdaq"):
        print(f"  {k}: {len(out[k])} rows")


if __name__ == "__main__":
    main()
