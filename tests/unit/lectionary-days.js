// Shared by the cli/*.test.js files: find a published day whose lessons
// exercise the slot count a test is about, rather than pinning a date that
// rots as the lectionary is regenerated.
import { readdirSync, readFileSync, existsSync } from 'fs';
import { join } from 'path';

export const ROOT = join(import.meta.dirname, '../..');
const DATA_DIR = join(ROOT, 'data');
const LECT_DIR = join(DATA_DIR, 'lectionary');

// data/ is gitignored and absent on a fresh clone.
export const HAS_DATA = existsSync(join(DATA_DIR, 'offices.json')) && existsSync(LECT_DIR);

/** The first published day whose morning or evening office appoints at
 *  least `min` lessons. */
export function findLessonDay(min) {
  if (!HAS_DATA) return null;
  for (const file of readdirSync(LECT_DIR).sort()) {
    if (!file.endsWith('.json')) continue;
    const month = JSON.parse(readFileSync(join(LECT_DIR, file), 'utf8'));
    for (const [date, day] of Object.entries(month)) {
      for (const [office, type] of [['morning', 'mp'], ['evening', 'ep']]) {
        if ((day[office]?.lessons || []).length >= min) {
          return { date, type, lessons: day[office].lessons };
        }
      }
    }
  }
  return null;
}
