/**
 * Shared rendering functions — browser (app.js) and Node (cli/office.js).
 * All functions are pure (data in → HTML/value out, no DOM or network calls).
 */

// localStorage polyfill for Node environment
const _ls = typeof localStorage !== 'undefined'
  ? localStorage
  : { getItem: () => null, setItem: () => {} };

// ── Constants ──────────────────────────────────────────────────────────────────

export const READING_RESPONSE = {
  type: 'alternatives',
  groups: [
    { label: 'I',   segments: [{ type: 'leader',   text: 'The word of the Lord.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
    { label: 'II',  segments: [{ type: 'leader',   text: 'Hear what the Spirit is saying to the Church.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
    { label: 'III', segments: [{ type: 'leader',   text: 'Holy wisdom, holy word.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
  ],
};

// Biblical citations for canticles, shown below the canticle name in the panel.
export const CANTICLE_SOURCE = {
  // Keys match offices.json labels exactly (U+2019 curly apostrophe where needed).
  // Citations match the BAS verse selections printed in the book.
  'Bless the Lord':                          'The Song of the Three 29–34',
  'Great and Wonderful':                     'Revelation 15:3, 4',
  'Prayer of Habakkuk':                      'Habakkuk 3:2, 13a, 15–16, 17–19',
  'Song of Mary':                            'Luke 1:46–55',
  'Song of Zechariah':                       'Luke 1:68–79',
  'Song of Moses and Miriam':                'Exodus 15:1b–3, 6, 10, 13, 17',
  'Song of Manasseh':                        'Manasseh 1a, 2, 4, 6, 7ab, 9ac, 11, 12, 14b, 15b',
  'Song of Christ’s Glory':             'Philippians 2:5–11',
  'A Song of Baruch':                        'Baruch 5:5, 6c, 7–9',
  'A Song of Christ the Servant':            '1 Peter 2:21b–25',
  'A Song of Christ’s Appearing':       '1 Timothy 3:16; 6:15a, 16',
  'A Song of Christ’s Glory':           'Philippians 2:5–11',
  'A Song of David':                         '1 Chronicles 29:10b–13, 14b',
  'A Song of Deliverance':                   'Isaiah 12:2–6',
  'A Song of Ezekiel':                       'Ezekiel 36:24–26, 28b',
  'A Song of Faith':                         '1 Peter 1:3–5, 18, 19, 21',
  'A Song of God’s Assembled':          'Hebrews 12:22–24a, 28, 29',
  'A Song of God’s Children':           'Romans 8:2, 14, 15b–19',
  'A Song of God’s Chosen One':         'Isaiah 11:1, 2, 3b–4a, 6, 9',
  'A Song of God’s Grace':              'Ephesians 1:3–10',
  'A Song of God’s Love':               '1 John 4:7–11, 12b',
  'A Song of Hannah':                        '1 Samuel 2:1, 2, 3b–5, 7, 8',
  'A Song of Humility':                      'Hosea 6:1, 3–4, 6',
  'A Song of Jerusalem Our Mother':          'Isaiah 66:10, 11a, 12a, 12c, 13a, 14a, 14b',
  'A Song of Jonah':                         'Jonah 2:2–7, 9',
  'A Song of Judith':                        'Judith 16:13–16',
  'A Song of Peace':                         'Isaiah 2:3–5',
  'A Song of Pilgrimage':                    'Ecclesiasticus 51:13a, 13c–17, 20, 21a, 22b',
  'A Song of Praise':                        'Revelation 4:11; 5:9b, 10',
  'A Song of Redemption':                    'Colossians 1:13–18a, 19, 20a',
  'A Song of Repentance':                    '1 John 1:5–9',
  'A Song of Tobit':                         'Tobit 13:1, 3, 4, 6a',
  'A Song of Wisdom':                        'Wisdom 9:1–4, 9–11',
  'A Song of the Blessed':                   'Matthew 5:3–12',
  'A Song of the Bride':                     'Isaiah 61:10, 11; 62:1–3',
  'A Song of the Covenant':                  'Isaiah 42:5–8a',
  'A Song of the Heavenly City':             'Revelation 21:22–26; 22:1, 2b, d, 3b, 4',
  'A Song of the Holy City':                 'Revelation 21:1–5a',
  'A Song of the Justified':                 'Romans 4:24, 25; 5:1–5, 11',
  'A Song of the Lamb':                      'Revelation 19:1b, 2a, 5b, 6b, 7, 9b',
  'A Song of the Lord’s Anointed':      'Isaiah 61:1–3, 11, 6a',
  'A Song of the New Creation':              'Isaiah 43:15, 16, 18, 19, 20c, 21',
  'A Song of the New Jerusalem':             'Isaiah 60:1–3, 11a, 18, 19, 14b',
  'A Song of the Spirit':                    'Revelation 22:12–14, 16, 17',
  'A Song of the Wilderness':                'Isaiah 35:1, 2b–4a, 4c–6, 10',
  'A Song of the Word of the Lord':          'Isaiah 55:6–11',
};

// Rubrics that are section-navigation cues in the printed book but are either
// rendered as explicit headings or added programmatically as inter-section transitions.
export const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$|continues with|may conclude with|^The (Responsory|Litany) is said or sung\./i;

// Exported so app.js can use them in collectToggleHtml without re-declaration.
export const SC_HEADER = /^Additional\s+intercessions/i;
export const SC_FOOTER = /^the\s+Lord['']s\s+Prayer/i;

const INTERCESSIONS_RE = /^(The community may offer|Additional intercessions)/;
const INTERCESSIONS_CONDENSED = '<p class="seg-rubric"><em>Offer intercessions, petitions, and thanksgivings, silently or aloud.</em></p>';

// Roman numerals and "Form X" labels don't need a repeated source heading inside the panel.
const SHORT_LABEL_RE = /^(?:Form\s+)?(?:I{1,3}|IV|V|VI{0,3}|IX|X)$/i;

export const ABBREV_TO_FILE = {
  'Gen':'Genesis','Ex':'Exodus','Lev':'Leviticus','Num':'Numbers','Dt':'Deuteronomy',
  'Jos':'Joshua','Jg':'Judges','Ruth':'Ruth','1 Sam':'1 Samuel','2 Sam':'2 Samuel',
  '1 Kgs':'1 Kings','2 Kgs':'2 Kings','1 Chr':'1 Chronicles','2 Chr':'2 Chronicles',
  'Ezra':'Ezra','Neh':'Nehemiah','Est':'Esther','Job':'Job','Ps':'Psalm',
  'Pr':'Proverbs','Ec':'Ecclesiastes','Song':'Song Of Songs','Is':'Isaiah',
  'Jer':'Jeremiah','Lam':'Lamentations','Ezek':'Ezekiel','Dan':'Daniel',
  'Hos':'Hosea','Jl':'Joel','Am':'Amos','Ob':'Obadiah','Jon':'Jonah',
  'Mic':'Micah','Nah':'Nahum','Hab':'Habakkuk','Zeph':'Zephaniah',
  'Hag':'Haggai','Zech':'Zechariah','Mal':'Malachi',
  'Mt':'Matthew','Mk':'Mark','Lk':'Luke','Jn':'John','Acts':'Acts',
  'Rom':'Romans','1 Cor':'1 Corinthians','2 Cor':'2 Corinthians',
  'Gal':'Galatians','Eph':'Ephesians','Phil':'Philippians','Col':'Colossians',
  '1 Th':'1 Thessalonians','2 Th':'2 Thessalonians','1 Tim':'1 Timothy',
  '2 Tim':'2 Timothy','Tit':'Titus','Philem':'Philemon','Heb':'Hebrews',
  'Jas':'James','1 Pet':'1 Peter','2 Pet':'2 Peter','1 Jn':'1 John',
  '2 Jn':'2 John','3 Jn':'3 John','Jude':'Jude','Rev':'Revelation',
  'Tob':'Tobit','Jdt':'Judith','Wis':'Wisdom Of Solomon','Sir':'Sirach',
  'Bar':'Baruch','1 Macc':'1 Maccabees','2 Macc':'2 Maccabees','2 Esd':'2 Esdras',
};

// ── Utility ────────────────────────────────────────────────────────────────────

export function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export function parseDate(s) { return s ? new Date(s + 'T00:00:00Z') : null; }

export function bindMidpoints(html) {
  // Wrap [word * ] in a nowrap group so the asterisk never orphans on a new line.
  return html.replace(/(\S+)(\s*)\*/g, (_, word, sp) =>
    `<span class="midpoint-group">${word}${sp}<span class="midpoint">*</span></span>`);
}

function formatLiturgicalText(text) {
  const lines = text.split('\n');
  if (lines.length < 2) return esc(text);
  return lines.map(l => esc(l)).join('<br>');
}

// ── Date / season ─────────────────────────────────────────────────────────────

export function seasonOf(dateStr, bounds) {
  const d = parseDate(dateStr);
  const passionStart = parseDate(bounds.passiontide || bounds.palm_sunday);
  if (parseDate(bounds.christmas_ii)  && d >= parseDate(bounds.christmas_ii))  return 'Christmas';
  if (parseDate(bounds.advent_ii)     && d >= parseDate(bounds.advent_ii))     return 'Advent';
  if (parseDate(bounds.all_saints)    && d >= parseDate(bounds.all_saints))    return 'AllSaints';
  if (parseDate(bounds.trinity_sunday) && d > parseDate(bounds.trinity_sunday)) return 'OrdinaryTime';
  if (parseDate(bounds.pentecost)     && d >= parseDate(bounds.pentecost))     return 'Pentecost';
  if (parseDate(bounds.easter)        && d >= parseDate(bounds.easter))        return 'Easter';
  if (passionStart                    && d >= passionStart)                    return 'Passiontide';
  if (parseDate(bounds.ash_wednesday) && d >= parseDate(bounds.ash_wednesday)) return 'Lent';
  if (parseDate(bounds.epiphany)      && d >= parseDate(bounds.epiphany))      return 'Epiphany';
  if (parseDate(bounds.christmas)     && d >= parseDate(bounds.christmas))     return 'Christmas';
  if (parseDate(bounds.advent_i)      && d >= parseDate(bounds.advent_i))      return 'Advent';
  return 'OrdinaryTime';
}

export function officeFormSeason(dateStr, bounds) {
  const d = parseDate(dateStr);
  const passionStart      = parseDate(bounds.passiontide || bounds.palm_sunday);
  const pentecostFormStart = parseDate(bounds.ascension || bounds.pentecost);
  const trinityEnd        = parseDate(bounds.trinity_sunday);
  if (parseDate(bounds.christmas_ii)  && d >= parseDate(bounds.christmas_ii))  return 'Christmas';
  if (parseDate(bounds.advent_ii)     && d >= parseDate(bounds.advent_ii))     return 'Advent';
  if (parseDate(bounds.all_saints)    && d >= parseDate(bounds.all_saints))    return 'AllSaints';
  if (trinityEnd                      && d > trinityEnd)                       return 'OrdinaryTime';
  if (pentecostFormStart              && d >= pentecostFormStart)              return 'Pentecost';
  if (parseDate(bounds.easter)        && d >= parseDate(bounds.easter))        return 'Easter';
  if (passionStart                    && d >= passionStart)                    return 'Passiontide';
  if (parseDate(bounds.ash_wednesday) && d >= parseDate(bounds.ash_wednesday)) return 'Lent';
  if (parseDate(bounds.presentation)  && d >= parseDate(bounds.presentation))  return 'OrdinaryTime';
  if (parseDate(bounds.epiphany)      && d >= parseDate(bounds.epiphany))      return 'Epiphany';
  if (parseDate(bounds.christmas)     && d >= parseDate(bounds.christmas))     return 'Christmas';
  if (parseDate(bounds.advent_i)      && d >= parseDate(bounds.advent_i))      return 'Advent';
  return 'OrdinaryTime';
}

// Returns 0-based week index within the season (0 = first week, 1 = second, …).
export function seasonWeekIndex(dateStr, season, bounds) {
  const d = parseDate(dateStr);
  const starts = {
    Easter:      bounds.easter,
    Lent:        bounds.ash_wednesday,
    Epiphany:    bounds.epiphany,
    Christmas:   bounds.christmas,
    AllSaints:   bounds.all_saints,
    Advent:      bounds.advent_i,
    Passiontide: bounds.passiontide || bounds.palm_sunday,
    Pentecost:   bounds.ascension   || bounds.pentecost,
  };
  const start = parseDate(starts[season] || null);
  if (!start) return 0;
  return Math.floor((d - start) / (7 * 24 * 3600 * 1000));
}

// Filter seasonal_collects to the period matching weekIdx.
export function filterSeasonalCollects(segs, weekIdx) {
  const pre = [], groups = [];
  let cur = null;
  for (const seg of segs) {
    if (seg.type === 'rubric' && SC_FOOTER.test(seg.text)) continue;
    const isPeriodMarker = seg.type === 'rubric' && !SC_HEADER.test(seg.text);
    if (isPeriodMarker) {
      if (cur !== null) groups.push(cur);
      cur = [seg];
    } else {
      if (cur === null) pre.push(seg);
      else cur.push(seg);
    }
  }
  if (cur !== null) groups.push(cur);

  if (!groups.length) return segs;

  const preRubrics  = pre.filter(s => s.type === 'rubric');
  const week0Content = pre.filter(s => s.type !== 'rubric');

  if (week0Content.length) {
    if (weekIdx <= 0) return [...preRubrics, ...week0Content];
    return [...preRubrics, ...groups[Math.min(weekIdx - 1, groups.length - 1)]];
  } else {
    return [...preRubrics, ...(groups[Math.min(weekIdx, groups.length - 1)] || [])];
  }
}

export function formKey(season, officeType, weekday) {
  let s = season.toLowerCase();
  if (s === 'ordinarytime') {
    const days = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
    s = 'ordinary-' + days[weekday];
  }
  return s + '-' + officeType;
}

// ── Citation parsing ──────────────────────────────────────────────────────────

export function parseCitation(rawCitation) {
  let citation = rawCitation;
  const orIdx = citation.indexOf(' or ');
  if (orIdx >= 0) citation = citation.slice(0, orIdx).trim();
  citation = citation.trim();

  let s = citation, prefix = '';
  if (s.length > 2 && s[0] >= '1' && s[0] <= '4' && s[1] === ' ') { prefix = s.slice(0, 2); s = s.slice(2); }

  let numStart = -1;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if ((c >= '0' && c <= '9') || c === ':') { numStart = i; break; }
  }
  if (numStart < 0) return null;

  const abbrev = (prefix + s.slice(0, numStart)).trim();
  let rest = s.slice(numStart).trim();
  const file = ABBREV_TO_FILE[abbrev];
  if (!file) return null;
  if (rest !== '' && !rest.includes(':')) rest = '1:' + rest;
  return { abbrev, file, rest };
}

function expandCitationForDisplay(rawCitation) {
  return rawCitation.split(' or ').map(part => {
    const p = parseCitation(part.trim());
    return p ? `${p.file}${p.rest ? ' ' + p.rest : ''}` : part.trim();
  }).join(' or ');
}

// ── Rendering ─────────────────────────────────────────────────────────────────

export function renderAlternatives(seg, shared, contextKey) {
  if (!seg.groups || !seg.groups.length) return '';
  const stateKey = contextKey
    ? 'pwc-alt-' + contextKey
    : 'pwc-alt-' + seg.groups.map(g => {
        const first = g.segments && g.segments[0];
        const word  = first ? first.text.trim().split(/\s+/)[0] : '';
        return g.label + (word ? ':' + word : '');
      }).join('\x1f');
  const savedIdx  = parseInt(_ls.getItem(stateKey) || '0');
  const activeIdx = Math.min(Math.max(0, savedIdx), seg.groups.length - 1);
  const idBase = stateKey.replace(/[^a-zA-Z0-9-]/g, '_');
  const tabsHtml = seg.groups.map((g, i) => {
    const label = g.label || '';
    const displayLabel = label.length > 22 ? label.slice(0, 21) + '…' : label;
    const isActive = i === activeIdx;
    return `<button class="alt-tab${isActive ? ' alt-tab-active' : ''}" role="tab" aria-selected="${isActive}" aria-controls="${idBase}-panel-${i}" id="${idBase}-tab-${i}" data-idx="${i}" data-key="${esc(stateKey)}" title="${esc(label)}">${esc(displayLabel)}</button>`;
  }).join('');
  const panelsHtml = seg.groups.map((g, i) => {
    let sourceHtml = '';
    if (!SHORT_LABEL_RE.test(g.label.trim())) {
      const citation = CANTICLE_SOURCE[g.label];
      if (!citation) console.warn('CANTICLE_SOURCE missing entry for:', g.label);
      sourceHtml = `<p class="alt-source">${esc(g.label)}${citation ? ` — ${esc(citation)}` : ''}</p>`;
    }
    return `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${i}" aria-labelledby="${idBase}-tab-${i}" data-idx="${i}">${sourceHtml}${renderSegments(g.segments, shared)}</div>`;
  }).join('');
  return `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabsHtml}</div>${panelsHtml}</div>`;
}

export function renderSegments(segs, shared) {
  if (!segs || !segs.length) return '';
  return segs.map(seg => {
    let contextKey;
    if (seg.type === 'shared' && shared) { contextKey = seg.key; seg = shared[seg.key] || seg; }
    if (seg.type === 'alternatives') return renderAlternatives(seg, shared, contextKey);
    if (seg.type === 'rubric' && INTERCESSIONS_RE.test(seg.text || '')) return INTERCESSIONS_CONDENSED;
    if (seg.type === 'rubric' && SKIP_RUBRICS.test(seg.text || '')) return '';
    const text = seg.text || '';
    if (seg.type === 'rubric')   return `<p class="seg-rubric">${esc(text)}</p>`;
    if (seg.type === 'response') return `<p class="seg-response">${bindMidpoints(formatLiturgicalText(text))}</p>`;
    return `<p class="seg-leader">${bindMidpoints(esc(text))}</p>`;
  }).join('');
}

export function renderSubsection(label, segs, shared) {
  if (!segs || !segs.length) return '';
  return `<h3 class="office-subsection-title">${esc(label)}</h3><div class="liturgy">${renderSegments(segs, shared)}</div>`;
}

export function lessonHtml(lesson, shared, form) {
  const rawCitation = typeof lesson === 'object' ? lesson.citation : lesson;
  const optional = typeof lesson === 'object' && lesson.optional;
  const displayCitation = expandCitationForDisplay(rawCitation);
  const display = optional ? `(${displayCitation})` : displayCitation;
  const preambleRubric = `<p class="seg-rubric">A Reading from the appointed lectionary is read.</p>`;
  const reflectionRubric = `<p class="seg-rubric">After a period of silent reflection one of the following is said.</p>`;
  if (!form || !form.reading_response) console.warn('lessonHtml: no reading_response on form, using fallback');
  let readingResponse = (form && form.reading_response) || READING_RESPONSE;
  if (readingResponse?.type === 'shared' && shared) {
    readingResponse = shared[readingResponse.key] || READING_RESPONSE;
  }
  const responseHtml = `<div class="liturgy">${renderAlternatives(readingResponse, shared, 'reading_response')}</div>`;
  return `<h3 class="reading-heading">The Reading: ${esc(display)}</h3>`
    + preambleRubric
    + `<div class="scripture-placeholder" data-citation="${esc(rawCitation)}"><p class="loading">Loading…</p></div>`
    + reflectionRubric
    + responseHtml;
}
