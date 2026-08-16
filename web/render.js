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

  // Affirmations of Faith — rendered via renderAlternatives but not canticles.
  // Included with empty citations to suppress CANTICLE_SOURCE warning.
  "The Apostles\u2019 Creed": '',
  'Hear, O Israel': '',
};

// Rubrics suppressed as duplicates (ADR 0013): each is already emitted as the
// heading named in `duplicate` by renderSubsection / the app, in the same view
// and mode. The exemption lives at the thing it exempts: validate_render.cjs
// asserts the duplicate heading is in the rendered DOM, so a suppression whose
// heading stops being emitted fails rather than silently swallowing the rubric.
export const SKIP_RUBRICS = [
  { re: /^The Lord['\u2019]?s Prayer\.?\s*$/i, duplicate: "The Lord's Prayer" },
  { re: /^The Responsory is said or sung\.$/i, duplicate: 'The Responsory' },
  { re: /^The Litany is said or sung\.$/i, duplicate: 'The Litany' },
];

export function isSkippedRubric(text) {
  return SKIP_RUBRICS.some(e => e.re.test(text || ''));
}

// Exported so app.js can use them in collectToggleHtml without re-declaration.
export const SC_HEADER = /^Additional\s+intercessions/i;
export const SC_FOOTER = /^the\s+Lord['’]s\s+Prayer/i;

// ── App-authored liturgical text register (ADR 0015) ─────────────────────────
// Rubrics the app authors rather than extracts, held to the same provenance
// standard as extracted text. Each entry records what the text is and what
// authorizes it; `source` uses the manifest vocabulary (PERMITTED_SOURCES in
// tools/validate_corrections.py). Call sites read from here rather than
// re-declaring the string.
export const LITURGICAL_TEXT_REGISTER = {
  // Nine of the ten entries ADR 0015 registered are gone, and the reason is the
  // same for all of them: #84 recovered the printed rubrics that the old
  // running-header filter had been swallowing, so the sentences the app was
  // authoring turned out to be book text we simply could not see.
  //
  //   readingIntro, reflectionPrompt -> form.reading_rubrics
  //   psalmIntro, psalmsIntro,
  //     singlePsalmIntro, psalmEnd   -> form.psalm_rubrics
  //   affirmationTransition          -> the canticle section trailer
  //   litanyTransition               -> the affirmation section trailer
  //   intercessionsPrompt            -> retired earlier, by ADR 0013 (#60)
  //
  // Where review had settled a wording (ADR 0019 items 3, 4 and 6), the
  // settled text now reaches the page as a correction on the extracted rubric
  // — `adr0019-*` in data/corrections.json — rather than as a second string
  // rendered beside the book's. That is the point: there is one sentence per
  // rubric now, in one place, with the divergence from the page recorded in
  // the manifest where it can be audited against the source.
  //
  // What is left is the one string with no printed sentence behind it at all.
  readingsPick: {
    text: 'One or two of the following readings are read.',
    source: 'upstream-review',
    note: 'ADR 0014/#63: replaces the app-computed per-count sentence (BUG-28) with the approved fixed form — one mechanism, not two adjacent ones.',
  },
};

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
  // The word class excludes '>' as well as whitespace: this runs over HTML, and
  // a bare \S+ backtracks past a tag's closing '>' into its attributes whenever
  // the starred word is the first in its element (`<span class="verse-line">Hallelujah! *`),
  // splicing the markup into the output as visible text. Escaped text never
  // contains a literal '>', so excluding it cannot truncate a real word.
  return html.replace(/([^\s>]+)(\s*)\*/g, (_, word, sp) =>
    `<span class="midpoint-group">${word}${sp}<span class="midpoint">*</span></span>`);
}

// A blank line in the source is a stanza break. It gets a box of its own: the
// lines are block spans, and an empty one generates no line box, so a break
// rendered as an empty line would have zero height (#119).
const STANZA_BREAK = '<span class="stanza-break"></span>';
const BREAK = Symbol('stanza break');

// Runs of blank lines collapse to one break and the ends carry none, so a stray
// blank in the data cannot open a double gap or push the first line down. Both
// said-text paths split here, so they break in the same places (#121).
function stanzaLines(text) {
  const lines = [];
  for (const raw of text.split('\n')) {
    if (raw.trim() === '') {
      if (lines.length && lines[lines.length - 1] !== BREAK) lines.push(BREAK);
    } else {
      lines.push(raw);
    }
  }
  if (lines[lines.length - 1] === BREAK) lines.pop();
  return lines;
}

// Prose said texts keep their line breaks through `white-space: pre-wrap`
// rather than one block per line, so a blank line already renders — but as a
// line box, which is the reading face's line height rather than the stanza
// token. The break element is the same size wherever the text is set.
export function formatProseText(text) {
  const lines = stanzaLines(text);
  return lines.reduce((out, l, i) => {
    if (l === BREAK) return out + STANZA_BREAK;
    return out + (i > 0 && lines[i - 1] !== BREAK ? '\n' : '') + esc(l);
  }, '');
}

// Verse second-halves (psalm/canticle/invitatory line-pairs) are physically
// indented in the source. Two independent signals mark a continuation line:
// a leading space (extraction's geometry-derived indent marker — see
// spans_to_typed_lines in tools/extract_office_styles.py) or the previous
// line ending in the psalter's "*" mid-verse marker (canticle/psalm text,
// where the marker itself survives but the leading space does not).
// `prefix` is trusted HTML placed inside the first line's block — a psalm verse
// number belongs on the same line as the text it numbers, and the lines are
// block boxes, so an inline prefix outside them would sit on a line of its own.
export function formatLiturgicalText(text, prefix = '') {
  // Dropping the leading blanks also keeps `prefix` on a real line.
  const lines = stanzaLines(text);
  if (lines.length < 2) return prefix + esc(lines[0] ?? '');
  let prevEndsWithStar = false;
  return lines.map((l, i) => {
    // A break interrupts the caesura pairing: the line after it starts a new
    // stanza, so it is a full verse however the line before it ended.
    if (l === BREAK) { prevEndsWithStar = false; return STANZA_BREAK; }
    const hasLeadingSpace = l.startsWith(' ');
    const indented = hasLeadingSpace || prevEndsWithStar;
    const clean = hasLeadingSpace ? l.slice(1) : l;
    prevEndsWithStar = clean.trimEnd().endsWith('*');
    const html = (i === 0 ? prefix : '') + esc(clean);
    // One block per line rather than <br>-joined spans, so each line can carry
    // a hanging indent: a wrapped full verse tucks under itself instead of
    // landing at the half-verse offset and imitating one.
    return indented
      ? `<span class="verse-cont">${html}</span>`
      : `<span class="verse-line">${html}</span>`;
  }).join('');
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

// The books whose verses are keyed under a single chapter, taken from the
// bundled corpus — every other book in data/translations/kjv/ has more.
export const SINGLE_CHAPTER_BOOKS = new Set([
  '2 John', '3 John', 'Jude', 'Obadiah', 'Philemon',
]);

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
  const abbrev = ABBREV_TO_FILE[rawAbbrev] ? rawAbbrev : rawAbbrev;
  let rest = s.slice(numStart).trim();
  const file = ABBREV_TO_FILE[abbrev];
  if (!file) return null;
  // A colonless range is ambiguous, and the book is what resolves it: in a
  // single-chapter book the numbers are verses ("Jude 17-25"), anywhere else
  // they are a whole chapter ("Mt 5"). Only the first case is handled here —
  // those verses are keyed under chapter 1, so lookup needs the chapter
  // supplied and the flag lets display strip it again (#110). A whole chapter
  // falls through with its range intact, for parseRanges to express (#112).
  const chapterInferred = SINGLE_CHAPTER_BOOKS.has(file) && rest !== '' && !rest.includes(':');
  if (chapterInferred) rest = '1:' + rest;
  return { abbrev, file, rest, chapterInferred };
}

export function expandCitationForDisplay(rawCitation) {
  return rawCitation.split(' or ').map(part => {
    const p = parseCitation(part.trim());
    if (!p) return part.trim();
    const rest = p.chapterInferred ? p.rest.replace(/^1:/, '') : p.rest;
    return `${p.file}${rest ? ' ' + rest : ''}`;
  }).join(' or ');
}

/**
 * Parse a chapter:verse range string (e.g. "1:1-10, 2:3—3:5") into an array of range objects.
 * Handles em-dash cross-chapter ranges and comma-delimited multi-ranges.
 * @param {string} s - verse range string after the book abbreviation
 * @returns {Array<{startCh, startV, endCh, endV}>}
 */
export function parseRanges(s) {
  s = s.replace(/—/g, '§');
  const parts = s.split('§');
  const ranges = [];
  let currentCh = 0;
  for (let pi = 0; pi < parts.length; pi++) {
    const subParts = parts[pi].trim().split(',');
    for (let si = 0; si < subParts.length; si++) {
      let sub = subParts[si].trim().replace(/^\(|\)$/g, '');
      if (!sub) continue;
      const colon = sub.indexOf(':');
      if (colon >= 0) { currentCh = parseInt(sub.slice(0, colon)); sub = sub.slice(colon + 1); }
      if (!currentCh) continue;
      const isCrossChapterStart = pi < parts.length - 1 && si === subParts.length - 1;
      const [startV, endV] = parseVerseRange(sub);
      if (!startV) continue;
      if (isCrossChapterStart) {
        const [endCh, endVerse] = parseChapterVerse(parts[pi + 1].trim(), currentCh);
        ranges.push({ startCh: currentCh, startV, endCh, endV: endVerse });
        parts[pi + 1] = consumeLeadingRef(parts[pi + 1]);
        currentCh = endCh;
      } else {
        ranges.push({ startCh: currentCh, startV, endCh: currentCh, endV });
      }
    }
  }
  return ranges;
}

export function parseVerseRange(s) {
  s = s.trim();
  const dash = s.indexOf('-');
  if (dash >= 0) return [parseVerseNum(s.slice(0, dash)), parseVerseNum(s.slice(dash + 1))];
  const v = parseVerseNum(s);
  return [v, v];
}

function parseVerseNum(s) {
  const n = parseInt(s.trim().replace(/[abc]$/, ''));
  return isNaN(n) ? 0 : n;
}

export function parseChapterVerse(s, defaultCh) {
  s = s.trim();
  const comma = s.indexOf(',');
  if (comma >= 0) s = s.slice(0, comma).trim();
  const colon = s.indexOf(':');
  if (colon >= 0) return [parseInt(s.slice(0, colon)), parseVerseNum(s.slice(colon + 1))];
  return [defaultCh, parseVerseNum(s)];
}

function consumeLeadingRef(s) {
  s = s.trim();
  const comma = s.indexOf(',');
  return comma >= 0 ? s.slice(comma + 1).trim() : '';
}

/**
 * Extract verse objects with chapter info for a single range from a loaded book JSON.
 * @returns {Array<{ch:number, v:number, text:string}>}
 */
export function extractVersesWithChapter(book, range) {
  const lines = [];
  for (let ch = range.startCh; ch <= range.endCh; ch++) {
    const chData = book[String(ch)];
    if (!chData) continue;
    const startV = ch === range.startCh ? range.startV : 1;
    const maxV = Math.max(...Object.keys(chData).map(Number));
    const endV = ch === range.endCh ? range.endV : maxV;
    for (let v = startV; v <= endV; v++) {
      if (chData[String(v)] !== undefined) lines.push({ ch, v, text: chData[String(v)] });
    }
  }
  return lines;
}

/**
 * Parse a psalm citation like "23" or "119:1-24" into a number + optional verse range.
 * @param {string} c
 * @returns {{num: number, start: number|null, end: number|null}}
 */
export function parsePsalmCitation(c) {
  const colon = c.indexOf(':');
  if (colon < 0) return { num: parseInt(c), start: null, end: null };
  const num = parseInt(c.slice(0, colon));
  const range = c.slice(colon + 1);
  const dash = range.indexOf('-');
  if (dash < 0) { const v = parseInt(range); return { num, start: v, end: v }; }
  return { num, start: parseInt(range.slice(0, dash)), end: parseInt(range.slice(dash + 1)) };
}

// ── Collect lookup ──────────────────────────────────────────────────────────────

// Mirrors Go's extractFirstPage: "344 (Eve of Easter VII)" → "344"
export function collectPageNum(ref) {
  const m = /\d+/.exec(ref);
  return m ? m[0] : null;
}

export function lookupCollect(collects, ref) {
  if (!ref) return null;
  const page = collectPageNum(ref);
  return page ? (collects[page] || null) : null;
}

// ── Rendering ─────────────────────────────────────────────────────────────────

// Monotonic ID salt: keeps tab/panel IDs unique when the same contextKey
// renders twice in one document (two lessons → 'reading_response', primary
// + alternate → 'doxology'). stateKey/data-key stay shared so cross-block
// tab sync and localStorage persistence are unchanged.
let _altUid = 0;

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
  const idBase = stateKey.replace(/[^a-zA-Z0-9-]/g, '_') + '-' + (++_altUid);
  // One layout for every label length: a wrapping row of pills, each sized by
  // its own label. The stacked variant and the 34-character truncation both
  // existed to fit labels into an equal-width segmented track; there is no
  // track any more, so a long name wraps the row instead of losing its tail —
  // the names are the book's, and "A Song of Jerusalem Our Mo…" is worse than
  // a second line.
  const tabsHtml = seg.groups.map((g, i) => {
    const label = g.label || '';
    const isActive = i === activeIdx;
    return `<button class="alt-tab${isActive ? ' alt-tab-active' : ''}" role="tab" aria-selected="${isActive}" aria-controls="${idBase}-panel-${i}" id="${idBase}-tab-${i}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(label)}</button>`;
  }).join('');
  const panelsHtml = seg.groups.map((g, i) => {
    let sourceHtml = '';
    if (!SHORT_LABEL_RE.test(g.label.trim())) {
      const citation = CANTICLE_SOURCE[g.label];
      if (citation === undefined) console.warn('CANTICLE_SOURCE missing entry for:', g.label);
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
    if (seg.type === 'rubric' && isSkippedRubric(seg.text)) return '';
    const text = seg.text || '';
    if (seg.type === 'rubric') {
      return `<p class="seg-rubric">${esc(text)}</p>`;
    }
    if (seg.type === 'label')    return `<p class="seg-label">${esc(text)}</p>`;
    if (seg.type === 'response') return `<p class="seg-response">${italicisePlaceholderN(bindMidpoints(formatLiturgicalText(text)))}</p>`;
    const formatted = verse ? formatLiturgicalText(text) : formatProseText(text);
    const amenMatch = seg.type === 'leader' && text.match(/^([\s\S]+)\s(Amen\.)$/);
    if (amenMatch) {
      const amenBody = verse ? formatLiturgicalText(amenMatch[1]) : formatProseText(amenMatch[1]);
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

// form.invitatory's extracted "label" segment carries the PDF's full heading
// ("Invitatory Psalm: Psalm 95:1–7") — see issue #1. The subsection already gets an "Invitatory Psalm"
// title bar (matching Introductory Responses etc.), so strip the redundant
// prefix here and let just the citation render as the italic seg-label line.
const INVITATORY_LABEL_PREFIX = /^Invitatory Psalm:\s*/i;

export function invitatorySegments(form) {
  const segs = form.invitatory;
  if (!segs || !segs.length) return segs;
  return segs.map(seg =>
    seg.type === 'label' ? { ...seg, text: seg.text.replace(INVITATORY_LABEL_PREFIX, '') } : seg
  );
}

// Same treatment as invitatorySegments above: form.phos_hilaron's label segment
// carries a redundant "The Evening Hymn:"/"Evening Hymn:" prefix once the
// subsection gets its own "Evening Hymn" title bar (matching Introductory
// Responses / Invitatory Psalm) — strip it so just the hymn's title quote
// renders as the italic seg-label line.
const EVENING_HYMN_LABEL_PREFIX = /^(?:The )?Evening Hymn:\s*/i;

export function phosHilaronSegments(form) {
  const segs = form.phos_hilaron;
  if (!segs || !segs.length) return segs;
  return segs.map(seg =>
    seg.type === 'label' ? { ...seg, text: seg.text.replace(EVENING_HYMN_LABEL_PREFIX, '') } : seg
  );
}

// Same family as the two above, but the label drops entirely rather than being
// trimmed: form.psalm_rubrics/reading_rubrics carry the extracted heading "The
// Psalm"/"The Reading" (#84), which is exactly the subsection title both
// renderers already emit — nothing survives a prefix strip. Every consumer of
// these blocks must go through here, or the title prints twice.
export function rubricBlockSegments(segs) {
  if (!segs || !segs.length) return segs;
  return segs.filter(seg => seg.type !== 'label');
}

// The Psalm and Reading blocks are not preambles: the book prints their
// rubrics on either side of the content, and each rubric says which side it
// belongs on. Rendering a block whole puts "At the end of the Psalm one of the
// following may be said or sung." above the psalm it follows, and leaves the
// Gloria with nothing introducing it. Both renderers split them here rather
// than each keeping its own idea of the order (ADR 0004).
const PSALM_DOXOLOGY_CUE = /^(?:At the end of|After) the Psalm/i;
const READING_HANDOFF    = /^(?:Morning|Evening) Prayer continues with the Reading\./i;
const READING_TRANSITION = /^(?:(?:Morning|Evening) Prayer continues with the Responsory|If two Readings are read)/i;

const split = (segs, tests) => {
  const rest = rubricBlockSegments(segs) || [];
  const out = tests.map(re => rest.filter(s => re.test((s.text || '').trim())));
  out.push(rest.filter(s => !tests.some(re => re.test((s.text || '').trim()))));
  return out;
};

/** → { intro, doxologyCue } — the sentence above the psalms, and the cue that
 *  introduces the Gloria printed after them. */
export function splitPsalmRubrics(segs) {
  const [doxologyCue, intro] = split(segs, [PSALM_DOXOLOGY_CUE]);
  return { intro, doxologyCue };
}

/** → { handoff, intro, after } — the hand-off printed at the foot of the Psalm
 *  block, the sentence above the reading, and the transitions that follow it. */
export function splitReadingRubrics(segs) {
  const [handoff, after, intro] = split(segs, [READING_HANDOFF, READING_TRANSITION]);
  return { handoff, intro, after };
}

export function lessonHtml(lesson, shared, form) {
  const rawCitation = typeof lesson === 'object' ? lesson.citation : lesson;
  const optional = typeof lesson === 'object' && lesson.optional;
  const displayCitation = expandCitationForDisplay(rawCitation);
  const display = optional ? `(${displayCitation})` : displayCitation;
  // The rubrics that introduce the reading and the silent-reflection prompt
  // are extracted book text since #84 and render with form.reading_rubrics —
  // they must not also be emitted per-lesson here.
  if (!form || !form.reading_response) console.warn('lessonHtml: no reading_response on form, using fallback');
  let readingResponse = (form && form.reading_response) || READING_RESPONSE;
  if (readingResponse?.type === 'shared' && shared) {
    readingResponse = shared[readingResponse.key] || READING_RESPONSE;
  }
  const responseHtml = `<div class="liturgy">${renderAlternatives(readingResponse, shared, 'reading_response')}</div>`;
  return `<h3 class="reading-heading">The Reading: ${esc(display)}</h3>`
    + `<div class="scripture-placeholder" data-citation="${esc(rawCitation)}"><p class="loading">Loading…</p></div>`
    + responseHtml;
}

// When the lectionary says pick N of M readings, the app now offers a tab
// selector over the readings (ADR 0014/#63) instead of silently rendering
// all M; this rubric is the fixed head-of-section text that announces the
// choice. Load-bearing, not book-only — the reader must know a choice
// exists. Returns '' when there's nothing to pick.
export function lessonsPickText(pick, total) {
  if (!pick || pick >= total) return '';
  return LITURGICAL_TEXT_REGISTER.readingsPick.text;
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
 * @param {boolean} [opts.showLabel=false] Include canticle citations as headers
 * @param {boolean} [opts.skipShortLabels=false] Inline Roman-numeral labels
 * @param {boolean} [opts.alleluia=false] Append Alleluia after each alt group
 * @returns {Array<{type:string, text:string}>}
 */
export function renderSegmentsText(segs, shared, opts = {}) {
  const blocks = [];
  for (const event of walkSegments(segs, shared)) {
    if (event.type === 'enter_alt') {
      continue;
    }
    if (event.type === 'exit_alt') {
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
      // One suppression allowlist, shared with renderSegments — ADR 0004
      // requires the two modes to agree, and a rule set passed per caller
      // cannot be one policy. The options this replaces (skipRubrics,
      // condenseRubrics) also dropped every rubric matching no condense
      // pattern, so the callers that set them rendered 14 of 321 (#58).
      // ADR 0013 (#59) deleted BOOK_ONLY_RUBRICS, so the two modes now share
      // the same SKIP_RUBRICS allowlist.
      if (isSkippedRubric(text)) continue;
      blocks.push({ type: 'rubric', text });
    } else if (seg.type === 'label') {
      blocks.push({ type: 'label', text });
    } else {
      // leader or response
      // Every newline surviving extraction is a break the book prints: forced
      // column wraps are joined at extraction time, so a \n here is always
      // deliberate and must never be flattened. This used to be opt-in via
      // opts.verse, which left the CLI and the QA tools showing verse as prose
      // and unable to see a whole class of lineation bug (#43).
      let formatted = text;
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

// ── For All The Saints (FATS) lookup ─────────────────────────────────────────

// Known name mismatches between lectionary and FATS keys. Add entries as discovered.
export const FATS_ALIASES = {};

const RE_ESCAPE = /[.*+?^${}()|[\]\\]/g;

/**
 * Every FATS key the name contains as a whole name, with where it starts (#136).
 * Whole-name, so `Richard` is not found inside `Richard Hooker`'s surname; a
 * key is a person, not a string.
 */
function fatsMatches(keys, needle) {
  const hits = [];
  for (const key of keys) {
    const pattern = key.toLowerCase().replace(RE_ESCAPE, '\\$&');
    const m = new RegExp(`(^|[^\\p{L}])(${pattern})([^\\p{L}]|$)`, 'u').exec(needle);
    if (m) hits.push({ key, at: m.index });
  }
  return hits;
}

/**
 * The FATS entry for a saint's name, or null (#136).
 *
 * Two keys can both appear in one name — `Richard` and `Richard Hooker` — and
 * the earlier-starting one is the person the day is named for, with the longer
 * winning where both start together. Taking whichever came first in the file
 * served Richard of Chichester's life on Richard Hooker's day, and Clement of
 * Rome's on Clement of Alexandria's, with nothing to say so.
 */
export function lookupFatsEntry(fats, name) {
  if (!fats || !name) return null;
  const keys = Object.keys(fats);
  const needle = (FATS_ALIASES[name] || name).toLowerCase();

  const exact = keys.find(k => k.toLowerCase() === needle);
  if (exact) return fats[exact];

  const hits = fatsMatches(keys, needle);
  if (hits.length) {
    hits.sort((a, b) => a.at - b.at || b.key.length - a.key.length
                                    || a.key.localeCompare(b.key));
    return fats[hits[0].key];
  }

  // The name is part of a longer entry title rather than the other way round —
  // the shortest such entry is the closest thing to the name asked for.
  const containing = keys.filter(k => k.toLowerCase().includes(needle));
  if (containing.length) {
    containing.sort((a, b) => a.length - b.length || a.localeCompare(b));
    return fats[containing[0]];
  }
  return null;
}

/**
 * The distinct people a name names, best key first for each (#136).
 *
 * Keys that overlap in the name are one person written more or less fully —
 * `Richard` inside `Richard Hooker` — and collapse to the fuller. Keys that
 * occupy different parts of it are different people, which is what makes a
 * name ambiguous rather than merely imprecise.
 */
export function fatsCandidates(fats, name) {
  if (!fats || !name) return [];
  const needle = (FATS_ALIASES[name] || name).toLowerCase();
  const hits = fatsMatches(Object.keys(fats), needle)
    .map(h => ({ ...h, end: h.at + h.key.length }))
    .sort((a, b) => a.at - b.at || b.key.length - a.key.length);

  const people = [];
  let reach = -1;
  for (const hit of hits) {
    if (hit.at >= reach) people.push(hit.key);
    reach = Math.max(reach, hit.end);
  }
  return people;
}

const RE_COMMEMORATION = /\((?:Com|Mem)([^:)]*):([^)]*)\)/g;

/**
 * The commemoration collects a ref names in parentheses (#135):
 *   "268 (Com: 434 or FAS 361)"        → [{ of: '', pages: ['434'] }]
 *   "336 (Mem: 432/3 or FAS 187)"      → [{ of: '', pages: ['432','433'] }]
 *   "388 (Com Wyclyf: 438/9 …) or (Com Hus: 436 …)"
 *                                      → [{of:'Wyclyf',pages:['438','439']},
 *                                         {of:'Hus',   pages:['436']}]
 *
 * On a commemoration the book names the day's collect and the commemoration's,
 * and this is the half collectPageNum cannot see — it stops at the first run
 * of digits. `438/9` is the printed shorthand for two facing pages and so for
 * two collects, Common of a Saint 1 and 2, which ADR 0014 says are offered
 * rather than chosen between. The `FAS nnn` alternative is deliberately not
 * returned: ADR 0020 keeps the For All the Saints collect a fallback and
 * never a peer.
 */
export function collectCommemorations(ref) {
  if (!ref) return [];
  const out = [];
  for (const m of String(ref).matchAll(RE_COMMEMORATION)) {
    const pages = [];
    for (const tok of m[2].split(/\bFAS\b/)[0].matchAll(/(\d+)(?:\/(\d+))?/g)) {
      pages.push(tok[1]);
      // "438/9" abbreviates 439 by its final digits, as the book prints it —
      // the tail replaces as many digits as it has. It can only abbreviate a
      // page it is shorter than, so a tail at least as long as the page it
      // follows is already the whole number ("99/100").
      if (tok[2]) {
        pages.push(tok[2].length >= tok[1].length
          ? tok[2]
          : tok[1].slice(0, tok[1].length - tok[2].length) + tok[2]);
      }
    }
    if (pages.length) out.push({ of: m[1].trim(), pages });
  }
  return out;
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
      const items = flattenSegs(invitatorySegments(form), shared);
      g.subsections.push({ label: 'Invitatory Psalm', segments: items });
      const labelSeg = items.find(s => s.type === 'label');
      g.dynamic.invitatory = { citation: labelSeg ? labelSeg.text : '' };
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

  // Psalm / Reading rubrics — the fixed text printed around the lectionary
  // content (#84). Both blocks stand ahead of the scripture they introduce:
  // the psalms and lessons are dynamic data here, not subsections, and app.js
  // renders both blocks before the readings for the same reason. Interleaving
  // each rubric with the content it sits beside on the page is #77.
  if (form && form.psalm_rubrics && form.psalm_rubrics.length) {
    p.subsections.push({
      label: 'The Psalm',
      segments: flattenSegs(rubricBlockSegments(form.psalm_rubrics), shared),
    });
  }

  if (form && form.reading_rubrics && form.reading_rubrics.length) {
    p.subsections.push({
      label: 'The Reading',
      segments: flattenSegs(rubricBlockSegments(form.reading_rubrics), shared),
    });
  }

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

  // ── Affirmation (subsection of Proclamation) ──────────────────────
  if (form && form.affirmation && form.affirmation.length) {
    p.subsections.push({
      label: 'Affirmation of Faith',
      segments: flattenSegs(form.affirmation, shared),
    });
    p.dynamic.hasAffirmation = true;
  }

  sections.push(p);

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
