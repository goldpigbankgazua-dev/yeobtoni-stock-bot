#!/usr/bin/env node
/**
 * ETF CHECK 랭킹 스크래퍼 — Playwright 기반
 *
 * 7개 카테고리 순회: 수익률·배당·자금유입·순자산증감·투자자·운용규모·거래량
 * 각 카테고리별 결과를 modules/etfstatus/data/{category}.json 으로 저장
 *
 * 실행: node scraper.js [category]
 *   category 생략 시 모두 수집. 단일 카테고리 지정 가능 (예: node scraper.js yield)
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.resolve(__dirname, '../../modules/etfstatus/data');
const HUB_ROOT = path.resolve(__dirname, '../../');

// SPA에서 카테고리별 endpoint를 호출하는 그룹 (yield/investor/volume — 각자 100개씩)
const CATEGORIES = {
  yield:       { url: '/mobile/rank/yield' },
  investor:    { url: '/mobile/rank/investor' },
  volume:      { url: '/mobile/rank/volume' },
};
// fundflow/navchange/aum 세 카테고리는 공통 endpoint(getEtpAumVariation)에서 1136개 받고
// 클라이언트 정렬로 다르게 표시. EtpMast로 종목명 join 필요. → scrapeAumVariation() 별도 처리.

const DEBUG = process.env.DEBUG === '1';

function countRows(data) {
  if (Array.isArray(data)) return data.length;
  if (data && typeof data === 'object') {
    for (const k of ['results', 'data', 'list', 'items', 'rows']) {
      if (Array.isArray(data[k])) return data[k].length;
    }
  }
  return 0;
}

async function scrapeCategory(browser, key, cat) {
  console.log(`[${key}] start: ${cat.url}`);
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();

  // 모든 JSON 응답을 캡쳐. 'Rank' 포함 + 결과 있는 응답을 우선 채택.
  const captured = [];
  const allResponses = []; // 디버그용 — 실패 시 dump
  page.on('response', async (resp) => {
    const u = resp.url();
    if (!u.includes('etfcheck.co.kr')) return;
    const ct = (resp.headers()['content-type'] || '').toLowerCase();
    if (!ct.includes('json')) return;
    try {
      const json = await resp.json();
      const n = countRows(json);
      const shortUrl = u.replace('https://www.etfcheck.co.kr', '');
      allResponses.push({ url: shortUrl, n });
      // 카테고리 데이터 응답 후보 — Rank/AumVariation/Inflow/MarketCap 포함, Investor2(공통 fallback) 제외
      const isFakeFallback = /Investor2/i.test(u);
      const isCategoryData = /rank/i.test(u) || /AumVariation/i.test(u) || /Inflow/i.test(u) || /MarketCap/i.test(u);
      if (isCategoryData && n > 0 && !isFakeFallback) {
        captured.push({ url: u, json, n });
      }
      if (DEBUG) console.log(`  [resp] ${n} rows ← ${shortUrl}`);
    } catch (e) {}
  });

  try {
    await page.goto(`https://www.etfcheck.co.kr${cat.url}?market=K`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  } catch (e) {
    console.error(`[${key}] goto error: ${e.message}`);
  }

  // 약관 모달이 떠 있으면 동의/닫기 시도
  try {
    await page.waitForTimeout(1500);
    const agreeBtn = await page.$('button:has-text("동의"), button:has-text("확인"), button:has-text("닫기"), [class*="agree"], [class*="close"]');
    if (agreeBtn) await agreeBtn.click().catch(() => {});
  } catch (e) {}

  // 페이지 안정화 + 스크롤로 lazy-load 유발
  try {
    await page.waitForLoadState('networkidle', { timeout: 15000 });
  } catch (e) {}
  try {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollTo(0, 0));
  } catch (e) {}
  await page.waitForTimeout(2500);

  // 페이지가 진입 시 미리보기(10 rows)만 부르는 카테고리가 있어서
  // 큰 응답(50+ rows)이 없으면 fallback 강제 트리거 (같은 page에서 fetch — cookie 유지)
  const hasFullResponse = captured.some(c => c.n >= 50);
  if (!hasFullResponse) {
    if (captured.length > 0) console.log(`[${key}] 미리보기만 (max=${Math.max(...captured.map(c=>c.n))}) → 같은 page에서 fetch fallback`);
    captured.length = 0;

    // JS bundle(/js/build.js)에서 추출한 정확한 endpoint 이름 (2026-06-06 캡쳐)
    const tryEndpoints = {
      fundflow:  ['/user/etp/getEtpRankListInflow'],
      navchange: ['/user/etp/getEtpRankListAumVariation'],
      aum:       ['/user/etp/getEtpRankListMarketCap'],
    };
    const candidates = tryEndpoints[key] || [];
    for (const ep of candidates) {
      // navchange/aum은 AumVariation/MarketCap 호출 + 적절한 정렬 파라미터
      const orderCol = (key === 'aum') ? 'A' : (key === 'navchange' ? 'M' : '');
      const url = `https://www.etfcheck.co.kr${ep}?type=ETF&annuityCode=A&ctgLargeCode=A&order=D&orderCol=${orderCol}&invCode=&leverage=&inverse=&coveredCall=&orderBy=DESC&limit=100`;
      try {
        const json = await page.evaluate(async (u) => {
          const r = await fetch(u, { credentials: 'include' });
          if (!r.ok) return { _err: 'HTTP ' + r.status };
          return await r.json();
        }, url);
        const n = countRows(json);
        console.log(`  [try] ${n} rows ← ${ep}${orderCol?'?orderCol='+orderCol:''}`);
        if (n > 0) { captured.push({ url, json, n }); break; }
      } catch (e) {
        console.log(`  [try] ✗ ${ep}: ${e.message}`);
      }
    }
  }

  await context.close();

  if (captured.length === 0) {
    const logFile = path.join(OUT_DIR, `_debug_${key}.log`);
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(logFile, allResponses
      .sort((a,b) => b.n - a.n)
      .map(r => `${String(r.n).padStart(6)}  ${r.url}`)
      .join('\n'));
    console.error(`[${key}] ✗ 실패 → 호출된 URL 목록: ${logFile}`);
    return null;
  }

  // 가장 큰 list를 가진 응답 채택 (Rank 후보 중)
  captured.sort((a, b) => b.n - a.n);
  const best = captured[0];
  const data = best.json;
  const outFile = path.join(OUT_DIR, `${key}.json`);
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify({
    updated_at: new Date().toISOString().slice(0, 10),
    source_url: best.url,
    raw: data,
  }, null, 0));

  console.log(`[${key}] ✓ saved: ${best.n} rows ← ${best.url.replace('https://www.etfcheck.co.kr','')}`);
  return data;
}

async function main() {
  const onlyCat = process.argv[2];
  const targets = onlyCat ? { [onlyCat]: CATEGORIES[onlyCat] } : CATEGORIES;
  if (!targets || Object.values(targets).some(v => !v)) {
    console.error('알 수 없는 카테고리:', onlyCat);
    console.error('사용 가능:', Object.keys(CATEGORIES).join(', '));
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  try {
    for (const [key, cat] of Object.entries(targets)) {
      await scrapeCategory(browser, key, cat);
    }
    // fundflow/navchange/aum 통합 fetch — EtpAumVariation(1136개) + EtpMast(종목명 매핑)
    if (!onlyCat || ['fundflow','navchange','aum'].includes(onlyCat)) {
      await scrapeAumVariation(browser, onlyCat);
    }
  } finally {
    await browser.close();
  }
}

async function scrapeAumVariation(browser, onlyCat) {
  console.log('[aumvar] start: fundflow 페이지 진입 → AumVariation + EtpMast 응답 캡쳐');
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();

  // 페이지가 자체 호출하는 응답을 캡쳐
  let aumv = null;
  let mast = null;
  page.on('response', async (resp) => {
    const u = resp.url();
    if (!u.includes('etfcheck.co.kr')) return;
    const ct = (resp.headers()['content-type'] || '').toLowerCase();
    if (!ct.includes('json')) return;
    try {
      const json = await resp.json();
      if (u.includes('getEtpAumVariation') && !aumv) {
        const rows = json?.results || json?.data;
        if (Array.isArray(rows) && rows.length > 100) aumv = json;
      }
      if (u.includes('getEtpMast') && !mast) {
        const rows = json?.results || json?.data || (Array.isArray(json) ? json : null);
        if (rows && rows.length > 100) mast = json;
      }
    } catch (e) {}
  });

  // fundflow 페이지 진입 — 여기서 페이지가 AumVariation 자체 호출 (debug log 검증됨)
  try {
    await page.goto('https://www.etfcheck.co.kr/mobile/rank/fundFlow?market=K', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2000);
    // 약관 모달 처리
    const agreeBtn = await page.$('button:has-text("동의"), button:has-text("확인"), button:has-text("닫기")');
    if (agreeBtn) await agreeBtn.click().catch(() => {});
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(()=>{});
    // 스크롤로 lazy-load 유발
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)).catch(()=>{});
    await page.waitForTimeout(2500);
    await page.evaluate(() => window.scrollTo(0, 0)).catch(()=>{});
    await page.waitForTimeout(2500);
  } catch (e) {
    console.error('[aumvar] fundflow page goto 실패:', e.message);
  }

  // Inflow (자금유입) — page axios로 직접 호출 시도
  let inflow = null;
  {
    console.log('[aumvar] Inflow page axios 시도');
    const result = await page.evaluate(async () => {
      const ax = window.axios;
      if (!ax) return { _err: 'no axios' };
      try {
        const r = await ax.get('/user/etp/getEtpRankListInflow?type=ETF&annuityCode=A&ctgLargeCode=A&order=D&orderCol=&invCode=&leverage=&inverse=&coveredCall=&orderBy=DESC&limit=100');
        return r.data;
      } catch (e) { return { _err: 'axios: ' + (e.response?.status || e.message) }; }
    }).catch(e => ({ _err: e.message }));
    if (result && !result._err) {
      inflow = result;
      const n = result?.results?.length || 0;
      console.log(`[aumvar] Inflow 성공: ${n} rows`);
    } else {
      console.error('[aumvar] Inflow 실패:', result?._err);
    }
  }

  // AumVariation이 자동 캡쳐 안 됐으면 페이지의 axios 인스턴스로 호출 (인증 헤더 자동)
  if (!aumv) {
    console.log('[aumvar] AumVariation 자동 캡쳐 실패 → page axios 시도');
    const result = await page.evaluate(async () => {
      // 페이지의 axios 사용 (window.axios 또는 등록된 인스턴스)
      const ax = window.axios;
      if (!ax) return { _err: 'no axios' };
      try {
        const r = await ax.get('/user/etp/getEtpAumVariation?type=ETF&order=D');
        return r.data;
      } catch (e) { return { _err: 'axios: ' + (e.response?.status || e.message) }; }
    }).catch(e => ({ _err: e.message }));
    if (result && !result._err) {
      aumv = result;
      console.log('[aumvar] axios 성공');
    } else {
      console.error('[aumvar] axios 실패:', result?._err);
      // 마지막: 헤더 강화 fetch
      const r2 = await page.evaluate(async () => {
        try {
          const r = await fetch('/user/etp/getEtpAumVariation?type=ETF&order=D', {
            credentials: 'include',
            headers: {
              'Accept': 'application/json, text/plain, */*',
              'X-Requested-With': 'XMLHttpRequest',
              'Referer': location.href,
            }
          });
          if (!r.ok) return { _err: 'HTTP ' + r.status };
          return await r.json();
        } catch (e) { return { _err: e.message }; }
      }).catch(e => ({ _err: e.message }));
      if (r2 && !r2._err) { aumv = r2; console.log('[aumvar] 헤더 강화 fetch 성공'); }
      else console.error('[aumvar] 헤더 fetch 실패:', r2?._err);
    }
  }

  await context.close();

  if (!aumv || !mast) {
    console.error(`[aumvar] 캡쳐 실패: aumv=${!!aumv}, mast=${!!mast}`);
    return;
  }

  const mastRows = mast?.results || mast?.data || (Array.isArray(mast) ? mast : []);
  const aumvRows = aumv?.results || aumv?.data || (Array.isArray(aumv) ? aumv : []);
  console.log(`[aumvar] Mast=${mastRows.length} rows, AumVariation=${aumvRows.length} rows`);

  if (!mastRows.length || !aumvRows.length) {
    console.error('[aumvar] 응답 비어있음. mast sample:', JSON.stringify(mast).slice(0, 200));
    return;
  }

  // 티커→종목명 dict (다른 필드도 같이 매핑 — F18070=종류, F15004=등락률 등 있으면)
  const tickerMap = {};
  for (const m of mastRows) {
    const t = m.F16013 || m.ticker || m.code;
    if (t) tickerMap[t] = m;
  }

  // AumVariation에 종목명·기타 필드 join
  const enriched = aumvRows.map(r => {
    const t = r.F16013;
    const m = tickerMap[t] || {};
    return {
      F16013: t,
      F16002: m.F16002 || m.name || '—',
      F18070: m.F18070 || '',
      F15001: m.F15001 || '',
      F15004: m.F15004 || '',
      F15015: m.F15015 || '',
      AUM: r.AUM,
      AUM_VAR: r.AUM_VAR,
    };
  });

  // navchange + aum 파일 저장 (같은 AumVariation 데이터, UI에서 정렬 다르게)
  const today = new Date().toISOString().slice(0, 10);
  const aumvPayload = {
    updated_at: today,
    source_url: 'getEtpAumVariation + getEtpMast (enriched)',
    raw: { results: enriched },
  };
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const targets = onlyCat ? [onlyCat] : ['navchange', 'aum'];
  for (const key of targets) {
    if (!['navchange','aum'].includes(key)) continue;
    fs.writeFileSync(path.join(OUT_DIR, `${key}.json`), JSON.stringify(aumvPayload));
    console.log(`[${key}] ✓ saved (aumvariation enriched): ${enriched.length} rows`);
  }

  // fundflow는 별도 (Inflow endpoint 응답 사용)
  if (inflow && (!onlyCat || onlyCat === 'fundflow')) {
    const inflowRows = inflow?.results || inflow?.data || [];
    if (inflowRows.length) {
      const inflowPayload = {
        updated_at: today,
        source_url: 'getEtpRankListInflow',
        raw: { results: inflowRows },
      };
      fs.writeFileSync(path.join(OUT_DIR, 'fundflow.json'), JSON.stringify(inflowPayload));
      console.log(`[fundflow] ✓ saved (Inflow endpoint): ${inflowRows.length} rows`);
    }
  } else if (!inflow) {
    console.warn('[fundflow] Inflow 못 받음 — 파일 갱신 안 함');
  }
}

main().catch(e => { console.error(e); process.exit(1); });
