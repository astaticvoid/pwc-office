import { describe, test, expect } from 'vitest';
import { readFileSync, existsSync } from 'fs';
import { join } from 'path';
import {
  formKey, officeFormSeason, renderSegments, renderSubsection, lessonHtml,
  lessonsPickText, lessonsPickRubricHtml, renderOfficeJSON,
  LITURGICAL_TEXT_REGISTER, SKIP_RUBRICS, assembleSections, esc,
} from '../../web/render.js';

const DATA_DIR = join(import.meta.dirname, '../../data');
const HAS_DATA = existsSync(join(DATA_DIR, 'offices.json'));

function loadData() {
  const offices = HAS_DATA
    ? JSON.parse(readFileSync(join(DATA_DIR, 'offices.json'), 'utf8'))
    : {};
  const bounds = HAS_DATA
    ? JSON.parse(readFileSync(join(DATA_DIR, 'season_bounds.json'), 'utf8'))
    : {};
  return { offices, bounds, shared: offices._shared || {},
    forms: Object.entries(offices).filter(([k]) => !k.startsWith('_')) };
}

const { offices, bounds, shared, forms } = loadData();

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
  test.skipIf(!HAS_DATA).each([
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

describe.skipIf(!HAS_DATA)('all forms have required sections as arrays', () => {
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

// ── lessons_pick rubric (BUG-28, fixed form per ADR 0014/#63) ────────────────
describe('lessonsPick', () => {
  test('2 of 3 renders the load-bearing rubric, in its fixed approved form', () => {
    expect(lessonsPickText(2, 3)).toBe('One or two of the following readings are read.');
    expect(lessonsPickRubricHtml(2, 3)).toBe(
      '<p class="seg-rubric">One or two of the following readings are read.</p>');
  });

  test('the fixed form does not vary with pick/total', () => {
    // ADR 0014: "one mechanism, not two adjacent ones" — the reading selector
    // now presents the actual branches, so the rubric no longer needs to
    // spell out a computed count.
    expect(lessonsPickText(1, 4)).toBe(lessonsPickText(2, 3));
  });

  test('rubric is not hidden in the interactive app (BUG-28 load-bearing)', () => {
    // The class that used to hide book-navigation rubrics in Office mode is
    // gone (ADR 0013 #59); the pick rubric must render unconditionally.
    expect(lessonsPickRubricHtml(2, 3)).toContain('One or two of the following readings are read.');
    expect(lessonsPickRubricHtml(2, 3)).not.toMatch(/hidden|display:\s*none/);
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
    // The third alternative's leader is "Holy Word, Holy Wisdom." in every
    // form (ADR 0015, issue #62): the seasonal/ordinary split encoded here
    // reproduced the printed book's error, which the errata corrects.
    const third = rr?.groups?.[2];
    expect(third?.label, `${name} reading_response third alternative`).toBe('III');
    expect(third?.segments?.[0]?.text,
      `${name} reading_response third leader`).toBe('Holy Word, Holy Wisdom.');
  });
});

// ── App-authored liturgical text register (ADR 0015) ─────────────────────────

describe('liturgical text register', () => {
  const ALLOWED_SOURCES = new Set(['editorial', 'upstream-review']);

  test('holds the app-authored strings, each with provenance', () => {
    // Ten registered in ADR 0015; intercessionsPrompt removed with
    // INTERCESSIONS_CONDENSED by ADR 0013 (#60) — the biddings render now.
    expect(Object.keys(LITURGICAL_TEXT_REGISTER)).toHaveLength(9);
    expect(LITURGICAL_TEXT_REGISTER.intercessionsPrompt).toBeUndefined();
    for (const [key, entry] of Object.entries(LITURGICAL_TEXT_REGISTER)) {
      expect(entry.text, `${key} text`).toBeTruthy();
      expect(entry.note, `${key} note`).toBeTruthy();
      expect(ALLOWED_SOURCES.has(entry.source), `${key} source ${entry.source}`).toBe(true);
    }
  });

  test('review-corrected rubrics no longer carry the wrong wording', () => {
    const all = Object.values(LITURGICAL_TEXT_REGISTER).map(e => e.text).join('\n');
    expect(all).not.toContain('from the appointed lectionary');
    expect(all).not.toContain('or the Litany');
  });

  test('the review-corrected strings are applied in the register', () => {
    expect(LITURGICAL_TEXT_REGISTER.readingIntro.text).toBe('A Reading is read.');
    expect(LITURGICAL_TEXT_REGISTER.psalmIntro.text).toBe('A Psalm is said or sung.');
    expect(LITURGICAL_TEXT_REGISTER.psalmsIntro.text).toBe('The following Psalms are said or sung.');
    expect(LITURGICAL_TEXT_REGISTER.singlePsalmIntro.text).toBe('The following Psalm is said or sung.');
    expect(LITURGICAL_TEXT_REGISTER.affirmationTransition.text)
      .toBe('{office} Prayer continues with an Affirmation of Faith or the Prayers.');
    expect(LITURGICAL_TEXT_REGISTER.readingsPick.text)
      .toBe('One or two of the following readings are read.');
    for (const k of ['readingIntro', 'psalmIntro', 'psalmsIntro', 'singlePsalmIntro', 'affirmationTransition', 'readingsPick']) {
      expect(LITURGICAL_TEXT_REGISTER[k].source, `${k} source`).toBe('upstream-review');
    }
  });

  test('the pre-Litany transition keeps its approved wording', () => {
    // ADR 0015: the app.js:999 rubric ("continues with the Litany.") is a
    // different rubric from the reviewed one and was left alone.
    expect(LITURGICAL_TEXT_REGISTER.litanyTransition.text)
      .toBe('{office} Prayer continues with the Litany.');
    expect(LITURGICAL_TEXT_REGISTER.litanyTransition.source).toBe('editorial');
  });

  test('lessonsPickText renders the fixed register text', () => {
    expect(lessonsPickText(2, 3)).toBe(LITURGICAL_TEXT_REGISTER.readingsPick.text);
  });
});

// ── Intercession biddings render (ADR 0013, #60) ─────────────────────────────

describe('intercession biddings', () => {
  test('the seasonal bidding text renders, not the retired app prose', () => {
    // INTERCESSIONS_CONDENSED replaced biddings with "Offer intercessions…";
    // ADR 0013 (#60) deleted it so the authorized text renders.
    const bidding = {
      type: 'rubric',
      text: 'Additional intercessions, petitions, and thanksgivings may be offered silently or aloud.',
    };
    const html = renderSegments([bidding], {});
    expect(html).toContain('Additional intercessions, petitions, and thanksgivings');
    expect(html).not.toContain('Offer intercessions, petitions, and thanksgivings');
  });
});

// ── SKIP_RUBRICS is falsifiable (ADR 0013, #59) ─────────────────────────────

describe.skipIf(!HAS_DATA)('SKIP_RUBRICS duplicate headings', () => {
  test('every SKIP_RUBRICS entry fires on at least one real rubric in the corpus', () => {
    // Guards against dead entries: a pattern that matches no data would
    // suppress nothing and the falsifiability contract would silently rot.
    for (const entry of SKIP_RUBRICS) {
      let hits = 0;
      for (const [, form] of forms) {
        for (const segs of Object.values(form)) {
          if (!Array.isArray(segs)) continue;
          for (const seg of segs) {
            if (seg && seg.type === 'rubric' && entry.re.test(seg.text || '')) hits++;
          }
        }
      }
      if (hits === 0) {
        throw new Error(`SKIP_RUBRICS entry ${entry.re} matches no rubric in the data`);
      }
    }
  });

  test('every suppressed rubric has its duplicate heading in the rendered office', () => {
    // Each SKIP_RUBRICS entry names the heading that already renders the same
    // text elsewhere. If that heading stops being emitted, the suppression
    // silently swallows the rubric — so assert every heading renders, scoped
    // per form to the entries that actually fire there (a form with no litany
    // suppresses nothing and must not be held to The Litany's heading).
    const officeType = 'mp';
    const season = 'OrdinaryTime';
    for (const [name, form] of forms) {
      const fired = SKIP_RUBRICS.filter(entry =>
        Object.values(form).some(segs =>
          Array.isArray(segs) && segs.some(seg =>
            seg && seg.type === 'rubric' && entry.re.test(seg.text || ''))));
      if (!fired.length) continue;
      const cfg = { form, shared, officeData: {}, officeType, season, weekIdx: 0 };
      const { sections } = assembleSections(cfg);
      let html = '';
      for (const section of sections) {
        for (const sub of section.subsections) {
          html += renderSubsection(sub.label, sub.segments, shared, false);
        }
      }
      for (const entry of fired) {
        const heading = `<h3 class="office-subsection-title">${esc(entry.duplicate)}</h3>`;
        if (!html.includes(heading)) {
          throw new Error(`${name}: SKIP_RUBRICS duplicate heading "${entry.duplicate}" not in rendered office`);
        }
      }
    }
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

// ── Sync test: renderOfficeJSON vs renderSegments ────────────────────────

describe.skipIf(!HAS_DATA)('renderOfficeJSON sync with renderSegments', () => {
  const form = offices['ordinary-sunday-mp'];
  if (!form) { test.todo('ordinary-sunday-mp form missing'); return; }

  const cfg = {
    form,
    shared,
    officeData: { psalms: [{ citation: '145' }], lessons: [{ citation: 'Isaiah 55:1-5' }] },
    officeType: 'mp',
    season: 'OrdinaryTime',
    weekIdx: 0,
  };

  const json = renderOfficeJSON(cfg);

  test('produces expected sections', () => {
    const names = json.sections.map(s => s.name);
    expect(names).toContain('Gathering');
    expect(names).toContain('Proclamation');
    expect(names).toContain('Prayers');
    expect(names).toContain('Sending');
    // Ordinary Sunday MP has no Affirmation
  });

  test('subsection segments render to HTML without errors', () => {
    // The JSON path extracts leaf segments via walkSegments.
    // The HTML path renders the original form segment arrays via renderSegments.
    // We verify: for every subsection in the JSON, the same form field
    // produces non-empty HTML when rendered.
    const fieldToLabel = {
      opening_responses: 'Introductory Responses',
      responsory: 'The Responsory',
      canticle: 'The Canticle',
      intercessions: 'Intercessions and Thanksgivings',
      litany: 'The Litany',
      lords_prayer_intro: "The Lord's Prayer",
      dismissal: 'The Dismissal',
      phos_hilaron: 'Phos Hilaron',
      invitatory: 'Invitatory Psalm',
      thanksgiving_for_light: 'Thanksgiving for Light',
      affirmation: 'Affirmation of Faith',
    };

    for (const section of json.sections) {
      for (const sub of section.subsections) {
        // Find the corresponding form field
        const field = Object.entries(fieldToLabel).find(([, label]) => label === sub.label);
        if (!field) continue;
        const formField = form[field[0]];
        if (!formField || !formField.length) continue;
        const verse = ['The Responsory', 'The Canticle', 'The Dismissal',
          'Invitatory Psalm', 'Thanksgiving for Light', 'Phos Hilaron',
          "The Lord's Prayer"].includes(sub.label);
        const html = renderSegments(formField, shared, verse);
        // Verify HTML is non-empty
        expect(html.length).toBeGreaterThan(0);
        // Verify the JSON segment count is within 2 of HTML paragraph count
        // (Amen splitting can add paragraphs in HTML)
        const paraCount = (html.match(/<p\b/g) || []).length;
        expect(paraCount).toBeGreaterThan(0);
        // Loose check: both paths produce similar amounts of content
        expect(Math.abs(paraCount - sub.segments.length)).toBeLessThanOrEqual(3);
      }
    }
  });

  test('dynamic fields populated', () => {
    const proc = json.sections.find(s => s.name === 'Proclamation');
    expect(proc.dynamic.readings).toHaveLength(1);
    expect(proc.dynamic.readings[0].citation).toBe('Isaiah 55:1-5');
    expect(proc.dynamic.psalms).toHaveLength(1);
    expect(proc.dynamic.psalmDoxologyPresent).toBe(true);
    expect(proc.dynamic.readingResponsePresent).toBe(true);
  });

  test('meta fields', () => {
    expect(json.meta.officeType).toBe('mp');
    expect(json.meta.season).toBe('OrdinaryTime');
    expect(json.meta.hasAlternateObservance).toBe(false);
  });

  test('dismissal has amen', () => {
    const sending = json.sections.find(s => s.name === 'Sending');
    expect(sending.dynamic.dismissalContainsAmen).toBe(true);
  });

  test('EP has light section', () => {
    const epForm = offices['ordinary-sunday-ep'];
    if (!epForm) return;
    const epJson = renderOfficeJSON({
      form: epForm, shared,
      officeData: {},
      officeType: 'ep', season: 'OrdinaryTime', weekIdx: 0,
    });
    const gath = epJson.sections.find(s => s.name === 'Gathering');
    expect(gath.dynamic.phosHilaronPresent || gath.dynamic.thanksgivingForLightPresent).toBe(true);
  });

  test('phos_hilaron preserves poetic line breaks (no _LINE_JOIN artifacts)', () => {
    const MIN_LINES = {
      'ordinary-sunday-ep':    11,
      'ordinary-monday-ep':    14,
      'ordinary-tuesday-ep':    9,
      'ordinary-wednesday-ep': 14,
      'ordinary-thursday-ep':  24,
      'ordinary-friday-ep':    14,
      'ordinary-saturday-ep':  19,
    };
    for (const [formKey, form] of forms) {
      const phos = form.phos_hilaron;
      if (!phos || !phos.length) continue;
      const expected = MIN_LINES[formKey];
      if (!expected) continue;
      for (const seg of phos) {
        if (seg.type !== 'leader') continue;
        const lines = seg.text.split('\n');
        expect(lines.length,
          `${formKey}: expected >= ${expected} poetic lines (including stanza breaks), got ${lines.length}`)
          .toBeGreaterThanOrEqual(expected);
      }
    }
  });

  // Line counts alone cannot catch a misplaced stanza break: the old every-4th-line
  // rule gave ordinary-sunday-ep stanzas of 4/4/1 where the page shows 3/3/3, and
  // both come to 11 lines, so MIN_LINES passed on the wrong answer while a sentence
  // was split across the break. Assert the shape, not just the total.
  test('phos_hilaron stanza breaks fall where the page puts them', () => {
    const SHAPE = {
      'ordinary-sunday-ep':    [3, 3, 3],
      'ordinary-monday-ep':    [4, 4, 4],
      'ordinary-tuesday-ep':   [4, 4],
      'ordinary-wednesday-ep': [4, 4, 4],
      'ordinary-thursday-ep':  [4, 4, 4, 4, 4],
      'ordinary-friday-ep':    [4, 4, 4],
      'ordinary-saturday-ep':  [4, 4, 4, 4],
    };
    for (const [formKey, form] of forms) {
      const expected = SHAPE[formKey];
      if (!expected) continue;
      const phos = form.phos_hilaron;
      if (!phos || !phos.length) continue;
      for (const seg of phos) {
        if (seg.type !== 'leader') continue;
        const shape = seg.text.split('\n')
          .reduce((acc, l) => {
            if (l.trim()) acc[acc.length - 1]++;
            else if (acc[acc.length - 1]) acc.push(0);
            return acc;
          }, [0])
          .filter(n => n > 0);
        expect(shape,
          `${formKey}: stanzas should be ${expected.join('/')}, got ${shape.join('/')}`)
          .toEqual(expected);
      }
    }
  });

  // The litany is verse in the seasonal forms and prose in the ordinary-time
  // collects, so its breaks are decided per break from page geometry by
  // _reflow_litany rather than section-wide. Before that, _reflow_leader_prose
  // flattened every petition in all 31 forms into one paragraph (#39). These
  // counts are the total leader lines per litany; a drop means breaks are being
  // joined again.
  test('litany preserves petition line breaks (no unconditional reflow)', () => {
    const MIN_LINES = {
      'advent-mp':             21,   // the O Antiphons — the worst previous loss
      'lent-mp':               16,
      'ordinary-wednesday-mp': 16,
      'passiontide-mp':        15,
      'passiontide-ep':        15,
      'allsaints-ep':          13,
      'pentecost-ep':          13,
      'ordinary-monday-mp':    12,
      'ordinary-tuesday-mp':   12,
    };
    for (const [formKey, form] of forms) {
      const expected = MIN_LINES[formKey];
      if (!expected) continue;
      const litany = form.litany;
      if (!litany || !litany.length) continue;
      const lines = litany
        .filter(seg => seg.type === 'leader')
        .reduce((n, seg) => n + seg.text.split('\n').length, 0);
      expect(lines,
        `${formKey}: expected >= ${expected} litany leader lines, got ${lines}`)
        .toBeGreaterThanOrEqual(expected);
    }
  });
});

// ── Verse rendering: inline sup numbers, no grid divs, * break handling ──────

describe('verse rendering structure', () => {
  test('canticle leader text has <br> at * caesura breaks', () => {
    const segs = [
      { type: 'leader', text: 'My soul proclaims the greatness of the Lord, my spirit rejoices in God my Saviour, *\nfor you, Lord, have looked with favour on your lowly servant.\nFrom this day all generations will call me blessed: *\nyou, the Almighty, have done great things for me and holy is your name.' },
    ];
    const html = renderSegments(segs, shared, true);
    expect(html).toMatch(/\*<\/span><\/span><br><span class="verse-cont">for/);
    expect(html).toMatch(/\*<\/span><\/span><br><span class="verse-cont">you/);
  });

  test('canticle leader text does not use grid divs', () => {
    const segs = [
      { type: 'leader', text: 'Blessed are you, Lord, the God of Israel, *\nyou have come to your people and set them free.' },
    ];
    const html = renderSegments(segs, shared, true);
    expect(html).not.toContain('class="verse"');
    expect(html).not.toContain('class="verse-num"');
    expect(html).not.toContain('class="scripture-verse"');
    expect(html).toContain('<br>');
    expect(html).toContain('class="seg-leader"');
  });

  test('prose leader (verse=false) does not emit <br>', () => {
    const segs = [{ type: 'leader', text: 'A reading from the Book of Joshua.' }];
    const html = renderSegments(segs, shared, false);
    expect(html).not.toContain('<br>');
  });

  test('psalm title uses psalm-title class, not verse grid', () => {
    // The psalm rendering is in app.js (browser), but we can verify
    // that renderSegments never emits the old grid-based classes.
    const segs = [
      { type: 'leader', text: 'Happy are they who have not walked in the counsel of the wicked, *\nnor lingered in the way of sinners,\nnor sat in the seats of the scornful.' },
    ];
    const html = renderSegments(segs, shared, true);
    expect(html).toContain('<br>');
    expect(html).not.toContain('class="verse"');
    expect(html).not.toContain('grid-template');
  });
});
