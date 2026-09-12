#!/usr/bin/env node
/**
 * @file slice_daily_payload.js
 * Slices unified calendar + scripture daily payloads for v3 BFF architecture (ADR 0025).
 *
 * Slices pure-data daily payloads containing calendar variables, structured verses,
 * and paragraph break metadata for NRSVue and KJV fallback, as well as rolling 14-day batches.
 *
 * Output:
 *   - .build/private/calendar/v3/nrsvue/YYYY-MM-DD.json
 *   - .build/private/calendar/v3/kjv/YYYY-MM-DD.json
 *   - .build/private/calendar/v3/nrsvue/batch/START_END.json
 *   - .build/private/calendar/v3/kjv/batch/START_END.json
 *
 * Usage:
 *   node tools/slice_daily_payload.js [--out-dir <path>]
 */

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { execSync } from 'child_process';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  parseCitation,
  parseRanges,
  extractVersesWithChapter,
} from '../web/render.js';
import { collectDayCitations } from '../web/data-provider.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

function getGitCommit() {
  if (process.env.GIT_COMMIT) return process.env.GIT_COMMIT;
  try {
    return execSync('git rev-parse --short HEAD', { cwd: root }).toString().trim();
  } catch (_) {
    return 'unknown';
  }
}
const CURRENT_COMMIT = getGitCommit();
const API_VERSION = '3.0.0';

const outDirArgIdx = process.argv.indexOf('--out-dir');
const BASE_OUT_DIR = (outDirArgIdx !== -1 && process.argv[outDirArgIdx + 1])
  ? process.argv[outDirArgIdx + 1]
  : join(root, '.build/private/calendar/v3');

const _bookCache = new Map();

export function loadBook(bookName, translation = 'nrsvue') {
  const cacheKey = `${translation}:${bookName}`;
  if (_bookCache.has(cacheKey)) return _bookCache.get(cacheKey);

  if (translation === 'nrsvue') {
    // 1. Try data/translations/nrsvue/{bookName}.json
    const bookPath = join(root, 'data/translations/nrsvue', `${bookName}.json`);
    if (existsSync(bookPath)) {
      try {
        const data = JSON.parse(readFileSync(bookPath, 'utf8'));
        _bookCache.set(cacheKey, { data, translation: 'nrsvue' });
        return { data, translation: 'nrsvue' };
      } catch (_) {
        /* fallback */
      }
    }

    // 2. Try sources/bible.json
    const bibleSrc = join(root, 'sources/bible.json');
    if (existsSync(bibleSrc)) {
      try {
        const raw = JSON.parse(readFileSync(bibleSrc, 'utf8'));
        for (const testament of Object.values(raw)) {
          if (testament && typeof testament === 'object' && testament[bookName]) {
            const bookObj = testament[bookName];
            _bookCache.set(cacheKey, { data: bookObj, translation: 'nrsvue' });
            return { data: bookObj, translation: 'nrsvue' };
          }
        }
      } catch (_) {
        /* fallback */
      }
    }

    // 3. Fallback to KJV if NRSVue is missing this book
    const kjvPath = join(root, 'data/translations/kjv', `${bookName}.json`);
    if (existsSync(kjvPath)) {
      try {
        const data = JSON.parse(readFileSync(kjvPath, 'utf8'));
        _bookCache.set(cacheKey, { data, translation: 'kjv', isFallback: true });
        return { data, translation: 'kjv', isFallback: true };
      } catch (_) {
        /* failed */
      }
    }
  } else {
    // KJV translation requested
    const kjvPath = join(root, 'data/translations/kjv', `${bookName}.json`);
    if (existsSync(kjvPath)) {
      try {
        const data = JSON.parse(readFileSync(kjvPath, 'utf8'));
        _bookCache.set(cacheKey, { data, translation: 'kjv', isFallback: false });
        return { data, translation: 'kjv', isFallback: false };
      } catch (_) {
        /* failed */
      }
    }
  }

  return null;
}

export function loadParagraphs() {
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

/**
 * Slice readings for a given day and translation.
 */
export function sliceReadingsForDay(day, translation, paragraphs) {
  const citations = collectDayCitations(day);
  const readings = {};

  for (const rawCitation of citations) {
    try {
      const parsed = parseCitation(rawCitation);
      if (!parsed) continue;

      const loaded = loadBook(parsed.file, translation);
      if (!loaded || !loaded.data) continue;

      const ranges = parseRanges(parsed.rest);
      if (!ranges || !ranges.length) continue;

      const allVerses = ranges.flatMap(r => extractVersesWithChapter(loaded.data, r));
      if (!allVerses.length) continue;

      const bookParas = paragraphs ? (paragraphs[parsed.file] || null) : null;
      const relevantParas = {};
      if (bookParas) {
        const chs = new Set(allVerses.map(v => String(v.ch)));
        for (const ch of chs) {
          if (bookParas[ch]) {
            relevantParas[ch] = bookParas[ch];
          }
        }
      }

      readings[rawCitation] = {
        citation: rawCitation,
        book: parsed.file,
        verses: allVerses,
        paragraphs: relevantParas,
        translation: loaded.translation,
        ...(loaded.isFallback ? { isFallback: true } : {}),
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
          const isFallback = subReadings.some(r => r.isFallback);
          const combinedParas = {};
          for (const r of subReadings) {
            if (r.paragraphs) Object.assign(combinedParas, r.paragraphs);
          }
          readings[raw] = {
            citation: raw,
            book: subReadings[0].book,
            verses: subReadings.flatMap(r => r.verses),
            paragraphs: combinedParas,
            translation: subReadings[0].translation,
            ...(isFallback ? { isFallback: true } : {}),
          };
        }
      }
    }
  }

  return readings;
}

/**
 * Creates a unified daily payload object combining calendar day variables and scripture.
 */
export function buildUnifiedDayPayload(day, translation, paragraphs) {
  const readings = sliceReadingsForDay(day, translation, paragraphs);
  const isFallback = Object.values(readings).some(r => r.isFallback);

  return {
    apiVersion: API_VERSION,
    commit: CURRENT_COMMIT,
    ...day,
    translation,
    isFallback,
    readings,
    fetchedAt: Date.now(),
    expiresAt: translation === 'nrsvue' ? Date.now() + 30 * 86400000 : Date.now() + 365 * 86400000,
  };
}

export function run() {
  const lectionaryDir = join(root, 'data/lectionary');
  if (!existsSync(lectionaryDir)) {
    console.error(`Lectionary directory not found: ${lectionaryDir}`);
    process.exit(1);
  }

  const nrsvueDir = join(BASE_OUT_DIR, 'nrsvue');
  const nrsvueBatchDir = join(nrsvueDir, 'batch');
  const kjvDir = join(BASE_OUT_DIR, 'kjv');
  const kjvBatchDir = join(kjvDir, 'batch');

  mkdirSync(nrsvueDir, { recursive: true });
  mkdirSync(nrsvueBatchDir, { recursive: true });
  mkdirSync(kjvDir, { recursive: true });
  mkdirSync(kjvBatchDir, { recursive: true });

  const paragraphs = loadParagraphs();
  const files = readdirSync(lectionaryDir).filter(f => f.endsWith('.json')).sort();

  const allDates = [];
  const nrsvueDays = {};
  const kjvDays = {};

  for (const file of files) {
    const filePath = join(lectionaryDir, file);
    const monthData = JSON.parse(readFileSync(filePath, 'utf8'));

    for (const [dateStr, day] of Object.entries(monthData)) {
      if (!day || typeof day !== 'object') continue;
      day.date = dateStr;
      allDates.push(dateStr);

      const nrsvuePayload = buildUnifiedDayPayload(day, 'nrsvue', paragraphs);
      const kjvPayload = buildUnifiedDayPayload(day, 'kjv', paragraphs);

      nrsvueDays[dateStr] = nrsvuePayload;
      kjvDays[dateStr] = kjvPayload;

      writeFileSync(join(nrsvueDir, `${dateStr}.json`), JSON.stringify(nrsvuePayload), 'utf8');
      writeFileSync(join(kjvDir, `${dateStr}.json`), JSON.stringify(kjvPayload), 'utf8');
    }
  }

  allDates.sort();

  // Generate rolling 14-day batches (today + 13 = 14 days total)
  let batchCount = 0;
  for (let i = 0; i < allDates.length; i++) {
    const startStr = allDates[i];
    const endIdx = Math.min(i + 13, allDates.length - 1);
    const endStr = allDates[endIdx];

    const nrsvueBatch = {
      apiVersion: API_VERSION,
      commit: CURRENT_COMMIT,
      start: startStr,
      end: endStr,
      days: {},
    };
    const kjvBatch = {
      apiVersion: API_VERSION,
      commit: CURRENT_COMMIT,
      start: startStr,
      end: endStr,
      days: {},
    };

    for (let j = i; j <= endIdx; j++) {
      const d = allDates[j];
      nrsvueBatch.days[d] = nrsvueDays[d];
      kjvBatch.days[d] = kjvDays[d];
    }

    writeFileSync(join(nrsvueBatchDir, `${startStr}_${endStr}.json`), JSON.stringify(nrsvueBatch), 'utf8');
    writeFileSync(join(kjvBatchDir, `${startStr}_${endStr}.json`), JSON.stringify(kjvBatch), 'utf8');
    batchCount++;
  }

  console.log(`Sliced ${allDates.length} unified daily payloads and ${batchCount} batches across nrsvue & kjv to ${BASE_OUT_DIR}`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  run();
}
