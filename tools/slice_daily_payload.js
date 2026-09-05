#!/usr/bin/env node
/**
 * @file slice_daily_payload.js
 * Slices unified calendar + scripture daily payloads for v2 BFF architecture (ADR 0025).
 *
 * Slices daily payloads containing both calendar variables and raw scripture readings
 * for NRSVue and KJV fallback, as well as rolling 14-day batch payloads.
 *
 * Output:
 *   - .build/private/calendar/v2/nrsvue/YYYY-MM-DD.json
 *   - .build/private/calendar/v2/kjv/YYYY-MM-DD.json
 *   - .build/private/calendar/v2/nrsvue/batch/START_END.json
 *   - .build/private/calendar/v2/kjv/batch/START_END.json
 *
 * Usage:
 *   node tools/slice_daily_payload.js [--out-dir <path>]
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
import { collectDayCitations } from '../web/data-provider.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');

const outDirArgIdx = process.argv.indexOf('--out-dir');
const BASE_OUT_DIR = (outDirArgIdx !== -1 && process.argv[outDirArgIdx + 1])
  ? process.argv[outDirArgIdx + 1]
  : join(root, '.build/private/calendar/v2');

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
        _bookCache.set(cacheKey, { data, translation: 'kjv', isFallback: true });
        return { data, translation: 'kjv', isFallback: true };
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

      const paraMap = paragraphs ? (paragraphs[parsed.file] || null) : null;
      const html = buildParagraphHtml(allVerses, paraMap);

      readings[rawCitation] = {
        citation: rawCitation,
        book: parsed.file,
        verses: allVerses,
        html,
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
          readings[raw] = {
            citation: raw,
            book: subReadings[0].book,
            verses: subReadings.flatMap(r => r.verses),
            html: subReadings.map(r => `<div class="scripture-option"><p class="scripture-choice-rubric"><strong>${r.citation}</strong></p>${r.html}</div>`).join('<p class="seg-rubric">or</p>'),
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
  const isFallback = translation === 'kjv';

  return {
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
      start: startStr,
      end: endStr,
      days: {},
    };
    const kjvBatch = {
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
