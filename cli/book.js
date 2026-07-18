#!/usr/bin/env node
/**
 * cli/book.js — Book-mode plain-text renderer for Daily Office forms.
 * Usage: node cli/book.js FORM [YYYY-MM-DD]
 *
 * Uses renderSegmentsText from web/render.js for all segment rendering.
 */
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  renderSegmentsText, blocksToString,
  ABBREV_TO_FILE, CANTICLE_SOURCE, lessonsPickText,
} from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const load = p => JSON.parse(readFileSync(join(__dir, '..', p), 'utf8'));

const offices = load('data/offices.json');
const psalter = load('data/psalter.json');

const formName = process.argv[2] || 'ordinary-sunday-ep';
const dateStr  = process.argv[3] || new Date().toISOString().slice(0, 10);
const [year, month] = dateStr.split('-');

let lectionaryDay = null;
try {
  const lect = load(`data/lectionary/${year}-${month}.json`);
  lectionaryDay = lect[dateStr] || null;
} catch (_) {}

const form    = offices[formName];
const shared  = offices._shared || {};

if (!form) {
  process.stderr.write(`Unknown form: ${formName}\n`);
  process.exit(1);
}

const officeType = formName.endsWith('-ep') ? 'ep' : 'mp';
const officeData = lectionaryDay
  ? lectionaryDay[officeType === 'ep' ? 'evening' : 'morning']
  : null;

// ── Book-mode rendering options ─────────────────────────────────────────────

const BK = {
  verse: false,
  showLabel: true,
  skipRubrics: /continues with|may conclude with|^The Litany is said or sung\./i,
  skipShortLabels: true,
  condenseRubrics: {
    'The community may offer': 'Offer intercessions, petitions, and thanksgivings, silently or aloud.',
  },
};

function text(segs, opts = {}) {
  return blocksToString(renderSegmentsText(segs, shared, { ...BK, ...opts }));
}

function resolveShared(field) {
  if (field?.type === 'shared' && shared) return shared[field.key];
  return field || [];
}

// ── Psalm ────────────────────────────────────────────────────────────────────

function renderPsalm(citation) {
  const raw = typeof citation === 'object' ? citation.citation : String(citation);
  const num = raw.replace(/[^0-9].*/, '');
  const ps  = psalter[num];
  if (!ps) return `[Psalm ${raw}: not found]`;
  const title = ps.title ? `Psalm ${ps.number} — ${ps.title}` : `Psalm ${ps.number}`;
  const verses = ps.text.split('\n')
    .map(l => l.replace(/^\d+\s/, '').trimStart()).join('\n').trimEnd();
  return `${title}\n\n${verses}`;
}

// ── Reading ─────────────────────────────────────────────────────────────────

function expandCitation(raw) {
  return raw.split(' or ').map(part => {
    const m = part.trim().match(/^([1-3]?\s*[A-Z][a-z]*)\s+(.+)$/);
    if (!m) return part.trim();
    const expanded = ABBREV_TO_FILE[m[1].trim()];
    return expanded ? `${expanded} ${m[2]}` : part.trim();
  }).join(' or ');
}

function citationStr(lesson) {
  const raw = typeof lesson === 'object' ? lesson.citation : lesson;
  return expandCitation(raw);
}

function renderLesson(lesson) {
  return [
    'The Reading',
    '(A Reading from the Daily Office Lectionary, the Weekday Eucharistic ' +
      'Lectionary, or the Revised Common Lectionary Daily Readings is read. ' +
      'After a period of silent reflection one of the following is said.)',
    `[Reading: ${citationStr(lesson)}]`,
    text(form.reading_response),
  ].join('\n\n');
}

// ── Build output ───────────────────────────────────────────────────────────

const B = [];

// Gathering
if (form.subtitle) B.push(form.subtitle);
B.push('The Gathering of the Community');

const opening = resolveShared(form.opening_responses);
// Separate doxology from opening responses (ordinary-time forms)
const openingWithoutDox = opening.filter(
  s => !(s.type === 'shared' && s.key === 'doxology')
);
B.push('Introductory Responses');
B.push(text(openingWithoutDox));
if (shared.doxology && opening.some(s => s.type === 'shared' && s.key === 'doxology')) {
  B.push(text(shared.doxology.groups, { alleluia: true }));
}

if (form.thanksgiving_for_light) {
  B.push('Thanksgiving for Light');
  B.push(text(form.thanksgiving_for_light));
} else if (form.phos_hilaron) {
  B.push(text(form.phos_hilaron));
}

// Proclamation
B.push('The Proclamation of the Word');
B.push('The Psalm');
B.push('(A Psalm from the Daily Office Lectionary, the Weekday Eucharistic '
  + 'Lectionary, or the Revised Common Lectionary Daily Readings is said or sung.)');

const psalms = officeData?.psalms || [];
for (const psalm of psalms) B.push(renderPsalm(psalm));

// Psalm doxology
const isSeasonal = !!form.subtitle;
const psalmDox = isSeasonal
  ? (formName.includes('pentecost')
      ? '(At the end of the Psalm(s) one of the following may be said or sung.)'
      : '(At the end of the Psalm one of the following may be said or sung.)')
  : '(After the Psalm one of the following may be said or sung.)';
if (psalms.length && shared.doxology) {
  B.push(psalmDox);
  B.push(text([shared.doxology]));
}

const lessons = officeData?.lessons || [];
if (officeData?.lessons_pick) {
  const pickText = lessonsPickText(officeData.lessons_pick, lessons.length);
  if (pickText) B.push(`(${pickText})`);
}
if (lessons[0]) B.push(renderLesson(lessons[0]));

B.push('The Responsory');
B.push(text(form.responsory));

if (lessons[1]) B.push(renderLesson(lessons[1]));

B.push('The Canticle');
B.push(text(form.canticle, { showLabel: true, verse: true }));

// Affirmation
B.push('Affirmation of Faith');
B.push(text(form.affirmation, { showLabel: true }));

// Prayers
B.push('The Prayers of the Community');
B.push('Intercessions and Thanksgivings');
B.push(text(form.intercessions));

B.push('The Litany');
B.push(text(form.litany));

B.push('The Collect');
B.push(`[Collect of the Day: ${dateStr}]`);
B.push(text(form.seasonal_collects, { joinLines: true }));

// Lord's Prayer (within Prayers, matching web app structure)
B.push("The Lord's Prayer");
B.push(text(form.lords_prayer_intro));

// Sending Forth
B.push('The Sending Forth of the Community');
B.push('The Dismissal');
B.push(text(form.dismissal));

process.stdout.write(B.filter(Boolean).join('\n\n') + '\n');
