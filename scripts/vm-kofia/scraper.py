#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KOFIA freesis 어제 발표분 1줄 스크랩 → GitHub Contents API로 직접 PUT (git 불필요)

환경 변수:
  GITHUB_PAT  — fine-grained PAT (contents:write, yeobtoni-stock-bot)
"""
import os, re, json, sys, base64
import datetime as dt
import requests

PAT = os.environ.get("GITHUB_PAT", "").strip()
if not PAT:
    print("ERROR: GITHUB_PAT 환경변수 없음", file=sys.stderr); sys.exit(1)

OWNER = "goldpigbankgazua-dev"
REPO  = "yeobtoni-stock-bot"
PATH  = "modules/market/data/kofia.json"
BRANCH = "main"
DAYS_KEEP = 400

API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{PATH}"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def fetch_kofia():
    url = "https://freesis.kofia.or.kr/stat/main.do"
    r = requests.get(url, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    })
    r.raise_for_status()
    html = r.text

    def _extract(label):
        m = re.search(label + r'[\s\S]{0,200}?(\d{2}\/\d{2})[\s\S]{0,80}?([\d,]{7,})', html)
        if not m:
            print(f"[kofia] '{label}' 패턴 못 찾음"); return None
        mmdd = m.group(1); val = m.group(2).replace(",", "")
        try: v = int(val) * 1_000_000  # 백만원 → 원
        except: return None
        mm, dd = mmdd.split("/")
        year = dt.date.today().year
        today = dt.date.today()
        cand = dt.date(year, int(mm), int(dd))
        if cand > today + dt.timedelta(days=1):
            cand = dt.date(year - 1, int(mm), int(dd))
        return {"date": cand.strftime("%Y-%m-%d"), "value": v}

    return _extract("투자자예탁금"), _extract("신용융자")


def github_get_file():
    """현재 파일 + sha 가져오기. 없으면 None."""
    r = requests.get(API_BASE + f"?ref={BRANCH}", headers=HEADERS, timeout=20)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    j = r.json()
    sha = j.get("sha")
    content_b64 = j.get("content", "")
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8")
        data = json.loads(decoded)
    except Exception as e:
        print(f"[gh] 기존 파일 파싱 실패: {e}")
        data = {"updated_at": "", "deposits": [], "credit": []}
    return data, sha


def github_put_file(content_json, sha, message):
    body = {
        "message": message,
        "content": base64.b64encode(content_json.encode("utf-8")).decode("ascii"),
        "branch": BRANCH,
        "committer": {"name": "vm-kofia-bot", "email": "vm-kofia@yeobtoni.local"},
    }
    if sha:
        body["sha"] = sha
    r = requests.put(API_BASE, headers=HEADERS, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"[gh] PUT 실패 HTTP {r.status_code}: {r.text[:300]}")
        return False
    print(f"[gh] PUT OK (HTTP {r.status_code})")
    return True


def merge_series(existing, new_row):
    if not new_row: return existing
    by_date = {p["date"]: p for p in existing}
    by_date[new_row["date"]] = new_row
    out = sorted(by_date.values(), key=lambda x: x["date"])
    cutoff = (dt.date.today() - dt.timedelta(days=DAYS_KEEP)).strftime("%Y-%m-%d")
    return [p for p in out if p["date"] >= cutoff]


def main():
    print(f"=== KOFIA scrape {dt.date.today()} ===")

    # 1) Scrape
    dep, cre = fetch_kofia()
    if dep: print(f"[deposits] {dep['date']} = {dep['value']:,}원")
    if cre: print(f"[credit]   {cre['date']} = {cre['value']:,}원")

    # 2) 기존 파일 GET
    existing, sha = github_get_file()
    if existing is None:
        existing = {"updated_at": "", "deposits": [], "credit": []}
        print("[gh] 기존 파일 없음, 새로 생성")
    else:
        print(f"[gh] 기존 파일 로드 (deposits={len(existing.get('deposits',[]))} credit={len(existing.get('credit',[]))})")

    # 3) 병합
    before_d = len(existing.get("deposits", []))
    before_c = len(existing.get("credit",   []))
    existing["deposits"] = merge_series(existing.get("deposits", []), dep)
    existing["credit"]   = merge_series(existing.get("credit",   []), cre)
    existing["updated_at"] = dt.date.today().strftime("%Y-%m-%d")

    print(f"[merge] deposits {before_d} → {len(existing['deposits'])}, credit {before_c} → {len(existing['credit'])}")

    # 4) 변경 없으면 PUT 스킵
    if before_d == len(existing["deposits"]) and before_c == len(existing["credit"]) and sha:
        print("[gh] 변경 없음 — PUT 스킵")
        return

    # 5) PUT
    new_json = json.dumps(existing, ensure_ascii=False, separators=(",", ":"))
    msg = f"data(kofia): {dt.date.today()}"
    github_put_file(new_json, sha, msg)


if __name__ == "__main__":
    main()
