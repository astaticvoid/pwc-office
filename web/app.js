'use strict';

// ── Data path ─────────────────────────────────────────────────────────────────
// Dev: python3 -m http.server 8080 from repo root, open /web/ — web/data symlink
// Prod: web/ synced to S3 bucket root, data/ at same root
const DATA = 'data';

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  date:        todayStr(),
  office:      defaultOffice(),
  translation: localStorage.getItem('pwc-translation') || 'nrsvue',
};

// Evening Prayer is said from ~5pm onward in Anglican practice.
function defaultOffice() {
  return new Date().getHours() >= 17 ? 'ep' : 'mp';
}

// ── Theme ─────────────────────────────────────────────────────────────────────

function initTheme() {
  const stored = localStorage.getItem('pwc-theme');
  if (stored) document.documentElement.setAttribute('data-theme', stored);
  // No stored pref = light (default; no attribute needed)
  updateThemeButton();
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('pwc-theme', next);
  updateThemeButton();
}

function updateThemeButton() {
  const btn = document.getElementById('theme-toggle');
  if (!btn) return;
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  btn.textContent = isDark ? '🌙' : '☀';
  btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
}

// ── In-memory fetch cache ─────────────────────────────────────────────────────

const _cache = {
  offices:  null, // Promise<object>
  collects: null, // Promise<object>
  bounds:   null, // Promise<object>
  psalter:  null, // Promise<object>  — full psalter keyed by psalm number string
  months:   {},   // 'YYYY-MM' → Promise<object>  — monthly lectionary dicts
  books:    {},   // 'kjv/Numbers' → Promise<object>
};

async function fetchOnce(key, url) {
  if (!_cache[key]) _cache[key] = fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  return _cache[key];
}

function fetchPsalm(num) {
  return fetchOnce('psalter', `${DATA}/psalter.json`)
    .then(psalter => {
      const ps = psalter[String(num)];
      if (!ps) throw new Error(`Psalm ${num} not found`);
      return ps;
    });
}

function fetchBook(translation, filename) {
  const k = `${translation}/${filename}`;
  if (!_cache.books[k]) _cache.books[k] = fetch(`${DATA}/translations/${translation}/${filename}.json`)
    .then(r => { if (!r.ok) throw new Error(`${filename}: ${r.status}`); return r.json(); });
  return _cache.books[k];
}

function fetchDay(dateStr) {
  const monthKey = dateStr.slice(0, 7); // 'YYYY-MM'
  if (!_cache.months[monthKey])
    _cache.months[monthKey] = fetch(`${DATA}/lectionary/${monthKey}.json`)
      .then(r => { if (!r.ok) throw new Error(`${monthKey}: ${r.status}`); return r.json(); });
  return _cache.months[monthKey].then(month => {
    const day = month[dateStr];
    if (!day) throw new Error(`${dateStr}: not found in ${monthKey}.json`);
    return day;
  });
}

// ── Collect lookup ────────────────────────────────────────────────────────────

// Mirrors Go's extractFirstPage: "344 (Eve of Easter VII)" → "344"
function collectPageNum(ref) {
  const m = /\d+/.exec(ref);
  return m ? m[0] : null;
}

function lookupCollect(collects, ref) {
  if (!ref) return null;
  const page = collectPageNum(ref);
  return page ? (collects[page] || null) : null;
}

// ── Season computation ────────────────────────────────────────────────────────

function parseDate(s) { return s ? new Date(s + 'T00:00:00Z') : null; }

function seasonOf(dateStr, bounds) {
  const d = parseDate(dateStr);
  if (parseDate(bounds.christmas_ii)   && d >= parseDate(bounds.christmas_ii))   return 'Christmas';
  if (parseDate(bounds.advent_ii)      && d >= parseDate(bounds.advent_ii))      return 'Advent';
  if (parseDate(bounds.all_saints)     && d >= parseDate(bounds.all_saints))      return 'AllSaints';
  if (parseDate(bounds.pentecost)      && d >= parseDate(bounds.pentecost))       return 'Pentecost';
  if (parseDate(bounds.easter)         && d >= parseDate(bounds.easter))          return 'Easter';
  if (parseDate(bounds.palm_sunday)    && d >= parseDate(bounds.palm_sunday))     return 'Passiontide';
  if (parseDate(bounds.ash_wednesday)  && d >= parseDate(bounds.ash_wednesday))   return 'Lent';
  if (parseDate(bounds.epiphany)       && d >= parseDate(bounds.epiphany))        return 'Epiphany';
  if (parseDate(bounds.christmas)      && d >= parseDate(bounds.christmas))       return 'Christmas';
  if (parseDate(bounds.advent_i)       && d >= parseDate(bounds.advent_i))        return 'Advent';
  return 'OrdinaryTime';
}

// Returns 0-based week index within the season (0 = first week, 1 = second, …).
function seasonWeekIndex(dateStr, season, bounds) {
  const d = parseDate(dateStr);
  const starts = {
    Easter: bounds.easter, Lent: bounds.ash_wednesday,
    Epiphany: bounds.epiphany, Christmas: bounds.christmas,
    AllSaints: bounds.all_saints, Advent: bounds.advent_i,
    Passiontide: bounds.palm_sunday, Pentecost: bounds.pentecost,
  };
  const start = parseDate(starts[season] || null);
  if (!start) return 0;
  return Math.floor((d - start) / (7 * 24 * 3600 * 1000));
}

// Filter seasonal_collects segments to the week matching weekIdx.
// Splits on rubrics matching /^\s*(The\s+)?Week\b/i; pre-group = week 0.
const WEEK_RUBRIC = /^\s*(?:The\s+)?Week\b/i;

function filterSeasonalCollects(segs, weekIdx) {
  const pre = [], groups = [];
  let cur = null;
  for (const seg of segs) {
    if (seg.type === 'rubric' && WEEK_RUBRIC.test(seg.text)) {
      if (cur !== null) groups.push(cur);
      cur = [seg];
    } else {
      if (cur === null) pre.push(seg);
      else cur.push(seg);
    }
  }
  if (cur !== null) groups.push(cur);

  if (!groups.length) return segs; // No weekly structure — show all.

  // General instruction rubrics (e.g. "Additional intercessions…") always appear.
  const preRubrics = pre.filter(s => s.type === 'rubric');
  const week0Content = pre.filter(s => s.type !== 'rubric');

  if (weekIdx <= 0) return [...preRubrics, ...week0Content];

  const g = groups[Math.min(weekIdx - 1, groups.length - 1)];
  return [...preRubrics, ...g];
}

// Returns the form key, mirroring Go's formKey + OrdinaryTime/Pentecost logic.
function formKey(season, officeType, weekday, rank) {
  let s = season.toLowerCase();
  if (s === 'pentecost' && rank !== 'principal_feast') s = 'ordinarytime';
  if (s === 'ordinarytime') {
    const days = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];
    s = 'ordinary-' + days[weekday];
  }
  return s + '-' + officeType;
}

// ── Liturgical colour → CSS hex ───────────────────────────────────────────────

const COLOUR_HEX = {
  'White':  '#c8b87a', 'Red':    '#8c2525', 'Green':  '#2d5a35',
  'Purple': '#5c3a8a', 'Rose':   '#b07a8a', 'Black':  '#2c2820', 'Gold': '#b8860b',
};

// ── Routing ───────────────────────────────────────────────────────────────────

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function parseHash(hash) {
  const m = /^#\/(\d{4}-\d{2}-\d{2})\/(mp|ep)$/.exec(hash);
  return m ? { date: m[1], office: m[2] } : null;
}

function hashFor(date, office) { return `#/${date}/${office}`; }

function offsetDate(dateStr, days) {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// ── HTML helpers ──────────────────────────────────────────────────────────────

function formatRank(rank) {
  if (!rank) return '';
  return rank.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Roman numerals and "Form X" labels don't need a repeated source heading inside the panel.
const SHORT_LABEL_RE = /^(?:Form\s+)?(?:I{1,3}|IV|V|VI{0,3}|IX|X)$/i;

// Biblical citations for canticles, shown below the canticle name in the panel.
const CANTICLE_SOURCE = {
  'Bless the Lord':                 'Daniel 3:57–88',
  'Great and Wonderful':            'Revelation 15:3–4',
  'Prayer of Habakkuk':             'Habakkuk 3:2–4, 13a, 15–19',
  'Song of Baruch':                 'Baruch 4:36–5:9',
  'Song of Christ the Servant':     'Isaiah 42:1–3, 6–7',
  'Song of Christ\'s Appearing':    '1 Timothy 3:16',
  'Song of Christ\'s Glory':        'Philippians 2:6–11',
  'Song of David':                  '1 Chronicles 29:10–13',
  'Song of Deliverance':            'Isaiah 12:1–6',
  'Song of Ezekiel':                'Ezekiel 36:24–28',
  'Song of Faith':                  '1 Timothy 3:16',
  'Song of God\'s Assembled':       'Isaiah 60:1–3, 11a, 14c, 18–19',
  'Song of God\'s Children':        'Romans 8:15–21, 28, 31b–32, 34–35, 37–39',
  'Song of God\'s Chosen One':      'Isaiah 42:1–4, 6–7',
  'Song of God\'s Grace':           'Ephesians 1:3–10',
  'Song of God\'s Love':            '1 John 4:7–8, 11–12, 16',
  'Song of Hannah':                 '1 Samuel 2:1–8',
  'Song of Humility':               'Philippians 2:6–11',
  'Song of Jerusalem Our Mother':   'Galatians 4:26; Revelation 21:3–5a',
  'Song of Jonah':                  'Jonah 2:2–9',
  'Song of Judith':                 'Judith 16:1–3, 11–15',
  'Song of Manasseh':               'Prayer of Manasseh',
  'Song of Mary':                   'Luke 1:46–55',
  'Song of Moses and Miriam':       'Exodus 15:1–11, 20–21',
  'Song of Peace':                  'Isaiah 26:1–4, 7–9, 12',
  'Song of Pilgrimage':             'Sirach 36:1–5, 10–11',
  'Song of Praise':                 'Daniel 3:52–57',
  'Song of Redemption':             'Colossians 1:13–20',
  'Song of Repentance':             'Prayer of Manasseh 1–2, 4, 6–7, 11–15',
  'Song of Tobit':                  'Tobit 13:1–4, 7–8',
  'Song of Wisdom':                 'Wisdom 10:15–19, 20b–21',
  'Song of Zechariah':              'Luke 1:68–79',
  'Song of the Blessed':            'Matthew 5:3–10',
  'Song of the Bride':              'Revelation 19:1–2, 5, 7, 9a',
  'Song of the Covenant':           'Jeremiah 31:10–14',
  'Song of the Heavenly City':      'Revelation 21:22–22:5',
  'Song of the Holy City':          'Revelation 21:2–4, 22–27',
  'Song of the Justified':          'Romans 8:29–32, 34–35, 37–39',
  'Song of the Lamb':               'Revelation 5:9–10, 13',
  'Song of the Lord\'s Anointed':   'Isaiah 11:1–2, 4a, 5–7',
  'Song of the New Creation':       'Isaiah 43:15–21',
  'Song of the New Jerusalem':      'Revelation 21:1–5',
  'Song of the Spirit':             'Revelation 22:12–17',
  'Song of the Wilderness':         'Isaiah 35:1–7, 10',
  'Song of the Word of the Lord':   'Isaiah 55:6–11',
};

function renderAlternatives(seg, shared, contextKey) {
  if (!seg.groups || !seg.groups.length) return '';
  // Use the shared block's semantic name when available; otherwise fingerprint
  // with each group's label + first word of first segment so that two different
  // alternatives blocks that happen to share the same Roman-numeral labels
  // (e.g. doxology vs berakah_blessings vs seasonal opening_responses)
  // each get their own localStorage slot.
  const stateKey = contextKey
    ? 'pwc-alt-' + contextKey
    : 'pwc-alt-' + seg.groups.map(g => {
        const first = g.segments && g.segments[0];
        const word  = first ? first.text.trim().split(/\s+/)[0] : '';
        return g.label + (word ? ':' + word : '');
      }).join('\x1f');
  const savedIdx  = parseInt(localStorage.getItem(stateKey) || '0');
  const activeIdx = Math.min(Math.max(0, savedIdx), seg.groups.length - 1);
  const tabsHtml = seg.groups.map((g, i) =>
    `<button class="alt-tab${i === activeIdx ? ' alt-tab-active' : ''}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(g.label)}</button>`
  ).join('');
  const panelsHtml = seg.groups.map((g, i) => {
    let sourceHtml = '';
    if (!SHORT_LABEL_RE.test(g.label.trim())) {
      const citation = CANTICLE_SOURCE[g.label];
      sourceHtml = `<p class="alt-source">${esc(g.label)}${citation ? ` — ${esc(citation)}` : ''}</p>`;
    }
    return `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" data-idx="${i}">${sourceHtml}${renderSegments(g.segments, shared)}</div>`;
  }).join('');
  return `<div class="alt-block"><div class="alt-tabs">${tabsHtml}</div>${panelsHtml}</div>`;
}

// Rubrics that are section-navigation cues in the printed book but are rendered
// as explicit headings/sections in the app — skip to avoid duplication.
const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$/i;

function formatLiturgicalText(text) {
  // For multi-sentence response text (creeds, LP, etc.), insert a visual paragraph
  // break wherever a sentence ends (. ; ? !) and the next line starts with a capital.
  const lines = text.split('\n');
  if (lines.length < 3) return esc(text);
  let html = '';
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) {
      const prevLine = lines[i - 1].trim();
      const curLine  = lines[i].trim();
      const sentenceEnd = /[.;?!]$/.test(prevLine);
      const capitalStart = /^[A-Z]/.test(curLine);
      html += (sentenceEnd && capitalStart) ? '<br><br>' : '<br>';
    }
    html += esc(lines[i]);
  }
  return html;
}

function renderSegments(segs, shared) {
  if (!segs || !segs.length) return '';
  return segs.map(seg => {
    let contextKey;
    if (seg.type === 'shared' && shared) { contextKey = seg.key; seg = shared[seg.key] || seg; }
    if (seg.type === 'alternatives') return renderAlternatives(seg, shared, contextKey);
    if (seg.type === 'rubric' && SKIP_RUBRICS.test(seg.text || '')) return '';
    const text = seg.text || '';
    if (seg.type === 'rubric')   return `<p class="seg-rubric">${esc(text)}</p>`;
    if (seg.type === 'response') return `<p class="seg-response">${formatLiturgicalText(text)}</p>`;
    return `<p class="seg-leader">${esc(text)}</p>`;
  }).join('');
}

function renderSubsection(label, segs, shared) {
  if (!segs || !segs.length) return '';
  return `<h3 class="office-subsection-title">${esc(label)}</h3><div class="liturgy">${renderSegments(segs, shared)}</div>`;
}

// ── Psalm parsing and rendering ───────────────────────────────────────────────

function parsePsalmCitation(c) {
  const colon = c.indexOf(':');
  if (colon < 0) return { num: parseInt(c), start: null, end: null };
  const num = parseInt(c.slice(0, colon));
  const range = c.slice(colon + 1);
  const dash = range.indexOf('-');
  if (dash < 0) { const v = parseInt(range); return { num, start: v, end: v }; }
  return { num, start: parseInt(range.slice(0, dash)), end: parseInt(range.slice(dash + 1)) };
}

function parsePsalmText(rawText) {
  const lines = rawText.split('\n');
  const verses = [];
  let cur = null;
  for (const line of lines) {
    const m = /^(\d+)\s{1,2}(.*)$/.exec(line);
    if (m) {
      if (cur) verses.push(cur);
      cur = { num: parseInt(m[1]), text: m[2] };
    } else if (cur) {
      cur.text += '\n' + line.replace(/^ /, '');
    }
  }
  if (cur) verses.push(cur);
  return verses;
}

function psalmPlaceholder(citation) {
  const citStr = typeof citation === 'object' ? citation.citation : String(citation);
  const optional = typeof citation === 'object' && citation.optional;
  const label = optional ? `[${citStr}]` : citStr;
  return `<div class="psalm-loading" data-citation="${esc(citStr)}"><p class="loading">Psalm ${esc(label)}…</p></div>`;
}

async function renderPsalm(citStr) {
  const ref = parsePsalmCitation(citStr);
  const data = await fetchPsalm(ref.num);
  const verses = parsePsalmText(data.text);
  const filtered = ref.start !== null ? verses.filter(v => v.num >= ref.start && v.num <= ref.end) : verses;
  const titleHtml = `<p class="psalm-title">Psalm ${data.number}${data.title ? ` — ${data.title}` : ''}</p>`;
  const versesHtml = filtered.map(v => {
    const txt = esc(v.text).replace(/\*/g, '<span class="midpoint">*</span>');
    return `<div class="verse"><span class="verse-num">${v.num}</span><span class="verse-text">${txt}</span></div>`;
  }).join('');
  return `${titleHtml}<div class="psalm-block">${versesHtml}</div>`;
}

// ── Scripture citation parsing ────────────────────────────────────────────────

const ABBREV_TO_FILE = {
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

function parseCitation(rawCitation) {
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

function parseRanges(s) {
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

function parseVerseRange(s) {
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

function parseChapterVerse(s, defaultCh) {
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

function extractVerses(book, range) {
  const lines = [];
  for (let ch = range.startCh; ch <= range.endCh; ch++) {
    const chData = book[String(ch)];
    if (!chData) continue;
    const startV = ch === range.startCh ? range.startV : 1;
    const maxV = Math.max(...Object.keys(chData).map(Number));
    const endV = ch === range.endCh ? range.endV : maxV;
    for (let v = startV; v <= endV; v++) {
      if (chData[String(v)] !== undefined) lines.push({ v, text: chData[String(v)] });
    }
  }
  return lines;
}

// ── Office HTML building ──────────────────────────────────────────────────────

const READING_RESPONSE = {
  type: 'alternatives',
  groups: [
    { label: 'I',   segments: [{ type: 'leader',   text: 'The word of the Lord.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
    { label: 'II',  segments: [{ type: 'leader',   text: 'Hear what the Spirit is saying to the Church.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
    { label: 'III', segments: [{ type: 'leader',   text: 'Holy Word, Holy Wisdom.' },
                                { type: 'response', text: 'Thanks be to God.' }] },
  ],
};

function expandCitationForDisplay(rawCitation) {
  return rawCitation.split(' or ').map(part => {
    const p = parseCitation(part.trim());
    return p ? `${p.file}${p.rest ? ' ' + p.rest : ''}` : part.trim();
  }).join(' or ');
}

function psalmWithGloria(citation, shared) {
  const gloriaRubric = `<p class="seg-rubric">At the end of the Psalm one of the following may be said or sung.</p>`;
  const gloria = shared && shared.doxology
    ? gloriaRubric + `<div class="psalm-gloria">${renderAlternatives(shared.doxology, shared, 'doxology')}</div>`
    : '';
  return psalmPlaceholder(citation) + gloria;
}

function psalmHtml(officeData, shared) {
  const psalms = officeData.psalms || [];
  const psalmSets = officeData.psalm_sets;
  const officeLabel = officeData.label ? `${esc(officeData.label)} — ` : '';
  let html = '';
  if (psalmSets && psalmSets.length) {
    const label = psalmSets.map(set =>
      set.map(p => { const c = typeof p === 'object' ? p.citation : p; return (typeof p === 'object' && p.optional) ? `[${c}]` : c; }).join(', ')
    ).join(' or ');
    html += `<h3 class="psalm-heading">${officeLabel}Psalm${psalmSets.flat().length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    html += `<p class="seg-rubric">A Psalm from the appointed lectionary is said or sung.</p>`;
    psalmSets.forEach((set, si) => {
      if (si > 0) html += `<p class="psalm-set-divider">— or —</p>`;
      set.forEach(p => { html += psalmWithGloria(p, shared); });
    });
  } else if (psalms.length) {
    const label = psalms.map(p => typeof p === 'object' ? p.citation : p).join(', ');
    html += `<h3 class="psalm-heading">${officeLabel}Psalm${psalms.length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    if (psalms.length === 1) {
      html += `<p class="seg-rubric">The following Psalm from the appointed lectionary is said or sung.</p>`;
      html += psalmWithGloria(psalms[0], shared);
    } else {
      // Multiple psalms: show as selectable tabs (PWOC directs one psalm per office).
      const stateKey = 'pwc-psalm-' + psalms.map(p => typeof p === 'object' ? p.citation : p).join('-');
      const saved = parseInt(localStorage.getItem(stateKey) || '0');
      const active = Math.min(Math.max(0, saved), psalms.length - 1);
      const tabsHtml = psalms.map((p, i) => {
        const c = typeof p === 'object' ? p.citation : p;
        return `<button class="alt-tab${i === active ? ' alt-tab-active' : ''}" data-idx="${i}" data-key="${esc(stateKey)}">Psalm ${esc(c)}</button>`;
      }).join('');
      html += `<p class="seg-rubric">One of the following Psalms from the appointed lectionary is said or sung.</p>`;
      html += `<div class="alt-block"><div class="alt-tabs">${tabsHtml}</div>`;
      psalms.forEach((p, i) => {
        html += `<div class="alt-panel${i !== active ? ' alt-panel-hidden' : ''}" data-idx="${i}">`;
        html += psalmWithGloria(p, shared);
        html += `</div>`;
      });
      html += `</div>`;
    }
  }
  return html;
}

function lessonHtml(lesson, shared) {
  const rawCitation = typeof lesson === 'object' ? lesson.citation : lesson;
  const optional = typeof lesson === 'object' && lesson.optional;
  const displayCitation = expandCitationForDisplay(rawCitation);
  const display = optional ? `(${displayCitation})` : displayCitation;
  const preambleRubric = `<p class="seg-rubric">A Reading from the appointed lectionary is read.</p>`;
  const endRubric = `<p class="seg-rubric">Here ends the Reading.</p>`;
  const reflectionRubric = `<p class="seg-rubric">After a period of silent reflection one of the following is said.</p>`;
  const responseHtml = `<div class="liturgy">${renderAlternatives(READING_RESPONSE, shared, 'reading_response')}</div>`;
  return `<h3 class="reading-heading">The Reading: ${esc(display)}</h3>`
    + preambleRubric
    + `<div class="scripture-placeholder" data-citation="${esc(rawCitation)}"><p class="loading">Loading…</p></div>`
    + endRubric
    + reflectionRubric
    + responseHtml;
}

// Psalms → lesson 1 → responsory → lesson 2 → canticle (PWC ordering).
function proclamationHtml(officeData, form, shared) {
  const lessons = (officeData.lessons || []);
  let html = psalmHtml(officeData, shared);
  if (lessons.length > 0) html += lessonHtml(lessons[0], shared);
  if (form) html += renderSubsection('The Responsory', form.responsory, shared);
  if (lessons.length > 1) html += lessonHtml(lessons[1], shared);
  if (form) html += renderSubsection('The Canticle', form.canticle, shared);
  for (const lesson of lessons.slice(2)) html += lessonHtml(lesson, shared);
  return html;
}

function collectHtml(collects, ref) {
  if (!ref) return '';
  const col = lookupCollect(collects, ref);
  const name = col && col.name ? col.name : `p. ${collectPageNum(ref) || ref}`;
  return `<p class="alt-source">${esc(name)}</p>`
       + (col ? `<p class="collect-text">${esc(col.text)}</p>` : '');
}

// Renders the collect section as a toggle between the daily collect and
// the seasonal alternatives, as the rubric directs: "either…or".
function collectToggleHtml(collects, collectRef, seasonalSegs, shared) {
  // Separate general instruction rubrics (shown above the toggle) from collect content.
  let splitAt = 0;
  while (splitAt < seasonalSegs.length && seasonalSegs[splitAt].type === 'rubric'
         && !WEEK_RUBRIC.test(seasonalSegs[splitAt].text)) splitAt++;
  const generalRubrics = seasonalSegs.slice(0, splitAt);
  const seasonalContent = seasonalSegs.slice(splitAt);

  const hasDaily    = !!collectRef;
  const hasSeasonal = seasonalContent.some(s => s.type !== 'rubric');

  let html = '';
  if (generalRubrics.length) html += `<div class="liturgy">${renderSegments(generalRubrics, shared)}</div>`;

  if (!hasDaily && !hasSeasonal) return html;

  if (hasDaily && hasSeasonal) {
    const stateKey = 'pwc-alt-collect';
    const activeIdx = parseInt(localStorage.getItem(stateKey) || '0') === 1 ? 1 : 0;
    const tab = (label, i) =>
      `<button class="alt-tab${i === activeIdx ? ' alt-tab-active' : ''}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(label)}</button>`;
    const panel = (content, i) =>
      `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" data-idx="${i}">${content}</div>`;
    // Strip "Week of Easter X" / "Week N" labels from the panel — those are selection
    // identifiers, not liturgical text to display.
    const displaySeasonal = seasonalContent.filter(s => !(s.type === 'rubric' && WEEK_RUBRIC.test(s.text)));
    html += `<div class="alt-block"><div class="alt-tabs">${tab('Collect of the Day', 0)}${tab('Seasonal Collect', 1)}</div>`
          + panel(collectHtml(collects, collectRef), 0)
          + panel(`<div class="liturgy">${renderSegments(displaySeasonal, shared)}</div>`, 1)
          + `</div>`;
  } else if (hasDaily) {
    html += `<h3 class="office-subsection-title">Collect of the Day</h3>${collectHtml(collects, collectRef)}`;
  } else {
    html += `<h3 class="office-subsection-title">Seasonal Collect</h3><div class="liturgy">${renderSegments(seasonalContent, shared)}</div>`;
  }
  return html;
}

// ── Date formatting ───────────────────────────────────────────────────────────

function fmtNavDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00Z');
  return ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][d.getUTCDay()]
       + ' ' + d.getUTCDate()
       + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getUTCMonth()];
}

function fmtFullDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00Z');
  const day = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'][d.getUTCDay()];
  const mon = ['January','February','March','April','May','June','July','August','September','October','November','December'][d.getUTCMonth()];
  return `${day}, ${d.getUTCDate()} ${mon} ${d.getUTCFullYear()}`;
}

// ── Main render ───────────────────────────────────────────────────────────────

async function render(dateStr, officeType, translation) {
  const contentEl = document.getElementById('office-content');
  contentEl.innerHTML = '<p class="loading">Loading…</p>';

  // Fetch bounds first so we can gate the day fetch.
  let bounds;
  try {
    bounds = await fetchOnce('bounds', `${DATA}/season_bounds.json`);
  } catch (err) {
    contentEl.innerHTML = `<p class="error-msg">Failed to load: ${esc(String(err))}</p>`;
    return;
  }

  // Bounds enforcement before attempting to fetch the day file.
  const boundsMax = offsetDate(bounds.christmas_ii, 6);
  if (dateStr < bounds.advent_i || dateStr > boundsMax) {
    location.hash = hashFor(todayStr(), defaultOffice());
    return;
  }

  let result;
  try {
    result = await Promise.all([
      fetchOnce('offices',  `${DATA}/offices.json`),
      fetchOnce('collects', `${DATA}/collects.json`),
      fetchDay(dateStr),
    ]);
  } catch (err) {
    contentEl.innerHTML = `<p class="error-msg">Failed to load: ${esc(String(err))}</p>`;
    return;
  }
  const [offices, collects, day] = result;
  const shared = offices._shared || {};

  // Sync date picker.
  const picker = document.getElementById('nav-date-picker');
  if (picker) { picker.min = bounds.advent_i; picker.max = boundsMax; picker.value = dateStr; }

  const d = new Date(dateStr + 'T00:00:00Z');
  const weekday = d.getUTCDay();
  const season = seasonOf(dateStr, bounds);
  const weekIdx = seasonWeekIndex(dateStr, season, bounds);
  const key = formKey(season, officeType, weekday, day.rank);
  const form = offices[key] || null;

  document.documentElement.setAttribute('data-season', season);

  const officeData = officeType === 'mp' ? (day.morning || {}) : (day.evening || {});

  // Nav
  document.getElementById('nav-date').textContent = fmtNavDate(dateStr);
  const prevEl = document.getElementById('nav-prev');
  const nextEl = document.getElementById('nav-next');
  const prevDate = offsetDate(dateStr, -1);
  const nextDate = offsetDate(dateStr, +1);
  if (prevDate < bounds.advent_i) { prevEl.removeAttribute('href'); prevEl.classList.add('nav-disabled'); }
  else { prevEl.href = hashFor(prevDate, officeType); prevEl.classList.remove('nav-disabled'); }
  if (nextDate > boundsMax) { nextEl.removeAttribute('href'); nextEl.classList.add('nav-disabled'); }
  else { nextEl.href = hashFor(nextDate, officeType); nextEl.classList.remove('nav-disabled'); }
  const todayEl = document.getElementById('nav-today');
  todayEl.href = hashFor(todayStr(), officeType);
  todayEl.style.visibility = dateStr === todayStr() ? 'hidden' : 'visible';
  document.getElementById('nav-mp').href    = hashFor(dateStr, 'mp');
  document.getElementById('nav-ep').href    = hashFor(dateStr, 'ep');
  document.getElementById('nav-mp').classList.toggle('nav-active', officeType === 'mp');
  document.getElementById('nav-ep').classList.toggle('nav-active', officeType === 'ep');
  document.getElementById('nav-translation').value = translation;

  // Header
  const officeName = officeType === 'mp' ? 'Morning Prayer' : 'Evening Prayer';
  document.title = `${officeName} — ${day.name}`;
  document.getElementById('day-office-name').textContent = officeName;
  document.getElementById('day-title').textContent = day.name;
  document.getElementById('day-subtitle').textContent = fmtFullDate(dateStr);
  // Observance toggle — own nav row so it doesn't shift nav-bottom layout
  const obsRow = document.getElementById('nav-observance-row');
  const obsEl  = document.getElementById('nav-observance');
  if (officeData.alternate) {
    const priLabel = officeData.label || 'Primary';
    const altLabel = officeData.alternate.label || 'Alternate';
    obsEl.innerHTML = `<a class="obs-nav-btn nav-active" data-obs="primary">${esc(priLabel)}</a>`
      + `<a class="obs-nav-btn" data-obs="alternate">${esc(altLabel)}</a>`;
    obsRow.classList.remove('nav-row-hidden');
  } else {
    obsEl.innerHTML = '';
    obsRow.classList.add('nav-row-hidden');
  }

  const hexColour = COLOUR_HEX[day.colour] || '#b5a882';
  document.documentElement.style.setProperty('--color-day', hexColour);
  document.getElementById('day-meta').innerHTML = `
    <span class="meta-item">${esc(season)}</span>
    <span class="meta-sep">·</span>
    <span class="meta-item">${esc(formatRank(day.rank))}</span>`;

  document.querySelectorAll('.day-note, .day-note-details').forEach(el => el.remove());
  if (day.notes && day.notes.length) {
    const headerEl = document.getElementById('day-header');
    day.notes.forEach(n => {
      const text = typeof n === 'object' ? n.text : n;
      const p = document.createElement('p');
      p.className = 'day-note';
      const renderNoteText = t => {
        // Convert bare URLs to clickable links.
        const urlPat = /https?:\/\/[^\s)>]+/g;
        let last = 0, frag = document.createDocumentFragment();
        let m;
        while ((m = urlPat.exec(t)) !== null) {
          if (m.index > last) frag.appendChild(document.createTextNode(t.slice(last, m.index)));
          const a = document.createElement('a');
          a.href = m[0]; a.textContent = m[0]; a.target = '_blank'; a.rel = 'noopener noreferrer';
          frag.appendChild(a);
          last = m.index + m[0].length;
        }
        if (last < t.length) frag.appendChild(document.createTextNode(t.slice(last)));
        return frag;
      };
      if (text.length > 200) {
        const cut = text.lastIndexOf(' ', 160) || 160;
        const short = text.slice(0, cut) + '…';
        p.appendChild(renderNoteText(short));
        p.classList.add('day-note-collapsible');
        p.addEventListener('click', () => {
          const isShort = p.classList.contains('day-note-collapsible') && !p.classList.contains('day-note-expanded');
          p.innerHTML = '';
          p.appendChild(renderNoteText(isShort ? text : short));
          p.classList.toggle('day-note-expanded', isShort);
        });
      } else {
        p.appendChild(renderNoteText(text));
      }
      headerEl.appendChild(p);
    });
  }

  const seasonalSegs = form ? filterSeasonalCollects(form.seasonal_collects || [], weekIdx) : [];

  let html = '';

  // ── Gathering ──────────────────────────────────────────────────────────────
  if (form && (form.opening_responses || form.thanksgiving_for_light || form.phos_hilaron || form.invitatory)) {
    html += `<h2 class="office-section-title">The Gathering of the Community</h2>`;
    if (form.opening_responses && form.opening_responses.length)
      html += renderSubsection('Introductory Responses', form.opening_responses, shared);
    if (form.thanksgiving_for_light && form.thanksgiving_for_light.length)
      html += renderSubsection('Thanksgiving', form.thanksgiving_for_light, shared);
    // Ordinary-time EP: evening hymn reference (Phos Hilaron).
    if (form.phos_hilaron && form.phos_hilaron.length)
      html += `<div class="liturgy">${renderSegments(form.phos_hilaron, shared)}</div>`;
    if (form.invitatory && form.invitatory.length)
      html += renderSubsection('Invitatory Psalm', form.invitatory, shared);
  }

  // ── Proclamation ───────────────────────────────────────────────────────────
  html += `<h2 class="office-section-title">The Proclamation of the Word</h2>`;

  // Primary readings — psalms, lesson 1, responsory, canticle, lesson 2+ (if any).
  html += `<div class="obs-readings" data-obs="primary">`;
  if (officeData.label) html += `<h3 class="office-subsection-title">${esc(officeData.label)}</h3>`;
  html += proclamationHtml(officeData, form, shared);
  html += `</div>`;

  // Alternate readings (hidden; toggled by observance buttons in header).
  if (officeData.alternate) {
    const alt = officeData.alternate;
    html += `<div class="obs-readings obs-hidden" data-obs="alternate">`;
    if (alt.label) html += `<h3 class="office-subsection-title">${esc(alt.label)}</h3>`;
    html += proclamationHtml(alt, form, shared);
    html += `</div>`;
  }

  // Affirmation of Faith closes the Proclamation section (not Prayers).
  if (form && form.affirmation && form.affirmation.length) {
    html += `<h3 class="office-subsection-title">Affirmation of Faith</h3>`;
    html += `<p class="seg-rubric">One of the following Affirmations of Faith may be said or sung.</p>`;
    html += `<div class="liturgy">${renderSegments(form.affirmation, shared)}</div>`;
  }

  // ── Prayers ────────────────────────────────────────────────────────────────
  if (form && (form.intercessions || form.litany || form.lords_prayer_intro || (form.seasonal_collects && form.seasonal_collects.length) || officeData.collect)) {
    html += `<h2 class="office-section-title">The Prayers of the Community</h2>`;
    // Day-specific intercession prompts guide the free-prayer period before the formal litany.
    if (form.intercessions && form.intercessions.length)
      html += renderSubsection('Intercessions and Thanksgivings', form.intercessions, shared);
    html += renderSubsection('The Litany', form.litany, shared);
    html += `<h3 class="office-subsection-title">The Collect</h3>`;
    html += `<div id="prayers-collect">${collectToggleHtml(collects, officeData.collect, seasonalSegs, shared)}</div>`;
    if (form.lords_prayer_intro && form.lords_prayer_intro.length) {
      html += `<h3 class="office-subsection-title">The Lord's Prayer</h3>`;
      html += `<div class="liturgy">${renderSegments(form.lords_prayer_intro, shared)}</div>`;
    }
  }

  // ── Sending ────────────────────────────────────────────────────────────────
  if (form && form.dismissal && form.dismissal.length) {
    html += `<h2 class="office-section-title">The Sending Forth of the Community</h2>`;
    html += `<h3 class="office-subsection-title">The Dismissal</h3>`;
    html += `<div class="liturgy">${renderSegments(form.dismissal, shared)}</div>`;
  }

  html += `<p class="scripture-attr" id="scripture-attr">Scripture: ${esc(translation.toUpperCase())}</p>`;

  contentEl.innerHTML = html;

  // Wire observance toggle — fill both blocks; toggling is instant show/hide.
  document.querySelectorAll('.obs-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.obs;
      document.querySelectorAll('.obs-nav-btn').forEach(b =>
        b.classList.toggle('nav-active', b.dataset.obs === target));
      contentEl.querySelectorAll('.obs-readings').forEach(r =>
        r.classList.toggle('obs-hidden', r.dataset.obs !== target));
      // Update heading and browser title to reflect selected observance.
      const alt = officeData.alternate;
      const officeName = document.getElementById('day-office-name').textContent;
      const titleEl = document.getElementById('day-title');
      if (target === 'alternate' && alt) {
        const altName = alt.label || alt.name || day.name;
        titleEl.textContent = altName;
        document.title = `${officeName} — ${altName}`;
      } else {
        titleEl.textContent = day.name;
        document.title = `${officeName} — ${day.name}`;
      }
      // Update collect to match the active observance.
      const collectEl = document.getElementById('prayers-collect');
      if (collectEl) {
        const activeObs = target === 'alternate' && alt ? alt : officeData;
        collectEl.innerHTML = collectToggleHtml(collects, activeObs.collect, seasonalSegs, shared);
      }
    });
  });

  fillPsalms(contentEl);
  fillScripture(contentEl, translation);
  prefetchBackground(dateStr);
}

// ── Background prefetch ───────────────────────────────────────────────────────
// Psalter is pre-cached at SW install. Here we warm the next 3 monthly
// lectionary files so a month of navigation works offline without any prior visits.
// Scripture books cache lazily on first read — no proactive Bible download.

let _prefetchDone = false;

function prefetchBackground(dateStr) {
  if (_prefetchDone) return;
  _prefetchDone = true;

  const months = new Set();
  for (let i = 1; i <= 90; i++) {
    months.add(offsetDate(dateStr, i).slice(0, 7));
  }
  const queue = [...months].slice(0, 3).map(m => `${DATA}/lectionary/${m}.json`);

  const schedule = window.requestIdleCallback
    ? cb => requestIdleCallback(cb, { timeout: 2000 })
    : cb => setTimeout(cb, 200);

  schedule(() => queue.forEach(url => fetch(url).catch(() => {})));
}

// ── Async fillers ─────────────────────────────────────────────────────────────

function fillPsalms(root) {
  root.querySelectorAll('.psalm-loading').forEach(async el => {
    const cit = el.dataset.citation;
    try { el.innerHTML = await renderPsalm(cit); }
    catch (e) { el.innerHTML = `<p class="error-msg">Psalm ${esc(cit)}: ${esc(String(e))}</p>`; }
  });
}

function fillScripture(root, translation) {
  root.querySelectorAll('.scripture-placeholder').forEach(async el => {
    const rawCitation = el.dataset.citation;
    try {
      const parsed = parseCitation(rawCitation);
      if (!parsed) { el.innerHTML = `<p class="error-msg">Cannot parse: ${esc(rawCitation)}</p>`; return; }

      let bookData, usedTranslation = translation;
      try {
        bookData = await fetchBook(translation, parsed.file);
      } catch (_) {
        if (translation !== 'kjv') {
          try { bookData = await fetchBook('kjv', parsed.file); usedTranslation = 'kjv'; }
          catch (_2) { /* unavailable */ }
        }
      }

      const ranges = parseRanges(parsed.rest);
      if (!bookData || !ranges.length) {
        el.innerHTML = `<p class="error-msg">Text unavailable: ${esc(rawCitation)}</p>`;
        return;
      }

      const allVerses = ranges.flatMap(r => extractVerses(bookData, r));
      el.innerHTML = allVerses.map(({ v, text }) =>
        `<div class="scripture-verse"><span class="verse-num">${v}</span><span class="verse-text">${esc(text)}</span></div>`
      ).join('');
    } catch (e) {
      el.innerHTML = `<p class="error-msg">Error: ${esc(String(e))}</p>`;
    }
  });
}

// ── Translation switch (no full re-render) ────────────────────────────────────

function switchTranslation(newTranslation) {
  state.translation = newTranslation;
  localStorage.setItem('pwc-translation', newTranslation);
  // Reset scripture placeholders to loading, then re-fill only those.
  const root = document.getElementById('office-content');
  root.querySelectorAll('.scripture-placeholder').forEach(el => {
    el.innerHTML = '<p class="loading">Loading…</p>';
  });
  const attr = document.getElementById('scripture-attr');
  if (attr) attr.textContent = `Scripture: ${newTranslation.toUpperCase()}`;
  fillScripture(root, newTranslation);
}

// ── Evaluation banner ─────────────────────────────────────────────────────────

function initEvalBanner() {
  if (sessionStorage.getItem('pwc-banner-dismissed')) return;
  const banner = document.createElement('div');
  banner.id = 'eval-banner';
  banner.className = 'eval-banner';
  banner.innerHTML = `<span>Private synod evaluation — please do not share or distribute.</span>`
    + `<button class="eval-banner-dismiss" aria-label="Dismiss">&#215;</button>`;
  document.getElementById('main').insertAdjacentElement('afterbegin', banner);
  banner.querySelector('.eval-banner-dismiss').addEventListener('click', () => {
    sessionStorage.setItem('pwc-banner-dismissed', '1');
    banner.remove();
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────

function handleHashChange() {
  const parsed = parseHash(location.hash);
  if (parsed) {
    state.date = parsed.date;
    state.office = parsed.office;
  } else {
    location.hash = hashFor(todayStr(), defaultOffice());
    return;
  }
  render(state.date, state.office, state.translation);
}

// ── Init ──────────────────────────────────────────────────────────────────────

function initScrollBehaviour() {
  const nav = document.getElementById('nav');
  const main = document.getElementById('main');
  let lastY = 0, compact = false, downTravel = 0, upTravel = 0;

  function syncNavPad() {
    main.style.paddingTop = nav.offsetHeight + 'px';
  }
  // Sync on load and whenever the nav resizes (compact toggle, observance row).
  syncNavPad();
  new ResizeObserver(syncNavPad).observe(nav);

  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    const delta = y - lastY;
    if (delta > 0) {
      upTravel = 0;
      downTravel += delta;
      if (!compact && y > 80 && downTravel > 40) {
        compact = true; downTravel = 0; nav.classList.add('nav-compact');
      }
    } else if (delta < 0) {
      downTravel = 0;
      upTravel += -delta;
      if (compact && upTravel > 30) {
        compact = false; upTravel = 0; nav.classList.remove('nav-compact');
      }
    }
    lastY = y;
  }, { passive: true });

  nav.addEventListener('click', e => {
    if (!compact) return;
    const interactive = e.target.closest('button, a, select, input, label');
    if (interactive) return;
    compact = false; upTravel = 0; downTravel = 0;
    nav.classList.remove('nav-compact');
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initScrollBehaviour();

  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  const sel = document.getElementById('nav-translation');
  sel.value = state.translation;
  sel.addEventListener('change', () => { switchTranslation(sel.value); });

  const picker = document.getElementById('nav-date-picker');
  picker.addEventListener('click', () => { try { picker.showPicker(); } catch (_) {} });
  picker.addEventListener('change', e => {
    if (e.target.value) location.hash = hashFor(e.target.value, state.office);
  });

  document.getElementById('office-content').addEventListener('click', e => {
    const tab = e.target.closest('.alt-tab');
    if (!tab) return;
    const idx = parseInt(tab.dataset.idx);
    const stateKey = tab.dataset.key;
    localStorage.setItem(stateKey, String(idx));
    // Update every alt-block sharing this key so linked blocks (e.g. doxology
    // after each psalm) stay in sync.
    const seen = new Set();
    document.querySelectorAll(`#office-content .alt-tab[data-key="${CSS.escape(stateKey)}"]`).forEach(t => {
      const b = t.closest('.alt-block');
      if (!b) return;
      t.classList.toggle('alt-tab-active', parseInt(t.dataset.idx) === idx);
      if (!seen.has(b)) {
        seen.add(b);
        b.querySelectorAll(':scope > .alt-panel').forEach((p, i) => p.classList.toggle('alt-panel-hidden', i !== idx));
      }
    });
  });

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.isContentEditable) return;
    if (e.key === 'ArrowLeft'  || e.key === 'h') location.hash = hashFor(offsetDate(state.date, -1), state.office);
    if (e.key === 'ArrowRight' || e.key === 'l') location.hash = hashFor(offsetDate(state.date, +1), state.office);
    if (e.key === 'm') location.hash = hashFor(state.date, 'mp');
    if (e.key === 'e') location.hash = hashFor(state.date, 'ep');
    if (e.key === 't') location.hash = hashFor(todayStr(), state.office);
  });

  window.addEventListener('hashchange', handleHashChange);

  initEvalBanner();

  // Warm up static fetches.
  fetchOnce('offices',  `${DATA}/offices.json`);
  fetchOnce('collects', `${DATA}/collects.json`);
  fetchOnce('bounds',   `${DATA}/season_bounds.json`);
  fetchOnce('psalter',  `${DATA}/psalter.json`);

  handleHashChange();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js');
  }
});
