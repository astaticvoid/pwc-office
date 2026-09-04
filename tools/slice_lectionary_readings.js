#!/usr/bin/env node
/**
 * @file slice_lectionary_readings.js
 * Build-time lectionary scripture slicer for NRSVue compliance (ADR 0024).
 *
 * Slices strictly the appointed lectionary readings for every date across
 * the lectionary coverage window into calendar-date JSON files.
 *
 * Input:
 *   - data/lectionary/YYYY-MM.json
 *   - sources/bible.json or data/translations/nrsvue/*.json
 *   - data/paragraphs.json
 *
 * Output:
 *   - .build/private/readings/v1/nrsvue/YYYY-MM-DD.json
 *
 * Usage:
 *   node tools/slice_lectionary_readings.js [--version <v1>] [--out-dir <path>]
 */

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  parseCitation,
  parseRanges,
  extractVersesWithChapter,
  buildParagraphHtml,
} from '../web/render.js';
import { collectDayCitations } from '../web/scripture-provider.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const versionArgIdx = process.argv.indexOf('--version');
const API_VERSION = (versionArgIdx !== -1 && process.argv[versionArgIdx + 1])
  ? process.argv[versionArgIdx + 1]
  : 'v1';

const outDirArgIdx = process.argv.indexOf('--out-dir');
const OUT_DIR = (outDirArgIdx !== -1 && process.argv[outDirArgIdx + 1])
  ? process.argv[outDirArgIdx + 1]
  : join(root, `.build/private/readings/${API_VERSION}/nrsvue`);

// Cache loaded book JSONs
const _bookCache = new Map();

function loadBook(bookName) {
  if (_bookCache.has(bookName)) return _bookCache.get(bookName);

  // 1. Try data/translations/nrsvue/{bookName}.json
  const bookPath = join(root, 'data/translations/nrsvue', `${bookName}.json`);
  if (existsSync(bookPath)) {
    try {
      const data = JSON.parse(readFileSync(bookPath, 'utf8'));
      _bookCache.set(bookName, data);
      return data;
    } catch (_) {
      /* fallback */
    }
  }

  // 2. Try sources/bible.json (flat or testament-grouped)
  const bibleSrc = join(root, 'sources/bible.json');
  if (existsSync(bibleSrc)) {
    try {
      const raw = JSON.parse(readFileSync(bibleSrc, 'utf8'));
      for (const testament of Object.values(raw)) {
        if (testament && typeof testament === 'object' && testament[bookName]) {
          const bookObj = testament[bookName];
          _bookCache.set(bookName, bookObj);
          return bookObj;
        }
      }
    } catch (_) {
      /* failed */
    }
  }

  return null;
}

function loadParagraphs() {
  const pPath = join(root, 'data/paragraphs.json');
  if (existsSync(pPath)) {
    try {
      return JSON.parse(readFileSync(pPath, 'utf8'));
    } catch (_) {
      return null;
    }
  }
  return null;
}

export function sliceDay(day, paragraphs) {
  const citations = collectDayCitations(day);
  const readings = {};

  for (const rawCitation of citations) {
    try {
      const parsed = parseCitation(rawCitation);
      if (!parsed) continue;

      const bookData = loadBook(parsed.file);
      if (!bookData) continue;

      const ranges = parseRanges(parsed.rest);
      if (!ranges || !ranges.length) continue;

      const allVerses = ranges.flatMap(r => extractVersesWithChapter(bookData, r));
      if (!allVerses.length) continue;

      const paraMap = paragraphs ? (paragraphs[parsed.file] || null) : null;
      const html = buildParagraphHtml(allVerses, paraMap);

      readings[rawCitation] = {
        citation: rawCitation,
        book: parsed.file,
        verses: allVerses,
        html,
        translation: 'nrsvue',
      };
    } catch (_) {
      /* Skip unresolvable citation */
    }
  }

  // Generate composite entries for lectionary choice citations containing " or "
  for (const off of [day.morning, day.evening, day.morning?.alternate, day.evening?.alternate]) {
    if (!off || !Array.isArray(off.lessons)) continue;
    for (const l of off.lessons) {
      const raw = typeof l === 'object' ? l.citation : l;
      if (typeof raw === 'string' && raw.includes(' or ') && !readings[raw]) {
        const parts = raw.split(' or ').map(s => s.trim());
        const subReadings = parts.map(p => readings[p]).filter(Boolean);
        if (subReadings.length > 0) {
          readings[raw] = {
            citation: raw,
            book: subReadings[0].book,
            verses: subReadings.flatMap(r => r.verses),
            html: subReadings.map(r => `<div class="scripture-option"><p class="scripture-choice-rubric"><strong>${r.citation}</strong></p>${r.html}</div>`).join('<p class="seg-rubric">or</p>'),
            translation: 'nrsvue',
          };
        }
      }
    }
  }

  return {
    date: day.date,
    translation: 'nrsvue',
    source: 'remote',
    readings,
    fetchedAt: Date.now(),
    expiresAt: Date.now() + 30 * 86400000,
  };
}

export function run() {
  const lectionaryDir = join(root, 'data/lectionary');
  if (!existsSync(lectionaryDir)) {
    console.error(`Lectionary directory not found: ${lectionaryDir}`);
    process.exit(1);
  }

  mkdirSync(OUT_DIR, { recursive: true });

  const paragraphs = loadParagraphs();
  const files = readdirSync(lectionaryDir).filter(f => f.endsWith('.json')).sort();

  let daysCount = 0;
  let readingsCount = 0;

  for (const file of files) {
    const filePath = join(lectionaryDir, file);
    const monthData = JSON.parse(readFileSync(filePath, 'utf8'));

    for (const [dateStr, day] of Object.entries(monthData)) {
      if (!day || typeof day !== 'object') continue;
      day.date = dateStr;

      const sliced = sliceDay(day, paragraphs);
      const outPath = join(OUT_DIR, `${dateStr}.json`);
      writeFileSync(outPath, JSON.stringify(sliced), 'utf8');

      daysCount++;
      readingsCount += Object.keys(sliced.readings).length;
    }
  }

  console.log(`Sliced ${readingsCount} readings across ${daysCount} dates to ${OUT_DIR}`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  run();
}
