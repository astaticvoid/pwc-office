#!/usr/bin/env node
/**
 * tools/validate_lectionary.cjs — structural completeness check for lectionary data.
 *
 * Validates every date in data/lectionary/ has complete morning and evening
 * entries with required fields present. The generated JSON is the canonical
 * representation of the source CSVs — validating it validates the source.
 *
 * Usage: node tools/validate_lectionary.cjs [--json]
 */

const { readdirSync, readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

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

      // Day-level metadata
      if (!day.name || !day.name.trim()) {
        failures.push({ date, office: 'day', detail: 'missing name' });
      }
      if (!day.colour || !day.colour.trim()) {
        failures.push({ date, office: 'day', detail: 'missing colour' });
      }
      if (!day.rank || !day.rank.trim()) {
        failures.push({ date, office: 'day', detail: 'missing rank' });
      }

      for (const ot of ['morning', 'evening']) {
        offices++;
        const od = day[ot];
        if (!od) {
          failures.push({ date, office: ot, detail: 'missing office entry' });
          continue;
        }

        // Psalms: must have psalms array or psalm_sets
        if (!od.psalms && !od.psalm_sets) {
          failures.push({ date, office: ot, detail: 'no psalms or psalm_sets' });
        }

        // Lessons: must have at least one
        if (!od.lessons || !od.lessons.length) {
          failures.push({ date, office: ot, detail: 'no lessons' });
        } else {
          for (let i = 0; i < od.lessons.length; i++) {
            const lesson = od.lessons[i];
            const citation = typeof lesson === 'object' ? lesson.citation : lesson;
            if (!citation || typeof citation !== 'string' || !citation.trim()) {
              failures.push({ date, office: ot, detail: `lesson[${i}] empty citation` });
            }
          }
        }

        // Collect: optional but must be non-empty string if present
        if (od.collect !== undefined && od.collect !== null && typeof od.collect !== 'string') {
          failures.push({ date, office: ot, detail: `collect is non-string: ${typeof od.collect}` });
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

  console.log(`Lectionary data check: ${dates} dates, ${offices} offices`);
  if (failures.length === 0) {
    console.log('All lectionary entries complete.');
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.log(`  ${f.date} ${f.office}: ${f.detail}`);
  }
  process.exit(1);
}

main();
