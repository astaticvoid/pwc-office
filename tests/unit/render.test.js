import { describe, test, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'fs';
import { join } from 'path';
import {
  formKey, officeFormSeason, renderSegments, renderSubsection, lessonHtml,
  lessonsPickText, lessonsPickRubricHtml, renderOfficeJSON,
  LITURGICAL_TEXT_REGISTER, SKIP_RUBRICS, assembleSections, esc,
  formatLiturgicalText, formatProseText, splitPsalmRubrics, splitReadingRubrics,
  parseCitation, expandCitationForDisplay, SINGLE_CHAPTER_BOOKS,
  collectCommemorations, lookupFatsEntry, fatsCandidates,
} from '../../web/render.js';

const DATA_DIR = join(import.meta.dirname, '../../data');
const HAS_DATA = existsSync(join(DATA_DIR, 'offices.json'));
const LECT_DIR = join(DATA_DIR, 'lectionary');
const HAS_LECTIONARY = existsSync(LECT_DIR);

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
    // ADR 0014: "one mechanism, not two adjacent ones" — the selector presents
    // the actual branches, so the rubric announces the choice without spelling
    // out a count.
    expect(lessonsPickText(1, 4)).toBe(lessonsPickText(2, 3));
  });

  test('rubric is not hidden in the interactive app (BUG-28 load-bearing)', () => {
    // The pick rubric renders unconditionally: it is load-bearing in the
    // interactive app, not book-only chrome (ADR 0013/#59).
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
    // Ten registered in ADR 0015. intercessionsPrompt went with
    // INTERCESSIONS_CONDENSED under ADR 0013 (#60); the other eight went with
    // #84, which recovered the printed rubrics the running-header filter had
    // been swallowing — each held book text the app could not see it had. One
    // entry is left, the only one with no printed sentence behind it.
    expect(Object.keys(LITURGICAL_TEXT_REGISTER)).toHaveLength(1);
    for (const retired of ['intercessionsPrompt', 'readingIntro', 'reflectionPrompt',
                           'psalmEnd', 'litanyTransition', 'psalmIntro', 'psalmsIntro',
                           'singlePsalmIntro', 'affirmationTransition']) {
      expect(LITURGICAL_TEXT_REGISTER[retired], retired).toBeUndefined();
    }
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

  test('the settled readings reach the data, not a second string beside it', () => {
    expect(LITURGICAL_TEXT_REGISTER.readingsPick.text)
      .toBe('One or two of the following readings are read.');
    expect(LITURGICAL_TEXT_REGISTER.readingsPick.source).toBe('upstream-review');

    // ADR 0019 items 3, 4 and 6 now reach the page as `adr0019-*` corrections
    // on the extracted rubric, so this asserts the shipped data rather than a
    // register entry: the introductions say the settled sentence once, in
    // every form, and the named lectionaries the page prints are gone from the
    // rubric blocks. Before #88 both wordings rendered, a few lines apart.
    if (!HAS_DATA) return;
    let psalmIntros = 0, readingIntros = 0;
    for (const [key, form] of forms) {
      const texts = f => (form[f] || []).map(s => s.text || '').join('\n');
      const psalm = texts('psalm_rubrics'), reading = texts('reading_rubrics');
      expect(psalm, `${key}.psalm_rubrics`).not.toContain('Daily Office Lectionary');
      expect(reading, `${key}.reading_rubrics`).not.toContain('Daily Office Lectionary');
      if (psalm.includes('A Psalm is said or sung.')) psalmIntros++;
      if (reading.includes('A Reading is read.')) readingIntros++;
      // Item 4, on the canticle's closing rubric.
      expect(texts('canticle'), `${key}.canticle`)
        .not.toContain('an Affirmation of Faith or the Litany.');
    }
    expect(psalmIntros).toBe(30);
    expect(readingIntros).toBe(30);
  });

  test('the office transitions come from the data, worded per office', () => {
    // Retired from the register by #84. ADR 0015 left litanyTransition alone
    // and flagged it for confirmation; the book turns out to print it, so it
    // is extracted, and emitting it from the register too printed it twice
    // verbatim. psalmEnd's note claimed it matched the printed rubric — the
    // extracted text shows it did not, for 16 of the 30 forms.
    expect(LITURGICAL_TEXT_REGISTER.litanyTransition).toBeUndefined();
    expect(LITURGICAL_TEXT_REGISTER.psalmEnd).toBeUndefined();

    // Each form must carry its OWN transition. These rubrics are printed at
    // the foot of an alternatives block, so _group_alternatives sweeps them
    // inside it and _dedup_shared — which keys the doxology and affirmation
    // blocks by shape, not equality — would hand all 30 forms whichever copy
    // it met first, giving every Evening Prayer form "Morning Prayer continues
    // with the Litany." _hoist_office_transition lifts them back out.
    if (!HAS_DATA) return;
    let checked = 0;
    for (const [key, form] of forms) {
      const office = key.endsWith('-ep') ? 'Evening' : 'Morning';
      for (const field of ['responsory', 'canticle', 'affirmation']) {
        const segs = form[field];
        if (!Array.isArray(segs) || !segs.length) continue;
        const last = segs[segs.length - 1];
        if (last.type !== 'rubric' || !/ Prayer continues with /.test(last.text)) continue;
        expect(last.text, `${key}.${field}`).toMatch(new RegExp(`^${office} Prayer continues with `));
        checked++;
      }
    }
    expect(checked).toBe(90);
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

  test('verse mode emits one block per line', () => {
    const html = renderSegments(segs, shared, true);
    // Each line is its own block so it can carry a hanging indent; a wrapped
    // full verse must not land at the half-verse offset and imitate one.
    expect(html).toContain('<span class="verse-line">Blessed are you, Sovereign God,</span>');
    expect(html).toContain('<span class="verse-line">creator of light and darkness,</span>');
    expect(html).not.toContain('<br>');
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
    expect(html).toContain('marvellous light</span>');
    expect(html).toContain('<span class="verse-line">of Christ,</span>');
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

  // The shape is asserted, not just the total: a line count cannot catch a
  // misplaced break. Stanzas of 4/4/1 and the page's 3/3/3 both come to 11
  // lines, and one of them splits a sentence across the break.
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
  test('canticle leader text breaks to a verse-cont block at * caesura', () => {
    const segs = [
      { type: 'leader', text: 'My soul proclaims the greatness of the Lord, my spirit rejoices in God my Saviour, *\nfor you, Lord, have looked with favour on your lowly servant.\nFrom this day all generations will call me blessed: *\nyou, the Almighty, have done great things for me and holy is your name.' },
    ];
    const html = renderSegments(segs, shared, true);
    // …*</span></span> closes the midpoint spans, </span> closes the verse-line
    expect(html).toMatch(/\*<\/span><\/span><\/span><span class="verse-cont">for/);
    expect(html).toMatch(/\*<\/span><\/span><\/span><span class="verse-cont">you/);
  });

  test('canticle leader text does not use grid divs', () => {
    const segs = [
      { type: 'leader', text: 'Blessed are you, Lord, the God of Israel, *\nyou have come to your people and set them free.' },
    ];
    const html = renderSegments(segs, shared, true);
    expect(html).not.toContain('class="verse"');
    expect(html).not.toContain('class="verse-num"');
    expect(html).not.toContain('class="scripture-verse"');
    expect(html).toContain('class="verse-line"');
    expect(html).toContain('class="seg-leader"');
  });

  // bindMidpoints runs over already-built HTML. A \S+ word class backtracks past
  // a tag's '>' into its attributes when the starred word is first in its
  // element, splicing markup into the page as visible text (it rendered as
  // `class="verse-line">Hallelujah! *`). One word before the * is the trigger.
  test('a one-word starred first line does not splice markup into the text', () => {
    const segs = [{ type: 'leader', text: 'Hallelujah! *\nPraise the Lord, O my soul!' }];
    const html = renderSegments(segs, shared, true);
    expect(html).not.toMatch(/<span\s+<span/);
    // no tag fragment survives as text content
    expect(html.replace(/<[^>]*>/g, '')).not.toContain('class=');
    expect(html).toContain('<span class="midpoint">*</span>');
  });

  test('formatLiturgicalText places a prefix inside the first line block', () => {
    // The psalm verse number must share a line with the text it numbers; the
    // lines are block boxes, so a prefix outside them lands on its own line.
    const out = formatLiturgicalText('Hallelujah! *\nPraise the Lord.', '<sup>1 </sup>');
    expect(out.startsWith('<span class="verse-line"><sup>1 </sup>Hallelujah!')).toBe(true);
    expect(out).not.toContain('</sup><span');
  });

  test('prose leader (verse=false) does not emit <br>', () => {
    const segs = [{ type: 'leader', text: 'A reading from the Book of Joshua.' }];
    const html = renderSegments(segs, shared, false);
    expect(html).not.toContain('<br>');
  });

  test('psalm title uses psalm-title class, not verse grid', () => {
    // The psalm rendering is in app.js (browser); what is checkable here is
    // that renderSegments emits the psalm-title class and no verse grid.
    const segs = [
      { type: 'leader', text: 'Happy are they who have not walked in the counsel of the wicked, *\nnor lingered in the way of sinners,\nnor sat in the seats of the scornful.' },
    ];
    const html = renderSegments(segs, shared, true);
    expect(html).toContain('class="verse-line"');
    expect(html).not.toContain('class="verse"');
    expect(html).not.toContain('grid-template');
  });
});


// ── Stanza breaks (#119) ─────────────────────────────────────────────────────

describe('stanza breaks', () => {
  test('a blank line becomes a break element, not an empty line block', () => {
    // An empty verse-line generates no line box, so the break the data carries
    // would render at zero height.
    const out = formatLiturgicalText('creator of heaven and earth.\n\nI believe in Jesus Christ,');
    expect(out).toContain('<span class="stanza-break"></span>');
    expect(out).not.toContain('<span class="verse-line"></span>');
  });

  test('a run of blank lines opens one gap, not several', () => {
    const out = formatLiturgicalText('first\n\n\n\nsecond');
    expect(out.match(/stanza-break/g)).toHaveLength(1);
  });

  test('blank lines at either end carry no gap', () => {
    const out = formatLiturgicalText('\n\nfirst\nsecond\n\n');
    expect(out).not.toContain('stanza-break');
    expect(out.startsWith('<span class="verse-line">first</span>')).toBe(true);
  });

  test('a prefix stays on the first real line when the text opens blank', () => {
    const out = formatLiturgicalText('\nHallelujah!\nPraise the Lord.', '<sup>1 </sup>');
    expect(out.startsWith('<span class="verse-line"><sup>1 </sup>Hallelujah!')).toBe(true);
  });

  test('the line after a break is a full verse, not a caesura continuation', () => {
    // A * on the line before the break pairs with nothing across it.
    const out = formatLiturgicalText('you have come to your people, *\n\nBlessed be the Lord.');
    expect(out).toContain('<span class="verse-line">Blessed be the Lord.</span>');
    expect(out).not.toContain('verse-cont');
  });

  test('a text that is one line once the blanks go is not wrapped in a block', () => {
    expect(formatLiturgicalText('Let us pray.\n\n')).toBe('Let us pray.');
  });

  test('a prose said text breaks with the same element as a verse one (#121)', () => {
    // The prose path keeps its line breaks through pre-wrap, so the blank line
    // already rendered — at a line box rather than the stanza token.
    const text = 'Let us pray to the Creator of the universe.\n\nHoly One,\nhear our prayer.';
    const html = renderSegments([{ type: 'leader', text }], shared, false);
    expect(html).toContain('universe.<span class="stanza-break"></span>Holy One,\nhear');
  });

  test('prose keeps single newlines for pre-wrap and eats the blank ones', () => {
    const out = formatProseText('one\ntwo\n\nthree');
    expect(out).toBe('one\ntwo<span class="stanza-break"></span>three');
  });

  test('prose escapes its text', () => {
    expect(formatProseText('a & b\n\n<c>')).toBe('a &amp; b<span class="stanza-break"></span>&lt;c&gt;');
  });

  test('both paths break the same text in the same places', () => {
    const text = 'first line\n\nsecond stanza\nits second line\n\nthird';
    const count = h => (h.match(/stanza-break/g) || []).length;
    expect(count(formatProseText(text))).toBe(count(formatLiturgicalText(text)));
  });

  test('the Creed renders its three articles with two breaks', () => {
    const segs = [{ type: 'response', text: 'I believe in God, the Father almighty,\ncreator of heaven and earth.\n\nI believe in Jesus Christ, God’s only Son, our Lord,\nand he will come again to judge the living and the dead.\n\nI believe in the Holy Spirit,\nand the life everlasting. Amen.' }];
    const html = renderSegments(segs, shared);
    expect(html.match(/stanza-break/g)).toHaveLength(2);
  });
});


// ── Psalm/Reading rubric placement (#84) ─────────────────────────────────────

describe('rubric block splits', () => {
  test('every form splits into the runs both renderers place', () => {
    // The blocks are not preambles: the book prints their rubrics on either
    // side of the lectionary content. Rendering one whole puts "At the end of
    // the Psalm…" above the psalm it follows and leaves the Gloria with
    // nothing introducing it. web/app.js and cli/book.js share this split so
    // they cannot disagree about which side a rubric belongs on (ADR 0004).
    if (!HAS_DATA) return;
    for (const [key, form] of forms) {
      const office = key.endsWith('-ep') ? 'Evening' : 'Morning';
      const psalm = splitPsalmRubrics(form.psalm_rubrics);
      const reading = splitReadingRubrics(form.reading_rubrics);

      expect(psalm.intro.map(s => s.text), `${key} psalm intro`)
        .toEqual(['A Psalm is said or sung.']);
      expect(psalm.doxologyCue, `${key} doxology cue`).toHaveLength(1);
      expect(psalm.doxologyCue[0].text).toMatch(/^(?:At the end of|After) the Psalm/);

      expect(reading.handoff.map(s => s.text), `${key} reading handoff`)
        .toEqual([`${office} Prayer continues with the Reading.`]);
      expect(reading.intro.map(s => s.text), `${key} reading intro`)
        .toEqual(['A Reading is read. After a period of silent reflection one of the following is said.']);
      // One form runs the two transitions together on a line, so they merge
      // into a single segment; every other form keeps them separate.
      expect(reading.after.length, `${key} reading after`).toBeGreaterThanOrEqual(1);
      for (const seg of reading.after) {
        expect(seg.text).toMatch(/^(?:\w+ Prayer continues with the Responsory|If two Readings are read)/);
      }
      // Nothing may fall out of a block: every rubric lands in exactly one run.
      const runs = [...psalm.intro, ...psalm.doxologyCue].length
                 + [...reading.handoff, ...reading.intro, ...reading.after].length;
      const rubrics = (form.psalm_rubrics.length - 1) + (form.reading_rubrics.length - 1);
      expect(runs, `${key} every rubric placed`).toBe(rubrics);
    }
  });

  // The words of a printed sentence are separated by what the page set between
  // them. The extractor re-homes the hand-off on that reading (#89), so this
  // side must classify every sentence it hands over, or the hand-off falls
  // through to the intro run and prints below the Reading heading it opens.
  test.each([
    ['a forced break kept as structural', 'Morning Prayer continues with the\nReading.'],
    ['a non-breaking space', 'Evening Prayer continues with\u00a0the Reading.'],
  ])('the hand-off is classified across %s', (_label, text) => {
    const segs = [{ type: 'label', text: 'The Reading' }, { type: 'rubric', text }];
    expect(splitReadingRubrics(segs).handoff.map(s => s.text)).toEqual([text]);
  });

  test('the doxology cue is classified across a non-breaking space', () => {
    // The book sets one in this very rubric, just past where the cue stops
    // matching; the classifier must not depend on where it happens to fall.
    const text = 'At the end of\u00a0the Psalm\u00a0one of the following may be said or sung.';
    const segs = [{ type: 'label', text: 'The Psalm' }, { type: 'rubric', text }];
    expect(splitPsalmRubrics(segs).doxologyCue.map(s => s.text)).toEqual([text]);
  });
});


// ── Citation display vs lookup (#110) ────────────────────────────────────────

describe('expandCitationForDisplay', () => {
  // A single-chapter book is cited without a chapter, and that is how the
  // lectionary source prints it. parseCitation supplies chapter 1 because the
  // verse data is keyed by chapter; display must not inherit that.
  test.each([
    ['Jude 1-16',  'Jude 1-16',       '1:1-16'],
    ['Jude 17-25', 'Jude 17-25',      '1:17-25'],
    ['3 Jn 1-15',  '3 John 1-15',     '1:1-15'],
    ['Ob 15-21',   'Obadiah 15-21',   '1:15-21'],
    ['Philem 8-20', 'Philemon 8-20',  '1:8-20'],
  ])('%s displays as %s, looks up %s', (raw, display, lookupRest) => {
    expect(expandCitationForDisplay(raw)).toBe(display);
    expect(parseCitation(raw).rest, 'lookup still needs the chapter').toBe(lookupRest);
    expect(parseCitation(raw).chapterInferred).toBe(true);
  });

  test.each([
    ['Am 5:1-17',       'Amos 5:1-17'],
    ['2 Sam 5:22—6:11', '2 Samuel 5:22—6:11'],
    ['Mt 22:1-14',      'Matthew 22:1-14'],
    ['Is 55:1-5 or Jer 31:1-6', 'Isaiah 55:1-5 or Jeremiah 31:1-6'],
  ])('%s is untouched beyond expanding the book', (raw, display) => {
    expect(expandCitationForDisplay(raw)).toBe(display);
    expect(parseCitation(raw).chapterInferred).toBe(false);
  });

  // A colonless range means verses only in a single-chapter book. Anywhere
  // else it is a whole chapter, or a separator this parser does not read, and
  // supplying chapter 1 would resolve a passage nobody appointed (#112).
  test.each([
    ['Mt 5',            'Matthew 5',        '5'],
    ['Gen 1',           'Genesis 1',        '1'],
    ['Acts 11.19-30',   'Acts 11.19-30',    '11.19-30'],
    ['Job 1.1-5',       'Job 1.1-5',        '1.1-5'],
  ])('%s keeps its range rather than becoming chapter 1', (raw, display, rest) => {
    const p = parseCitation(raw);
    expect(p.chapterInferred, 'no chapter is invented').toBe(false);
    expect(p.rest).toBe(rest);
    expect(expandCitationForDisplay(raw)).toBe(display);
  });

  test('the single-chapter list matches the bundled corpus', () => {
    // The list is the reason a colonless range is read as verses, so it has to
    // stay true of the data it describes.
    expect([...SINGLE_CHAPTER_BOOKS].sort())
      .toEqual(['2 John', '3 John', 'Jude', 'Obadiah', 'Philemon']);
  });

  // The invariant behind the cases above, over every reading the lectionary
  // appoints, so a single-chapter book new to regenerated data is covered too.
  test.skipIf(!HAS_LECTIONARY)('never prints a chapter the appointed citation lacks', () => {
    let checked = 0;
    for (const file of readdirSync(LECT_DIR)) {
      if (!file.endsWith('.json')) continue;
      const month = JSON.parse(readFileSync(join(LECT_DIR, file), 'utf8'));
      for (const day of Object.values(month)) {
        for (const office of ['morning', 'evening']) {
          for (const lesson of day[office]?.lessons || []) {
            const raw = typeof lesson === 'object' ? lesson.citation : String(lesson);
            checked++;
            if (raw.includes(':')) continue;
            expect(expandCitationForDisplay(raw), raw).not.toContain(':');
          }
        }
      }
    }
    expect(checked, 'lectionary had readings to check').toBeGreaterThan(0);
  });
});

// ── collectCommemorations (#135) ──────────────────────────────────────────────

describe('collectCommemorations', () => {
  test('reads the commemoration collect the ref names in parentheses', () => {
    expect(collectCommemorations('268 (Com: 434 or FAS 361)'))
      .toEqual([{ of: '', pages: ['434'] }]);
  });

  test('a slashed page is the book\'s shorthand for two facing collects', () => {
    expect(collectCommemorations('268 (Com: 438/9 or FAS 363)'))
      .toEqual([{ of: '', pages: ['438', '439'] }]);
    expect(collectCommemorations('336 (Mem: 432/3 or FAS 187)'))
      .toEqual([{ of: '', pages: ['432', '433'] }]);
  });

  test('a tail no shorter than its page is the whole page number', () => {
    // The shorthand can only abbreviate a page it is shorter than. Not a shape
    // the current window carries; the arithmetic should not invent 9100 if it
    // ever does.
    expect(collectCommemorations('268 (Com: 99/100 or FAS 361)'))
      .toEqual([{ of: '', pages: ['99', '100'] }]);
  });

  test('a day commemorating two people names whose collect is whose', () => {
    expect(collectCommemorations(
      '388 (Com Wyclyf: 438/9 or FAS 323) or (Com Hus: 436 or FAS 325)'
    )).toEqual([
      { of: 'Wyclyf', pages: ['438', '439'] },
      { of: 'Hus', pages: ['436'] },
    ]);
  });

  test('the FAS page is not returned — ADR 0020 keeps it a fallback', () => {
    const [entry] = collectCommemorations('268 (Com: 434 or FAS 361)');
    expect(entry.pages).not.toContain('361');
  });

  test('a ref with no commemoration yields none', () => {
    expect(collectCommemorations('344 or 8, 677 (The King)')).toEqual([]);
    expect(collectCommemorations('268')).toEqual([]);
    expect(collectCommemorations('')).toEqual([]);
  });

  test.skipIf(!HAS_LECTIONARY)('every commemoration page in the window resolves', () => {
    const collects = JSON.parse(readFileSync(join(DATA_DIR, 'collects.json'), 'utf8'));
    const missing = [];
    let slots = 0;
    for (const file of readdirSync(LECT_DIR).filter(f => f.endsWith('.json'))) {
      const days = JSON.parse(readFileSync(join(LECT_DIR, file), 'utf8'));
      for (const [date, day] of Object.entries(days)) {
        if (!day || typeof day !== 'object') continue;
        for (const office of ['morning', 'evening']) {
          const ref = (day[office] || {}).collect;
          if (typeof ref !== 'string') continue;
          const found = collectCommemorations(ref);
          if (found.length) slots++;
          for (const cm of found)
            for (const page of cm.pages)
              if (!collects[page]) missing.push(`${date} ${office} p.${page}`);
        }
      }
    }
    expect(slots).toBeGreaterThan(0);
    expect(missing).toEqual([]);
  });
});


// ── lookupFatsEntry (#136) ────────────────────────────────────────────────────

describe('lookupFatsEntry', () => {
  // The short key is deliberately first: a matcher that followed insertion
  // order would serve Richard of Chichester's life for Richard Hooker.
  const fats = {
    'Richard': { bio: 'Richard of Chichester' },
    'Richard Hooker': { bio: 'Richard Hooker' },
    'Clement': { bio: 'Clement of Rome' },
    'Clement of Alexandria': { bio: 'Clement of Alexandria' },
    'Teresa of Avila': { bio: 'Teresa' },
    'John of the Cross': { bio: 'John' },
  };

  test('the fuller name wins over a shorter one starting in the same place', () => {
    expect(lookupFatsEntry(fats, 'Richard Hooker, Priest and Teacher of the Faith, 1600').bio)
      .toBe('Richard Hooker');
    expect(lookupFatsEntry(fats, 'Clement of Alexandria, Priest, c. 210').bio)
      .toBe('Clement of Alexandria');
  });

  test('a name that is only a shorter key still finds it', () => {
    expect(lookupFatsEntry(fats, 'Richard, Bishop of Chichester, 1253').bio)
      .toBe('Richard of Chichester');
  });

  test('the earliest-named person is the day\'s, where two are named', () => {
    expect(lookupFatsEntry(fats, 'Teresa of Avila, 1582 and John of the Cross, 1591').bio)
      .toBe('Teresa');
  });

  test('a key is a person, not a substring', () => {
    // "Richard" must not be found inside a surname it merely spells.
    expect(lookupFatsEntry({ 'Richard': { bio: 'x' } }, 'Prichards of Wales')).toBeNull();
  });

  test('an unknown name resolves to nothing', () => {
    expect(lookupFatsEntry(fats, 'Advent Feria')).toBeNull();
    expect(lookupFatsEntry(fats, '')).toBeNull();
    expect(lookupFatsEntry(null, 'Richard')).toBeNull();
  });
});

describe('fatsCandidates', () => {
  const fats = { 'Richard': {}, 'Richard Hooker': {}, 'Teresa of Avila': {}, 'John of the Cross': {} };

  test('overlapping keys are one person written more or less fully', () => {
    expect(fatsCandidates(fats, 'Richard Hooker, Priest, 1600')).toEqual(['Richard Hooker']);
  });

  test('keys in different parts of the name are different people', () => {
    expect(fatsCandidates(fats, 'Teresa of Avila, 1582 and John of the Cross, 1591'))
      .toEqual(['Teresa of Avila', 'John of the Cross']);
  });
});
