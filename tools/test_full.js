#!/usr/bin/env node
// tools/test_full.js — Port of e2e/full_test.go.
// Walks all lectionary JSON files, runs cli/book.js for each date × MP+EP,
// asserts required plain-text section headings are present.
// Exit 0 on pass, exit 1 with failure summary.

import { readdirSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { formKey, officeFormSeason } from '../web/render.js';

const execFileAsync = promisify(execFile);
const __dir = dirname(fileURLToPath(import.meta.url));
const root = join(__dir, '..');

const bounds = JSON.parse(readFileSync(join(root, 'data/season_bounds.json'), 'utf8'));
const BOOK_JS = join(root, 'cli/book.js');

const REQUIRED = [
  'The Gathering of the Community',
  'The Proclamation of the Word',
  'The Psalm',
  'The Prayers of the Community',
  "The Lord's Prayer",
  'The Sending Forth of the Community',
];

// Build list of all (date, officeType) pairs from the lectionary files.
const lectionaryDir = join(root, 'data/lectionary');
const files = readdirSync(lectionaryDir).filter(f => f.endsWith('.json')).sort();

const tasks = [];
for (const file of files) {
  const data = JSON.parse(readFileSync(join(lectionaryDir, file), 'utf8'));
  for (const date of Object.keys(data).sort()) {
    for (const ot of ['mp', 'ep']) {
      const season = officeFormSeason(date, bounds);
      const weekday = new Date(date + 'T12:00:00Z').getUTCDay();
      const form = formKey(season, ot, weekday);
      tasks.push({ date, ot, form });
    }
  }
}

// Run tasks with bounded concurrency.
async function runWithPool(tasks, concurrency) {
  const failures = [];
  let idx = 0;
  async function worker() {
    while (idx < tasks.length) {
      const { date, ot, form } = tasks[idx++];
      let stdout;
      try {
        ({ stdout } = await execFileAsync('node', [BOOK_JS, form, date], { timeout: 15000 }));
      } catch (e) {
        failures.push(`${date} ${ot} (${form}): process error — ${e.message}`);
        continue;
      }
      for (const section of REQUIRED) {
        if (!stdout.includes(section)) {
          failures.push(`${date} ${ot} (${form}): missing section "${section}"`);
        }
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, tasks.length) }, worker));
  return failures;
}

console.log(`Checking ${tasks.length} offices (${tasks.length / 2} dates × 2)...`);
const failures = await runWithPool(tasks, 8);

if (failures.length) {
  console.error(`\n${failures.length} failure(s) out of ${tasks.length} checks:\n`);
  for (const f of failures) console.error('  FAIL:', f);
  process.exit(1);
} else {
  console.log(`All ${tasks.length} checks passed.`);
}
