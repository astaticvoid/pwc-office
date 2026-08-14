#!/usr/bin/env node
/**
 * Usage: node cli/office.js [mp|ep] [YYYY-MM-DD]
 * Renders a Daily Office to stdout using the shared render.js text mode.
 */
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  officeFormSeason, formKey,
  renderSegmentsText, blocksToString,
  lessonsPickText, expandCitationForDisplay,
  splitPsalmRubrics, splitReadingRubrics,
} from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(__dir, '..', p), 'utf8'));

const offices = load('data/offices.json');
const bounds  = load('data/season_bounds.json');

const officeType = process.argv[2] || 'mp';
const dateStr    = process.argv[3] || new Date().toISOString().slice(0, 10);

const [year, month] = dateStr.split('-');
let lectionaryDay = null;
try {
  const lect = load(`data/lectionary/${year}-${month}.json`);
  lectionaryDay = lect[dateStr] || null;
} catch {}

const fSeason = officeFormSeason(dateStr, bounds);
const weekday = new Date(dateStr + 'T12:00:00Z').getUTCDay();
const key     = formKey(fSeason, officeType, weekday);
const form    = offices[key];
const shared  = offices._shared || {};

if (!form) {
  console.error(`No form found for key: ${key}`);
  process.exit(1);
}

const officeData = lectionaryDay ? lectionaryDay[officeType === 'mp' ? 'morning' : 'evening'] : null;

const BK = {};

function text(segs, opts = {}) {
  return blocksToString(renderSegmentsText(segs, shared, { ...BK, ...opts }));
}

// The Psalm/Reading rubrics come from the form since #84, and each says which
// side of the lectionary content it belongs on — split them the same way the
// other two renderers do rather than printing either block whole.
const { intro: psalmIntro, doxologyCue: psalmDoxCue } = splitPsalmRubrics(form.psalm_rubrics);
const { handoff: readingHandoff, intro: readingIntro, after: readingAfter } =
  splitReadingRubrics(form.reading_rubrics);

// This CLI names dynamic content rather than resolving it: the Psalm slot has
// always printed citations, not psalter text, and the lessons match that.
const citations = (lesson) =>
  expandCitationForDisplay(typeof lesson === 'object' ? lesson.citation : String(lesson));

let out = `# ${officeType.toUpperCase()} — ${dateStr}\n`;
out += `Season: ${fSeason} | Form: ${key}\n`;
if (lectionaryDay) out += `Day: ${lectionaryDay.name}\n`;

out += `\n## Opening Responses\n${text(form.opening_responses)}\n`;

// Length, not truthiness: `psalms: []` is not psalms, and the rubrics describe
// content, so they go when it does — the same guard web/app.js keeps, for the
// same reason. Unreachable with shipped lectionary data, latent otherwise.
const psalmSrc = officeData?.psalms?.length ? officeData.psalms : officeData?.psalm_sets?.[0];
const psalms = psalmSrc?.length
  ? (Array.isArray(psalmSrc[0]) ? psalmSrc[0] : psalmSrc)
  : [];
if (psalms.length) {
  out += '\n## Psalm\n';
  if (psalmIntro.length) out += `${text(psalmIntro)}\n`;
  out += `${psalms.map(p => typeof p === 'object' ? p.citation : p).join(', ')}\n`;
  // The cue introduces the Gloria — printing "one of the following may be said"
  // with nothing following it is what rendering the block whole would have
  // done. Bound to the doxology here as cli/book.js and web/app.js bind it.
  if (shared.doxology) {
    if (psalmDoxCue.length) out += `${text(psalmDoxCue)}\n`;
    out += `${text([shared.doxology])}\n`;
  }
}

const lessons = officeData?.lessons ?? [];
if (officeData?.lessons_pick) {
  const pickText = lessonsPickText(officeData.lessons_pick, lessons.length);
  if (pickText) out += `\n${pickText}\n`;
}
// Guarded on the lessons, like the psalm rubrics above: with no lectionary
// file for the month these would otherwise print the hand-off into a Reading
// that never arrives.
if (lessons[0] && readingHandoff.length) out += `\n${text(readingHandoff)}\n`;
if (lessons[0]) {
  out += '\n## Lesson 1\n';
  // The intro rubric heads the Reading block once, as the book prints it, and
  // is not repeated over Lesson 2 — that duplication is #98 in cli/book.js.
  if (readingIntro.length) out += `${text(readingIntro)}\n`;
  out += `${citations(lessons[0])}\n${text(form.reading_response)}\n`;
}
if (lessons[0] && readingAfter.length) out += `\n${text(readingAfter)}\n`;
out += `\n## Responsory\n${text(form.responsory)}\n`;
if (lessons[1]) {
  out += `\n## Lesson 2\n${citations(lessons[1])}\n${text(form.reading_response)}\n`;
}
out += `\n## Canticle\n${text(form.canticle)}\n`;
out += `\n## Intercessions\n${text(form.intercessions)}\n`;
out += `\n## Litany\n${text(form.litany)}\n`;

if (lectionaryDay?.collect_inline) {
  const ci = lectionaryDay.collect_inline;
  out += `\n## Collect of the Day\n${ci.name}\n${ci.text}\n`;
}
out += `\n## Lord's Prayer\n${text(form.lords_prayer_intro)}\n`;
out += `\n## Dismissal\n${text(form.dismissal)}\n`;

console.log(out);
