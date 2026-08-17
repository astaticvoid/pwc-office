import { describe, test, expect } from 'vitest';
import { execFileSync } from 'child_process';
import { readFileSync } from 'fs';
import { join } from 'path';
import { expandCitationForDisplay, officeFormSeason, formKey } from '../../web/render.js';
import { ROOT, HAS_DATA, findLessonDay } from './lectionary-days.js';

// Regression coverage for #148: a third appointed lesson must reach book-mode
// output too, in book order after the Canticle — mirroring the coverage
// cli-office.test.js carries for cli/office.js.

const DATA_DIR = join(ROOT, 'data');
const bounds = HAS_DATA ? JSON.parse(readFileSync(join(DATA_DIR, 'season_bounds.json'), 'utf8')) : null;

// cli/book.js takes a form name (e.g. "advent-mp"), not an office type —
// derive it the same way cli/office.js does internally.
function formNameFor(date, type) {
  const season  = officeFormSeason(date, bounds);
  const weekday = new Date(date + 'T12:00:00Z').getUTCDay();
  return formKey(season, type, weekday);
}

const run = (formName, date) =>
  execFileSync('node', [join(ROOT, 'cli/book.js'), formName, date], { encoding: 'utf8' });

describe.skipIf(!HAS_DATA)('cli/book.js: a third appointed lesson (#148)', () => {
  const day = findLessonDay(3);

  test.skipIf(!day)('reaches the page, after the Canticle', () => {
    const out = run(formNameFor(day.date, day.type), day.date);
    const cite = l => expandCitationForDisplay(typeof l === 'object' ? l.citation : String(l));
    const thirdCitation = `[Reading: ${cite(day.lessons[2])}]`;

    expect(out).toContain(thirdCitation);
    // Book order: Canticle, then any lesson beyond the second.
    expect(out.indexOf('The Canticle')).toBeGreaterThan(-1);
    expect(out.indexOf(thirdCitation)).toBeGreaterThan(out.indexOf('The Canticle'));
  });
});
