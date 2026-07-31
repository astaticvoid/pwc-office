#!/usr/bin/env node
/**
 * tools/validate_lectionary.cjs — verify extraction integrity AND referential
 * resolution for every date in the lectionary.
 *
 * Two different classes of check, both walking all ~397 dates x 2 offices:
 *   1. Syntax — psalm references are valid numbers, lesson citations parse,
 *      no raw HTML entities leaked through, collect refs look like page numbers.
 *   2. Resolution — every reference a rendered office actually depends on
 *      resolves to real data: the collect page exists in data/collects.json,
 *      every psalm number exists in data/psalter.json, every lesson citation
 *      resolves to at least one real verse in the KJV translation data.
 *      Reuses the exact runtime resolution functions from web/render.js
 *      (lookupCollect, parsePsalmCitation, parseCitation, parseRanges,
 *      extractVersesWithChapter) rather than reimplementing the parsing —
 *      a syntax-only check already missed a real bug once (BUG: six Sunday-
 *      in-Lent collect pages silently dropped by extraction, "collect ref
 *      is a well-formed page number" passed while the page didn't exist;
 *      see issue #18) precisely because it never checked resolution.
 *
 * Usage: node tools/validate_lectionary.cjs [--json]
 */

const { readdirSync, readFileSync, existsSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

// Pattern: bare psalm number (converter strips "Ps" prefix)
const PSALM_RE = /^\d+$/;
// Pattern: "119:1-24" or "18:1-20" (bare verse-range in psalm_sets)
const PSALM_VERSE_RE = /^\d+:\d+/;
// Pattern: lesson citation — book name + chapter:verse or chapter-verse
// Accepts: "1 Cor 2:6-16", "Jude 1-16", "3 Jn 1-15", "Is 42:(1-9), 10-17"
const LESSON_RE = /^\d?\s*[A-Z][A-Za-z]*\s+\d+/;
// Pattern: collect ref — page number, optionally with qualifiers
// Accepts: "384", "438/9", "430 or FAS 359", "268 (Com: 434 or FAS 361)"
const COLLECT_RE = /^\d+/;

const KNOWN_HOLIDAY_NOTE_PREFIXES = [
  'The Christmas Cycle', 'Notes on Festivals', 'Notes on Holy Days',
  'Other Notes on the Christian Year', 'The Liturgical Year', 'Calendar',
];

function checkCitation(cit) {
  const results = [];
  const parts = cit.split(/\s+or\s+/);
  for (const part of parts) {
    // Strip parenthetical annotations: "95 (Invitatory)" → "95"
    const trimmed = part.trim().replace(/\s*\([^)]*\)\s*/g, ' ').trim();
    if (!trimmed) continue;
    if (PSALM_RE.test(trimmed)) continue;
    if (PSALM_VERSE_RE.test(trimmed)) continue;
    if (LESSON_RE.test(trimmed)) continue;
    if (trimmed.match(/^\(/)) continue; // optional lesson in parens
    results.push(trimmed);
  }
  return results.length === 0 ? null : results;
}

// ── Resolution helpers ──────────────────────────────────────────────────────

const _bookCache = new Map();
function loadBook(file) {
  if (_bookCache.has(file)) return _bookCache.get(file);
  const path = join(root, 'data/translations/kjv', `${file}.json`);
  const book = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null;
  _bookCache.set(file, book);
  return book;
}

/** Returns [{raw, num}, ...] for each " or "-separated alternative in a
 * psalm citation that parses to a numeric psalm reference. */
function psalmNumbersIn(cit, parsePsalmCitation) {
  return cit.split(/\s+or\s+/).map(part => {
    const trimmed = part.trim().replace(/\s*\([^)]*\)\s*/g, ' ').trim();
    if (!trimmed) return null;
    const { num } = parsePsalmCitation(trimmed);
    return isNaN(num) ? null : { raw: trimmed, num };
  }).filter(Boolean);
}

/** True if a lesson citation resolves to at least one real verse (KJV, the
 * always-available fallback translation — matches what the app itself falls
 * back to when a preferred translation is missing a book). */
function resolvesToVerses(citation, { parseCitation, parseRanges, extractVersesWithChapter }) {
  const parsed = parseCitation(citation);
  if (!parsed) return false;
  const book = loadBook(parsed.file);
  if (!book) return false;
  const ranges = parseRanges(parsed.rest);
  if (!ranges.length) return false;
  return ranges.some(r => extractVersesWithChapter(book, r).length > 0);
}

async function main() {
  const { parseCitation, parseRanges, extractVersesWithChapter, parsePsalmCitation, lookupCollect } =
    await import('../web/render.js');

  const useJson = process.argv.includes('--json');
  const lectionaryDir = join(root, 'data/lectionary');
  let files;
  try {
    files = readdirSync(lectionaryDir).filter(f => f.endsWith('.json')).sort();
  } catch (_) {
    console.error('No lectionary data found.');
    process.exit(useJson ? 0 : 1);
  }

  const collects = JSON.parse(readFileSync(join(root, 'data/collects.json'), 'utf8'));
  const psalter = JSON.parse(readFileSync(join(root, 'data/psalter.json'), 'utf8'));

  const failures = [];
  let dates = 0, offices = 0;

  for (const file of files) {
    const data = JSON.parse(readFileSync(join(lectionaryDir, file), 'utf8'));
    for (const [date, day] of Object.entries(data).sort()) {
      dates++;

      // Check for raw HTML entities that should have been cleaned
      const rawName = day.name || '';
      if (/&mdash;|&amp;|<br>|&#\d+;/.test(rawName)) {
        failures.push({ date, field: 'name', detail: `contains HTML entity: "${rawName.slice(0,40)}"` });
      }

      // Day metadata
      if (!day.name || !day.name.trim()) {
        failures.push({ date, field: 'name', detail: 'missing' });
      }
      if (!day.colour || !day.colour.trim()) {
        failures.push({ date, field: 'colour', detail: 'missing' });
      }
      if (!day.rank || !day.rank.trim()) {
        failures.push({ date, field: 'rank', detail: 'missing' });
      }

      for (const ot of ['morning', 'evening']) {
        offices++;
        const od = day[ot];
        if (!od) {
          failures.push({ date, office: ot, detail: 'missing office entry' });
          continue;
        }

        // Psalm citations must parse as valid psalm references AND resolve
        // to a real psalm in data/psalter.json.
        const psalms = od.psalms || [];
        for (let i = 0; i < psalms.length; i++) {
          const cit = typeof psalms[i] === 'object' ? psalms[i].citation : psalms[i];
          if (!cit) {
            failures.push({ date, office: ot, detail: `psalm[${i}] empty citation` });
            continue;
          }
          if (checkCitation(cit)) {
            failures.push({ date, office: ot, detail: `psalm[${i}] unparseable: "${cit}"` });
            continue;
          }
          for (const { raw, num } of psalmNumbersIn(cit, parsePsalmCitation)) {
            if (!psalter[String(num)]) {
              failures.push({ date, office: ot, detail: `psalm[${i}] "${raw}" — Psalm ${num} not found in psalter.json` });
            }
          }
        }

        // Psalm sets: each entry must parse and resolve
        if (od.psalm_sets) {
          for (let gi = 0; gi < od.psalm_sets.length; gi++) {
            const group = od.psalm_sets[gi];
            for (let pi = 0; pi < group.length; pi++) {
              const cit = typeof group[pi] === 'object' ? group[pi].citation : group[pi];
              if (!cit) {
                failures.push({ date, office: ot, detail: `psalm_set[${gi}][${pi}] empty` });
                continue;
              }
              if (checkCitation(cit)) {
                failures.push({ date, office: ot, detail: `psalm_set[${gi}][${pi}] unparseable: "${cit}"` });
                continue;
              }
              for (const { raw, num } of psalmNumbersIn(cit, parsePsalmCitation)) {
                if (!psalter[String(num)]) {
                  failures.push({ date, office: ot, detail: `psalm_set[${gi}][${pi}] "${raw}" — Psalm ${num} not found in psalter.json` });
                }
              }
            }
          }
        }

        if (!psalms.length && !od.psalm_sets) {
          failures.push({ date, office: ot, detail: 'no psalms or psalm_sets' });
        }

        // Lesson citations must match book:chapter:verse pattern AND resolve
        // to at least one real verse in the KJV translation data.
        if (!od.lessons || !od.lessons.length) {
          failures.push({ date, office: ot, detail: 'no lessons' });
        } else {
          for (let i = 0; i < od.lessons.length; i++) {
            const lesson = od.lessons[i];
            const citation = typeof lesson === 'object' ? lesson.citation : lesson;
            if (!citation || typeof citation !== 'string' || !citation.trim()) {
              failures.push({ date, office: ot, detail: `lesson[${i}] empty citation` });
              continue;
            }
            if (!LESSON_RE.test(citation)) {
              failures.push({ date, office: ot, detail: `lesson[${i}] unparseable: "${citation}"` });
            } else if (!resolvesToVerses(citation, { parseCitation, parseRanges, extractVersesWithChapter })) {
              failures.push({ date, office: ot, detail: `lesson[${i}] "${citation}" does not resolve to any verses` });
            }
            // Check for raw HTML entities
            if (/&mdash;|&amp;|<br>/.test(citation)) {
              failures.push({ date, office: ot, detail: `lesson[${i}] contains HTML entity` });
            }
          }
        }

        // Collect reference: must start with a page number if present, AND
        // that page must actually exist in data/collects.json. (This is the
        // check that was missing when 6 real collects went silently missing
        // — a well-formed page-number string isn't the same as a page that
        // exists. See file header.)
        if (od.collect !== undefined && od.collect !== null) {
          const ref = String(od.collect);
          if (!COLLECT_RE.test(ref)) {
            failures.push({ date, office: ot, detail: `collect unparseable: "${ref}"` });
          } else if (!lookupCollect(collects, ref)) {
            failures.push({ date, office: ot, detail: `collect "${ref}" does not resolve to any entry in collects.json` });
          }
        }
      }
    }
  }

  if (useJson) {
    console.log(JSON.stringify({
      dates_checked: dates,
      offices_checked: offices,
      failures: failures,
      failure_count: failures.length,
    }, null, 2));
    process.exit(0);
  }

  console.log(`Lectionary extraction check: ${dates} dates, ${offices} offices`);
  if (failures.length === 0) {
    console.log('All lectionary entries correctly extracted.');
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    const loc = f.office ? `${f.date} ${f.office}` : f.date;
    console.log(`  ${loc}: ${f.field || ''} ${f.detail}`);
  }
  process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
