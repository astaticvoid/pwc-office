#!/usr/bin/env node
/**
 * Usage: node cli/office.js [mp|ep] [YYYY-MM-DD]
 * Renders a Daily Office to stdout using the same render.js as the browser.
 */
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderSegments, renderSubsection, lessonHtml
} from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(__dir, '..', p), 'utf8'));

const offices = load('data/offices.json');
const bounds  = load('data/season_bounds.json');

const officeType = process.argv[2] || 'mp';
const dateStr    = process.argv[3] || new Date().toISOString().slice(0, 10);

// Load lectionary for the month
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

// Minimal text render (HTML tags stripped for readability)
function strip(html) { return html.replace(/<[^>]+>/g, '').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'); }
function section(title, segs) {
  if (segs?.type === 'shared' && shared) segs = shared[segs.key];
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}

let out = `# ${officeType.toUpperCase()} — ${dateStr}\n`;
out += `Season: ${fSeason} | Form: ${key}\n`;
if (lectionaryDay) out += `Day: ${lectionaryDay.name}\n`;

out += section('Opening Responses', form.opening_responses);
const psalms = officeData?.psalms ?? officeData?.psalm_sets?.[0];
if (psalms) out += `\n## Psalm\n${(Array.isArray(psalms[0]) ? psalms[0] : psalms).map(p => typeof p === 'object' ? p.citation : p).join(', ')}\n`;
if (officeData?.lessons?.[0]) out += `\n## Lesson 1\n${strip(lessonHtml(officeData.lessons[0], shared, form))}\n`;
out += section('Responsory', form.responsory);
if (officeData?.lessons?.[1]) out += `\n## Lesson 2\n${strip(lessonHtml(officeData.lessons[1], shared, form))}\n`;
out += section('Canticle', form.canticle);
out += section('Intercessions', form.intercessions);
out += section('Litany', form.litany);
if (lectionaryDay?.collect_inline) {
  const ci = lectionaryDay.collect_inline;
  out += `\n## Collect of the Day\n\n${ci.name}\n${ci.text}\n`;
}
out += section("Lord's Prayer", form.lords_prayer_intro);
out += section('Dismissal', form.dismissal);

console.log(out);
