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
SERIES = [
    {"key": "ust10y",   "id": "DGS10",                       "label": "미국채 10년물",      "unit": "%",   "years": 3, "freq": "d"},
    {"key": "fedfunds", "id": "DFF",                         "label": "연준 기준금리",       "unit": "%",   "years": 5, "freq": "d"},
    {"key": "core_cpi", "id": "CPILFESL",                    "label": "Core CPI",            "unit": "%yoy","years": 3, "freq": "m", "transform": "yoy"},
    {"key": "sticky",   "id": "STICKCPIXSHLTRM158SFRBATL",   "label": "Sticky CPI ex Shelter","unit": "%yoy","years": 3, "freq": "m"},
    {"key": "gdp",      "id": "A191RL1Q225SBEA",             "label": "미국 GDP 성장률",     "unit": "%",   "years": 5, "freq": "q"},
    {"key": "wti",      "id": "DCOILWTICO",                  "label": "WTI 유가",            "unit": "$",   "years": 3, "freq": "d"},
]

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


def main():
    print(f"=== 글로벌 매크로 수집 ({dt.date.today()}) ===")
    today = dt.date.today()
    result = {"updated_at": today.strftime("%Y-%m-%d"), "series": {}}

    for spec in SERIES:
        years = spec.get("years", 3)
        # yoy 변환이 필요한 경우 추가로 1년 더 받아야 함
        extra = 1 if spec.get("transform") == "yoy" else 0
        start = today - dt.timedelta(days=365 * (years + extra) + 30)
        pts = fetch_series(spec["id"], start)
        if spec.get("transform") == "yoy":
            pts = apply_yoy(pts)
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

    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"\n→ {OUT}")
    for k, s in result["series"].items():
        print(f"  {k:10s} ({s['label']}): {len(s['data'])} pts")


if __name__ == "__main__":
    main()
