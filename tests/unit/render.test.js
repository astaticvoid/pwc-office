import { describe, test, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import {
  formKey, officeFormSeason, renderSegments, renderSubsection, lessonHtml, filterSeasonalCollects,
  lessonsPickText, lessonsPickRubricHtml
} from '../../web/render.js';

const offices = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/offices.json'), 'utf8'));
const bounds  = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/season_bounds.json'), 'utf8'));
const shared  = offices._shared || {};
const forms   = Object.entries(offices).filter(([k]) => !k.startsWith('_'));

// ── Form selection ───────────────────────────────────────────────────────────────

describe('formKey', () => {
  test.each([
    ['OrdinaryTime', 'mp', 0, 'ordinary-sunday-mp'],
    ['OrdinaryTime', 'mp', 3, 'ordinary-wednesday-mp'],
    ['OrdinaryTime', 'ep', 5, 'ordinary-friday-ep'],
    ['Advent',       'mp', 3, 'advent-mp'],
    ['Easter',       'ep', 6, 'easter-ep'],
  ])('%s %s weekday=%i → %s', (season, type, day, expected) => {
    expect(formKey(season, type, day)).toBe(expected);
  });
});

describe('officeFormSeason', () => {
  test.each([
    ['2026-06-17', 'OrdinaryTime'],
    ['2025-12-03', 'Advent'],
    ['2025-12-25', 'Christmas'],
    ['2026-04-08', 'Easter'],
    ['2026-02-25', 'Lent'],
    ['2026-03-25', 'Passiontide'],
    ['2026-05-20', 'Pentecost'],
    ['2026-11-04', 'AllSaints'],
  ])('%s → %s', (date, expected) => {
    expect(officeFormSeason(date, bounds)).toBe(expected);
  });
});

// ── Form completeness (data-layer, duplicates pytest but faster) ─────────────

describe('all forms have required sections as arrays', () => {
  test.each(forms)('%s', (name, form) => {
    // lords_prayer_intro and dismissal must always be inline arrays (BUG-19 guard)
    for (const field of ['lords_prayer_intro', 'dismissal']) {
      expect(Array.isArray(form[field]), `${name}.${field} must be array`).toBe(true);
      expect(form[field].length, `${name}.${field} must be non-empty`).toBeGreaterThan(0);
    }
    // opening_responses may be an inline array OR a valid shared ref (BUG-14: EP seasonal forms)
    const or = form.opening_responses;
    const isInlineArray = Array.isArray(or) && or.length > 0;
    const isSharedRef = or?.type === 'shared' && shared[or.key] != null;
    expect(isInlineArray || isSharedRef, `${name}.opening_responses must be array or valid shared ref`).toBe(true);
    expect(form.reading_response, `${name} missing reading_response`).toBeTruthy();
  });
});

// ── Rendering ────────────────────────────────────────────────────────────────────

describe('renderSegments', () => {
  test('renders leader and response', () => {
    const segs = [
      { type: 'leader',   text: 'Lord, open our lips,' },
      { type: 'response', text: 'and our mouth shall proclaim your praise.' },
    ];
    const html = renderSegments(segs, shared);
    expect(html).toContain('Lord, open our lips');
    expect(html).toContain('and our mouth shall proclaim');
  });

  test('resolves shared ref', () => {
    const segs = [{ type: 'shared', key: 'doxology' }];
    const html = renderSegments(segs, shared);
    expect(html).toContain('alt-tabs'); // doxology is an alternatives block
  });
});

describe('lessonHtml', () => {
  test('reading response renders for ordinary-time form', () => {
    const form = offices['ordinary-wednesday-mp'];
    const html = lessonHtml('Genesis 1:1-5', shared, form);
    expect(html).toContain('alt-tabs'); // response tabs present
    expect(html).toContain('The word of the Lord');
  });

  test('reading response renders for seasonal form', () => {
    const form = offices['lent-mp'];
    const html = lessonHtml('Isaiah 55:1-9', shared, form);
    expect(html).toContain('alt-tabs');
  });

  test("Lord's Prayer present in ordinary-time form", () => {
    const form = offices['ordinary-wednesday-mp'];
    const lpHtml = renderSegments(form.lords_prayer_intro, shared);
    expect(lpHtml).toContain('Our Father in heaven');
  });
});

// ── lessons_pick rubric (BUG-28) ──────────────────────────────────────────────
describe('lessonsPick', () => {
  test('2 of 3 renders the load-bearing rubric', () => {
    expect(lessonsPickText(2, 3)).toBe('Two of the following three readings are read.');
    expect(lessonsPickRubricHtml(2, 3)).toBe(
      '<p class="seg-rubric">Two of the following three readings are read.</p>');
  });

  test('rubric is not book-only (must show in the interactive app)', () => {
    expect(lessonsPickRubricHtml(2, 3)).not.toContain('rubric-book-only');
  });

  test('no rubric when pick >= total or pick is falsy', () => {
    expect(lessonsPickText(3, 3)).toBe('');
    expect(lessonsPickText(0, 3)).toBe('');
    expect(lessonsPickRubricHtml(undefined, 3)).toBe('');
  });
});

// ── placeholder N italics (BUG-30) ────────────────────────────────────────────
describe('placeholder N', () => {
  test('leader "May N our bishop" renders italic N', () => {
    const html = renderSegments([{ type: 'leader', text: 'May N our bishop and all bishops' }], shared);
    expect(html).toContain('May <em>N</em> our bishop');
  });

  test('does not italicise N inside a word', () => {
    const html = renderSegments([{ type: 'leader', text: 'Nations and peoples' }], shared);
    expect(html).not.toContain('<em>N</em>');
  });
});

// ── Shared-ref render coverage ────────────────────────────────────────────────

describe('all forms: shared-ref fields render non-empty HTML', () => {
  test.each(forms)('%s opening_responses', (name, form) => {
    let or = form.opening_responses;
    if (or?.type === 'shared') or = shared[or.key];
    const html = renderSubsection('Introductory Responses', or, shared);
    expect(html, `${name} opening_responses rendered empty`).toBeTruthy();
  });

  test.each(forms)('%s reading_response', (name, form) => {
    let rr = form.reading_response;
    if (rr?.type === 'shared') rr = shared[rr.key];
    expect(Array.isArray(rr) ? rr.length : rr?.groups?.length,
      `${name} reading_response resolves to empty`).toBeGreaterThan(0);
  });
});

// ── Verse rendering ────────────────────────────────────────────────────────────

describe('verse rendering preserves leader line breaks', () => {
  const segs = [
    { type: 'leader', text: 'Blessed are you, Sovereign God,\ncreator of light and darkness,\nto you be glory and praise for ever.' },
    { type: 'response', text: 'To you be glory and praise for ever.' },
  ];

  test('leader has <br> in verse mode', () => {
    const html = renderSegments(segs, shared, true);
    expect(html).toContain('Sovereign God,<br>creator');
  });

  test('leader has no <br> in prose mode (default)', () => {
    const html = renderSegments(segs, shared);
    expect(html).not.toContain('<br>');
  });

  test('prose leader collapses newline to space', () => {
    const html = renderSegments(segs, shared, false);
    expect(html).not.toContain('<br>');
    expect(html).toContain('Sovereign God,\ncreator');
  });

  test('verse leader with Amen splits Amen to response', () => {
    const amenSegs = [
      { type: 'leader', text: 'May God, who has called us out of darkness into the marvellous light\nof Christ,\nbless us and fill us with peace. Amen.' },
    ];
    const html = renderSegments(amenSegs, shared, true);
    expect(html).toContain('light<br>of Christ');
    expect(html).toContain('seg-response');
    expect(html).toContain('Amen.');
  });
});
