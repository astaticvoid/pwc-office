// @ts-check
// Ask the lectionary for a day with the property a test is about, rather than
// naming a date the rolling window will drop (#141).
//
// The window always spans a full liturgical year, so a day identified by what
// it *is* — the first Sunday of Advent, a day offering a choice of readings,
// a day whose alternate carries its own colour — is findable in any window.
// A date is findable only until the window moves past it, and then the test
// fails reporting a missing element rather than a moved window.
//
// The lectionary is read from disk here, in Node, before any browser starts;
// only the resolved date crosses into the page.

import { readdirSync, readFileSync, existsSync } from 'fs';
import { join } from 'path';
import { seasonOf } from '../../web/render.js';

const ROOT = join(import.meta.dirname, '../..');
const LECT_DIR = join(ROOT, 'data/lectionary');

export const HAS_LECTIONARY = existsSync(LECT_DIR);

/** Every published day, ascending by date. */
function allDays() {
  if (!HAS_LECTIONARY) return [];
  return readdirSync(LECT_DIR)
    .filter(f => /^\d{4}-\d{2}\.json$/.test(f))
    .sort()
    .flatMap(f => Object.values(JSON.parse(readFileSync(join(LECT_DIR, f), 'utf8'))))
    .filter(d => d && d.date)
    .sort((a, b) => a.date.localeCompare(b.date));
}

const DAYS = allDays();

const BOUNDS = existsSync(join(ROOT, 'data/season_bounds.json'))
  ? JSON.parse(readFileSync(join(ROOT, 'data/season_bounds.json'), 'utf8'))
  : {};

/**
 * The season the app would render a date in — the app's own seasonOf, not a
 * second reading of the bounds. Which form a day renders is decided by season
 * first and weekday only within OrdinaryTime, so a test about a weekday form
 * has to ask for both (a Wednesday in Christmastide renders christmas-mp).
 */
export function seasonFor(date) {
  return seasonOf(date, BOUNDS);
}

/**
 * The date of the first day satisfying `predicate`.
 *
 * `what` describes the day being asked for and is not decoration: when no day
 * matches, that sentence is the failure. A test that says "no day offers a
 * choice of readings" sends the reader to the lectionary; one that says
 * "expected element to be visible" sends them to the DOM, which is the wrong
 * place when the real answer is that the window moved.
 */
export function findDay(what, predicate) {
  // Searched newest-first: where several days qualify, the latest one survives
  // the most windows before it rolls out, which is the whole point here.
  const hit = [...DAYS].reverse().find(predicate);
  if (!hit) {
    throw new Error(
      `no day in the published lectionary is ${what} — ` +
      `searched ${DAYS.length} days from ${DAYS[0]?.date} to ${DAYS[DAYS.length - 1]?.date}`,
    );
  }
  return hit.date;
}

/** The day the calendar names, matched on the name column. */
export function dayNamed(pattern) {
  return findDay(`named ${pattern}`, d => pattern.test(d.name || ''));
}

/**
 * Every date the calendar gives that name, ascending. An observance recurs, so
 * a window wider than a year holds two — which is what a test crossing the
 * liturgical new year is about.
 */
export function daysNamed(pattern) {
  const hits = DAYS.filter(d => pattern.test(d.name || '')).map(d => d.date);
  if (!hits.length) throw new Error(`no day in the published lectionary is named ${pattern}`);
  return hits;
}

/**
 * The reference day for tests that are about the chrome around an office
 * rather than the office: both slots filled, an alternate observance in each,
 * two lessons apiece, and a pastoral note long enough to exercise the
 * expand/collapse.
 */
export function richDay() {
  return findDay(
    'a day with an alternate observance in both offices, two lessons in each, and a long pastoral note',
    d => d.morning?.alternate && d.evening?.alternate
      && (d.morning.lessons || []).length >= 2 && (d.evening.lessons || []).length >= 2
      && (d.notes || []).some(n => n.type === 'pastoral' && (n.text || '').length > 200)
      // Navigation tests step to the neighbours, and the bounds check refuses a
      // date outside the published window — so the reference day must not be the
      // window's own edge. Same room ordinaryDay() leaves.
      && d.date > DAYS[2]?.date && d.date < DAYS[DAYS.length - 3]?.date,
  );
}

/** The office block for a date, or an empty object. */
export function officeOf(date, office) {
  const day = DAYS.find(d => d.date === date);
  return (day && day[office === 'ep' ? 'evening' : 'morning']) || {};
}

/** The whole entry for a date. */
export function dayOf(date) {
  return DAYS.find(d => d.date === date) || {};
}

/** The day before / after one this module found, for navigation tests. */
export function shiftDate(date, days) {
  const d = new Date(date + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The date whose entry maximises `score`, among those `predicate` admits. */
export function extremeDay(what, predicate, score) {
  const pool = DAYS.filter(predicate);
  if (!pool.length) throw new Error(`no day in the published lectionary is ${what}`);
  return pool.reduce((best, d) => (score(d) > score(best) ? d : best)).date;
}

/**
 * An unremarkable weekday: no alternate observance, no eve, no reading choice,
 * both offices present. What a test that is about the chrome rather than the
 * day wants, and what breaks if it accidentally lands on Christmas.
 */
export function ordinaryDay() {
  return findDay('an ordinary weekday with both offices and no alternate', d => {
    const dow = new Date(d.date + 'T12:00:00Z').getUTCDay();
    return dow !== 0 && d.morning && d.evening
      && !d.alternate && !d.morning.lessons_pick && !d.evening.lessons_pick
      && !/\bEve of\b/i.test(d.name || '')
      // Leave room either side: navigation tests step to the neighbours, and
      // the bounds check refuses a date outside the published window.
      && d.date > DAYS[2]?.date && d.date < DAYS[DAYS.length - 3]?.date;
  });
}
