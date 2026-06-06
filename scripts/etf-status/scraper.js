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

// API endpoint hint: 페이지마다 'getEtpRankList...' 같은 endpoint 호출. 정확한 이름이 안 맞아도
// "Rank" 또는 "rank"를 포함하는 모든 JSON 응답을 캡쳐하고 results.length 큰 걸 채택.
const CATEGORIES = {
  yield:       { url: '/mobile/rank/yield' },
  dividend:    { url: '/mobile/rank/dividend' },
  fundflow:    { url: '/mobile/rank/fundFlow' },
  navchange:   { url: '/mobile/rank/netAssetIncrease' },
  investor:    { url: '/mobile/rank/investor' },
  aum:         { url: '/mobile/rank/manageScale' },
  volume:      { url: '/mobile/rank/volume' },
};

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
      // 'Rank' 포함된 응답 + 0건 아닌 것만 후보 (Investor2는 공통 fallback이라 진짜 카테고리 응답으로 인정 안 함)
      const isFakeFallback = /Investor2/i.test(u);
      if (/rank/i.test(u) && n > 0 && !isFakeFallback) {
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

  await context.close();

  if (captured.length === 0) {
    // 자동 캡쳐 실패 — 추측 endpoint 후보를 in-page fetch로 시도
    const tryEndpoints = {
      dividend:  ['/user/etp/getEtpRankListDividend', '/user/etp/getEtpRankListDistribution', '/stock/etp/getEtpRankListDividend'],
      fundflow:  ['/user/etp/getEtpRankListFundFlow', '/user/etp/getEtpRankListInflow', '/stock/etp/getEtpRankListFundFlow'],
      navchange: ['/user/etp/getEtpRankListNetAsset', '/user/etp/getEtpRankListNetAssetChange', '/user/etp/getEtpRankListNavChange'],
      aum:       ['/user/etp/getEtpRankListAum', '/user/etp/getEtpRankListManageScale', '/user/etp/getEtpRankListScale'],
    };
    const candidates = tryEndpoints[key] || [];
    if (candidates.length > 0) {
      console.log(`[${key}] 추측 endpoint ${candidates.length}개로 fallback 시도...`);
      const page2 = await (await browser.newContext()).newPage();
      await page2.goto(`https://www.etfcheck.co.kr${cat.url}?market=K`, { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(()=>{});
      await page2.waitForTimeout(2000);
      for (const ep of candidates) {
        const url = `https://www.etfcheck.co.kr${ep}?type=ETF&annuityCode=A&ctgLargeCode=A&order=D&orderCol=&invCode=&leverage=&inverse=&coveredCall=&orderBy=DESC&limit=100`;
        try {
          const json = await page2.evaluate(async (u) => {
            const r = await fetch(u, { credentials: 'include' });
            if (!r.ok) return { _err: 'HTTP ' + r.status };
            return await r.json();
          }, url);
          const n = countRows(json);
          console.log(`  [try] ${n} rows ← ${ep}`);
          if (n > 0) { captured.push({ url, json, n }); break; }
        } catch (e) {
          console.log(`  [try] ✗ ${ep}: ${e.message}`);
        }
      }
      await page2.context().close();
    }

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
  } finally {
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
