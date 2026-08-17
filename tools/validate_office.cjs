#!/usr/bin/env node
/**
 * tools/validate_office.cjs — liturgical coherence validators for full office output.
 *
 * Consumes renderOfficeJSON from render.js and checks rules against all 30 forms
 * using representative dates from qa_dates.json. Each rule returns {pass, detail}.
 *
 * Usage: node tools/validate_office.cjs [--json]
 *   Without --json: human-readable output, exits 1 on failures.
 *   With --json:    JSON to stdout, always exits 0.
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

async function main() {
  const { renderOfficeJSON, segmentsToJSON, walkSegments, seasonOf, officeFormSeason, seasonWeekIndex,
          isSkippedRubric } = await import('../web/render.js');

  const useJson = process.argv.includes('--json');

  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared  = offices._shared || {};

  // Load date fixture for full-office validation
  let qaDates;
  try {
    qaDates = JSON.parse(readFileSync(join(root, 'tools/qa_dates.json'), 'utf8'));
  } catch (_) {
    qaDates = [];
  }

  const rules = [];
  const failures = [];
  // qa_dates entries whose date or form did not resolve; see the dynamic pass below.
  const unresolved = [];
  // Forms whose dynamic render threw; every DYNAMIC_RULE is lost for them, same as `unresolved`.
  const renderErrors = [];

  // Line breaks the errata prints deliberately, lifted from the corrections
  // that introduce them (ADR 0012). A break after a line with no terminal
  // punctuation usually means a column wrap leaked through — except where an
  // editorial source says the line ends there on purpose:
  //
  //     May God, who has called us out of darkness
  //     into the marvellous light of Christ,
  //
  // Keyed on `office|field` so a correction vouches only where it points, and
  // on `source` rather than an id prefix, because an id is a label. Derived so
  // the exemption cannot outlive its reason: drop the correction and the line
  // stops being sanctioned on the next run.
  const ERRATA_BREAKS = new Set();
  try {
    const corr = JSON.parse(readFileSync(join(root, 'data/corrections.json'), 'utf8'));
    // A correction on _shared.K vouches at every form whose field references K.
    // The opposite of corrections_lib.iter_text_segments, which refuses to
    // follow shared references: applying through one would rewrite siblings
    // silently, but the text really does appear at every form that uses it.
    const sharedUsers = {};
    for (const [fk, form] of Object.entries(offices)) {
      if (fk.startsWith('_')) continue;
      for (const [field, value] of Object.entries(form)) {
        if (value && value.type === 'shared' && value.key) {
          (sharedUsers[value.key] ||= []).push(`${fk}|${field}`);
        }
      }
    }
    for (const c of corr.office_text || []) {
      if (!String(c.source || '').startsWith('pwc-errata-')) continue;
      if (typeof c.new !== 'string') continue;
      const targets = c.office === '_shared'
        ? (sharedUsers[c.field] || [])
        : [`${c.office}|${c.field}`];
      const lines = c.new.split('\n');
      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (!line) continue;          // a blank line vouches for nothing
        for (const t of targets) ERRATA_BREAKS.add(`${t} ${line}`);
      }
    }
  } catch (_) { /* no manifest — every break is checked, the safe default */ }

  // ── Tier 1: Structural (penalty: -10) ────────────────────────────────

  rules.push({ name: 'dismissal-has-amen', tier: 1, check(form, formKey, data) {
    const dism = data.sections.find(s => s.name === 'Sending');
    if (!dism) return { pass: true, detail: 'no Sending section' };
    const allSegs = dism.subsections.flatMap(sub => sub.segments);
    const amens = allSegs.filter(i => i.text.includes('Amen'));
    return { pass: amens.length > 0, detail: amens.length ? '' : 'no Amen found in dismissal' };
  }});

  rules.push({ name: 'no-stray-space-before-period', tier: 1, check(form, formKey, data) {
    const all = data.sections.flatMap(s => s.subsections.flatMap(sub => sub.segments));
    const stray = all.filter(i => /Amen \./.test(i.text) || /\w \.$/.test(i.text));
    return { pass: stray.length === 0, detail: stray.length ? `${stray.length} segments` : '' };
  }});

  rules.push({ name: 'non-empty-responses', tier: 1, check(form, _formKey, _data) {
    // Walks form's own segments via walkSegments directly, not the rendered
    // `data` structure: segmentsToJSON/flattenSegs (web/render.js) drop any
    // segment whose text is empty or whitespace-only before it ever reaches
    // that structure, so a rule filtering `data` for near-empty responses
    // could never encounter one (#70, #72). Raw segments still have it.
    const near = [];
    for (const [sectionKey, segs] of Object.entries(form)) {
      if (sectionKey.startsWith('_') || sectionKey === 'title' || sectionKey === 'subtitle') continue;
      for (const event of walkSegments(segs, shared)) {
        if (event.type === 'segment' && event.seg.type === 'response' && event.seg.text.trim().length < 3) {
          near.push(event.seg.text);
        }
      }
    }
    return { pass: near.length === 0, detail: near.length ? `${near.length} near-empty responses` : '' };
  }});

  rules.push({ name: 'opening-has-leader-and-response', tier: 1, check(form, formKey, data) {
    const gath = data.sections.find(s => s.name === 'Gathering');
    if (!gath) return { pass: false, detail: 'no Gathering section' };
    const openSub = gath.subsections.find(sub => sub.label === 'Introductory Responses');
    if (!openSub) return { pass: false, detail: 'no Introductory Responses' };
    const segs = openSub.segments;
    const hasL = segs.some(i => i.type === 'leader');
    const hasR = segs.some(i => i.type === 'response');
    return { pass: hasL && hasR, detail: `leader=${hasL} response=${hasR}` };
  }});

  rules.push({ name: 'no-empty-segments', tier: 1, check(form, formKey, data) {
    const all = data.sections.flatMap(s => s.subsections.flatMap(sub => sub.segments));
    const bare = all.filter(i => i.text === 'N');
    return { pass: bare.length === 0, detail: bare.length ? `${bare.length} bare 'N' placeholders` : '' };
  }});

  rules.push({ name: 'canticle-has-verse-content', tier: 1, check(form, formKey, data) {
    const proc = data.sections.find(s => s.name === 'Proclamation');
    if (!proc) return { pass: true, detail: 'no Proclamation' };
    const cantSub = proc.subsections.find(sub => sub.label === 'The Canticle');
    if (!cantSub) return { pass: false, detail: 'no canticle subsection' };
    const leaders = cantSub.segments.filter(i => i.type === 'leader');
    return { pass: leaders.length > 0, detail: leaders.length ? '' : 'canticle has no leader verse text' };
  }});

  rules.push({ name: 'evening-has-light', tier: 1, check(form, formKey, data) {
    if (data.meta.officeType !== 'ep') return { pass: true, detail: 'not EP' };
    const gath = data.sections.find(s => s.name === 'Gathering');
    if (!gath) return { pass: false, detail: 'no Gathering section' };
    const has = gath.dynamic.phosHilaronPresent || gath.dynamic.thanksgivingForLightPresent;
    return { pass: has, detail: has ? '' : 'EP has no Phos Hilaron or Thanksgiving for Light' };
  }});

  rules.push({ name: 'leader-response-alternation', tier: 1, check(form, _formKey, _data) {
    // Check alternation in non-alternative dialogic sections.
    // Sections with alternatives (opening_responses, affirmation, canticle)
    // naturally have consecutive same-type segments across group boundaries
    // and are excluded from this check.
    const sections = [
      { key: 'responsory', label: 'Responsory' },
      { key: 'litany', label: 'Litany' },
      { key: 'dismissal', label: 'Dismissal' },
    ];
    for (const { key, label } of sections) {
      if (!form[key]) continue;
      const resolved = key === 'dismissal' && form[key] ? form[key] : form[key];
      let prevType = null;
      for (const event of walkSegments(Array.isArray(resolved) ? resolved : [resolved], shared)) {
        if (event.type === 'enter_group') { prevType = null; continue; }
        if (event.type === 'exit_group') { prevType = null; continue; }
        if (event.type !== 'segment') continue;
        if (event.seg.type === 'rubric') continue;
        if (prevType && prevType === event.seg.type) {
          return { pass: false, detail: `${label}: two consecutive ${event.seg.type} segments` };
        }
        prevType = event.seg.type;
      }
    }
    return { pass: true, detail: '' };
  }});

  rules.push({ name: 'psalter-gloria-present', tier: 1, check(form, formKey, data) {
    const proc = data.sections.find(s => s.name === 'Proclamation');
    if (!proc) return { pass: true, detail: 'no Proclamation' };
    const hasPsalms = proc.dynamic.psalms?.length || proc.dynamic.psalmSets?.length;
    if (!hasPsalms) return { pass: true, detail: 'no psalms appointed' };
    return { pass: !!proc.dynamic.psalmDoxologyPresent, detail: proc.dynamic.psalmDoxologyPresent ? '' : 'doxology missing after psalms' };
  }});

  rules.push({ name: 'reading-response-present', tier: 1, check(form, formKey, data) {
    const proc = data.sections.find(s => s.name === 'Proclamation');
    if (!proc) return { pass: true, detail: 'no Proclamation' };
    if (!proc.dynamic.readings || !proc.dynamic.readings.length) return { pass: true, detail: 'no readings' };
    return { pass: !!proc.dynamic.readingResponsePresent, detail: proc.dynamic.readingResponsePresent ? '' : 'reading response missing' };
  }});

  rules.push({ name: 'collect-resolvable', tier: 1, check(form, formKey, data) {
    const pr = data.sections.find(s => s.name === 'Prayers');
    if (!pr) return { pass: true, detail: 'no Prayers section' };
    const d = pr.dynamic;
    const has = d.collectRef || d.collectInline || d.collectFatsFallback || d.collectSeasonalItems?.length;
    return { pass: !!has, detail: has ? '' : 'no collect option available' };
  }});

  // ── Tier 2: Format (penalty: -3) ────────────────────────────────────

  // Sections that contain *any* intentional line breaks, so no-prose-line-breaks
  // must not treat a \n here as a prose orphan.
  //
  // Validator-only: extraction decides each break from the page geometry, so a
  // section needs no verse/prose classification to be extracted correctly —
  // only to be validated here (#36, #39, #41, #42, #46).
  const VERSE_SECTIONS = ['opening_responses', 'responsory', 'canticle', 'invitatory',
    'phos_hilaron', 'thanksgiving_for_light', 'lords_prayer_intro',
    'intercessions', 'affirmation', 'litany', 'dismissal'];

  rules.push({ name: 'no-prose-line-breaks', tier: 2, check(form, formKey, data) {
    const proseSubs = data.sections.flatMap(s => s.subsections).filter(sub =>
      !VERSE_SECTIONS.some(vs => sub.segments.some(seg => seg.section === vs)));
    const orphans = [];
    for (const sub of proseSubs) {
      for (const seg of sub.segments) {
        if ((seg.type === 'leader' || seg.type === 'response') && seg.text.includes('\n') && !seg.text.endsWith('\n')) {
          orphans.push(`${sub.label}: "${seg.text.slice(0, 50)}..."`);
        }
      }
    }
    return { pass: orphans.length === 0, detail: orphans.length ? `${orphans.length} break(s)` : '' };
  }});

  rules.push({ name: 'canticle-has-verse-breaks', tier: 2, check(form, formKey, data) {
    const proc = data.sections.find(s => s.name === 'Proclamation');
    if (!proc) return { pass: true, detail: 'no Proclamation' };
    const cantSub = proc.subsections.find(sub => sub.label === 'The Canticle');
    if (!cantSub) return { pass: true, detail: 'no canticle' };
    const leaders = cantSub.segments.filter(i => i.type === 'leader');
    const hasBreaks = leaders.some(l => l.text.includes('\n'));
    // Doxology leaders at the end are single-line invocations — fine.
    // Only fail if NO leader has verse breaks.
    return { pass: hasBreaks, detail: hasBreaks ? '' : 'all canticle text is prose-joined (no verse breaks)' };
  }});

  // Minimum line count per phos_hilaron hymn (including stanza-break blank lines).
  // A drop indicates _LINE_JOIN in extract_offices.py is incorrectly joining
  // poetic lines.  Must stay in sync with VERSE_SECTIONS in extract_offices.py
  // and with the Vitest unit test in tests/unit/render.test.js.
  const PHOS_MIN_LINES = {
    'ordinary-sunday-ep':    11, 'ordinary-monday-ep':  14, 'ordinary-tuesday-ep':   9,
    'ordinary-wednesday-ep': 14, 'ordinary-thursday-ep': 24, 'ordinary-friday-ep':   14,
    'ordinary-saturday-ep':  19,
  };
  rules.push({ name: 'phos-hilaron-line-count', tier: 2, check(form, formKey, _data) {
    const expected = PHOS_MIN_LINES[formKey];
    if (expected == null) return { pass: true, detail: 'no phos hilaron' };
    const phos = form.phos_hilaron;
    if (!phos || !phos.length) return { pass: true, detail: 'no phos hilaron' };
    for (const seg of phos) {
      if (seg.type !== 'leader') continue;
      const count = seg.text.split('\n').length;
      return { pass: count >= expected, detail: count >= expected ? '' : `${count} lines (expected >= ${expected})` };
    }
    return { pass: true, detail: 'no leader segment' };
  }});

  rules.push({ name: 'collect-and-dismissal-no-orphan-breaks', tier: 2, check(form, formKey, data) {
    const collectLabels = ['The Collect', 'Seasonal Collect'];
    const dumpTexts = [];
    for (const section of data.sections) {
      for (const sub of section.subsections) {
        const isCollect = collectLabels.includes(sub.label) || sub.label.includes('Collect');
        const isDismissal = sub.label === 'The Dismissal';
        if (!isCollect && !isDismissal) continue;
        const field = isDismissal ? 'dismissal' : 'seasonal_collects';
        for (const seg of sub.segments) {
          // Only check leader/response segments — rubric bullet lists are intentional
          if (seg.type !== 'leader' && seg.type !== 'response') continue;
          const lines = seg.text.split('\n');
          for (let i = 0; i < lines.length - 1; i++) {
            const line = lines[i];
            const trimmed = line.trim();
            if (trimmed && !/[.,;:!?]\s*$/.test(trimmed)
                && !ERRATA_BREAKS.has(`${formKey}|${field} ${trimmed}`)) {
              dumpTexts.push(seg.text.slice(0, 60));
            }
          }
        }
      }
    }
    return { pass: dumpTexts.length === 0, detail: dumpTexts.length ? `${dumpTexts.length} orphan breaks` : '' };
  }});

  rules.push({ name: 'seasonal-title-coherence', tier: 2, check(form, formKey, data) {
    if (data.meta.season === 'OrdinaryTime') return { pass: true, detail: 'ordinary — title suppression is correct' };
    const hasTitle = form.title && form.title.trim();
    return { pass: !!hasTitle, detail: hasTitle ? '' : 'seasonal form missing title' };
  }});

  rules.push({ name: 'no-orphan-rubrics', tier: 2, check(form, formKey, data) {
    const orphans = [];
    // Rubrics that legitimately close a subsection with nothing after them.
    // The exemption names what it covers, tightly (ADR 0013/#59). A bare prefix
    // would exempt every longer rubric starting the same way: 'The Lord’s
    // Prayer' waves through a real orphan like "The Lord's Prayer is omitted.",
    // and isSkippedRubric already matches the exact-match form, so such an entry
    // buys nothing but the hole.

    // Prefix matching survives only where the exempt rubric is a long block
    // with a stable opening — the intercessions free-prayer prompt, whose
    // bullet list differs per form.
    const trailingOkPrefix = [
      'The community may offer its intercessions, petitions, and thanksgivings',
    ];

    // The "{office} Prayer continues with …" family: a hand-off naming the
    // section that follows, which is exactly what makes it section-closing.
    // Nine wordings across the 30 forms (office × destination), so it is
    // matched as the family it is rather than enumerated. These are the
    // rubrics _hoist_office_transition lifts back out of the alternatives
    // block that swallowed them (#84), so they close canticle, affirmation
    // and responsory in every form.
    // The words are separated by what the page set between them, which is the
    // reading the extractor and web/render.js both take (#138): a wrap inside
    // the sentence is no-prose-line-breaks' finding to report, not this rule's.
    const trailingOkRe = [
      /^(?:Morning|Evening)\s+Prayer\s+continues\s+with\s[\s\S]+\.$/,
    ];

    // Exact texts: the Psalm block's doxology cue and the Reading block's
    // two-reading rule, each introducing lectionary content that renders after
    // the rubric block rather than inside it (#84).
    const trailingOkExact = [
      'At the end of the Psalm one of the following may be said or sung.',
      'At the end of the Psalm(s) one of the following may be said or sung.',
      'After the Psalm one of the following may be said or sung.',
      'If two Readings are read, then the Responsory follows the first Reading and the Canticle the second.',
    ];

    for (const section of data.sections) {
      for (const sub of section.subsections) {
        if (!sub.segments.length) continue;
        const last = sub.segments[sub.segments.length - 1];
        if (last.type !== 'rubric') continue;
        const txt = last.text;
        // The book binds "Psalm" to the word after it with a non-breaking
        // space; compare against ordinary spaces so the exact texts above read
        // as the sentences they are.
        const t = txt.trim().replace(/\u00a0/g, ' ');
        if (!isSkippedRubric(txt)
            && !trailingOkPrefix.some(prefix => t.startsWith(prefix))
            && !trailingOkRe.some(re => re.test(t))
            && !trailingOkExact.includes(t)) {
          orphans.push(`${sub.label}: "${txt.slice(0, 50)}..."`);
        }
      }
    }
    return { pass: orphans.length === 0, detail: orphans.length ? `${orphans.length} orphan rubrics` : '' };
  }});

  rules.push({ name: 'intercessions-nonempty', tier: 2, check(form, formKey, data) {
    // form.intercessions absent: the form legitimately has no intercessions.
    // form.intercessions present but empty: assembleSections drops the
    // subsection entirely (render.js), so `sub` below would be missing too —
    // that must fail, not read as "no intercessions" like the absent case.
    if (!form.intercessions) return { pass: true, detail: 'no intercessions' };
    const pr = data.sections.find(s => s.name === 'Prayers');
    const sub = pr && pr.subsections.find(s => s.label === 'Intercessions and Thanksgivings');
    const nonEmpty = !!sub && sub.segments.some(i => i.text.length > 2 && i.text !== 'N');
    return { pass: nonEmpty, detail: nonEmpty ? '' : 'intercessions empty' };
  }});

  // ── Tier 3: Seasonal (penalty: -5) ──────────────────────────────────

  // Daily canticles used year-round
  const DAILY_CANTICLES = ['Song of Zechariah', 'Song of Mary'];

  const SEASONAL_CANTICLES = {
    Advent: [...DAILY_CANTICLES, 'A Song of Christ\u2019s Glory', 'A Song of Christ the Servant', 'Great and Wonderful', 'A Song of Baruch'],
    Christmas: [...DAILY_CANTICLES, 'Song of Christ\u2019s Glory', 'Great and Wonderful'],
    Epiphany: [...DAILY_CANTICLES, 'Song of Christ\u2019s Glory', 'A Song of Christ the Servant', 'Great and Wonderful'],
    Lent: [...DAILY_CANTICLES, 'Song of Moses and Miriam', 'Song of Christ\u2019s Appearing', 'Song of Manasseh', 'Prayer of Habakkuk', 'A Song of Christ the Servant', 'Song of David'],
    Passiontide: [...DAILY_CANTICLES, 'Song of Moses and Miriam', 'A Song of Christ the Servant', 'Song of Christ\u2019s Appearing', 'Song of Manasseh'],
    Easter: [...DAILY_CANTICLES, 'Bless the Lord', 'Song of Christ\u2019s Glory', 'Song of Moses and Miriam', 'Great and Wonderful', 'Song of Deliverance'],
    Pentecost: [...DAILY_CANTICLES, 'Bless the Lord', 'Song of Deliverance', 'A Song of God\u2019s Grace', 'A Song of Faith', 'Song of Christ\u2019s Glory'],
  };

  rules.push({ name: 'seasonal-canticle-coherence', tier: 3, check(form, formKey, data) {
    const season = data.meta.season;
    if (season === 'OrdinaryTime') return { pass: true, detail: 'ordinary — default canticle set' };
    const proc = data.sections.find(s => s.name === 'Proclamation');
    if (!proc) return { pass: true, detail: 'no Proclamation' };
    const label = proc.dynamic.canticleLabel;
    if (!label) return { pass: true, detail: 'no canticle label' };
    const expect = SEASONAL_CANTICLES[season] || [];
    if (!expect.length) return { pass: true, detail: `no known canticle set for ${season}` };
    const match = expect.some(e => label.startsWith(e));
    return { pass: match, detail: match ? '' : `canticle "${label}" not in ${season} set` };
  }});

  rules.push({ name: 'collect-week-in-range', tier: 3, check(form, formKey, data) {
    const pr = data.sections.find(s => s.name === 'Prayers');
    if (!pr) return { pass: true, detail: 'no Prayers' };
    if (data.meta.season === 'OrdinaryTime') return { pass: true, detail: 'ordinary — single alternatives block' };
    // Check that seasonal collects exist for the weekIdx
    const seasonalSegs = form.seasonal_collects;
    if (!seasonalSegs || !seasonalSegs.length) return { pass: true, detail: 'no seasonal collects' };
    // Count the number of period groups
    let periods = 0;
    for (const seg of seasonalSegs) {
      if (seg.type === 'rubric' && !/\bAdditional intercessions\b/i.test(seg.text)) periods++;
    }
    if (!pr.dynamic.collectSeasonalItems || pr.dynamic.collectSeasonalItems.length === 0) {
      return { pass: false, detail: `weekIdx ${data.meta.weekIdx} returned no seasonal collect items (${periods} periods available)` };
    }
    return { pass: true, detail: '' };
  }});

  // ── Run rules ────────────────────────────────────────────────────────

  let totalChecks = 0;

  // Map raw section keys from segmentsToJSON to human-readable labels
  const SECTION_LABEL = {
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
    seasonal_collects: 'The Collect',
    psalm_rubrics: 'The Psalm',
    reading_rubrics: 'The Reading',
  };

  const SECTION_NAME = {
    opening_responses: 'Gathering',
    phos_hilaron: 'Gathering',
    thanksgiving_for_light: 'Gathering',
    invitatory: 'Gathering',
    psalm_rubrics: 'Proclamation',
    reading_rubrics: 'Proclamation',
    responsory: 'Proclamation',
    canticle: 'Proclamation',
    affirmation: 'Proclamation',
    intercessions: 'Prayers',
    litany: 'Prayers',
    seasonal_collects: 'Prayers',
    lords_prayer_intro: 'Prayers',
    dismissal: 'Sending',
  };

  // Rules that need lectionary data — skip them in the static pass
  const DYNAMIC_RULES = new Set([
    'evening-has-light', 'psalter-gloria-present', 'reading-response-present',
    'collect-resolvable', 'collect-week-in-range', 'seasonal-canticle-coherence',
    'canticle-has-verse-breaks', 'canticle-has-verse-content',
    'collect-and-dismissal-no-orphan-breaks', 'intercessions-nonempty',
  ]);

  // Static checks (fast, always run) — existing rules against all 30 forms
  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));
  for (const fk of formKeys) {
    const form = offices[fk];
    const staticItems = segmentsToJSON(form, shared);
    const officeType = fk.endsWith('-ep') ? 'ep' : 'mp';

    // Build minimal OfficeJSON-like structure from static data with correct labels
    const grouped = {};
    for (const item of staticItems) {
      if (!grouped[item.section]) grouped[item.section] = [];
      grouped[item.section].push(item);
    }
    const staticSections = [];
    for (const [rawName, segs] of Object.entries(grouped)) {
      const sectionName = SECTION_NAME[rawName] || 'Unknown';
      const label = SECTION_LABEL[rawName] || rawName;
      let section = staticSections.find(s => s.name === sectionName);
      if (!section) {
        section = { name: sectionName, visible: true, subsections: [], dynamic: {} };
        staticSections.push(section);
      }
      section.subsections.push({ label, segments: segs });
    }

    const staticData = {
      meta: { officeType, season: fk.startsWith('ordinary-') ? 'OrdinaryTime' : 'Seasonal', formKey: fk, weekIdx: 0, hasAlternateObservance: false },
      sections: staticSections,
    };

    for (const rule of rules) {
      if (DYNAMIC_RULES.has(rule.name)) continue;
      const { pass, detail } = rule.check(form, fk, staticData);
      totalChecks++;
      if (!pass) {
        failures.push({ rule: rule.name, tier: rule.tier, form: fk, detail });
      }
    }
  }

  // Dynamic checks (slower, needs lectionary) — per-date form validation
  let bounds;
  try {
    bounds = JSON.parse(readFileSync(join(root, 'data/season_bounds.json'), 'utf8'));
  } catch (_) { bounds = null; }

  if (bounds) {

  // A qa_dates entry that does not resolve silently removes every DYNAMIC_RULE
  // from the forms it names, while the summary still reports the full form
  // count. That is how allsaints-mp/-ep lost all 10 dynamic rules when
  // 2025-11-01 rolled out of the lectionary's 12-month window, with `make qa`
  // green throughout. Record rather than skip, and fail loudly below.
  const dateCache = {};
  for (const entry of qaDates) {
    const [year, month] = entry.date.split('-');
    let lect;
    const cacheKey = `${year}-${month}`;
    if (dateCache[cacheKey]) {
      lect = dateCache[cacheKey];
    } else {
      try {
        lect = JSON.parse(readFileSync(join(root, `data/lectionary/${year}-${month}.json`), 'utf8'));
        dateCache[cacheKey] = lect;
      } catch (_) {
        unresolved.push({ date: entry.date, forms: entry.forms, reason: `no lectionary file for ${cacheKey}` });
        continue;
      }
    }
    const day = lect[entry.date];
    if (!day) {
      unresolved.push({ date: entry.date, forms: entry.forms, reason: 'date not in the lectionary window' });
      continue;
    }

    for (const fk of entry.forms) {
      const form = offices[fk];
      if (!form) {
        unresolved.push({ date: entry.date, forms: [fk], reason: 'form not in offices.json' });
        continue;
      }
      const officeType = fk.endsWith('-ep') ? 'ep' : 'mp';
      const officeData = officeType === 'ep' ? (day.evening || {}) : (day.morning || {});
      const fSeason = officeFormSeason(entry.date, bounds);
      const season = seasonOf(entry.date, bounds);
      const weekIdx = seasonWeekIndex(entry.date, fSeason, bounds);

      const cfg = {
        form, shared, officeData, officeType, season,
        weekIdx: weekIdx || 0,
        collectRef: officeData.collect || null,
        collectInline: day.collect_inline || null,
      };

      try {
        const officeJSON = renderOfficeJSON(cfg);
        for (const rule of rules) {
          if (!DYNAMIC_RULES.has(rule.name)) continue;
          const { pass, detail } = rule.check(form, fk, officeJSON);
          if (!pass) {
            failures.push({ rule: rule.name, tier: rule.tier, form: fk, detail });
          }
          totalChecks++;
        }
      } catch (e) {
        renderErrors.push({ date: entry.date, form: fk, error: e.message });
      }
    }
  }
  } // if (bounds)

  // ── Report ───────────────────────────────────────────────────────────
  if (useJson) {
    const perForm = {};
    for (const f of failures) {
      if (!perForm[f.form]) perForm[f.form] = { tier1: 0, tier2: 0, tier3: 0, details: [] };
      perForm[f.form][`tier${f.tier}`]++;
      perForm[f.form].details.push({ rule: f.rule, tier: f.tier, detail: f.detail });
    }
    const output = {
      forms_checked: formKeys.length,
      rules_checked: rules.length,
      total_checks: totalChecks,
      unresolved_qa_dates: unresolved,
      render_errors: renderErrors,
      failures: failures.map(f => ({ rule: f.rule, tier: f.tier, form: f.form, detail: f.detail })),
      perFormScores: perForm,
    };
    console.log(JSON.stringify(output, null, 2));
    process.exit(0);
  }

  // Human-readable output
  console.log(`Checked ${formKeys.length} forms × ${rules.length} rules + dynamic lectionary context`);

  // Reported before rule failures: an unresolved entry means the dynamic rules
  // never ran for those forms, so "all rules passed" would be a claim about
  // checks that did not happen.
  if (unresolved.length) {
    console.error(`\n${unresolved.length} qa_dates entry(s) did not resolve — dynamic rules were NOT run for:\n`);
    for (const u of unresolved) {
      console.error(`  ${u.date}  ${u.forms.join(', ')}  — ${u.reason}`);
    }
    console.error('\nUpdate tools/qa_dates.json to a date inside the current lectionary window.');
    process.exitCode = 1;
  }

  // Reported before rule failures for the same reason as `unresolved`: a form
  // whose dynamic render threw never ran the rules it would otherwise be
  // charged for, so "all rules passed" would misstate what was checked.
  if (renderErrors.length) {
    console.error(`\n${renderErrors.length} render error(s) — dynamic rules were NOT run for:\n`);
    for (const r of renderErrors) {
      console.error(`  ${r.date}  ${r.form}  — ${r.error}`);
    }
    process.exitCode = 1;
  }

  if (failures.length === 0) {
    if (!unresolved.length && !renderErrors.length) console.log('All rules passed.');
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.log(`  [${f.tier === 1 ? 'T1' : f.tier === 2 ? 'T2' : 'T3'} ${f.rule}] ${f.form}: ${f.detail}`);
  }

  const byRule = {};
  for (const f of failures) {
    byRule[f.rule] = (byRule[f.rule] || 0) + 1;
  }
  console.log('\nBy rule:');
  for (const [rule, count] of Object.entries(byRule)) {
    console.log(`  ${rule}: ${count}/${formKeys.length} forms`);
  }

  process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
