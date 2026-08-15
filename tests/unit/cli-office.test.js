import { describe, test, expect } from 'vitest';
import { execFileSync } from 'child_process';
import { readdirSync, readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { expandCitationForDisplay } from '../../web/render.js';

// Each lesson slot in cli/office.js holds the reading appointed for that slot,
// and nothing else (#95).

const ROOT = join(import.meta.dirname, '../..');
const DATA_DIR = join(ROOT, 'data');
const LECT_DIR = join(DATA_DIR, 'lectionary');
const HAS_DATA = existsSync(join(DATA_DIR, 'offices.json')) && existsSync(LECT_DIR);

// Pinning a date would rot as the lectionary is regenerated; ask the data for
// one instead. Two lessons is what exercises both slots.
function findTwoLessonDay() {
  // vitest runs a skipped describe's factory, so the read is guarded here as
  // well as on the suite — data/ is gitignored and absent on a fresh clone.
  if (!HAS_DATA) return null;
  for (const file of readdirSync(LECT_DIR).sort()) {
    if (!file.endsWith('.json')) continue;
    const month = JSON.parse(readFileSync(join(LECT_DIR, file), 'utf8'));
    for (const [date, day] of Object.entries(month)) {
      for (const [office, type] of [['morning', 'mp'], ['evening', 'ep']]) {
        if ((day[office]?.lessons || []).length >= 2) {
          return { date, type, lessons: day[office].lessons };
        }
      }
    }
  }
  return null;
}

const run = (type, date) =>
  execFileSync('node', [join(ROOT, 'cli/office.js'), type, date], { encoding: 'utf8' });

/** The body of one `## Heading` section, up to the next heading. */
function section(out, heading) {
  const lines = out.split('\n');
  const start = lines.indexOf(`## ${heading}`);
  if (start < 0) return null;
  const rest = lines.slice(start + 1);
  const end = rest.findIndex(l => l.startsWith('## '));
  return (end < 0 ? rest : rest.slice(0, end)).join('\n');
}

describe.skipIf(!HAS_DATA)('cli/office.js lesson slots', () => {
  const day = findTwoLessonDay();

  test.skipIf(!day)('prints each appointed reading in its own slot', () => {
    const out = run(day.type, day.date);
    const cite = l => expandCitationForDisplay(typeof l === 'object' ? l.citation : String(l));

    expect(section(out, 'Lesson 1')).toContain(cite(day.lessons[0]));
    expect(section(out, 'Lesson 2')).toContain(cite(day.lessons[1]));
  });

  test.skipIf(!day)('does not render the responsory into the lesson slots', () => {
    const out = run(day.type, day.date);
    const responsory = section(out, 'Responsory');
    expect(responsory).toBeTruthy();

    // The refrain opens the responsory and is distinctive per form.
    const refrain = responsory.split('\n').find(l => l.trim().length > 20);
    expect(refrain, 'responsory has a line to key on').toBeTruthy();

    for (const slot of ['Lesson 1', 'Lesson 2']) {
      expect(section(out, slot), `${slot} is not the responsory`).not.toContain(refrain);
    }
  });
});
