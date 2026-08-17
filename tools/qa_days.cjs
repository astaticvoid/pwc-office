/**
 * tools/qa_days.cjs — resolve tools/qa_dates.json to concrete days.
 *
 * An entry names the season, and in Ordinary Time the weekday, that selects
 * the forms it lists. Naming a date instead made the fixture expire: the
 * lectionary window advances, the date leaves it, and the entry stops
 * resolving — which is how allsaints-mp/-ep once lost all 10 dynamic rules
 * with `make qa` green throughout (#141).
 *
 * validate_office.cjs and validate_render.cjs both walk these days, so the
 * resolution lives here rather than in each: two readers of one fixture that
 * disagreed about which day an entry meant would be comparing different
 * offices while reporting the same form.
 */

const { readFileSync, readdirSync } = require('fs');
const { join } = require('path');

/** Every published day as [date, entry], ascending. */
function publishedDays(root) {
  const dir = join(root, 'data/lectionary');
  let files;
  try {
    files = readdirSync(dir).filter(f => /^\d{4}-\d{2}\.json$/.test(f)).sort();
  } catch (_) {
    return [];
  }
  return files
    .flatMap(f => Object.entries(JSON.parse(readFileSync(join(dir, f), 'utf8'))))
    .filter(([date, day]) => date && day)
    .sort(([a], [b]) => a.localeCompare(b));
}

/**
 * → [{ ...entry, date, day }] for the entries that resolve, and
 *   [{ spec, forms, reason }] for those that do not.
 *
 * `officeFormSeason` is passed in rather than imported: this file is CommonJS
 * and render.js is ESM, and both callers already hold it.
 */
function resolveQaDates(root, qaDates, bounds, officeFormSeason) {
  const published = publishedDays(root);
  const resolved = [];
  const unresolved = [];

  for (const entry of qaDates) {
    const spec = entry.season
      + (entry.weekday === undefined ? '' : ` weekday ${entry.weekday}`);
    // The middle of the run rather than its first day: a season's collect is
    // chosen by week index, and the edges of a season are where that is least
    // representative of the form being exercised.
    const hits = published.filter(([date, day]) =>
      officeFormSeason(date, bounds) === entry.season
      && (entry.weekday === undefined
        || new Date(`${date}T12:00:00Z`).getUTCDay() === entry.weekday)
      && day.morning && day.evening);
    if (!hits.length) {
      unresolved.push({
        date: spec,
        forms: entry.forms,
        reason: 'no day in the lectionary window is in this season',
      });
      continue;
    }
    const [date, day] = hits[Math.floor(hits.length / 2)];
    resolved.push({ ...entry, spec, date, day });
  }
  return { resolved, unresolved };
}

module.exports = { resolveQaDates };
