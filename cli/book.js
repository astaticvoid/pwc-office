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
  expandCitationForDisplay, lessonsPickText, splitPsalmRubrics, splitReadingRubrics,
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
  showLabel: true,
  skipShortLabels: true,
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

function citationStr(lesson) {
  const raw = typeof lesson === 'object' ? lesson.citation : lesson;
  return expandCitationForDisplay(raw);
}

// Book mode prints these rubrics around the lectionary content, not as one
// block. The split lives in render.js so this mode and the web renderer cannot
// disagree about which side of the content a rubric belongs on (#84).
const { intro: psalmIntro, doxologyCue: psalmDoxCue } = splitPsalmRubrics(form.psalm_rubrics);
const { handoff: readingHandoff, intro: readingIntro, after: readingAfter } =
  splitReadingRubrics(form.reading_rubrics);

// readingIntro is the sentence above the reading ("A Reading is read. After a
// period of silent reflection...") — the book prints it once, ahead of the
// first reading, not before each (#98).
function renderLesson(lesson, { showIntro = false } = {}) {
  return [
    'The Reading',
    showIntro && readingIntro.length ? text(readingIntro) : '',
    `[Reading: ${citationStr(lesson)}]`,
    text(form.reading_response),
  ].filter(Boolean).join('\n\n');
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
if (psalmIntro.length) B.push(text(psalmIntro));

const psalms = officeData?.psalms || [];
for (const psalm of psalms) B.push(renderPsalm(psalm));

// Psalm doxology
if (psalms.length && shared.doxology) {
  if (psalmDoxCue.length) B.push(text(psalmDoxCue));
  B.push(text([shared.doxology]));
}

const lessons = officeData?.lessons || [];
if (officeData?.lessons_pick) {
  const pickText = lessonsPickText(officeData.lessons_pick, lessons.length);
  if (pickText) B.push(`(${pickText})`);
}
// Guarded on the lessons like every neighbour here: with no lectionary file
// for the month these would otherwise print "continues with the Reading",
// "continues with the Responsory or the Canticle or both" and the two-reading
// rule back to back, with no Reading between them.
if (lessons[0] && readingHandoff.length) B.push(text(readingHandoff));
if (lessons[0]) B.push(renderLesson(lessons[0], { showIntro: true }));

if (lessons[0] && readingAfter.length) B.push(text(readingAfter));
B.push('The Responsory');
B.push(text(form.responsory));

if (lessons[1]) B.push(renderLesson(lessons[1]));

B.push('The Canticle');
B.push(text(form.canticle, { showLabel: true }));

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
