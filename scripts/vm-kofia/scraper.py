#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KOFIA freesis 시계열 API 직접 호출 → 예탁금 + 신용잔고(전체/코스피/코스닥) 누적 → GitHub PUT

env: GITHUB_PAT (fine-grained contents:write, yeobtoni-stock-bot)

endpoint 캡쳐 (2026-06-06): POST https://freesis.kofia.or.kr/meta/getMetaDataList.do
  body: {"dmSearch":{"tmpV40":"1000000","tmpV41":"1","tmpV1":"D",
                     "tmpV45":"YYYYMMDD","tmpV46":"YYYYMMDD","OBJ_NM":"..."}}
  - 예탁금:   OBJ_NM=STATSCU0100000060BO  (TMPV2=투자자예탁금)
  - 신용잔고: OBJ_NM=STATSCU0100000070BO  (TMPV2=전체, TMPV3=코스피, TMPV4=코스닥)
  - 응답 단위: 백만원
"""
import os, json, sys, base64
import datetime as dt
import requests

PAT = os.environ.get("GITHUB_PAT", "").strip()
if not PAT:
    print("ERROR: GITHUB_PAT 환경변수 없음", file=sys.stderr); sys.exit(1)

OWNER  = "goldpigbankgazua-dev"
REPO   = "yeobtoni-stock-bot"
PATH   = "modules/market/data/kofia.json"
BRANCH = "main"
DAYS_KEEP = 400

API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{PATH}"
GH_HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

KOFIA_URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
KOFIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Content-Type": "application/json",
    "Referer": "https://freesis.kofia.or.kr/stat/FreeSIS.do",
    "Origin":  "https://freesis.kofia.or.kr",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch_kofia_series(obj_nm, start_date, end_date):
    """OBJ_NM에 해당하는 일별 시계열 받기. start/end_date: datetime.date"""
    body = {
        "dmSearch": {
            "tmpV40": "1000000",
            "tmpV41": "1",
            "tmpV1":  "D",
            "tmpV45": start_date.strftime("%Y%m%d"),
            "tmpV46": end_date.strftime("%Y%m%d"),
            "OBJ_NM": obj_nm,
        }
    }
    r = requests.post(KOFIA_URL, headers=KOFIA_HEADERS, json=body, timeout=30)
    r.raise_for_status()
    j = r.json()
    return j.get("ds1", [])

def to_won(million_int):
    """백만원 → 원"""
    try: return int(million_int) * 1_000_000
    except Exception: return None

def to_date(yyyymmdd):
    s = str(yyyymmdd)
    if len(s) != 8: return None
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"

def parse_deposits(rows):
    """OBJ_NM=STATSCU0100000060BO 응답 → [{date,value}]"""
    out = []
    for r in rows:
        d = to_date(r.get("TMPV1")); v = to_won(r.get("TMPV2"))
        if d and v is not None: out.append({"date": d, "value": v})
    return out

def parse_credit(rows):
    """OBJ_NM=STATSCU0100000070BO 응답 → (total, kospi, kosdaq) 각각 [{date,value}]"""
    total, kospi, kosdaq = [], [], []
    for r in rows:
        d = to_date(r.get("TMPV1"))
        if not d: continue
        t = to_won(r.get("TMPV2")); k = to_won(r.get("TMPV3")); kd = to_won(r.get("TMPV4"))
        if t  is not None: total.append({"date": d, "value": t})
        if k  is not None: kospi.append({"date": d, "value": k})
        if kd is not None: kosdaq.append({"date": d, "value": kd})
    return total, kospi, kosdaq

def merge_series(existing, new_rows):
    """existing + new_rows → date 유일성 + DAYS_KEEP cutoff."""
    by_date = {p["date"]: p for p in existing}
    for r in new_rows:
        by_date[r["date"]] = r
    out = sorted(by_date.values(), key=lambda x: x["date"])
    cutoff = (dt.date.today() - dt.timedelta(days=DAYS_KEEP)).strftime("%Y-%m-%d")
    return [p for p in out if p["date"] >= cutoff]

def github_get_file():
    r = requests.get(API_BASE + f"?ref={BRANCH}", headers=GH_HEADERS, timeout=20)
    if r.status_code == 404: return None, None
    r.raise_for_status()
    j = r.json(); sha = j.get("sha")
    try:
        data = json.loads(base64.b64decode(j.get("content","")).decode("utf-8"))
    except Exception as e:
        print(f"[gh] 기존 파일 파싱 실패: {e}")
        data = {}
    return data, sha

def github_put_file(content_json, sha, message):
    body = {
        "message": message,
        "content": base64.b64encode(content_json.encode("utf-8")).decode("ascii"),
        "branch":  BRANCH,
        "committer": {"name": "vm-kofia-bot", "email": "vm-kofia@yeobtoni.local"},
    }
    if sha: body["sha"] = sha
    r = requests.put(API_BASE, headers=GH_HEADERS, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"[gh] PUT 실패 HTTP {r.status_code}: {r.text[:300]}"); return False
    print(f"[gh] PUT OK (HTTP {r.status_code})"); return True

def main():
    today = dt.date.today()
    # 최근 10일 범위로 받음 (휴일 보정 + 누락 보충). 1년치는 백필 끝났으니 daily는 짧게.
    start = today - dt.timedelta(days=10)
    print(f"=== KOFIA scrape {start} → {today} ===")

    # 1) freesis fetch
    try:
        dep_rows = fetch_kofia_series("STATSCU0100000060BO", start, today)
        cre_rows = fetch_kofia_series("STATSCU0100000070BO", start, today)
    except Exception as e:
        print(f"[kofia] fetch 실패: {e}"); sys.exit(1)

    deposits_new = parse_deposits(dep_rows)
    credit_total_new, credit_kospi_new, credit_kosdaq_new = parse_credit(cre_rows)
    print(f"[fetch] deposits={len(deposits_new)} credit total/kospi/kosdaq={len(credit_total_new)}/{len(credit_kospi_new)}/{len(credit_kosdaq_new)}")
    if deposits_new: print(f"  최신 예탁금: {deposits_new[-1]}")
    if credit_total_new: print(f"  최신 신용 전체: {credit_total_new[-1]}")

    # 2) 기존 파일 GET
    existing, sha = github_get_file()
    if existing is None:
        existing = {"updated_at": "", "deposits": [], "credit": [], "credit_total": [], "credit_kospi": [], "credit_kosdaq": []}
        print("[gh] 기존 파일 없음, 새로 생성")
    else:
        print(f"[gh] 기존 deposits={len(existing.get('deposits',[]))} credit_total={len(existing.get('credit_total',[]))} credit_kospi={len(existing.get('credit_kospi',[]))} credit_kosdaq={len(existing.get('credit_kosdaq',[]))}")

    # 3) 병합
    before = {
        "d": len(existing.get("deposits", [])),
        "t": len(existing.get("credit_total", [])),
        "k": len(existing.get("credit_kospi", [])),
        "kd": len(existing.get("credit_kosdaq", [])),
    }
    existing["deposits"]      = merge_series(existing.get("deposits", []), deposits_new)
    existing["credit_total"]  = merge_series(existing.get("credit_total", []) or existing.get("credit", []), credit_total_new)
    existing["credit"]        = existing["credit_total"]  # backward compat
    existing["credit_kospi"]  = merge_series(existing.get("credit_kospi", []),  credit_kospi_new)
    existing["credit_kosdaq"] = merge_series(existing.get("credit_kosdaq", []), credit_kosdaq_new)
    existing["updated_at"]    = today.strftime("%Y-%m-%d")

    after = {
        "d": len(existing["deposits"]),
        "t": len(existing["credit_total"]),
        "k": len(existing["credit_kospi"]),
        "kd": len(existing["credit_kosdaq"]),
    }
    print(f"[merge] dep {before['d']}→{after['d']}, cred t/k/kd {before['t']}→{after['t']} / {before['k']}→{after['k']} / {before['kd']}→{after['kd']}")

    # 4) 변경 없으면 skip
    if before == after and sha:
        # updated_at만 갱신해도 push? skip이 깔끔.
        print("[gh] 변경 없음 — PUT 스킵"); return

    # 5) PUT
    new_json = json.dumps(existing, ensure_ascii=False, separators=(",", ":"))
    msg = f"data(kofia): {today}"
    github_put_file(new_json, sha, msg)

if __name__ == "__main__":
    main()
