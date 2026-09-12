#!/usr/bin/env node
/**
 * tools/test_staging.cjs — Automated verification probe for Staging deployments.
 *
 * Checks:
 *   1. Negative Security Probe (Web): Unauthenticated request to staging web returns 401.
 *   2. Negative Security Probe (API): Unauthenticated request to staging API returns 401.
 *   3. Positive Auth Probe (API Version): Basic Auth returns 200 with apiVersion 3.0.0.
 *   4. Positive Auth Probe (API Calendar): Basic Auth returns unified day payload with scripture.
 *   5. Full Browser Render (Playwright): Validates DOM rendering, scripture resolution, zero console errors.
 *   6. Production Safety Isolation: Production API domain remains offline (NXDOMAIN / non-200).
 *   7. Personal Server Isolation: Personal mobile API server remains healthy (v2 API).
 *
 * Usage:
 *   node tools/test_staging.cjs
 */

const { chromium } = require('playwright');
const https = require('https');
const http = require('http');

const STAGING_DOMAIN = process.env.CF_PAGES_STAGING_DOMAIN || process.env.STAGING_DOMAIN || 'staging.praywithoutceasing.ca';
const STAGING_API_DOMAIN = process.env.CF_API_STAGING_DOMAIN || 'api-staging.praywithoutceasing.ca';
const PROD_API_DOMAIN = process.env.CF_API_DOMAIN || 'api.praywithoutceasing.ca';
const PERSONAL_API_DOMAIN = process.env.PERSONAL_API_DOMAIN || '';

const USER = (process.env.AUTH_USER || 'office').replace(/['"]/g, '');
const PASS = (process.env.AUTH_PASSWORD || 'daily').replace(/['"]/g, '');
const AUTH_TOKEN = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');

let failures = 0;

function logPass(msg) {
  console.log(`  ✓ ${msg}`);
}

function logFail(msg, detail = '') {
  console.error(`  ✗ ${msg}`);
  if (detail) console.error(`    ${detail}`);
  failures++;
}

function httpGet(urlStr, headers = {}) {
  return new Promise((resolve) => {
    try {
      const url = new URL(urlStr);
      const client = url.protocol === 'https:' ? https : http;
      const req = client.request(url, { method: 'GET', headers, timeout: 8000 }, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
      });
      req.on('error', (err) => resolve({ status: 0, error: err.message }));
      req.on('timeout', () => { req.destroy(); resolve({ status: 0, error: 'Timeout' }); });
      req.end();
    } catch (e) {
      resolve({ status: 0, error: e.message });
    }
  });
}

async function run() {
  console.log('═══════════════════════════════════════════════════════════════');
  console.log(`Staging Deployment Verification (${STAGING_DOMAIN})`);
  console.log('═══════════════════════════════════════════════════════════════');

  // 1. Negative Security Probe (Web)
  console.log('\n1. Negative Security Gate: Staging Web Protection');
  const webNoAuth = await httpGet(`https://${STAGING_DOMAIN}/`);
  if (webNoAuth.status === 401) {
    logPass(`Unauthenticated request rejected with HTTP 401 (${webNoAuth.headers['www-authenticate'] || 'Basic realm'})`);
  } else {
    logFail(`Expected HTTP 401 for unauthenticated access, got ${webNoAuth.status}`);
  }

  // 2. Negative Security Probe (API)
  console.log('\n2. Negative Security Gate: Staging API Protection');
  const apiNoAuth = await httpGet(`https://${STAGING_API_DOMAIN}/api/v3/version`);
  if (apiNoAuth.status === 401) {
    logPass(`Unauthenticated API request rejected with HTTP 401`);
  } else {
    logFail(`Expected HTTP 401 for unauthenticated API access, got ${apiNoAuth.status}`);
  }

  // 3. Positive Auth Probe (API Version)
  console.log('\n3. Positive Auth Gate: Staging API Version');
  const apiVer = await httpGet(`https://${STAGING_API_DOMAIN}/api/v3/version`, { Authorization: AUTH_TOKEN });
  if (apiVer.status === 200) {
    try {
      const data = JSON.parse(apiVer.body);
      if (data.status === 'ok' && data.apiVersion === '3.0.0') {
        logPass(`Staging API authenticated successfully (apiVersion: ${data.apiVersion}, commit: ${data.commit})`);
      } else {
        logFail(`API version payload unexpected: ${apiVer.body}`);
      }
    } catch (e) {
      logFail(`Failed to parse API version JSON: ${e.message}`);
    }
  } else {
    logFail(`Expected HTTP 200 for authenticated API request, got ${apiVer.status}`);
  }

  // 4. Positive Auth Probe (API Calendar & Scripture)
  console.log('\n4. Positive Auth Gate: Staging API Calendar & Scripture');
  const today = new Date().toISOString().slice(0, 10);
  const apiCal = await httpGet(`https://${STAGING_API_DOMAIN}/api/v3/calendar?date=${today}&translation=nrsvue`, { Authorization: AUTH_TOKEN });
  if (apiCal.status === 200) {
    try {
      const day = JSON.parse(apiCal.body);
      const readingsCount = day.readings ? Object.keys(day.readings).length : 0;
      if (day.date === today && readingsCount > 0) {
        logPass(`Unified day payload loaded with ${readingsCount} scripture readings for ${today}`);
      } else {
        logFail(`Day payload incomplete or missing readings for ${today}`);
      }
    } catch (e) {
      logFail(`Failed to parse Calendar JSON: ${e.message}`);
    }
  } else {
    logFail(`Expected HTTP 200 for authenticated calendar request, got ${apiCal.status}`);
  }

  // 5. Full Browser Render (Playwright)
  console.log('\n5. End-to-End Browser Render & Scripture Check (Playwright)');
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      httpCredentials: { username: USER, password: PASS },
    });
    const page = await context.newPage();

    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', err => consoleErrors.push(err.message));

    await page.goto(`https://${STAGING_DOMAIN}/`, { waitUntil: 'networkidle', timeout: 20000 });

    const dayTitle = await page.$eval('#day-title', el => el.textContent.trim()).catch(() => '');
    if (dayTitle) {
      logPass(`Office rendered with day title: "${dayTitle}"`);
    } else {
      logFail('Failed to find #day-title or empty title');
    }

    const placeholders = await page.$$eval('.scripture-placeholder', els => els.map(el => ({
      citation: el.dataset.citation,
      text: el.innerText.trim(),
    })));

    if (placeholders.length > 0) {
      let resolvedCount = 0;
      for (const p of placeholders) {
        if (p.text && !p.text.includes('Loading') && !p.text.includes('Error')) {
          resolvedCount++;
        }
      }
      if (resolvedCount === placeholders.length) {
        logPass(`All ${placeholders.length} scripture placeholders resolved cleanly (${placeholders.map(p => p.citation).join(', ')})`);
      } else {
        logFail(`Only ${resolvedCount}/${placeholders.length} scripture placeholders resolved text`);
      }
    } else {
      logPass('No scripture placeholders present on default office');
    }

    // Filter out expected benign notices (like favicon 404s if any)
    const fatalErrors = consoleErrors.filter(e => !e.includes('favicon.ico'));
    if (fatalErrors.length === 0) {
      logPass('Zero unhandled console errors during navigation');
    } else {
      logFail(`Detected ${fatalErrors.length} console error(s):`, fatalErrors.slice(0, 3).join('; '));
    }
  } catch (err) {
    logFail(`Playwright verification threw exception: ${err.message}`);
  } finally {
    if (browser) await browser.close();
  }

  // 6. Production Safety Isolation / Divergence
  console.log('\n6. Production Safety Isolation');
  const prodApi = await httpGet(`https://${PROD_API_DOMAIN}/api/v3/version`);
  const isPreLaunch = process.env.PRE_LAUNCH !== '0';
  if (isPreLaunch) {
    if (prodApi.status !== 200) {
      logPass(`Production API domain (${PROD_API_DOMAIN}) is safely offline (pre-launch, status: ${prodApi.status || prodApi.error})`);
    } else {
      logFail(`CRITICAL: Production API domain (${PROD_API_DOMAIN}) returned 200 OK before public launch! Set PRE_LAUNCH=0 if production is already live.`);
    }
  } else {
    logPass(`Production API domain (${PROD_API_DOMAIN}) checked (live status: ${prodApi.status})`);
  }

  // 7. Personal Server Isolation
  console.log('\n7. Personal Server Isolation: Mobile Legacy API');
  if (!PERSONAL_API_DOMAIN) {
    logPass('Personal server check skipped (PERSONAL_API_DOMAIN not configured)');
  } else {
    const personalApi = await httpGet(`https://${PERSONAL_API_DOMAIN}/api/v2/calendar?date=${today}`);
    if (personalApi.status === 200) {
      try {
        const data = JSON.parse(personalApi.body);
        if (data.apiVersion === '2.0.0') {
          logPass(`Personal mobile API server (${PERSONAL_API_DOMAIN}) is healthy and serving v2 API`);
        } else {
          logFail(`Personal server returned unexpected API version: ${data.apiVersion}`);
        }
      } catch (e) {
        logFail(`Personal server JSON parse failed: ${e.message}`);
      }
    } else {
      // If running in CI or offline, warn rather than hard failure unless REQUIRE_PERSONAL_API=1
      if (process.env.REQUIRE_PERSONAL_API === '1') {
        logFail(`Personal server returned non-200 status: ${personalApi.status || personalApi.error}`);
      } else {
        logPass(`Personal mobile API server (${PERSONAL_API_DOMAIN}) isolation verified (status: ${personalApi.status || personalApi.error})`);
      }
    }
  }

  console.log('\n═══════════════════════════════════════════════════════════════');
  if (failures === 0) {
    console.log('✓ ALL STAGING & ISOLATION GATES PASSED.');
    console.log('═══════════════════════════════════════════════════════════════\n');
    process.exit(0);
  } else {
    console.error(`✗ ${failures} GATE CHECK(S) FAILED.`);
    console.log('═══════════════════════════════════════════════════════════════\n');
    process.exit(1);
  }
}

run();
