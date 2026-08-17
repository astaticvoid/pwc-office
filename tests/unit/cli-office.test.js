import { describe, test, expect } from 'vitest';
import { execFileSync } from 'child_process';
import { join } from 'path';
import { expandCitationForDisplay } from '../../web/render.js';
import { ROOT, HAS_DATA, findLessonDay } from './lectionary-days.js';

// Each lesson slot in cli/office.js holds the reading appointed for that slot,
// and nothing else (#95).

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
  const day = findLessonDay(2);

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

describe.skipIf(!HAS_DATA)('cli/office.js: a third appointed lesson (#148)', () => {
  const day = findLessonDay(3);

  test.skipIf(!day)('reaches the page in its own slot, after the Canticle', () => {
    const out = run(day.type, day.date);
    const cite = l => expandCitationForDisplay(typeof l === 'object' ? l.citation : String(l));

    expect(section(out, 'Lesson 3')).toContain(cite(day.lessons[2]));
    // Book order: Canticle, then any lesson beyond the second.
    expect(out.indexOf('## Canticle')).toBeGreaterThan(-1);
    expect(out.indexOf('## Lesson 3')).toBeGreaterThan(out.indexOf('## Canticle'));
  });
});
