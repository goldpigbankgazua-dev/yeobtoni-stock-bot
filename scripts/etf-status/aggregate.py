#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 현황 누적 데이터 합산기

modules/etfstatus/history/raw/{YYYY-MM-DD}.json 파일들을 읽어
기간별 사전 계산 파일을 생성:
- {cat}_1d.json   당일/전일 (가장 최근 1일)
- {cat}_1w.json   최근 5영업일 합산
- {cat}_1m.json   최근 20영업일 합산
- {cat}_3m.json   최근 60영업일
- {cat}_6m.json   최근 120영업일
- {cat}_ytd.json  올해 1월 1일 이후
- {cat}_1y.json   최근 250영업일
- {cat}_5d_avg.json   최근 5일 거래량 평균 (volume 전용)
- {cat}_10d_avg.json  10일 평균

데이터가 N일치 모이지 않으면 해당 기간은 생성 안 함 (UI에서 "데이터 축적 중" 표시).
"""
import os, json, re
import datetime as dt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
HISTORY_DIR = os.path.join(ROOT, 'modules', 'etfstatus', 'history', 'raw')
OUT_DIR     = os.path.join(ROOT, 'modules', 'etfstatus', 'data')

# 카테고리별 합산 대상 필드 (누적 가능한 수치)
SUMMABLE_FIELDS = {
    'fundflow':  ['INFLOW'],                 # 자금유입 (원)
    'navchange': ['AUM_VAR'],                # 순자산변화 (원)
    'investor':  ['RANK_VALUE'],             # 순매수금액 (원)
    'volume':    ['F15015', 'F15023'],       # 거래량(주), 거래대금(원)
    'yield':     ['F15004', 'NAV_YIELD'],    # 등락률/수익률 — 복리 합산 별도
    # aum은 스냅샷이라 합산 무의미 — 가장 최근 값만
}

# 카테고리별 표시 필드 (변하지 않는 정보 — 종목명/티커 등)
META_FIELDS = ['F16002', 'F16013', 'F18070']

PERIODS = {
    '1d':  1,
    '1w':  5,
    '1m':  20,
    '3m':  60,
    '6m':  120,
    '1y':  250,
}

VOLUME_AVG_PERIODS = {
    '5d_avg':  5,
    '10d_avg': 10,
}

def list_history_dates():
    """history/raw 폴더의 모든 날짜 파일 (오래된 → 최신 순)"""
    if not os.path.isdir(HISTORY_DIR):
        return []
    files = sorted([f for f in os.listdir(HISTORY_DIR) if re.match(r'\d{4}-\d{2}-\d{2}\.json$', f)])
    return [f[:10] for f in files]

def load_day(date):
    """{date}.json 로드"""
    path = os.path.join(HISTORY_DIR, f'{date}.json')
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print(f'[load] {date}: {e}')
        return None

def aggregate_sum(cat, days_data, meta_source):
    """일별 데이터들을 합산. days_data: [{date, rows: [...]}, ...]"""
    fields = SUMMABLE_FIELDS.get(cat, [])
    if not fields:
        return []
    # 티커 → 누적 dict
    by_ticker = {}
    for entry in days_data:
        for row in entry['rows']:
            t = row.get('F16013')
            if not t: continue
            if t not in by_ticker:
                by_ticker[t] = {'F16013': t}
                for mf in META_FIELDS:
                    if mf in row: by_ticker[t][mf] = row[mf]
                for f in fields:
                    by_ticker[t][f] = 0.0
            for f in fields:
                v = row.get(f)
                try:
                    by_ticker[t][f] += float(v) if v is not None and v != '' else 0
                except (ValueError, TypeError):
                    pass
    # 메타 정보 보완 (최신 일자 우선)
    if meta_source:
        for row in meta_source:
            t = row.get('F16013')
            if t in by_ticker:
                for mf in META_FIELDS:
                    if mf in row and not by_ticker[t].get(mf):
                        by_ticker[t][mf] = row[mf]
    return list(by_ticker.values())

def aggregate_avg(cat, days_data, n):
    """평균 — 거래량 등"""
    fields = SUMMABLE_FIELDS.get(cat, [])
    if not fields:
        return []
    by_ticker = {}
    for entry in days_data:
        for row in entry['rows']:
            t = row.get('F16013')
            if not t: continue
            if t not in by_ticker:
                by_ticker[t] = {'F16013': t, '_count': 0}
                for mf in META_FIELDS:
                    if mf in row: by_ticker[t][mf] = row[mf]
                for f in fields:
                    by_ticker[t][f] = 0.0
            for f in fields:
                v = row.get(f)
                try:
                    by_ticker[t][f] += float(v) if v is not None and v != '' else 0
                except (ValueError, TypeError):
                    pass
            by_ticker[t]['_count'] += 1
    # 평균 계산
    out = []
    for t, agg in by_ticker.items():
        cnt = agg.pop('_count')
        if cnt > 0:
            for f in fields:
                agg[f] = agg[f] / cnt
        out.append(agg)
    return out

def yield_compound(days_data):
    """수익률 복리 합산: (1+r1)(1+r2)... - 1, 단위: %"""
    by_ticker = {}
    for entry in days_data:
        for row in entry['rows']:
            t = row.get('F16013')
            if not t: continue
            if t not in by_ticker:
                by_ticker[t] = {'F16013': t, '_factor': 1.0}
                for mf in META_FIELDS:
                    if mf in row: by_ticker[t][mf] = row[mf]
            r = row.get('F15004')  # 일별 등락률
            try:
                rv = float(r) if r is not None and r != '' else 0
                by_ticker[t]['_factor'] *= (1 + rv / 100)
            except (ValueError, TypeError):
                pass
    out = []
    for t, agg in by_ticker.items():
        factor = agg.pop('_factor', 1.0)
        agg['NAV_YIELD'] = round((factor - 1) * 100, 4)
        agg['F15004'] = agg['NAV_YIELD']
        out.append(agg)
    return out

def write_aggregate(cat, period_key, rows, days_used):
    """결과 파일 저장 — 기존 형식 호환"""
    today = dt.date.today().isoformat()
    payload = {
        'updated_at': today,
        'period': period_key,
        'days_used': days_used,
        'raw': {'results': rows},
    }
    out_path = os.path.join(OUT_DIR, f'{cat}_{period_key}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    print(f'  ✓ {cat}_{period_key}.json — {len(rows)} ETF × {days_used}일')

def ytd_cutoff():
    return f'{dt.date.today().year}-01-01'

def main():
    dates = list_history_dates()
    if not dates:
        print('[aggregate] history/raw 폴더에 데이터 없음 — scraper 먼저 실행')
        return
    print(f'[aggregate] history: {len(dates)}일 ({dates[0]} ~ {dates[-1]})')

    # 모든 날짜 로드 (역순: 최신 → 과거)
    loaded = []
    for d in reversed(dates):
        day = load_day(d)
        if day: loaded.append({'date': d, 'data': day})

    if not loaded:
        print('[aggregate] 로드된 데이터 없음')
        return

    latest = loaded[0]['data']
    ytd_d = ytd_cutoff()

    # 카테고리별 합산
    cats = ['fundflow', 'navchange', 'investor', 'volume', 'yield']
    for cat in cats:
        print(f'\n[{cat}]')
        # 각 기간별
        for period, days_needed in PERIODS.items():
            days_data = []
            for entry in loaded[:days_needed]:
                rows = entry['data'].get('categories', {}).get(cat, [])
                if rows:
                    days_data.append({'date': entry['date'], 'rows': rows})
            if not days_data:
                print(f'  - {period}: 데이터 없음')
                continue
            if period == '1d':
                # 가장 최근 1일 그대로
                write_aggregate(cat, period, days_data[0]['rows'], 1)
            elif cat == 'yield':
                rows = yield_compound(days_data)
                write_aggregate(cat, period, rows, len(days_data))
            else:
                meta_source = latest.get('categories', {}).get(cat, [])
                rows = aggregate_sum(cat, days_data, meta_source)
                write_aggregate(cat, period, rows, len(days_data))

        # YTD (올해 첫 영업일 ~ 오늘)
        ytd_days = [e for e in loaded if e['date'] >= ytd_d]
        if ytd_days:
            days_data = []
            for entry in ytd_days:
                rows = entry['data'].get('categories', {}).get(cat, [])
                if rows:
                    days_data.append({'date': entry['date'], 'rows': rows})
            if days_data:
                if cat == 'yield':
                    rows = yield_compound(days_data)
                else:
                    meta_source = latest.get('categories', {}).get(cat, [])
                    rows = aggregate_sum(cat, days_data, meta_source)
                write_aggregate(cat, 'ytd', rows, len(days_data))

        # 거래량 — 평균 옵션
        if cat == 'volume':
            for period, n in VOLUME_AVG_PERIODS.items():
                days_data = []
                for entry in loaded[:n]:
                    rows = entry['data'].get('categories', {}).get(cat, [])
                    if rows:
                        days_data.append({'date': entry['date'], 'rows': rows})
                if days_data:
                    meta_source = latest.get('categories', {}).get(cat, [])
                    rows = aggregate_avg(cat, days_data, n)
                    # 메타 정보 보완
                    if meta_source:
                        meta_map = {r.get('F16013'): r for r in meta_source if r.get('F16013')}
                        for r in rows:
                            t = r.get('F16013')
                            if t in meta_map:
                                for mf in META_FIELDS:
                                    if mf in meta_map[t] and not r.get(mf):
                                        r[mf] = meta_map[t][mf]
                    write_aggregate(cat, period, rows, len(days_data))

    # 운용규모(aum) — 스냅샷, 항상 가장 최근 그대로
    aum_rows = latest.get('categories', {}).get('aum', [])
    if aum_rows:
        write_aggregate('aum', 'snapshot', aum_rows, 1)

    print(f'\n[aggregate] 완료 — {len(loaded)}일 데이터로 사전 계산')

if __name__ == '__main__':
    main()
