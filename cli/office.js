#!/usr/bin/env node
/**
 * Usage: node cli/office.js [mp|ep] [YYYY-MM-DD]
 * Renders a Daily Office to stdout using the shared render.js text mode.
 */
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderSegmentsText, blocksToString,
  lessonHtml, lessonsPickText,
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
const weekIdx = seasonWeekIndex(dateStr, fSeason, bounds);
const key     = formKey(fSeason, officeType, weekday);
const form    = offices[key];
const shared  = offices._shared || {};

if (!form) {
  console.error(`No form found for key: ${key}`);
  process.exit(1);
}

const officeData = lectionaryDay ? lectionaryDay[officeType === 'mp' ? 'morning' : 'evening'] : null;

const BK = { verse: true };

function text(segs, opts = {}) {
  return blocksToString(renderSegmentsText(segs, shared, { ...BK, ...opts }));
}

let out = `# ${officeType.toUpperCase()} — ${dateStr}\n`;
out += `Season: ${fSeason} | Form: ${key}\n`;
if (lectionaryDay) out += `Day: ${lectionaryDay.name}\n`;

out += `\n## Opening Responses\n${text(form.opening_responses)}\n`;

const psalms = officeData?.psalms ?? officeData?.psalm_sets?.[0];
if (psalms) out += `\n## Psalm\n${(Array.isArray(psalms[0]) ? psalms[0] : psalms).map(p => typeof p === 'object' ? p.citation : p).join(', ')}\n`;

if (officeData?.lessons_pick) {
  const pickText = lessonsPickText(officeData.lessons_pick, officeData.lessons?.length || 0);
  if (pickText) out += `\n${pickText}\n`;
}
if (officeData?.lessons?.[0]) out += `\n## Lesson 1\n${text(form.responsory || [])}\n`;
out += `\n## Responsory\n${text(form.responsory)}\n`;
if (officeData?.lessons?.[1]) out += `\n## Lesson 2\n${text(form.responsory || [])}\n`;
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
