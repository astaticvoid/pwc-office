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
export const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord['\u2019]?s Prayer)\.?\s*$|may conclude with|^The (Responsory|Litany) is said or sung\./i;

// Rubrics that are book-navigation instructions (pick one, introduces a section,
// etc.) — noisy in the interactive app but needed in flat book mode.
export const BOOK_ONLY_RUBRICS = /one of the following may be said or sung|the following psalms|at the end of the (psalm|canticle)|after the (psalm|canticle)|may be said or sung\.|one of the following affirmations|continues with|Evening Prayer continues|The community may offer|may be offered silently/i;

// Exported so app.js can use them in collectToggleHtml without re-declaration.
export const SC_HEADER = /^Additional\s+intercessions/i;
export const SC_FOOTER = /^the\s+Lord['’]s\s+Prayer/i;

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

// Map full book names → BAS abbreviations (for RCL Daily data which uses full names).
const FULL_TO_ABBREV = {
  'Genesis':'Gen','Exodus':'Ex','Leviticus':'Lev','Numbers':'Num','Deuteronomy':'Dt',
  'Joshua':'Jos','Judges':'Jg','Ruth':'Ruth','1 Samuel':'1 Sam','2 Samuel':'2 Sam',
  '1 Kings':'1 Kgs','2 Kings':'2 Kgs','1 Chronicles':'1 Chr','2 Chronicles':'2 Chr',
  'Ezra':'Ezra','Nehemiah':'Neh','Esther':'Est','Job':'Job','Psalm':'Ps','Psalms':'Ps',
  'Proverbs':'Pr','Ecclesiastes':'Ec','Song of Solomon':'Song','Song of Songs':'Song',
  'Isaiah':'Is','Jeremiah':'Jer','Lamentations':'Lam','Ezekiel':'Ezek','Daniel':'Dan',
  'Hosea':'Hos','Joel':'Jl','Amos':'Am','Obadiah':'Ob','Jonah':'Jon',
  'Micah':'Mic','Nahum':'Nah','Habakkuk':'Hab','Zephaniah':'Zeph',
  'Haggai':'Hag','Zechariah':'Zech','Malachi':'Mal',
  'Matthew':'Mt','Mark':'Mk','Luke':'Lk','John':'Jn','Acts':'Acts',
  'Romans':'Rom','1 Corinthians':'1 Cor','2 Corinthians':'2 Cor',
  'Galatians':'Gal','Ephesians':'Eph','Philippians':'Phil','Colossians':'Col',
  '1 Thessalonians':'1 Th','2 Thessalonians':'2 Th','1 Timothy':'1 Tim',
  '2 Timothy':'2 Tim','Titus':'Tit','Philemon':'Philem','Hebrews':'Heb',
  'James':'Jas','1 Peter':'1 Pet','2 Peter':'2 Pet','1 John':'1 Jn',
  '2 John':'2 Jn','3 John':'3 Jn','Jude':'Jude','Revelation':'Rev',
  'Tobit':'Tob','Judith':'Jdt','Wisdom':'Wis','Wisdom of Solomon':'Wis',
  'Sirach':'Sir','Baruch':'Bar','1 Maccabees':'1 Macc','2 Maccabees':'2 Macc',
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
  // Strip leading "or " / "Or " from alternative reading options.
  citation = citation.replace(/^[Oo]r\s+/, '');
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

  const rawAbbrev = (prefix + s.slice(0, numStart)).trim();
  // Try BAS abbreviation first, then full book name → abbreviation fallback.
  const abbrev = ABBREV_TO_FILE[rawAbbrev] ? rawAbbrev : (FULL_TO_ABBREV[rawAbbrev] || rawAbbrev);
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

export function renderAlternatives(seg, shared, contextKey, verse = false) {
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
    return `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${i}" aria-labelledby="${idBase}-tab-${i}" data-idx="${i}">${sourceHtml}${renderSegments(g.segments, shared, verse)}</div>`;
  }).join('');
  return `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabsHtml}</div>${panelsHtml}</div>`;
}

// BUG-30: the printed book italicises the placeholder N (e.g. "May N our bishop
// and all bishops"); a plain capital "N" reads as a typo. Applied to
// already-escaped leader/response HTML only — the 2 standalone-N instances in
// offices.json are both this placeholder.
function italicisePlaceholderN(html) {
  return html.replace(/\bN\b(?=[ ,.])/g, '<em>N</em>');
}

export function renderSegments(segs, shared, verse = false) {
  if (!segs || !segs.length) return '';
  return segs.map(seg => {
    let contextKey;
    if (seg.type === 'shared' && shared) { contextKey = seg.key; seg = shared[seg.key] || seg; }
    if (seg.type === 'alternatives') return renderAlternatives(seg, shared, contextKey, verse);
    if (seg.type === 'rubric' && INTERCESSIONS_RE.test(seg.text || '')) return INTERCESSIONS_CONDENSED;
    if (seg.type === 'rubric' && SKIP_RUBRICS.test(seg.text || '')) return '';
    const text = seg.text || '';
    if (seg.type === 'rubric') {
      const cls = BOOK_ONLY_RUBRICS.test(text) ? 'seg-rubric rubric-book-only' : 'seg-rubric';
      return `<p class="${cls}">${esc(text)}</p>`;
    }
    if (seg.type === 'label')    return `<p class="seg-label">${esc(text)}</p>`;
    if (seg.type === 'response') return `<p class="seg-response">${italicisePlaceholderN(bindMidpoints(formatLiturgicalText(text)))}</p>`;
    const formatted = verse ? formatLiturgicalText(text) : esc(text);
    const amenMatch = seg.type === 'leader' && text.match(/^([\s\S]+)\s(Amen\.)$/);
    if (amenMatch) {
      const amenBody = verse ? formatLiturgicalText(amenMatch[1]) : esc(amenMatch[1]);
      return `<p class="seg-leader">${italicisePlaceholderN(bindMidpoints(amenBody))}</p>`
           + `<p class="seg-response">Amen.</p>`;
    }
    return `<p class="seg-leader">${italicisePlaceholderN(bindMidpoints(formatted))}</p>`;
  }).join('');
}

export function renderSubsection(label, segs, shared, verse = false) {
  if (!segs || !segs.length) return '';
  return `<h3 class="office-subsection-title">${esc(label)}</h3><div class="liturgy">${renderSegments(segs, shared, verse)}</div>`;
}

export function lessonHtml(lesson, shared, form) {
  const rawCitation = typeof lesson === 'object' ? lesson.citation : lesson;
  const optional = typeof lesson === 'object' && lesson.optional;
  const displayCitation = expandCitationForDisplay(rawCitation);
  const display = optional ? `(${displayCitation})` : displayCitation;
  const preambleRubric = `<p class="seg-rubric rubric-book-only">A Reading from the appointed lectionary is read.</p>`;
  const reflectionRubric = `<p class="seg-rubric rubric-book-only">After a period of silent reflection one of the following is said.</p>`;
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

const _NUM_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six'];

// BUG-28: when the lectionary says pick N of M readings, the app renders all M
// (it has no pick-interaction). This rubric is load-bearing, not book-only —
// the reader must know only N are appointed. Returns '' when there's nothing to pick.
export function lessonsPickText(pick, total) {
  if (!pick || pick >= total) return '';
  const p = _NUM_WORDS[pick] || String(pick);
  const t = _NUM_WORDS[total] || String(total);
  const cap = p.charAt(0).toUpperCase() + p.slice(1);
  return `${cap} of the following ${t} readings are read.`;
}

export function lessonsPickRubricHtml(pick, total) {
  const text = lessonsPickText(pick, total);
  return text ? `<p class="seg-rubric">${esc(text)}</p>` : '';
}

// ── Text-mode rendering ──────────────────────────────────────────────────────

/**
 * Walk segments depth-first, resolving shared refs and recursing into
 * alternatives. Yields leaf-level display items.
 *
 * @generator
 * @param {Array} segs
 * @param {Object} shared
 * @yields {Object} {type:'segment', seg} | {type:'enter_alt', groups} | {type:'exit_alt'}
 *                | {type:'enter_group', group} | {type:'exit_group'}
 */
export function* walkSegments(segs, shared) {
  if (!segs) return;
  if (!Array.isArray(segs)) segs = [segs];
  for (const seg of segs) {
    if (seg.type === 'shared' && shared) {
      yield* walkSegments(shared[seg.key] || seg, shared);
      continue;
    }
    if (seg.type === 'alternatives') {
      yield { type: 'enter_alt', groups: seg.groups };
      for (const group of seg.groups) {
        yield { type: 'enter_group', group };
        yield* walkSegments(group.segments, shared);
        yield { type: 'exit_group' };
      }
      yield { type: 'exit_alt' };
      continue;
    }
    yield { type: 'segment', seg };
  }
}

/**
 * Render segments as structured text blocks.
 * @param {Array} segs
 * @param {Object} shared
 * @param {Object} [opts]
 * @param {boolean} [opts.verse=false] Preserve internal line breaks
 * @param {boolean} [opts.showLabel=false] Include canticle citations as headers
 * @param {RegExp} [opts.skipRubrics] Rubric patterns to omit entirely
 * @param {boolean} [opts.skipShortLabels=false] Inline Roman-numeral labels
 * @param {Object} [opts.condenseRubrics] Pattern→replacement map for rubric shorthand
 * @param {boolean} [opts.alleluia=false] Append Alleluia after each alt group
 * @returns {Array<{type:string, text:string}>}
 */
export function renderSegmentsText(segs, shared, opts = {}) {
  const blocks = [];
  let inAlt = false;
  for (const event of walkSegments(segs, shared)) {
    if (event.type === 'enter_alt') {
      inAlt = true;
      continue;
    }
    if (event.type === 'exit_alt') {
      inAlt = false;
      continue;
    }
    if (event.type === 'enter_group') {
      if (opts.showLabel && event.group.label && !SHORT_LABEL_RE.test(event.group.label)) {
        const cite = CANTICLE_SOURCE[event.group.label];
        blocks.push({ type: 'label', text: cite ? `${event.group.label} — ${cite}` : event.group.label });
      } else if (!opts.skipShortLabels && event.group.label) {
        blocks.push({ type: 'label', text: event.group.label });
      }
      continue;
    }
    if (event.type === 'exit_group') {
      if (opts.alleluia) blocks.push({ type: 'para', text: 'Alleluia.' });
      // Insert 'or' separator between groups (but not after the last)
      continue;
    }

    // Leaf segment
    const { seg } = event;
    const text = (seg.text || '').trim();
    if (!text) continue;

    if (seg.type === 'rubric') {
      // Check skip patterns
      if (opts.skipRubrics && opts.skipRubrics.test(text)) continue;
      // Check condense patterns
      if (opts.condenseRubrics) {
        for (const [pattern, replacement] of Object.entries(opts.condenseRubrics)) {
          if (text.includes(pattern)) {
            blocks.push({ type: 'rubric', text: replacement });
            continue;
          }
        }
        continue;
      }
      blocks.push({ type: 'rubric', text });
    } else if (seg.type === 'label') {
      blocks.push({ type: 'label', text });
    } else {
      // leader or response
      let formatted = opts.verse ? text : text.replace(/\n/g, ' ');
      // Italicise the liturgical "N" placeholder (Name) in text mode
      formatted = formatted.replace(/\bN\b(?=[ ,.])/g, '(N)');
      blocks.push({ type: 'para', text: formatted });
    }
  }
  return blocks;
}

/**
 * Join text blocks into a string with appropriate spacing.
 * Consecutive 'para' blocks are joined with '\n' (same paragraph).
 * Other block types get '\n\n' separation.
 */
export function blocksToString(blocks) {
  const parts = [];
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (b.type === 'rubric') {
      parts.push(`(${b.text})`);
    } else if (b.type === 'label') {
      parts.push(b.text);
    } else {
      parts.push(b.text);
    }
  }
  return parts.join('\n\n');
}

// ── Structured output for validation ───────────────────────────────────────

/**
 * Walk segments and emit a flat JSON array of annotated leaf items.
 * Each item has { type, text, section } — parseable without HTML.
 * Validators consume this output instead of parsing rendered HTML.
 *
 * @param {Object} form - office form data (from offices.json)
 * @param {Object} shared - _shared reference map
 * @returns {Array<{section:string, type:string, text:string}>}
 */
export function segmentsToJSON(form, shared) {
  const items = [];
  for (const [sectionKey, segs] of Object.entries(form)) {
    if (sectionKey.startsWith('_')) continue;
    if (sectionKey === 'title' || sectionKey === 'subtitle') continue;
    // Resolve shared refs at the top level (EP forms store opening_responses as {type:'shared',key:'...'})
    let resolved = segs;
    if (segs && typeof segs === 'object' && segs.type === 'shared' && shared) {
      resolved = shared[segs.key] || segs;
    }
    if (!Array.isArray(resolved)) continue;
    for (const event of walkSegments(resolved, shared)) {
      if (event.type === 'segment') {
        const seg = event.seg;
        if (seg.text && seg.text.trim()) {
          items.push({
            section: sectionKey,
            type: seg.type,
            text: seg.text.trim(),
          });
        }
      }
    }
  }
  return items;
}

/**
 * Extracts the Occasional Prayer page number from collect refs like:
 *   "344 or 8, 677 (The King)"     → "677"  (prayer-number,page format)
 *   "378 or 17, 680 (Labour Day)"  → "680"
 *   "365 or 413 or FAS 211"        → "413"  (bare page before another or/FAS)
 * Returns null when no secondary page is present.
 */
export function collectSecondaryPage(ref) {
  const s = ref.replace(/\([^)]*\)/g, '');
  let m = /\bor\s+\d+,\s+(\d+)/.exec(s);
  if (m) return m[1];
  m = /\bor\s+(\d{3,})\b/.exec(s);
  return m ? m[1] : null;
}

// ── Full-office structured output ─────────────────────────────────────────

function resolveSharedRef(field, shared) {
  if (field && typeof field === 'object' && field.type === 'shared' && shared)
    return shared[field.key] || field;
  return field;
}

function flattenSegs(segs, shared) {
  if (!segs) return [];
  const resolved = resolveSharedRef(segs, shared);
  const arr = Array.isArray(resolved) ? resolved : [];
  const items = [];
  for (const event of walkSegments(arr, shared)) {
    if (event.type === 'segment') {
      const seg = event.seg;
      if (seg.text && seg.text.trim()) {
        items.push({ section: '', type: seg.type, text: seg.text.trim() });
      }
    }
  }
  return items;
}

/**
 * Assemble section structure for a complete office.
 * Shared by renderOfficeJSON (validators) and app.js render() (browser HTML).
 * Returns the same structure regardless of consumer.
 *
 * @param {Object} cfg — see renderOfficeJSON for full schema
 * @returns {{ meta: Object, sections: Array<Object> }}
 */
export function assembleSections(cfg) {
  const { form, shared, officeData, officeType, season, weekIdx,
          fatsEntry, collects, collectRef, collectInline } = cfg;

  // Shared refs used across sections
  const doxology = shared && shared.doxology;
  const readingResponse = form && form.reading_response;

  const sections = [];

  // ── Gathering ──────────────────────────────────────────────────────
  const hasGathering = form && (
    form.opening_responses ||
    (form.thanksgiving_for_light && form.thanksgiving_for_light.length) ||
    (form.phos_hilaron && form.phos_hilaron.length) ||
    (form.invitatory && form.invitatory.length)
  );

  if (hasGathering) {
    const g = { name: 'Gathering', visible: true, subsections: [], dynamic: {} };

    const openingResolved = resolveSharedRef(form.opening_responses, shared);
    if (Array.isArray(openingResolved) && openingResolved.length) {
      g.subsections.push({
        label: 'Introductory Responses',
        segments: flattenSegs(form.opening_responses, shared),
      });
    }

    if (form.thanksgiving_for_light && form.thanksgiving_for_light.length) {
      g.subsections.push({
        label: 'Thanksgiving for Light',
        segments: flattenSegs(form.thanksgiving_for_light, shared),
      });
      g.dynamic.thanksgivingForLightPresent = true;
    }

    if (form.phos_hilaron && form.phos_hilaron.length) {
      const items = flattenSegs(form.phos_hilaron, shared);
      g.subsections.push({ label: 'Phos Hilaron', segments: items });
      g.dynamic.phosHilaronPresent = true;
    }

    if (form.invitatory && form.invitatory.length) {
      g.subsections.push({
        label: 'Invitatory Psalm',
        segments: flattenSegs(form.invitatory, shared),
      });
      g.dynamic.invitatory = { citation: form.invitatory[0] ? (form.invitatory[0].text || '').slice(0, 80) : '' };
    }

    sections.push(g);
  }

  // ── Proclamation ───────────────────────────────────────────────────
  const lessons = officeData.lessons || [];
  const psalms = officeData.psalms || [];
  const psalmSets = officeData.psalm_sets;

  const p = { name: 'Proclamation', visible: true, subsections: [], dynamic: {} };

  p.dynamic.psalms = psalms.length ? psalms.map(c => typeof c === 'object' ? c : { citation: c }) : undefined;
  p.dynamic.psalmSets = psalmSets
    ? psalmSets.map(set => set.map(c => typeof c === 'object' ? c : { citation: c }))
    : undefined;
  p.dynamic.psalmDoxologyPresent = !!(doxology && (psalms.length || (psalmSets && psalmSets.length)));
  p.dynamic.readings = lessons.map(l => ({
    citation: typeof l === 'object' ? l.citation : l,
    optional: !!(typeof l === 'object' && l.optional),
  }));
  p.dynamic.readingResponsePresent = !!(readingResponse);
  if (officeData.lessons_pick)
    p.dynamic.lessonsPick = { pick: officeData.lessons_pick, total: lessons.length };

  // Responsory
  if (form && form.responsory) {
    p.subsections.push({
      label: 'The Responsory',
      segments: flattenSegs(form.responsory, shared),
    });
  }

  // Canticle
  if (form && form.canticle) {
    p.subsections.push({
      label: 'The Canticle',
      segments: flattenSegs(form.canticle, shared),
    });
    // Extract the canticle label from the alternatives structure
    const canticleResolved = resolveSharedRef(form.canticle, shared);
    if (Array.isArray(canticleResolved) && canticleResolved.length) {
      const alt = canticleResolved.find(s => s.type === 'alternatives');
      if (alt && alt.groups && alt.groups[0]) {
        p.dynamic.canticleLabel = alt.groups[0].label || null;
      }
    }
  }

  sections.push(p);

  // ── Affirmation ────────────────────────────────────────────────────
  if (form && form.affirmation && form.affirmation.length) {
    const a = { name: 'Affirmation', visible: true, subsections: [], dynamic: {} };
    a.subsections.push({
      label: 'Affirmation of Faith',
      segments: flattenSegs(form.affirmation, shared),
    });
    a.dynamic.hasAffirmation = true;
    sections.push(a);
  }

  // ── Prayers ────────────────────────────────────────────────────────
  const hasPrayers = form && (
    (form.intercessions && form.intercessions.length) ||
    (form.litany && form.litany.length) ||
    (form.lords_prayer_intro && form.lords_prayer_intro.length) ||
    (form.seasonal_collects && form.seasonal_collects.length) ||
    officeData.collect ||
    (fatsEntry && fatsEntry.collect) ||
    collectInline
  );

  if (hasPrayers) {
    const pr = { name: 'Prayers', visible: true, subsections: [], dynamic: {} };

    // Intercessions
    if (form.intercessions && form.intercessions.length) {
      const items = flattenSegs(form.intercessions, shared);
      pr.subsections.push({ label: 'Intercessions and Thanksgivings', segments: items });
      pr.dynamic.intercessionsCount = items.length;
    }

    // Litany
    if (form.litany && form.litany.length) {
      const items = flattenSegs(form.litany, shared);
      pr.subsections.push({ label: 'The Litany', segments: items });
      pr.dynamic.litanyLeaderCount = items.filter(i => i.type === 'leader').length;
      pr.dynamic.litanyResponseCount = items.filter(i => i.type === 'response').length;
    }

    // Collect
    const seasonalSegs = form.seasonal_collects
      ? filterSeasonalCollects(form.seasonal_collects, weekIdx || 0)
      : [];
    const seasonalItems = flattenSegs(seasonalSegs, shared);
    pr.dynamic.collectSeasonalItems = seasonalItems;

    if (collectRef) {
      pr.dynamic.collectRef = collectRef;
      // Occasional Prayer alternate from collect ref (e.g. "344 or 8, 677")
      const occPage = collectSecondaryPage(collectRef);
      if (occPage && collects && collects[occPage]) {
        pr.dynamic.collectOccasional = {
          page: parseInt(occPage),
          name: collects[occPage].name || '',
          text: collects[occPage].text || '',
        };
      }
    }
    if (collectInline) {
      pr.dynamic.collectInline = { name: collectInline.name, text: collectInline.text };
    }
    if (fatsEntry && fatsEntry.collect) {
      pr.dynamic.collectFatsFallback = true;
    }

    // Lord's Prayer
    if (form.lords_prayer_intro && form.lords_prayer_intro.length) {
      pr.subsections.push({
        label: "The Lord's Prayer",
        segments: flattenSegs(form.lords_prayer_intro, shared),
      });
      pr.dynamic.lordsPrayerPresent = true;
    }

    sections.push(pr);
  }

  // ── Sending ────────────────────────────────────────────────────────
  if (form && form.dismissal && form.dismissal.length) {
    const s = { name: 'Sending', visible: true, subsections: [], dynamic: {} };
    const items = flattenSegs(form.dismissal, shared);
    s.subsections.push({ label: 'The Dismissal', segments: items });
    s.dynamic.dismissalContainsAmen = items.some(i => i.text.includes('Amen'));
    sections.push(s);
  }

  return {
    meta: {
      officeType: officeType,
      season: season,
      formKey: form._key || '',
      weekIdx: weekIdx || 0,
      hasAlternateObservance: !!(officeData.alternate),
    },
    sections,
  };
}

/**
 * Full office as structured JSON — thin wrapper around assembleSections
 * for consumers that want the data directly (validators, audit tools).
 */
export function renderOfficeJSON(cfg) {
  return assembleSections(cfg);
}
