#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 매크로 지표 수집기 — FRED API (Lightsail VM 버전).

GitHub Action 대신 Lightsail cron 으로 매 4시간 실행 → FRED publish 잡힐 확률↑
fetch 후 GitHub Contents API PUT 로 직접 push (autosync 또는 git clone 안 씀).

env:
  FRED_API_KEY  — https://fred.stlouisfed.org 에서 무료 발급
  GITHUB_PAT    — yeobtoni-stock-bot 리포 쓰기 권한
"""

import os
import sys
import json
import ssl
import base64
import datetime as dt
import urllib.parse
import urllib.request
import urllib.error

import requests

REPO = "goldpigbankgazua-dev/yeobtoni-stock-bot"
REPO_PATH = "modules/macro/data/macro.json"
BRANCH = "main"

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

FRED_KEY = os.environ.get("FRED_API_KEY", "").strip()
GITHUB_PAT = os.environ.get("GITHUB_PAT", "").strip()
print(f"[env] FRED_API_KEY: {'SET' if FRED_KEY else '*** NOT SET ***'}")
print(f"[env] GITHUB_PAT:   {'SET' if GITHUB_PAT else '*** NOT SET ***'}")

# 시리즈 정의 — (id, label, unit, observation_start years back, freq hint)
SERIES = [
    {"key": "ust10y",      "id": "DGS10",                          "label": "미국채 10년물",            "unit": "%",    "years": 3, "freq": "d"},
    {"key": "_fed_upper",  "id": "DFEDTARU",                       "label": "Fed Target Upper",         "unit": "%",    "years": 5, "freq": "d", "internal": True},
    {"key": "_fed_lower",  "id": "DFEDTARL",                       "label": "Fed Target Lower",         "unit": "%",    "years": 5, "freq": "d", "internal": True},
    {"key": "core_cpi",    "id": "CPILFENS",                       "label": "Core CPI",                 "unit": "%yoy", "years": 3, "freq": "m", "transform": "yoy"},
    {"key": "_core_idx",   "id": "CPILFENS",                       "label": "Core CPI index (NSA)",     "unit": "idx",  "years": 4, "freq": "m", "internal": True},
    {"key": "_shelter_idx","id": "CUUR0000SAH1",                   "label": "Shelter index (NSA)",      "unit": "idx",  "years": 4, "freq": "m", "internal": True},
    {"key": "sticky",      "id": "CRESTKCPIXSLTRM159SFRBATL",      "label": "Core Sticky CPI ex Shelter","unit": "%yoy","years": 3, "freq": "m"},
    {"key": "gdp",         "id": "A191RL1Q225SBEA",                "label": "미국 GDP 성장률",         "unit": "%",    "years": 5, "freq": "q"},
    {"key": "wti",         "id": "DCOILWTICO",                     "label": "WTI 유가",                 "unit": "$",    "years": 3, "freq": "d"},
    {"key": "vix",         "id": "VIXCLS",                         "label": "VIX 지수",                 "unit": "",     "years": 3, "freq": "d"},
]

SHELTER_WEIGHT_IN_CORE = 0.458

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id, start_date):
    if not FRED_KEY:
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
    print(f"  [{series_id}] {len(out)} pts ({out[0]['date'] if out else '—'} ~ {out[-1]['date'] if out else '—'})")
    return out


def apply_yoy(points):
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


# ============================================================
# GitHub Contents API — push
# ============================================================
def github_get_sha():
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            return json.loads(resp.read())["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def github_put(content_str, sha=None):
    url = f"https://api.github.com/repos/{REPO}/contents/{REPO_PATH}"
    payload = {
        "message": f"data: macro {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} KST (VM)",
        "content": base64.b64encode(content_str.encode("utf-8")).decode(),
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="PUT", headers={
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return resp.status


# ============================================================
# 메인
# ============================================================
def main():
    if not FRED_KEY:
        print("✗ FRED_API_KEY 없음", file=sys.stderr); sys.exit(1)
    if not GITHUB_PAT:
        print("✗ GITHUB_PAT 없음", file=sys.stderr); sys.exit(1)

    print(f"=== 매크로 수집 ({dt.date.today()}) ===")
    today = dt.date.today()
    result = {"updated_at": today.strftime("%Y-%m-%d"), "series": {}}
    raw_cache = {}

    for spec in SERIES:
        years = spec.get("years", 3)
        extra = 1 if spec.get("transform") == "yoy" else 0
        start = today - dt.timedelta(days=365 * (years + extra) + 30)
        pts = fetch_series(spec["id"], start)
        if spec.get("transform") == "yoy":
            pts = apply_yoy(pts)
        if spec.get("internal"):
            raw_cache[spec["key"]] = pts
            continue
        cutoff = (today - dt.timedelta(days=365 * years + 30)).strftime("%Y-%m-%d")
        pts = [p for p in pts if p["date"] >= cutoff]
        result["series"][spec["key"]] = {
            "id": spec["id"], "label": spec["label"], "unit": spec["unit"],
            "freq": spec["freq"], "data": pts,
        }

    # derived: 연준 기준금리 band
    if "_fed_upper" in raw_cache and "_fed_lower" in raw_cache:
        u_by = {p["date"]: p["value"] for p in raw_cache["_fed_upper"]}
        l_by = {p["date"]: p["value"] for p in raw_cache["_fed_lower"]}
        band_pts = []
        for date, u in u_by.items():
            l = l_by.get(date)
            if l is None: continue
            band_pts.append({"date": date, "value": round((u + l) / 2.0, 4), "upper": u, "lower": l})
        band_pts.sort(key=lambda x: x["date"])
        cutoff = (today - dt.timedelta(days=365 * 5 + 30)).strftime("%Y-%m-%d")
        band_pts = [p for p in band_pts if p["date"] >= cutoff]
        new_series = {}
        inserted = False
        for k, v in result["series"].items():
            new_series[k] = v
            if k == "ust10y" and not inserted:
                new_series["fedfunds"] = {
                    "id": "DERIVED:DFEDTARU+DFEDTARL", "label": "연준 기준금리",
                    "unit": "%", "freq": "d", "data": band_pts,
                }
                inserted = True
        if not inserted:
            new_series = {"fedfunds": {
                "id": "DERIVED:DFEDTARU+DFEDTARL", "label": "연준 기준금리",
                "unit": "%", "freq": "d", "data": band_pts,
            }, **result["series"]}
        result["series"] = new_series

    # derived: Core CPI ex Shelter
    if "_core_idx" in raw_cache and "_shelter_idx" in raw_cache:
        core_xs = compute_core_xs(raw_cache["_core_idx"], raw_cache["_shelter_idx"])
        cutoff = (today - dt.timedelta(days=365 * 3 + 30)).strftime("%Y-%m-%d")
        core_xs = [p for p in core_xs if p["date"] >= cutoff]
        new_series = {}
        for k, v in result["series"].items():
            new_series[k] = v
            if k == "core_cpi":
                new_series["core_cpi_xs"] = {
                    "id": "DERIVED:CPILFESL-Shelter*0.458", "label": "Core CPI ex Shelter",
                    "unit": "%yoy", "freq": "m", "data": core_xs,
                }
        result["series"] = new_series

    # 요약 + GitHub push
    print("\n=== 요약 ===")
    for k, s in result["series"].items():
        last = s["data"][-1] if s["data"] else None
        print(f"  {k:12s} {len(s['data']):4d} pts · last {last}")

    content_str = json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    try:
        sha = github_get_sha()
        status = github_put(content_str, sha=sha)
        print(f"\n[gh] PUT OK HTTP {status} → {REPO}/{REPO_PATH}")
    except Exception as e:
        print(f"\n[gh] PUT 실패: {e}", file=sys.stderr); sys.exit(2)


if __name__ == "__main__":
    main()
