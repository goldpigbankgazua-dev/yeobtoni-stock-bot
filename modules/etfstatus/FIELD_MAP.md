# ETF CHECK API 필드 매핑

ETF CHECK 모바일 페이지에서 캡쳐한 응답의 코드 필드명 → 한글 라벨.

## 공통 필드

| 코드 | 의미 |
|------|------|
| F16002 | 종목명 |
| F16013 | 티커(단축코드) |
| F18070 | 종류 코드 ("00"=일반) |
| F15001 | 현재가 (원) |
| F15472 | 전일대비 (원) |
| F15004 | 등락률 (%) |
| F15015 | 거래량 (주) |
| F15023 | 거래대금 (원) |
| F15301 | NAV (원) |
| F30818 | NAV 수익률 (%) |
| ETF_TYPE | "ETF" / "ETN" |
| NAV_YIELD | NAV 수익률 (%) |
| YIELD | 수익률 (%) |
| RANK_VALUE | 정렬 기준값 (카테고리마다 의미 다름) |

## 카테고리별 endpoint + RANK_VALUE 의미

| 카테고리 | endpoint | RANK_VALUE 의미 | 캡쳐 상태 |
|----------|----------|-----------------|----------|
| yield (수익률) | `/user/etp/getEtpRankListYield` | 등락률(%) | ✓ 100건 |
| dividend (배당) | (미확정 — SPA 클릭 필요) | 분배금률 추정 | ✗ fallback만 |
| fundflow (자금유입) | (미확정) | 순유입(원) 추정 | ✗ fallback만 |
| navchange (순자산증감) | (미확정) | 순자산 변화(원) 추정 | ✗ fallback만 |
| investor (투자자) | `/user/etp/getEtpRankListInvestor` | 투자주체 순매수(원) | ✓ 100건 |
| aum (운용규모) | (미확정) | 순자산총액(원) 추정 | ✗ fallback만 |
| volume (거래량) | `/user/etp/getEtpRankListVolume` | 거래량(주) | ✓ 100건 |

## fallback endpoint

4개 실패 카테고리에서 공통으로 잡힌 `/stock/etp/getEtpRankListInvestor2?order=W&limit=all` (1516개 전종목)
- 필드: F16013, F16002, F06511_08_SUM, F06511_10_SUM, F06511_14_SUM, YIELD
- F06511_08/10/14_SUM은 투자주체(개인/외국인/기관) 매수/매도 합계로 추정
- 카테고리별 정확한 데이터 아니므로 UI에서는 사용 안 함

## 다음 단계

scraper.js에 SPA 카테고리 탭 클릭 동작 추가:
```js
// 페이지 진입 후
await page.click('[role=tab]:has-text("배당")');
await page.waitForResponse(r => r.url().includes('Rank') && r.status() === 200);
```

또는 4개 카테고리 각각 직접 endpoint 패턴 fetch:
- `/user/etp/getEtpRankListDividend?type=ETF&ctgLargeCode=A&order=D&orderBy=DESC&limit=100`
- `/user/etp/getEtpRankListFundFlow?...`
- `/user/etp/getEtpRankListNetAsset?...`
- `/user/etp/getEtpRankListAum?...`
