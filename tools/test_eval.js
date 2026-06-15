#!/usr/bin/env node
// tools/test_eval.js — Port of e2e/smoke_test.go + seasonal_test.go + lectionary_fetch_test.go.
//
// Fetches https://lectionary.anglican.ca/?date=YYYY-MM-DD, parses the
// id='lectionary_MP' / id='lectionary_EP' elements for psalm and reading
// citations, checks they appear in cli/book.js output.
// Skips (does not fail) if the site is unreachable.
//
// Usage:
//   node tools/test_eval.js --smoke      # 4 cases
//   node tools/test_eval.js --seasonal   # 26 cases

import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { spawnSync } from 'child_process';
import { formKey, officeFormSeason, ABBREV_TO_FILE } from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const root = join(__dir, '..');
const bounds = JSON.parse(readFileSync(join(root, 'data/season_bounds.json'), 'utf8'));
const BOOK_JS = join(root, 'cli/book.js');

// ── Test cases ────────────────────────────────────────────────────────────────

const SMOKE_CASES = [
  { name: 'Easter-MP',   date: '2026-04-05', ot: 'mp' },
  { name: 'Easter-EP',   date: '2026-04-05', ot: 'ep' },
  { name: 'Lent-MP',     date: '2026-03-08', ot: 'mp', noAlleluia: true },
  { name: 'FeastDay-MP', date: '2026-05-15', ot: 'mp' }, // Saint Matthias
];

// Verbatim from e2e/seasonal_test.go — one representative day per liturgical form.
const SEASONAL_CASES = [
  // Named seasons
  { name: 'Advent-MP',              date: '2026-11-29', ot: 'mp' },
  { name: 'Advent-EP',              date: '2026-11-29', ot: 'ep' },
  { name: 'Christmas-MP',           date: '2025-12-28', ot: 'mp' }, // Dec 25 returns Advent; use Dec 28
  { name: 'Christmas-EP',           date: '2025-12-28', ot: 'ep' },
  { name: 'Epiphany-MP',            date: '2026-01-11', ot: 'mp' },
  { name: 'Epiphany-EP',            date: '2026-01-11', ot: 'ep' },
  { name: 'Lent-MP',                date: '2026-03-08', ot: 'mp' },
  { name: 'Lent-EP',                date: '2026-03-08', ot: 'ep' },
  { name: 'Passiontide-MP',         date: '2026-03-29', ot: 'mp' },
  { name: 'Passiontide-EP',         date: '2026-03-29', ot: 'ep' },
  { name: 'Easter-MP',              date: '2026-04-19', ot: 'mp' },
  { name: 'Easter-EP',              date: '2026-04-19', ot: 'ep' },
  { name: 'Pentecost-MP',           date: '2026-05-24', ot: 'mp' },
  { name: 'Pentecost-EP',           date: '2026-05-24', ot: 'ep' },
  { name: 'AllSaints-MP',           date: '2026-11-01', ot: 'mp' },
  { name: 'AllSaints-EP',           date: '2026-11-01', ot: 'ep' },
  // OrdinaryTime — weekday-specific forms (June 2026)
  { name: 'OrdinaryTime-Sunday-MP',    date: '2026-06-07', ot: 'mp' },
  { name: 'OrdinaryTime-Sunday-EP',    date: '2026-06-07', ot: 'ep' },
  { name: 'OrdinaryTime-Monday-MP',    date: '2026-06-08', ot: 'mp' },
  { name: 'OrdinaryTime-Monday-EP',    date: '2026-06-08', ot: 'ep' },
  { name: 'OrdinaryTime-Wednesday-MP', date: '2026-06-10', ot: 'mp' },
  { name: 'OrdinaryTime-Wednesday-EP', date: '2026-06-10', ot: 'ep' },
  { name: 'OrdinaryTime-Friday-MP',    date: '2026-06-12', ot: 'mp' },
  { name: 'OrdinaryTime-Friday-EP',    date: '2026-06-12', ot: 'ep' },
  { name: 'OrdinaryTime-Saturday-MP',  date: '2026-06-13', ot: 'mp' },
  { name: 'OrdinaryTime-Saturday-EP',  date: '2026-06-13', ot: 'ep' },
];

const REQUIRED_SECTIONS = [
  'The Gathering of the Community',
  'The Proclamation of the Word',
  'The Psalm',
  'The Prayers of the Community',
  "The Lord's Prayer",
  'The Sending Forth of the Community',
];

// ── Rendering ─────────────────────────────────────────────────────────────────

function renderOffice(date, ot) {
  const season = officeFormSeason(date, bounds);
  const weekday = new Date(date + 'T12:00:00Z').getUTCDay();
  const form = formKey(season, ot, weekday);
  const result = spawnSync('node', [BOOK_JS, form, date], { encoding: 'utf8', timeout: 15000 });
  if (result.error || result.status !== 0) {
    return { output: '', form, error: result.stderr || String(result.error) };
  }
  return { output: result.stdout, form };
}

// ── Citation fetching ─────────────────────────────────────────────────────────

async function fetchOfficialReadings(date, ot) {
  const url = `https://lectionary.anglican.ca/?date=${date}`;
  let html;
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
    html = await resp.text();
  } catch (e) {
    return { skipped: true, reason: String(e) };
  }

  const id = ot === 'ep' ? 'lectionary_EP' : 'lectionary_MP';
  const re = new RegExp(`id='${id}'[^>]*>([\\s\\S]*?)</p>`);
  const m = html.match(re);
  if (!m) {
    return { skipped: true, reason: `Could not locate #${id} on lectionary.anglican.ca for ${date}` };
  }

  let raw = m[1]
    .replace(/<[^>]+>/g, '')
    .replace(/&mdash;/g, '—').replace(/&ndash;/g, '–').replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ')
    .trim();

  // Remove "Morning Prayer:" / "Evening Prayer:" label.
  const colonIdx = raw.indexOf(':');
  if (colonIdx >= 0) raw = raw.slice(colonIdx + 1).trim();

  return parseCitations(raw);
}

function parseCitations(raw) {
  const psalms = [], readings = [];
  let collect = '';
  for (const part of raw.split(';')) {
    const p = part.trim();
    if (!p) continue;
    if (p.startsWith('Ps ')) {
      psalms.push(...p.slice(3).split(',').map(n => n.trim()));
    } else if (p.startsWith('Coll ')) {
      collect = p.slice(5).trim();
    } else {
      readings.push(p);
    }
  }
  return { psalms, readings, collect, raw };
}

// ── Checking ──────────────────────────────────────────────────────────────────

function expandCitation(citation) {
  const m = citation.trim().match(/^([1-3]?\s*[A-Z][a-z]*)\s+(.+)$/);
  if (!m) return citation.trim();
  const expanded = ABBREV_TO_FILE[m[1].trim()];
  return expanded ? `${expanded} ${m[2]}` : citation.trim();
}

function checkStructure(output) {
  return REQUIRED_SECTIONS.filter(s => !output.includes(s)).map(s => `missing section "${s}"`);
}

function verifyReadings(output, or) {
  const errs = [];
  if (or.psalms.length) {
    const found = or.psalms.some(ps => output.includes(`Psalm ${ps}`));
    if (!found) errs.push(`official psalms [${or.psalms.join(', ')}] not found in output`);
  }
  for (const reading of or.readings) {
    const alts = reading.split(' or ');
    const found = alts.some(alt => output.includes(expandCitation(alt.trim())));
    if (!found) errs.push(`official reading "${reading}" not found in output`);
  }
  return errs;
}

// ── Runner ────────────────────────────────────────────────────────────────────

async function runCase(tc) {
  const { name, date, ot, noAlleluia } = tc;
  const { output, form, error } = renderOffice(date, ot);
  if (error) return { name, date, ot, form, errors: [`render error: ${error}`] };

  const errors = checkStructure(output);
  if (noAlleluia && output.toLowerCase().includes('alleluia')) {
    errors.push('"alleluia" found in Lenten office');
  }

  const or = await fetchOfficialReadings(date, ot);
  if (or.skipped) {
    console.log(`    SKIP citation check: ${or.reason}`);
    return { name, date, ot, form, errors, siteSkipped: true };
  }
  console.log(`    official (${ot} ${date}): ${or.raw}`);
  errors.push(...verifyReadings(output, or));

  return { name, date, ot, form, errors };
}

// ── Main ──────────────────────────────────────────────────────────────────────

const mode = process.argv[2];
if (mode !== '--smoke' && mode !== '--seasonal') {
  console.error('Usage: node tools/test_eval.js --smoke | --seasonal');
  process.exit(1);
}

const cases = mode === '--smoke' ? SMOKE_CASES : SEASONAL_CASES;
const failures = [];
let siteSkips = 0;

console.log(`Running ${cases.length} ${mode.slice(2)} case(s)...\n`);
for (const tc of cases) {
  process.stdout.write(`  ${tc.name} (${tc.date} ${tc.ot})...\n`);
  const result = await runCase(tc);
  if (result.siteSkipped) siteSkips++;
  if (result.errors.length) {
    console.log(`  => FAIL`);
    failures.push(result);
  } else {
    console.log(`  => pass`);
  }
}

if (failures.length) {
  console.error(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.error(`  ${f.name} (${f.date} ${f.ot}, form: ${f.form}):`);
    for (const e of f.errors) console.error(`    - ${e}`);
  }
  process.exit(1);
} else {
  const skippedNote = siteSkips ? ` (${siteSkips} site-unreachable skips)` : '';
  console.log(`\nAll ${cases.length} case(s) passed${skippedNote}.`);
}
