#!/usr/bin/env node
/**
 * cli/book.js — Book-mode plain-text renderer for Daily Office forms.
 * Usage: node cli/book.js FORM [YYYY-MM-DD]
 * Output: clean plain text suitable for diffing against PDF golden files.
 *
 * Does NOT use renderSegments/renderAlternatives from render.js — those
 * produce HTML with tab UI. This renderer is self-contained plain text.
 */
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { CANTICLE_SOURCE, ABBREV_TO_FILE } from '../web/render.js';

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

// ── Skip / condense patterns ───────────────────────────────────────────────────

// Navigation rubrics that are section cues in the printed book, not content.
const BOOK_SKIP_RUBRICS = /continues with|may conclude with|^The Litany is said or sung\./i;

// Structural rubrics in seasonal_collects: not content.
// Use [''] to match both straight and curly apostrophes.
const SKIP_COLLECT_RE = /^Either the Collect of the Day|^the Lord['’]\s*s Prayer$/i;

// Intercessions rubric: condense to first sentence only.
const INTERCESSIONS_RE = /^(The community may offer|Additional intercessions)/i;

// Roman-numeral labels (I, II, III …) are not section headers in plain text.
const SHORT_LABEL_RE = /^(?:Form\s+)?(?:I{1,3}|IV|V|VI{0,3}|IX|X)$/i;

// ── Rubric rendering ──────────────────────────────────────────────────────────

function textRubric(seg, opts = {}) {
  const t = (seg.text || '').trim();
  if (BOOK_SKIP_RUBRICS.test(t)) return '';
  if (opts.skipCollectRubric && SKIP_COLLECT_RE.test(t)) return '';
  if (INTERCESSIONS_RE.test(t)) {
    const joined = t.replace(/\n/g, ' ');
    const firstSentence = joined.split(/\.\s/)[0] + '.';
    return `(${firstSentence.trim()})`;
  }
  return `(${t})`;
}

// ── Core segment renderers ────────────────────────────────────────────────────

/**
 * Render an alternatives block: each group's segments joined with \n,
 * groups separated by \n\nor\n\n. When opts.showLabel is true and the group
 * label is not a short Roman-numeral label, emit the label (+ CANTICLE_SOURCE
 * citation if available) as a header before the group text.
 */
function textAlternatives(groups, shared, opts = {}) {
  return groups
    .map(g => {
      const groupText = textFlatSegs(g.segments, shared, opts);
      if (!groupText) return '';
      let body = groupText;
      if (opts.alleluia) body += '\nAlleluia.';
      if (opts.showLabel && g.label && !SHORT_LABEL_RE.test(g.label)) {
        const cite = CANTICLE_SOURCE[g.label];
        const header = cite ? `${g.label} — ${cite}` : g.label;
        return `${header}\n\n${body}`;
      }
      return body;
    })
    .filter(Boolean)
    .join('\n\nor\n\n');
}

/**
 * Render an array (or single object) of segments as plain text.
 *
 * Within a "paragraph" of consecutive leader/response segments, lines are
 * joined with \n (no blank lines). Rubrics and alternatives blocks flush the
 * current paragraph and become their own blocks, with \n\n between blocks.
 * Skipped rubrics (empty string) do NOT flush the paragraph or create gaps.
 */
function textFlatSegs(segs, shared, opts = {}) {
  if (!segs) return '';
  const blocks = [];
  let para = [];

  function flush() {
    if (para.length) { blocks.push(para.join('\n')); para = []; }
  }

  function proc(seg) {
    if (seg.type === 'shared') {
      const resolved = shared[seg.key];
      if (!resolved) return;
      if (Array.isArray(resolved)) { resolved.forEach(proc); return; }
      proc(resolved);
      return;
    }
    if (seg.type === 'label') {
      // Plain titled heading — no parentheses, emitted as its own block.
      const text = (seg.text || '').trim();
      if (text) { flush(); blocks.push(text); }
    } else if (seg.type === 'rubric') {
      const text = textRubric(seg, opts);
      if (text) { flush(); blocks.push(text); }
      // skipped rubric: do NOT flush — keeps adjacent leader/response together
    } else if (seg.type === 'alternatives') {
      const text = textAlternatives(seg.groups, shared, opts);
      if (text) { flush(); blocks.push(text); }
    } else {
      // leader or response: accumulate into current paragraph
      let text = (seg.text || '').trimEnd();
      if (opts.joinLines) text = text.replace(/\n/g, ' ');
      if (text) para.push(text);
    }
  }

  if (!Array.isArray(segs)) { proc(segs); } else { segs.forEach(proc); }
  flush();
  return blocks.join('\n\n');
}

// ── Psalm renderer ────────────────────────────────────────────────────────────

function renderPsalm(citation) {
  const raw = typeof citation === 'object' ? citation.citation : String(citation);
  const num = raw.replace(/[^0-9].*/, '');
  const ps  = psalter[num];
  if (!ps) return `[Psalm ${raw}: not found in psalter]`;
  const title  = ps.title ? `Psalm ${ps.number} — ${ps.title}` : `Psalm ${ps.number}`;
  const verses = ps.text.split('\n')
    .map(l => l.replace(/^\d+\s/, '').trimStart())
    .join('\n')
    .trimEnd();
  return `${title}\n\n${verses}`;
}

// ── Reading renderer ──────────────────────────────────────────────────────────

const READING_RUBRIC =
  '(A Reading from the Daily Office Lectionary, the Weekday Eucharistic ' +
  'Lectionary, or the Revised Common Lectionary Daily Readings is read. ' +
  'After a period of silent reflection one of the following is said.)';

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

function renderLesson(lesson, form, shared) {
  let rr = form.reading_response;
  if (rr?.type === 'shared') rr = shared[rr.key];
  const rrText = rr ? textFlatSegs([rr], shared) : '';
  return ['The Reading', READING_RUBRIC, `[Reading: ${citationStr(lesson)}]`, rrText]
    .filter(Boolean).join('\n\n');
}

// ── Build output ──────────────────────────────────────────────────────────────

const B = []; // output blocks, joined by \n\n

// ── The Gathering of the Community ───────────────────────────────────────────
B.push('The Gathering of the Community');
B.push('Introductory Responses');
// EP opening doxology: append Alleluia after each alternative (BAS EP Sunday rubric).
// Render pre-doxology segs first, then doxology separately with alleluia flag.
if (officeType === 'ep' && shared.doxology) {
  const preDoxa = (form.opening_responses || []).filter(
    s => !(s.type === 'shared' && s.key === 'doxology')
  );
  B.push(textFlatSegs(preDoxa, shared));
  B.push(textAlternatives(shared.doxology.groups, shared, { alleluia: true }));
} else {
  B.push(textFlatSegs(form.opening_responses, shared));
}

// Phos Hilaron / Thanksgiving for Light
const phosSegs = form.phos_hilaron || form.thanksgiving_for_light;
if (phosSegs) {
  B.push(textFlatSegs(phosSegs, shared));
}

// ── The Proclamation of the Word ─────────────────────────────────────────────
B.push('The Proclamation of the Word');
B.push('The Psalm');
B.push('(A Psalm from the Daily Office Lectionary, the Weekday Eucharistic Lectionary, or the Revised Common Lectionary Daily Readings is said or sung.)');

const psalms = officeData?.psalms || [];
for (const psalm of psalms) {
  B.push(renderPsalm(psalm));
}
if (psalms.length && shared.doxology) {
  B.push('(After the Psalm one of the following may be said or sung.)');
  B.push(textAlternatives(shared.doxology.groups, shared, {}));
}

const lessons = officeData?.lessons || [];
if (lessons[0]) B.push(renderLesson(lessons[0], form, shared));

B.push('The Responsory');
B.push(textFlatSegs(form.responsory, shared));

if (lessons[1]) B.push(renderLesson(lessons[1], form, shared));

B.push('The Canticle');
// DATA GAP: canticle intro rubric (naming the three canticles) not in form data.
B.push(textFlatSegs(form.canticle, shared, { showLabel: true }));

// ── Affirmation of Faith ──────────────────────────────────────────────────────
B.push('Affirmation of Faith');
// DATA GAP: "(One of the following Affirmations of Faith may be said or sung.)"
// rubric is not in shared.affirmation data.
B.push(textFlatSegs(form.affirmation, shared, { showLabel: true }));

// ── The Prayers of the Community ─────────────────────────────────────────────
B.push('The Prayers of the Community');
B.push('Intercessions and Thanksgivings');
B.push(textFlatSegs(form.intercessions, shared));

B.push('The Litany');
// "The Litany is said or sung." rubric is suppressed by BOOK_SKIP_RUBRICS.
B.push(textFlatSegs(form.litany, shared));

B.push('The Collect');
B.push(`[Collect of the Day: ${dateStr}]`);
B.push(textFlatSegs(form.seasonal_collects, shared, { skipCollectRubric: true, joinLines: true }));

// ── The Sending Forth of the Community ───────────────────────────────────────
B.push('The Sending Forth of the Community');
B.push("The Lord's Prayer");
B.push(textFlatSegs(form.lords_prayer_intro, shared));

B.push('The Dismissal');
B.push(textFlatSegs(form.dismissal, shared));

process.stdout.write(B.filter(Boolean).join('\n\n') + '\n');
