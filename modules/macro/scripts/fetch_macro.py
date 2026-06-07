#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 매크로 지표 수집기 — FRED API

env: FRED_API_KEY (https://fred.stlouisfed.org 에서 무료 발급)

6개 시계열:
  1. 미국채 10년물 금리       DGS10                          (일별, %)
  2. 연준 기준금리            DFF                            (일별, %)
  3. Core CPI                CPILFESL                       (월별, 지수)
  4. Core Sticky CPI ex Shelter STICKCPIXSHLTRM158SFRBATL    (월별, % yoy)
  5. 미국 분기 GDP 성장률     A191RL1Q225SBEA                (분기, % 연율)
  6. WTI 유가                DCOILWTICO                     (일별, $)

각 지표별로 최대 3년치 (혹은 5년치) 누적해서 macro.json에 저장.
"""

import os
import sys
import json
import datetime as dt
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "data" / "macro.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
print(f"[env] FRED_API_KEY: {'SET (len=' + str(len(FRED_KEY)) + ')' if FRED_KEY else '*** NOT SET ***'}")

# 시리즈 정의 — (id, label, unit, observation_start years back, freq hint)
# internal=True 인 시리즈는 derived 계산용 raw 데이터로만 사용, JSON 출력에서 제외
SERIES = [
    {"key": "ust10y",      "id": "DGS10",                          "label": "미국채 10년물",            "unit": "%",    "years": 3, "freq": "d"},
    {"key": "fedfunds",    "id": "DFF",                            "label": "연준 기준금리",            "unit": "%",    "years": 5, "freq": "d"},
    # 공식 발표(BLS press release)와 동일하게 비조정(NSA) 기준으로 YoY 계산
    {"key": "core_cpi",    "id": "CPILFENS",                       "label": "Core CPI",                 "unit": "%yoy", "years": 3, "freq": "m", "transform": "yoy"},
    # core_cpi_xs는 raw fetch가 아니라 _core_idx + _shelter_idx 에서 계산 (NSA 기준)
    {"key": "_core_idx",   "id": "CPILFENS",                       "label": "Core CPI index (NSA)",     "unit": "idx",  "years": 4, "freq": "m", "internal": True},
    {"key": "_shelter_idx","id": "CUUR0000SAH1",                   "label": "Shelter index (NSA)",      "unit": "idx",  "years": 4, "freq": "m", "internal": True},
    {"key": "sticky",      "id": "CRESTKCPIXSLTRM159SFRBATL",      "label": "Core Sticky CPI ex Shelter","unit": "%yoy","years": 3, "freq": "m"},
    {"key": "gdp",         "id": "A191RL1Q225SBEA",                "label": "미국 GDP 성장률",         "unit": "%",    "years": 5, "freq": "q"},
    {"key": "wti",         "id": "DCOILWTICO",                     "label": "WTI 유가",                 "unit": "$",    "years": 3, "freq": "d"},
]

# Core CPI 중 Shelter의 가중치
# BLS 2024 Relative Importance: Shelter 36.671% / Core 80.012% = 0.458
SHELTER_WEIGHT_IN_CORE = 0.458

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id, start_date):
    """FRED API에서 시계열 가져오기. [{date, value}] 반환."""
    if not FRED_KEY:
        print(f"  [{series_id}] FRED_API_KEY 없음 — 스킵")
        return []
    params = {
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "observation_start": start_date.strftime("%Y-%m-%d"),
    }
    try:
        r = requests.get(FRED_BASE, params=params, timeout=30)
    except Exception as e:
        print(f"  [{series_id}] 요청 실패: {e}")
        return []
    if r.status_code != 200:
        print(f"  [{series_id}] HTTP {r.status_code}: {r.text[:200]}")
        return []
    try:
        data = r.json()
    except Exception as e:
        print(f"  [{series_id}] JSON 파싱 실패: {e}")
        return []
    obs = data.get("observations", [])
    out = []
    for o in obs:
        date = o.get("date")
        val = o.get("value")
        if not date or val in (".", "", None):
            continue
        try:
            v = float(val)
        except Exception:
            continue
        out.append({"date": date, "value": v})
    print(f"  [{series_id}] {len(out)} 포인트 ({out[0]['date'] if out else '—'} ~ {out[-1]['date'] if out else '—'})")
    return out


def apply_yoy(points):
    """월별 지수를 전년동월 대비 % 변화율로 변환 (Core CPI 용)."""
    # date → value 맵
    by_date = {p["date"]: p["value"] for p in points}
    out = []
    for p in points:
        d = dt.date.fromisoformat(p["date"])
        prev = d.replace(year=d.year - 1).isoformat()
        if prev in by_date and by_date[prev]:
            yoy = (p["value"] / by_date[prev] - 1.0) * 100.0
            out.append({"date": p["date"], "value": round(yoy, 2)})
    return out


def compute_core_xs(core_idx_pts, shelter_idx_pts):
    """Core CPI ex Shelter (식·에너지·주거 제외) YoY % 계산.
    Core CPI = (Shelter 가중치) × Shelter + (1 - Shelter 가중치) × Core_ex_Shelter
    → Core_ex_Shelter = (Core - w × Shelter) / (1 - w)
    BLS 2024 기준 Shelter의 Core 내 가중치 약 0.42.
    """
    w = SHELTER_WEIGHT_IN_CORE
    core_by = {p["date"]: p["value"] for p in core_idx_pts}
    shelter_by = {p["date"]: p["value"] for p in shelter_idx_pts}
    out = []
    for date, c in core_by.items():
        s = shelter_by.get(date)
        if s is None:
            continue
        d = dt.date.fromisoformat(date)
        prev = d.replace(year=d.year - 1).isoformat()
        cp = core_by.get(prev)
        sp = shelter_by.get(prev)
        if not cp or not sp:
            continue
        core_yoy = (c / cp - 1.0) * 100.0
        shelter_yoy = (s / sp - 1.0) * 100.0
        core_xs_yoy = (core_yoy - w * shelter_yoy) / (1.0 - w)
        out.append({"date": date, "value": round(core_xs_yoy, 2)})
    return out


def main():
    print(f"=== 글로벌 매크로 수집 ({dt.date.today()}) ===")
    today = dt.date.today()
    result = {"updated_at": today.strftime("%Y-%m-%d"), "series": {}}
    raw_cache = {}

    for spec in SERIES:
        years = spec.get("years", 3)
        # yoy 변환이 필요한 경우 추가로 1년 더 받아야 함
        extra = 1 if spec.get("transform") == "yoy" else 0
        start = today - dt.timedelta(days=365 * (years + extra) + 30)
        pts = fetch_series(spec["id"], start)
        if spec.get("transform") == "yoy":
            pts = apply_yoy(pts)
        # internal 시리즈는 raw 그대로 캐시 (계산용)
        if spec.get("internal"):
            raw_cache[spec["key"]] = pts
            continue
        # years 잘라내기 (최종 표시 기간)
        cutoff = (today - dt.timedelta(days=365 * years + 30)).strftime("%Y-%m-%d")
        pts = [p for p in pts if p["date"] >= cutoff]

        result["series"][spec["key"]] = {
            "id": spec["id"],
            "label": spec["label"],
            "unit": spec["unit"],
            "freq": spec["freq"],
            "data": pts,
        }

    # ── derived: Core CPI ex Shelter (KB증권/LSEG와 동일 기준) ──
    if "_core_idx" in raw_cache and "_shelter_idx" in raw_cache:
        core_xs = compute_core_xs(raw_cache["_core_idx"], raw_cache["_shelter_idx"])
        cutoff = (today - dt.timedelta(days=365 * 3 + 30)).strftime("%Y-%m-%d")
        core_xs = [p for p in core_xs if p["date"] >= cutoff]
        # 위치: core_cpi 다음에 끼워넣기
        new_series = {}
        for k, v in result["series"].items():
            new_series[k] = v
            if k == "core_cpi":
                new_series["core_cpi_xs"] = {
                    "id": "DERIVED:CPILFESL-Shelter*0.42",
                    "label": "Core CPI ex Shelter",
                    "unit": "%yoy",
                    "freq": "m",
                    "data": core_xs,
                }
        result["series"] = new_series
        print(f"[derived] Core CPI ex Shelter: {len(core_xs)} pts" + (f", 최신 {core_xs[-1]['date']} = {core_xs[-1]['value']}%" if core_xs else ""))

    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n→ {OUT}")
    for k, s in result["series"].items():
        print(f"  {k:12s} ({s['label']}): {len(s['data'])} pts")


if __name__ == "__main__":
    main()
