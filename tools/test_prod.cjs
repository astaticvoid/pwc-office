#!/usr/bin/env node
/* global document */
/**
 * tools/test_prod.cjs — Automated verification probe for Production deployments.
 *
 * Checks:
 *   1. Negative Security Probe (Apex Web): Unauthenticated request to praywithoutceasing.ca MUST return 401 and serve the takedown notice.
 *   2. Negative Security Probe (WWW Web): Unauthenticated request to www.praywithoutceasing.ca MUST return 401 (or redirect to 401 apex).
 *   3. Negative Security Probe (API Version): Unauthenticated request to api.praywithoutceasing.ca MUST return 401.
 *   4. Negative Security Probe (API Calendar): Unauthenticated request to api.praywithoutceasing.ca/api/v3/calendar MUST return 401.
 *   5. Positive Auth Gate (API Version): Basic Auth returns 200 with apiVersion 3.0.0 and environment production.
 *   6. Positive Auth Gate (API Calendar): Basic Auth returns unified day payload with scripture.
 *   7. Full Browser Render (Playwright): Validates DOM rendering, scripture resolution, zero console errors with evaluation credentials.
 *   8. Unauthenticated Browser Isolation: Fresh browser context without credentials CANNOT reach #office-content or view scripture.
 *
 * Usage:
 *   node tools/test_prod.cjs
 */

const { chromium } = require('playwright');
const https = require('https');
const http = require('http');

const PROD_DOMAIN = process.env.CF_PAGES_DOMAIN || 'praywithoutceasing.ca';
const PROD_API_DOMAIN = process.env.CF_API_DOMAIN || 'api.praywithoutceasing.ca';

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
      const req = client.request(url, { method: 'GET', headers, timeout: 10000 }, (res) => {
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
  console.log(`Production Deployment & Security Verification (${PROD_DOMAIN})`);
  console.log('═══════════════════════════════════════════════════════════════');

  // 1. Negative Security Probe (Apex Web)
  console.log('\n1. Negative Security Gate: Apex Web Protection (Unauthenticated)');
  const apexNoAuth = await httpGet(`https://${PROD_DOMAIN}/`);
  if (apexNoAuth.status === 401) {
    if (apexNoAuth.body.includes('For reasons of copyright, this website is no longer available') &&
        apexNoAuth.body.includes('Evaluation Sign In')) {
      logPass('Apex web rejected unauthenticated access with 401 and served copyright takedown notice with evaluation dialog');
    } else {
      logFail('Apex web returned 401 but did not contain the expected takedown notice HTML');
    }
  } else {
    logFail(`CRITICAL SECURITY FAILURE: Apex web returned status ${apexNoAuth.status} instead of 401 Unauthorized!`);
  }

  // 2. Negative Security Probe (WWW Web)
  console.log('\n2. Negative Security Gate: WWW Web Protection (Unauthenticated)');
  const wwwNoAuth = await httpGet(`https://www.${PROD_DOMAIN}/`);
  if (wwwNoAuth.status === 401 || (wwwNoAuth.status === 301 && (wwwNoAuth.headers.location || '').includes(PROD_DOMAIN))) {
    logPass(`WWW host safely gated (status: ${wwwNoAuth.status})`);
  } else {
    logFail(`CRITICAL SECURITY FAILURE: WWW host returned status ${wwwNoAuth.status} instead of 401 or 301 redirect!`);
  }

  // 3. Negative Security Probe (API Version)
  console.log('\n3. Negative Security Gate: Production API Version (Unauthenticated)');
  const apiVerNoAuth = await httpGet(`https://${PROD_API_DOMAIN}/api/v3/version`);
  if (apiVerNoAuth.status === 401) {
    logPass('Unauthenticated request to production API version rejected with HTTP 401');
  } else {
    logFail(`CRITICAL SECURITY FAILURE: API version endpoint returned HTTP ${apiVerNoAuth.status} without authentication!`);
  }

  // 4. Negative Security Probe (API Calendar & Scripture)
  console.log('\n4. Negative Security Gate: Production API Scripture Payload (Unauthenticated)');
  const today = new Date().toISOString().slice(0, 10);
  const apiCalNoAuth = await httpGet(`https://${PROD_API_DOMAIN}/api/v3/calendar?date=${today}&translation=nrsvue`);
  if (apiCalNoAuth.status === 401) {
    logPass('Unauthenticated request to production API calendar/scripture rejected with HTTP 401');
  } else {
    logFail(`CRITICAL SECURITY FAILURE: API calendar returned HTTP ${apiCalNoAuth.status} without authentication! Scripture was exposed!`);
  }

  // 5. Positive Auth Gate (API Version)
  console.log('\n5. Positive Auth Gate: Production API Version (Authenticated)');
  const apiVer = await httpGet(`https://${PROD_API_DOMAIN}/api/v3/version`, { Authorization: AUTH_TOKEN });
  if (apiVer.status === 200) {
    try {
      const data = JSON.parse(apiVer.body);
      if (data.status === 'ok' && data.apiVersion === '3.0.0' && data.environment === 'production') {
        logPass(`Production API authenticated successfully (apiVersion: ${data.apiVersion}, commit: ${data.commit}, env: ${data.environment})`);
      } else {
        logFail(`API version payload unexpected: ${apiVer.body}`);
      }
    } catch (e) {
      logFail(`Failed to parse API version JSON: ${e.message}`);
    }
  } else {
    logFail(`Expected HTTP 200 for authenticated API request, got ${apiVer.status}`);
  }

  // 6. Positive Auth Gate (API Calendar & Scripture)
  console.log('\n6. Positive Auth Gate: Production API Calendar & Scripture (Authenticated)');
  const apiCal = await httpGet(`https://${PROD_API_DOMAIN}/api/v3/calendar?date=${today}&translation=nrsvue`, { Authorization: AUTH_TOKEN });
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
      logFail(`Failed to parse API calendar JSON: ${e.message}`);
    }
  } else {
    logFail(`Expected HTTP 200 for authenticated API calendar, got ${apiCal.status}`);
  }

  // 7. Full Browser Render & Scripture Check (Playwright - Authenticated)
  console.log('\n7. End-to-End Browser Render with Evaluation Credentials (Playwright)');
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      httpCredentials: { username: USER, password: PASS },
      viewport: { width: 1280, height: 800 },
    });
    const page = await context.newPage();

    const consoleErrors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto(`https://${PROD_DOMAIN}/`, { waitUntil: 'networkidle', timeout: 20000 });

    const titleEl = await page.waitForSelector('#day-title', { timeout: 8000 });
    const titleText = await titleEl.innerText();
    logPass(`Office rendered with day title: "${titleText.trim()}"`);

    await page.waitForFunction(() => {
      const placeholders = document.querySelectorAll('.scripture-placeholder');
      if (placeholders.length === 0) return false;
      return Array.from(placeholders).every(el => {
        return !el.querySelector('.loading') && el.textContent.trim().length > 20;
      });
    }, { timeout: 12000 });

    const scriptureEls = await page.$$('.scripture-placeholder');
    const citations = [];
    for (const el of scriptureEls) {
      const cit = await el.getAttribute('data-citation');
      citations.push(cit);
    }
    logPass(`All ${scriptureEls.length} scripture placeholders resolved cleanly (${citations.join(', ')})`);

    const fatalErrors = consoleErrors.filter(e => !e.includes('favicon.ico'));
    if (fatalErrors.length === 0) {
      logPass('Zero unhandled console errors during navigation');
    } else {
      logFail(`Detected ${fatalErrors.length} console error(s):`, fatalErrors.slice(0, 3).join('; '));
    }
    await context.close();
  } catch (err) {
    logFail(`Playwright authenticated verification threw exception: ${err.message}`);
  } finally {
    if (browser) await browser.close();
  }

  // 8. Unauthenticated Browser Isolation (Playwright)
  console.log('\n8. Unauthenticated Browser Isolation Check');
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();

    await page.goto(`https://${PROD_DOMAIN}/`, { waitUntil: 'domcontentloaded', timeout: 15000 });

    // Ensure #office-content does NOT render
    const hasOffice = await page.$('#office-content');
    const pageText = await page.textContent('body');

    if (!hasOffice || hasOffice === null) {
      logPass('Unauthenticated browser session cannot access #office-content');
    } else {
      const isVisible = await hasOffice.isVisible();
      if (!isVisible) {
        logPass('App container is completely hidden from unauthenticated session');
      } else {
        logFail('CRITICAL: #office-content is visible to unauthenticated session!');
      }
    }

    if (pageText.includes('For reasons of copyright, this website is no longer available')) {
      logPass('Unauthenticated browser sees copyright takedown notice');
    } else {
      logFail('Unauthenticated browser does NOT see copyright notice!');
    }
    await context.close();
  } catch (err) {
    logFail(`Playwright unauthenticated verification threw exception: ${err.message}`);
  } finally {
    if (browser) await browser.close();
  }

  console.log('\n═══════════════════════════════════════════════════════════════');
  if (failures === 0) {
    console.log('✓ ALL PRODUCTION SECURITY GATES PASSED.');
    console.log('  No unauthorized access is possible.');
    console.log('═══════════════════════════════════════════════════════════════\n');
    process.exit(0);
  } else {
    console.error(`✗ ${failures} CRITICAL PRODUCTION SECURITY CHECK(S) FAILED.`);
    console.error('  DEPLOYMENT IS NOT SECURE.');
    console.log('═══════════════════════════════════════════════════════════════\n');
    process.exit(1);
  }
}

run();
