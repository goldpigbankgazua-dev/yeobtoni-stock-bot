#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIS API → 코스피·코스닥 지수/거래대금 누적 → GitHub PUT
(GitHub Actions cron 신뢰성 문제로 Oracle VM 이관)

env:
  KIS_APP_KEY, KIS_APP_SECRET  — 한국투자증권 OpenAPI 키
  GITHUB_PAT                    — fine-grained contents:write, yeobtoni-stock-bot
"""
import os
import sys
import json
import time
import base64
import datetime as dt
import requests

PAT = os.environ.get("GITHUB_PAT", "").strip()
APP_KEY = os.environ.get("KIS_APP_KEY", "").strip()
APP_SECRET = os.environ.get("KIS_APP_SECRET", "").strip()

if not PAT:        sys.exit("ERROR: GITHUB_PAT 환경변수 없음")
if not APP_KEY:    sys.exit("ERROR: KIS_APP_KEY 환경변수 없음")
if not APP_SECRET: sys.exit("ERROR: KIS_APP_SECRET 환경변수 없음")

OWNER  = "goldpigbankgazua-dev"
REPO   = "yeobtoni-stock-bot"
PATH   = "modules/market/data/market.json"
BRANCH = "main"
DAYS   = 400

API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{PATH}"
GH_HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

KIS_BASE = "https://openapi.koreainvestment.com:9443"


def kis_token():
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
    if r.status_code != 200:
        print(f"[KIS] 토큰 HTTP {r.status_code}: {r.text[:300]}")
        return None
    return r.json().get("access_token")


def fetch_kis_index(token, iscd, label):
    """국내업종 일별지수 — inquire-index-daily-price (TR_ID: FHPUP02120000)
    30영업일씩 받아 DAYS만큼 누적.
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
    out, seen = [], set()
    today = dt.date.today()
    start = today - dt.timedelta(days=DAYS)
    cur = today
    safety = 25
    while cur > start and safety > 0:
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
            print(f"[{label}] 예외: {e}")
            break
        if r.status_code != 200:
            print(f"[{label}] HTTP {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        if data.get("rt_cd") != "0":
            print(f"[{label}] rt_cd={data.get('rt_cd')} msg={data.get('msg1','')[:160]}")
            break
        bars = data.get("output2") or data.get("output") or []
        if not bars:
            break
        added, earliest = 0, cur
        for b in bars:
            d_str = b.get("stck_bsop_date") or b.get("bsop_date") or ""
            if len(d_str) != 8: continue
            d_iso = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
            if d_iso in seen: continue
            amt = (b.get("acml_tr_pbmn") or b.get("acml_tr_pbm")
                   or b.get("acc_trd_value") or b.get("tr_pbmn"))
            close = b.get("bstp_nmix_prpr") or b.get("bstp_nmix_close") or b.get("nmix_prpr")
            if not amt: continue
            try:
                v = int(str(amt).replace(",", "")) * 1_000_000  # 백만원 → 원
            except Exception:
                continue
            if v <= 0: continue
            try:
                cl = float(str(close).replace(",", "")) if close else None
            except Exception:
                cl = None
            row = {"date": d_iso, "value": v}
            if cl and cl > 0: row["close"] = cl
            out.append(row)
            seen.add(d_iso)
            added += 1
            try:
                d_date = dt.date(int(d_str[:4]), int(d_str[4:6]), int(d_str[6:]))
                if d_date < earliest: earliest = d_date
            except Exception:
                pass
        print(f"[{label}] +{added} (누계 {len(out)}, 최오래 {earliest})")
        if added == 0 or earliest >= cur: break
        cur = earliest - dt.timedelta(days=1)
        time.sleep(0.3)
    out.sort(key=lambda x: x["date"])
    return out


def github_get_file():
    r = requests.get(API_BASE + f"?ref={BRANCH}", headers=GH_HEADERS, timeout=20)
    if r.status_code == 404: return None, None
    r.raise_for_status()
    j = r.json()
    try:
        data = json.loads(base64.b64decode(j.get("content","")).decode("utf-8"))
    except Exception as e:
        print(f"[gh] 기존 파일 파싱 실패: {e}")
        data = {}
    return data, j.get("sha")


def github_put_file(content_json, sha, message):
    body = {
        "message": message,
        "content": base64.b64encode(content_json.encode("utf-8")).decode("ascii"),
        "branch":  BRANCH,
        "committer": {"name": "vm-market-bot", "email": "vm-market@yeobtoni.local"},
    }
    if sha: body["sha"] = sha
    r = requests.put(API_BASE, headers=GH_HEADERS, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"[gh] PUT 실패 HTTP {r.status_code}: {r.text[:300]}")
        return False
    print(f"[gh] PUT OK HTTP {r.status_code}")
    return True


def merge(existing, new):
    if not new and existing: return existing
    if not existing: return new
    seen = {p["date"] for p in new}
    merged = list(new) + [p for p in existing if p["date"] not in seen]
    merged.sort(key=lambda x: x["date"])
    cutoff = (dt.date.today() - dt.timedelta(days=DAYS)).strftime("%Y-%m-%d")
    return [p for p in merged if p["date"] >= cutoff]


def main():
    today = dt.date.today()
    print(f"=== Market fetch ({today}) ===")
    token = kis_token()
    if not token: sys.exit("KIS 토큰 발급 실패 — 중단")

    raw_kospi  = fetch_kis_index(token, "0001", "KOSPI")
    time.sleep(0.3)
    raw_kosdaq = fetch_kis_index(token, "1001", "KOSDAQ")

    tr_kospi  = [{"date": r["date"], "value": r["value"]} for r in raw_kospi]
    tr_kosdaq = [{"date": r["date"], "value": r["value"]} for r in raw_kosdaq]
    idx_kospi  = [{"date": r["date"], "value": r["close"]} for r in raw_kospi  if "close" in r]
    idx_kosdaq = [{"date": r["date"], "value": r["close"]} for r in raw_kosdaq if "close" in r]

    existing, sha = github_get_file()
    if existing is None:
        existing = {}
        print("[gh] 기존 파일 없음")

    before = {k: len(existing.get(k, [])) for k in ["trading_kospi","trading_kosdaq","index_kospi","index_kosdaq"]}

    new = {
        "updated_at":     today.strftime("%Y-%m-%d"),
        "deposits":       existing.get("deposits", []),       # KOFIA가 따로 관리
        "credit_kospi":   existing.get("credit_kospi", []),
        "credit_kosdaq":  existing.get("credit_kosdaq", []),
        "credit_total":   existing.get("credit_total", []),
        "loan":           existing.get("loan", []),
        "trading_kospi":  merge(existing.get("trading_kospi", []), tr_kospi),
        "trading_kosdaq": merge(existing.get("trading_kosdaq", []), tr_kosdaq),
        "index_kospi":    merge(existing.get("index_kospi", []),   idx_kospi),
        "index_kosdaq":   merge(existing.get("index_kosdaq", []),  idx_kosdaq),
    }

    after = {k: len(new.get(k, [])) for k in before}
    print(f"[merge] " + ", ".join(f"{k} {before[k]}→{after[k]}" for k in before))

    if before == after and sha:
        print("[gh] 변경 없음 — PUT 스킵")
        return

    github_put_file(
        json.dumps(new, ensure_ascii=False, separators=(",", ":")),
        sha, f"data(market): {today}"
    )


if __name__ == "__main__":
    main()
