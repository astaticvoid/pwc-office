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
  btn.textContent = document.documentElement.getAttribute('data-theme') === 'dark' ? 'Light' : 'Dark';
}

// ── In-memory fetch cache ─────────────────────────────────────────────────────

const _cache = {
  offices:  null, // Promise<object>
  collects: null, // Promise<object>
  bounds:   null, // Promise<object>
  psalms:   {},   // num(str) → Promise<object>
  books:    {},   // 'kjv/Numbers' → Promise<object>
};

async function fetchOnce(key, url) {
  if (!_cache[key]) _cache[key] = fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
  return _cache[key];
}

function fetchPsalm(num) {
  const k = String(num);
  if (!_cache.psalms[k]) _cache.psalms[k] = fetch(`${DATA}/psalms/${k}.json`).then(r => r.json());
  return _cache.psalms[k];
}

function fetchBook(translation, filename) {
  const k = `${translation}/${filename}`;
  if (!_cache.books[k]) _cache.books[k] = fetch(`${DATA}/translations/${translation}/${filename}.json`)
    .then(r => { if (!r.ok) throw new Error(`${filename}: ${r.status}`); return r.json(); });
  return _cache.books[k];
}

function fetchDay(dateStr) {
  return fetch(`${DATA}/lectionary/${dateStr}.json`).then(r => {
    if (!r.ok) throw new Error(`${dateStr}: ${r.status}`);
    return r.json();
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
  'White':  '#f0ede4', 'Red':    '#cc2200', 'Green':  '#00402f',
  'Purple': '#5c3a8a', 'Rose':   '#c06090', 'Black':  '#1a1a18', 'Gold': '#b8860b',
};

// ── Routing ───────────────────────────────────────────────────────────────────

function todayStr() { return new Date().toISOString().slice(0, 10); }

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

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function renderSegments(segs) {
  if (!segs || !segs.length) return '';
  return segs.map(seg => {
    const t = esc(seg.text);
    if (seg.type === 'rubric')   return `<p class="seg-rubric">${t}</p>`;
    if (seg.type === 'response') return `<p class="seg-response">${t}</p>`;
    return `<p class="seg-leader">${t}</p>`;
  }).join('');
}

function renderSubsection(label, segs) {
  if (!segs || !segs.length) return '';
  return `<h3 class="office-subsection-title">${esc(label)}</h3><div class="liturgy">${renderSegments(segs)}</div>`;
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
  const titleHtml = data.title ? `<p class="psalm-title">${esc(data.title)}</p>` : '';
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

function readingsHtml(officeData) {
  const psalms = officeData.psalms || [];
  const psalmSets = officeData.psalm_sets;
  const lessons = officeData.lessons || [];
  let html = '';

  if (psalmSets && psalmSets.length) {
    const label = psalmSets.map(set =>
      set.map(p => { const c = typeof p === 'object' ? p.citation : p; return (typeof p === 'object' && p.optional) ? `[${c}]` : c; }).join(', ')
    ).join(' or ');
    html += `<h3 class="psalm-heading">Psalm${psalmSets.flat().length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    psalmSets.forEach((set, si) => {
      if (si > 0) html += `<p class="psalm-set-divider">— or —</p>`;
      set.forEach(p => { html += psalmPlaceholder(p); });
    });
  } else if (psalms.length) {
    const label = psalms.map(p => typeof p === 'object' ? p.citation : p).join(', ');
    html += `<h3 class="psalm-heading">Psalm${psalms.length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    psalms.forEach(p => { html += psalmPlaceholder(p); });
  }

  lessons.forEach(lesson => {
    const rawCitation = typeof lesson === 'object' ? lesson.citation : lesson;
    const optional = typeof lesson === 'object' && lesson.optional;
    const display = optional ? `(${rawCitation})` : rawCitation;
    html += `<h3 class="reading-heading">Reading: ${esc(display)}</h3>`;
    html += `<div class="scripture-placeholder" data-citation="${esc(rawCitation)}"><p class="loading">Loading…</p></div>`;
    html += `<p class="word-of-lord">The word of the Lord.<br><span class="response">Thanks be to God.</span></p>`;
  });

  return html;
}

function collectHtml(collects, ref, label) {
  if (!ref) return '';
  const col = lookupCollect(collects, ref);
  const heading = col && col.name
    ? `${label}: ${col.name} (p. ${esc(collectPageNum(ref))})`
    : `${label} (p. ${esc(collectPageNum(ref) || ref)})`;
  return `<h3 class="office-subsection-title">${esc(heading)}</h3>`
       + (col ? `<p class="collect-text">${esc(col.text)}</p>` : '');
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

  let result;
  try {
    result = await Promise.all([
      fetchOnce('offices',  `${DATA}/offices.json`),
      fetchOnce('collects', `${DATA}/collects.json`),
      fetchOnce('bounds',   `${DATA}/season_bounds.json`),
      fetchDay(dateStr),
    ]);
  } catch (err) {
    contentEl.innerHTML = `<p class="error-msg">Failed to load: ${esc(String(err))}</p>`;
    return;
  }
  const [offices, collects, bounds, day] = result;

  // Bounds enforcement: redirect if date is outside the lectionary range.
  const boundsMax = offsetDate(bounds.christmas_ii, 6);
  if (dateStr < bounds.advent_i || dateStr > boundsMax) {
    location.hash = hashFor(todayStr(), defaultOffice());
    return;
  }

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
  document.getElementById('nav-prev').href  = hashFor(offsetDate(dateStr, -1), officeType);
  document.getElementById('nav-next').href  = hashFor(offsetDate(dateStr, +1), officeType);
  document.getElementById('nav-today').href = hashFor(todayStr(), officeType);
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
  // Observance toggle in nav (only when alternate readings exist)
  const obsEl = document.getElementById('nav-observance');
  if (officeData.alternate) {
    const priLabel = officeData.label || 'Primary';
    const altLabel = officeData.alternate.label || 'Alternate';
    obsEl.innerHTML = `<a class="obs-nav-btn nav-active" data-obs="primary">${esc(priLabel)}</a>`
      + `<a class="obs-nav-btn" data-obs="alternate">${esc(altLabel)}</a>`;
  } else {
    obsEl.innerHTML = '';
  }

  const hexColour = COLOUR_HEX[day.colour] || '#aaa';
  document.getElementById('day-meta').innerHTML = `
    <span class="meta-item"><span class="colour-chip" style="background:${esc(hexColour)}"></span>${esc(day.colour)}</span>
    <span class="meta-item">Season: ${esc(season)}</span>
    <span class="meta-item">${esc(day.rank)}</span>`;

  document.querySelectorAll('.day-note').forEach(el => el.remove());
  if (day.notes && day.notes.length) {
    const headerEl = document.getElementById('day-header');
    day.notes.forEach(n => {
      const p = document.createElement('p');
      p.className = 'day-note';
      p.textContent = typeof n === 'object' ? n.text : n;
      headerEl.appendChild(p);
    });
  }

  let html = '';

  // ── Gathering ──────────────────────────────────────────────────────────────
  if (form && form.opening_responses && form.opening_responses.length) {
    html += `<h2 class="office-section-title">The Gathering of the Community</h2>`;
    html += renderSubsection('Introductory Responses', form.opening_responses);
    if (form.invitatory && form.invitatory.length)
      html += renderSubsection('Invitatory Psalm', form.invitatory);
  }

  // ── Proclamation ───────────────────────────────────────────────────────────
  html += `<h2 class="office-section-title">The Proclamation of the Word</h2>`;

  // Primary readings (always visible by default)
  html += `<div class="obs-readings" data-obs="primary">`;
  if (officeData.label) html += `<h3 class="office-subsection-title">${esc(officeData.label)}</h3>`;
  html += readingsHtml(officeData);
  html += collectHtml(collects, officeData.collect, 'Collect of the Day');
  html += `</div>`;

  // Alternate readings (hidden; toggled by observance buttons in header)
  if (officeData.alternate) {
    const alt = officeData.alternate;
    html += `<div class="obs-readings obs-hidden" data-obs="alternate">`;
    if (alt.label) html += `<h3 class="office-subsection-title">${esc(alt.label)}</h3>`;
    html += readingsHtml(alt);
    html += collectHtml(collects, alt.collect, 'Collect of the Day');
    html += `</div>`;
  }

  if (form) {
    html += renderSubsection('The Responsory', form.responsory);
    html += renderSubsection('The Canticle', form.canticle);
  }

  // ── Prayers ────────────────────────────────────────────────────────────────
  if (form && (form.affirmation || form.litany || form.lords_prayer_intro)) {
    html += `<h2 class="office-section-title">The Prayers of the Community</h2>`;
    html += renderSubsection('Affirmation of Faith', form.affirmation);
    html += renderSubsection('The Litany', form.litany);
    html += renderSubsection('Seasonal Collect', filterSeasonalCollects(form.seasonal_collects || [], weekIdx));
    if (form.lords_prayer_intro && form.lords_prayer_intro.length) {
      html += `<h3 class="office-subsection-title">The Lord's Prayer</h3>`;
      html += `<div class="liturgy">${renderSegments(form.lords_prayer_intro)}</div>`;
    }
  }

  // ── Sending ────────────────────────────────────────────────────────────────
  if (form && form.dismissal && form.dismissal.length) {
    html += `<h2 class="office-section-title">The Sending Forth of the Community</h2>`;
    html += `<div class="liturgy">${renderSegments(form.dismissal)}</div>`;
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
    });
  });

  fillPsalms(contentEl);
  fillScripture(contentEl, translation);
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
  let lastY = 0, triggerY = 0, compact = false;
  window.addEventListener('scroll', () => {
    const y = window.scrollY;
    if (!compact && y > lastY && y > 80) {
      compact = true; triggerY = y;
      nav.classList.add('nav-compact');
    } else if (compact && y < triggerY - 40) {
      compact = false;
      nav.classList.remove('nav-compact');
    }
    lastY = y;
  }, { passive: true });
  document.addEventListener('touchstart', () => {
    compact = false; nav.classList.remove('nav-compact');
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initScrollBehaviour();

  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

  const sel = document.getElementById('nav-translation');
  sel.value = state.translation;
  sel.addEventListener('change', () => { switchTranslation(sel.value); });

  const picker = document.getElementById('nav-date-picker');
  picker.addEventListener('change', e => {
    if (e.target.value) location.hash = hashFor(e.target.value, state.office);
  });
  document.getElementById('nav-date-wrapper').addEventListener('click', () => {
    try { picker.showPicker(); } catch (_) {}
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

  // Warm up static fetches.
  fetchOnce('offices',  `${DATA}/offices.json`);
  fetchOnce('collects', `${DATA}/collects.json`);
  fetchOnce('bounds',   `${DATA}/season_bounds.json`);

  handleHashChange();
});
