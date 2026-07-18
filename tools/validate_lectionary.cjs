#!/usr/bin/env node
/**
 * tools/validate_lectionary.cjs — verify extraction integrity for every date.
 *
 * Checks that the converter correctly parsed every day in the lectionary:
 * psalm references are valid numbers, lesson citations parse correctly,
 * no raw HTML entities leaked through, collect refs are valid page numbers.
 *
 * Usage: node tools/validate_lectionary.cjs [--json]
 */

const { readdirSync, readFileSync } = require('fs');
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

function main() {
  const useJson = process.argv.includes('--json');
  const lectionaryDir = join(root, 'data/lectionary');
  let files;
  try {
    files = readdirSync(lectionaryDir).filter(f => f.endsWith('.json')).sort();
  } catch (_) {
    console.error('No lectionary data found.');
    process.exit(useJson ? 0 : 1);
  }

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

        // Psalm citations must parse as valid psalm references
        const psalms = od.psalms || [];
        for (let i = 0; i < psalms.length; i++) {
          const cit = typeof psalms[i] === 'object' ? psalms[i].citation : psalms[i];
          if (!cit) {
            failures.push({ date, office: ot, detail: `psalm[${i}] empty citation` });
            continue;
          }
          if (checkCitation(cit)) {
            failures.push({ date, office: ot, detail: `psalm[${i}] unparseable: "${cit}"` });
          }
        }

        // Psalm sets: each entry must parse
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
              }
            }
          }
        }

        if (!psalms.length && !od.psalm_sets) {
          failures.push({ date, office: ot, detail: 'no psalms or psalm_sets' });
        }

        // Lesson citations must match book:chapter:verse pattern
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
            }
            // Check for raw HTML entities
            if (/&mdash;|&amp;|<br>/.test(citation)) {
              failures.push({ date, office: ot, detail: `lesson[${i}] contains HTML entity` });
            }
          }
        }

        // Collect reference: must start with a page number if present
        if (od.collect !== undefined && od.collect !== null) {
          const ref = String(od.collect);
          if (!COLLECT_RE.test(ref)) {
            failures.push({ date, office: ot, detail: `collect unparseable: "${ref}"` });
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

main();
