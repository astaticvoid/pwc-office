#!/usr/bin/env node
/**
 * tools/compare_staging.js — A/B diff of staging vs production rendered DOM.
 *
 * Usage: node tools/compare_staging.js [YYYY-MM-DD] [mp|ep]
 *
 * Renders both staging and production for the given date/office, extracts
 * the office content as plain text, and produces a unified diff.
 *
 * Exit 0 always (informational). Exits non-zero if either URL fails to load.
 */
const { chromium } = require('playwright');

const dateStr = process.argv[2] || new Date().toISOString().slice(0, 10);
const office   = process.argv[3] || 'mp';

const AUTH = { username: 'office', password: 'daily' };

async function renderOffice(browser, url) {
  const context = await browser.newContext({ httpCredentials: AUTH });
  const page = await context.newPage();
  await page.goto(`${url}/#${dateStr}/${office}`, { timeout: 20000 });
  await page.waitForTimeout(4000);

  // Extract office content as structured text
  const result = await page.evaluate(() => {
    const content = document.getElementById('office-content');
    if (!content) return { error: 'No office-content element' };

    const errors = [...content.querySelectorAll('.error-msg')].map(e => e.textContent.trim());
    const title  = document.querySelector('.office-title')?.textContent?.trim() || '';

    // Walk DOM and emit a text representation
    const lines = [];
    const warnings = [];
    function walk(el, indent) {
      if (!el) return;
      // Skip loading placeholders and hidden elements
      if (el.classList.contains('loading')) return;
      
      // Flag unexpected elements
      const style = window.getComputedStyle(el);
      if (el.id === 'debug-log' && style.display !== 'none') {
        warnings.push('Debug-log panel is visible (should be hidden): ' + el.textContent.trim().slice(0, 80));
      }
      // Flag fixed/sticky elements at the bottom of the viewport
      if ((style.position === 'fixed' || style.position === 'sticky') 
          && parseInt(style.bottom) === 0 && el.id !== 'nav' && el.id !== 'settings-sheet') {
        warnings.push('Unexpected fixed element at page bottom: id=' + (el.id || '(none)') + ' ' + el.textContent.trim().slice(0, 80));
      }

      const tag = el.tagName?.toLowerCase() || '';
      const cls = el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '';
      const label = tag ? `<${tag}${cls}>` : '';

      if (tag === 'p' || tag === 'h1' || tag === 'h2' || tag === 'h3') {
        const text = el.textContent.trim().slice(0, 120);
        if (text) lines.push(`${indent}${label} ${text}`);
      } else if (tag === 'button') {
        const text = el.textContent.trim();
        lines.push(`${indent}${label} "${text}"`);
      }

      for (const child of el.children) {
        walk(child, indent + '  ');
      }
    }
    walk(content, '');

    return { title, errors, lines, warnings };
  });

  await context.close();
  return result;
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  console.log(`=== A/B Diff: ${dateStr} ${office.toUpperCase()} ===\n`);

  const prod = await renderOffice(browser, 'https://office.k-sprawl.net');
  const stag = await renderOffice(browser, 'https://office-staging.k-sprawl.net');

  await browser.close();

  console.log(`PRODUCTION: ${prod.title}`);
  if (prod.errors.length) {
    console.log(`  ERRORS: ${prod.errors.join('; ')}`);
  }
  console.log(`STAGING:    ${stag.title}`);
  if (stag.errors.length) {
    console.log(`  ERRORS: ${stag.errors.join('; ')}`);
  }

  console.log(`\n--- DOM diff (production vs staging) ---\n`);

  const maxLines = Math.max(prod.lines.length, stag.lines.length);
  let diffs = 0;
  for (let i = 0; i < maxLines; i++) {
    const p = prod.lines[i] || '';
    const s = stag.lines[i] || '';
    if (p !== s) {
      diffs++;
      console.log(`  L${i}:`);
      console.log(`    PROD: ${p || '(missing)'}`);
      console.log(`    STAG: ${s || '(missing)'}`);
      console.log();
    }
  }

  if (diffs === 0) {
    console.log('  No differences detected.');
  } else {
    console.log(`  ${diffs} line(s) differ. Review before promoting.`);
  }

  // Print warnings (unexpected elements)
  if (prod.warnings.length) {
    console.log(`\n--- Production warnings ---`);
    prod.warnings.forEach(w => console.log(`  ${w}`));
  }
  if (stag.warnings.length) {
    console.log(`\n--- Staging warnings ---`);
    stag.warnings.forEach(w => console.log(`  ${w}`));
  }

  console.log('\n--- Plain text diff ---\n');
  const { spawnSync } = require('child_process');
  const fs = require('fs');
  // Write plain text versions
  const prodText = prod.lines.join('\n');
  const stagText = stag.lines.join('\n');
  fs.writeFileSync('/tmp/prod-text.txt', prodText);
  fs.writeFileSync('/tmp/stag-text.txt', stagText);

  const diff = spawnSync('diff', ['-u', '/tmp/prod-text.txt', '/tmp/stag-text.txt'], { encoding: 'utf8' });
  if (diff.stdout) {
    console.log(diff.stdout.slice(0, 3000));
    if (diff.stdout.length > 3000) console.log('... (truncated)');
  } else {
    console.log('No differences.');
  }
}

main().catch(e => { console.error(e.message); process.exit(1); });
