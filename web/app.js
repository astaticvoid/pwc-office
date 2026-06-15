'use strict';

import {
  esc, parseDate, seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderAlternatives, renderSegments, renderSubsection,
  lessonHtml, bindMidpoints, parseCitation,
  READING_RESPONSE, CANTICLE_SOURCE, SKIP_RUBRICS, SC_HEADER, SC_FOOTER,
} from './render.js';

// ── Cache reset escape hatch ───────────────────────────────────────────────────
// Visit /?reset to unregister the service worker and clear all caches.
// Useful when a stale SW is stuck on a device after a deploy.
if (location.search === '?reset' && 'serviceWorker' in navigator) {
  Promise.all([
    navigator.serviceWorker.getRegistrations().then(regs => Promise.all(regs.map(r => r.unregister()))),
    caches.keys().then(keys => Promise.all(keys.map(k => caches.delete(k)))),
  ]).then(() => { location.replace(location.pathname); });
}

// ── Data path ─────────────────────────────────────────────────────────────────
// Dev: python3 -m http.server 8080 from repo root, open /web/ — web/data symlink
// Prod: web/ synced to S3 bucket root, data/ at same root
const DATA = 'data';

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  date:        todayStr(),
  office:      defaultOffice(),
  observance:  'primary',
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
  btn.textContent = isDark ? 'Dark' : 'Light';
  btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
}

// ── Font size ─────────────────────────────────────────────────────────────────

const FONT_SIZES = ['medium', 'large'];
const FONT_LABELS = { medium: 'Medium', large: 'Large' };

function initFontSize() {
  const raw = localStorage.getItem('pwc-font-size') || 'medium';
  const stored = raw === 'small' ? 'medium' : raw;
  document.documentElement.setAttribute('data-font-size', stored);
  updateFontSizeButton(stored);
}

function cycleFontSize() {
  const current = document.documentElement.getAttribute('data-font-size') || 'medium';
  const next = FONT_SIZES[(FONT_SIZES.indexOf(current) + 1) % FONT_SIZES.length];
  document.documentElement.setAttribute('data-font-size', next);
  localStorage.setItem('pwc-font-size', next);
  updateFontSizeButton(next);
}

function updateFontSizeButton(size) {
  const btn = document.getElementById('font-size-toggle');
  if (!btn) return;
  btn.textContent = FONT_LABELS[size] || 'A';
  btn.setAttribute('aria-label', `Text size: ${size}. Click to cycle.`);
}

// ── In-memory fetch cache ─────────────────────────────────────────────────────

const _cache = {
  offices:  null, // Promise<object>
  collects: null, // Promise<object>
  bounds:   null, // Promise<object>
  psalter:  null, // Promise<object>  — full psalter keyed by psalm number string
  fats:     null, // Promise<object>  — For All The Saints saints.json (optional, may be absent)
  months:   {},   // 'YYYY-MM' → Promise<object>  — monthly lectionary dicts
  books:    {},   // 'kjv/Numbers' → Promise<object>
};

/** Fetch JSON at `url` once; all callers share the same in-flight or resolved promise. */
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

/** Load a Bible book JSON file; keyed by translation + filename so each file is only fetched once. */
function fetchBook(translation, filename) {
  const k = `${translation}/${filename}`;
  if (!_cache.books[k]) _cache.books[k] = fetch(`${DATA}/translations/${translation}/${filename}.json`)
    .then(r => { if (!r.ok) throw new Error(`${filename}: ${r.status}`); return r.json(); });
  return _cache.books[k];
}

/** Fetch the lectionary entry for `dateStr` (YYYY-MM-DD) from the monthly JSON file. */
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

// Extracts the Occasional Prayer page number from refs like:
//   "344 or 8, 677 (The King)"     → "677"  (prayer-number,page format)
//   "378 or 17, 680 (Labour Day)"  → "680"
//   "365 or 413 or FAS 211"        → "413"  (bare page before another or/FAS)
// Returns null when no secondary page is present.
function collectSecondaryPage(ref) {
  const s = ref.replace(/\([^)]*\)/g, ''); // strip (Com: ...) and similar asides
  let m = /\bor\s+\d+,\s+(\d+)/.exec(s);
  if (m) return m[1];
  m = /\bor\s+(\d{3,})\b/.exec(s);
  return m ? m[1] : null;
}

function lookupCollect(collects, ref) {
  if (!ref) return null;
  const page = collectPageNum(ref);
  return page ? (collects[page] || null) : null;
}

// ── For All The Saints (FATS) lookup ─────────────────────────────────────────

// Known name mismatches between lectionary and FATS keys. Add entries as discovered.
const FATS_ALIASES = {};

/** Find a FATS entry by saint name using case-insensitive substring matching. */
function lookupFatsEntry(fats, name) {
  if (!fats || !name) return null;
  const needle = (FATS_ALIASES[name] || name).toLowerCase();
  const key = Object.keys(fats).find(k => {
    const kl = k.toLowerCase();
    return kl === needle || kl.includes(needle) || needle.includes(kl);
  });
  return key ? fats[key] : null;
}

// ── Season computation ────────────────────────────────────────────────────────

// ── Liturgical colour → CSS hex ───────────────────────────────────────────────

const COLOUR_HEX = {
  'White':  '#f0ece2', 'Red':    '#8c2525', 'Green':  '#2d5a35',
  'Violet': '#5c3a8a', 'Blue':   '#2c5f8a', 'Rose':   '#b07a8a',
  'Black':  '#2c2820', 'Gold':   '#b8860b',
};

// Standard liturgical colours offered when rubric says "or other appropriate colour"
const OTHER_APPROPRIATE = ['White', 'Red', 'Green', 'Violet', 'Blue'];

function colourHexes(str) {
  if (!str) return [];
  const hexes = [];
  for (const part of str.split(' or ').map(s => s.trim())) {
    if (part === 'other appropriate colour') {
      for (const c of OTHER_APPROPRIATE) {
        const h = COLOUR_HEX[c];
        if (h && !hexes.includes(h)) hexes.push(h);
      }
    } else {
      const h = COLOUR_HEX[part];
      if (h && !hexes.includes(h)) hexes.push(h);
    }
  }
  return hexes;
}

// ── Routing ───────────────────────────────────────────────────────────────────

function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function parseHash(hash) {
  const m = /^#\/(\d{4}-\d{2}-\d{2})\/(mp|ep)(?:\/(primary|alternate))?$/.exec(hash);
  return m ? { date: m[1], office: m[2], observance: m[3] || 'primary' } : null;
}

function hashFor(date, office, observance) {
  const obs = observance && observance !== 'primary' ? '/' + observance : '';
  return `#/${date}/${office}${obs}`;
}

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
    } else if (cur && (line.startsWith(' ') || /^[a-z]/.test(line))) {
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
    const txt = bindMidpoints(esc(v.text));
    return `<div class="verse"><span class="verse-num" aria-hidden="true">${v.num}</span><span class="verse-text">${txt}</span></div>`;
  }).join('');
  return `${titleHtml}<div class="psalm-block">${versesHtml}</div>`;
}

// ── Scripture citation parsing ────────────────────────────────────────────────

/**
 * Parse a chapter:verse range string (e.g. "1:1-10, 2:3—3:5") into an array of range objects.
 * Handles em-dash cross-chapter ranges and comma-delimited multi-ranges.
 * @param {string} s - verse range string after the book abbreviation
 * @returns {Array<{startCh, startV, endCh, endV}>}
 */
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

/**
 * Extract verse objects for a single range from a loaded book JSON.
 * @param {object} book - book JSON keyed by chapter → verse → text
 * @param {{startCh, startV, endCh, endV}} range - from parseRanges()
 * @returns {Array<{v:number, text:string}>}
 */
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

// ── Observance card ───────────────────────────────────────────────────────────

function renderObservanceCard(officeData, currentObservance) {
  const alt = officeData.alternate;
  if (!alt) return '';
  const isUsingAlt = currentObservance === 'alternate';
  if (isUsingAlt) {
    return `<div class="observance-card observance-card--alt">
      <span class="observance-card-name">${esc(alt.label)}</span>
      <a href="${hashFor(state.date, state.office, 'primary')}" class="observance-card-link">← Primary observance</a>
    </div>`;
  }
  return `<div class="observance-card">
    <span class="observance-card-label">Also observed</span>
    <span class="observance-card-name">${esc(alt.label)}</span>
    <a href="${hashFor(state.date, state.office, 'alternate')}" class="observance-card-link">Use this observance →</a>
  </div>`;
}

// ── Office HTML building ──────────────────────────────────────────────────────

function psalmWithGloria(citation, shared) {
  return psalmPlaceholder(citation) + gloriaHtml(shared);
}

function gloriaHtml(shared) {
  if (!shared || !shared.doxology) return '';
  return `<p class="seg-rubric">At the end of the Psalm one of the following may be said or sung.</p>`
       + `<div class="psalm-gloria">${renderAlternatives(shared.doxology, shared, 'doxology')}</div>`;
}

/**
 * Render the psalm section: heading, rubric, and tab panels (All + individual).
 * Handles both psalm_sets (alternative groups) and plain psalms (sequential + multi-tab).
 * @param {object} officeData - morning|evening office object from lectionary JSON
 * @param {object} shared - offices._shared
 * @returns {string} HTML string
 */
function psalmHtml(officeData, shared) {
  const psalms = officeData.psalms || [];
  const psalmSets = officeData.psalm_sets;
  const officeLabel = officeData.label ? `${esc(officeData.label)} — ` : '';
  let html = '';
  if (psalmSets && psalmSets.length) {
    // psalm_sets: alternative groups (e.g. [59, 60] or 19, 46).
    // Add an "All" tab so the user can see every psalm; individual set tabs follow.
    const allFlat = psalmSets.flat();
    const setLabels = psalmSets.map(set =>
      set.map(p => { const c = typeof p === 'object' ? p.citation : p; return (typeof p === 'object' && p.optional) ? `[${c}]` : c; }).join(', ')
    );
    const label = setLabels.join(' or ');
    html += `<h3 class="psalm-heading">${officeLabel}Psalm${allFlat.length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    html += `<p class="seg-rubric">A Psalm from the appointed lectionary is said or sung.</p>`;
    const stateKey = 'pwc-psalmset-' + allFlat.map(p => typeof p === 'object' ? p.citation : p).join('-');
    const idBase = stateKey.replace(/[^a-zA-Z0-9-]/g, '_');
    const saved = parseInt(localStorage.getItem(stateKey) || '0');
    const active = Math.min(Math.max(0, saved), psalmSets.length); // 0 = All
    const tabsHtml = [
      `<button class="alt-tab${active === 0 ? ' alt-tab-active' : ''}" role="tab" aria-selected="${active === 0}" aria-controls="${idBase}-panel-0" id="${idBase}-tab-0" data-idx="0" data-key="${esc(stateKey)}">All</button>`
    ].concat(psalmSets.map((set, si) => {
      const lbl = setLabels[si];
      const i = si + 1;
      return `<button class="alt-tab${i === active ? ' alt-tab-active' : ''}" role="tab" aria-selected="${i === active}" aria-controls="${idBase}-panel-${i}" id="${idBase}-tab-${i}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(lbl)}</button>`;
    })).join('');
    // Panel 0: all psalms in sequence
    let allHtml = '';
    allFlat.forEach(p => { allHtml += psalmPlaceholder(p); });
    allHtml += gloriaHtml(shared);
    html += `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabsHtml}</div>`;
    html += `<div class="alt-panel${active !== 0 ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-0" aria-labelledby="${idBase}-tab-0" data-idx="0">${allHtml}</div>`;
    // Panels 1…N: individual sets
    psalmSets.forEach((set, si) => {
      const i = si + 1;
      let setHtml = '';
      set.forEach(p => { setHtml += psalmPlaceholder(p); });
      setHtml += gloriaHtml(shared);
      html += `<div class="alt-panel${i !== active ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${i}" aria-labelledby="${idBase}-tab-${i}" data-idx="${i}">${setHtml}</div>`;
    });
    html += `</div>`;
  } else if (psalms.length) {
    const label = psalms.map(p => typeof p === 'object' ? p.citation : p).join(', ');
    html += `<h3 class="psalm-heading">${officeLabel}Psalm${psalms.length > 1 ? 's' : ''}: ${esc(label)}</h3>`;
    if (psalms.length === 1) {
      html += `<p class="seg-rubric">The following Psalm from the appointed lectionary is said or sung.</p>`;
      html += psalmWithGloria(psalms[0], shared);
    } else {
      // Multiple appointed psalms — all said in sequence; tabs let you focus on one.
      const stateKey = 'pwc-psalm-' + psalms.map(p => typeof p === 'object' ? p.citation : p).join('-');
      const idBase = stateKey.replace(/[^a-zA-Z0-9-]/g, '_');
      const saved = parseInt(localStorage.getItem(stateKey) || '0');
      const active = Math.min(Math.max(0, saved), psalms.length); // 0 = All
      const tabsHtml = [
        `<button class="alt-tab${active === 0 ? ' alt-tab-active' : ''}" role="tab" aria-selected="${active === 0}" aria-controls="${idBase}-panel-0" id="${idBase}-tab-0" data-idx="0" data-key="${esc(stateKey)}">All</button>`
      ].concat(psalms.map((p, i) => {
        const c = typeof p === 'object' ? p.citation : p;
        const tabIdx = i + 1;
        return `<button class="alt-tab${tabIdx === active ? ' alt-tab-active' : ''}" role="tab" aria-selected="${tabIdx === active}" aria-controls="${idBase}-panel-${tabIdx}" id="${idBase}-tab-${tabIdx}" data-idx="${tabIdx}" data-key="${esc(stateKey)}">Psalm ${esc(c)}</button>`;
      })).join('');
      html += `<p class="seg-rubric">The following Psalms from the appointed lectionary are said or sung.</p>`;
      html += `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabsHtml}</div>`;
      // Panel 0: all psalms in sequence
      let allHtml = '';
      psalms.forEach(p => { allHtml += psalmPlaceholder(p); });
      allHtml += gloriaHtml(shared);
      html += `<div class="alt-panel${active !== 0 ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-0" aria-labelledby="${idBase}-tab-0" data-idx="0">${allHtml}</div>`;
      // Panels 1…N: individual psalms
      psalms.forEach((p, i) => {
        const tabIdx = i + 1;
        html += `<div class="alt-panel${tabIdx !== active ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${tabIdx}" aria-labelledby="${idBase}-tab-${tabIdx}" data-idx="${tabIdx}">`;
        html += psalmWithGloria(p, shared);
        html += `</div>`;
      });
      html += `</div>`;
    }
  }
  return html;
}

/**
 * Render the full Proclamation of the Word section: psalms → lesson 1 → responsory → lesson 2 → canticle.
 * @param {object} officeData - morning|evening office object
 * @param {object} form - office form from offices.json
 * @param {object} shared - offices._shared
 * @returns {string} HTML string
 */
function proclamationHtml(officeData, form, shared) {
  const lessons = (officeData.lessons || []);
  let html = psalmHtml(officeData, shared);
  if (lessons.length > 0) html += lessonHtml(lessons[0], shared, form);
  if (form) html += renderSubsection('The Responsory', form.responsory, shared);
  if (lessons.length > 1) html += lessonHtml(lessons[1], shared, form);
  if (form) html += renderSubsection('The Canticle', form.canticle, shared);
  for (const lesson of lessons.slice(2)) html += lessonHtml(lesson, shared, form);
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
function collectToggleHtml(collects, collectRef, seasonalSegs, shared, fatsEntry) {
  // Separate the general "Additional intercessions…" rubric (display above toggle)
  // from the actual seasonal collect content.
  let splitAt = 0;
  while (splitAt < seasonalSegs.length && seasonalSegs[splitAt].type === 'rubric'
         && SC_HEADER.test(seasonalSegs[splitAt].text)) splitAt++;
  const generalRubrics = seasonalSegs.slice(0, splitAt);
  const seasonalContent = seasonalSegs.slice(splitAt);

  const hasDaily      = !!collectRef;
  const basResolvable = hasDaily && !!lookupCollect(collects, collectRef);
  const hasSeasonal   = seasonalContent.some(s => s.type !== 'rubric');

  // Detect Occasional Prayer alternative in the collect ref (e.g. "344 or 8, 677 (The King)")
  const occPage = hasDaily ? collectSecondaryPage(collectRef) : null;
  const occCollect = (occPage && collects[occPage]) || null;

  // FATS collect: shown as fallback when BAS collect is absent or unresolvable.
  const fatsCollect = (!hasDaily || !basResolvable) ? (fatsEntry && fatsEntry.collect) || null : null;

  let html = '';
  if (generalRubrics.length) html += `<div class="liturgy">${renderSegments(generalRubrics, shared)}</div>`;

  if (!hasDaily && !hasSeasonal && !fatsCollect) return html;

  const stateKey = 'pwc-alt-collect';
  const idBase   = 'pwc-alt-collect';
  const savedIdx = parseInt(localStorage.getItem(stateKey) || '0');

  // Helper: builds one tab-block from arrays of [label, htmlContent] pairs.
  function tabBlock(entries) {
    const activeIdx = Math.min(Math.max(0, savedIdx), entries.length - 1);
    const tabs = entries.map(([label], i) =>
      `<button class="alt-tab${i === activeIdx ? ' alt-tab-active' : ''}" role="tab" aria-selected="${i === activeIdx}" aria-controls="${idBase}-panel-${i}" id="${idBase}-tab-${i}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(label)}</button>`
    ).join('');
    const panels = entries.map(([, content], i) =>
      `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${i}" aria-labelledby="${idBase}-tab-${i}" data-idx="${i}">${content}</div>`
    ).join('');
    return `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabs}</div>${panels}</div>`;
  }

  function occPanelHtml() {
    return `<p class="alt-source">${esc(occCollect.name)}</p><p class="collect-text">${esc(occCollect.text)}</p>`;
  }

  function fatsPanelHtml() {
    const label = fatsEntry && fatsEntry.collect ? (fatsEntry.date || 'For All The Saints') : '';
    return `<p class="alt-source">${esc(label)}</p><p class="collect-text">${esc(fatsCollect)}</p>`;
  }

  // Ordinary time: seasonal_collects is a single alternatives block (Group I / Group II).
  // Render as 3 flat tabs (+ optional Occasional Prayer tab) instead of nesting.
  const isSingleAlt = seasonalContent.length === 1 && seasonalContent[0].type === 'alternatives';
  const SC_ALT_EITHER = /^Either the Collect/i;

  if (isSingleAlt) {
    const altGroups = seasonalContent[0].groups || [];
    const entries = [];
    if (hasDaily) entries.push(['Collect of the Day', collectHtml(collects, collectRef)]);
    if (fatsCollect && !hasDaily) entries.push(['Collect of the Day', fatsPanelHtml()]);
    altGroups.forEach(g => {
      const cleanSegs = g.segments.filter(s =>
        !(s.type === 'rubric' && (SC_ALT_EITHER.test(s.text) || SC_FOOTER.test(s.text)))
      );
      entries.push(['Seasonal ' + g.label, `<div class="liturgy">${renderSegments(cleanSegs, shared)}</div>`]);
    });
    if (occCollect) entries.push([occCollect.name, occPanelHtml()]);
    html += tabBlock(entries);
    return html;
  }

  if (hasDaily && hasSeasonal) {
    const periodMarker = seasonalContent.find(s => s.type === 'rubric');
    const displaySeasonal = seasonalContent.filter(s => s.type !== 'rubric');
    const seasonalTitle = periodMarker ? `<p class="alt-source">${esc(periodMarker.text)}</p>` : '';
    const entries = [
      ['Collect of the Day', collectHtml(collects, collectRef)],
      ['Seasonal Collect', seasonalTitle + `<div class="liturgy">${renderSegments(displaySeasonal, shared)}</div>`],
    ];
    if (occCollect) entries.push([occCollect.name, occPanelHtml()]);
    html += tabBlock(entries);
  } else if (hasDaily) {
    if (occCollect) {
      html += tabBlock([
        ['Collect of the Day', collectHtml(collects, collectRef)],
        [occCollect.name, occPanelHtml()],
      ]);
    } else {
      html += `<h3 class="office-subsection-title">Collect of the Day</h3>${collectHtml(collects, collectRef)}`;
    }
  } else if (fatsCollect) {
    // No BAS collect entry — fall back to FATS collect
    if (hasSeasonal) {
      const periodMarker = seasonalContent.find(s => s.type === 'rubric');
      const displaySeasonal = seasonalContent.filter(s => s.type !== 'rubric');
      const seasonalTitle = periodMarker ? `<p class="alt-source">${esc(periodMarker.text)}</p>` : '';
      html += tabBlock([
        ['Collect of the Day', fatsPanelHtml()],
        ['Seasonal Collect', seasonalTitle + `<div class="liturgy">${renderSegments(displaySeasonal, shared)}</div>`],
      ]);
    } else {
      html += `<h3 class="office-subsection-title">Collect of the Day</h3>${fatsPanelHtml()}`;
    }
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

/**
 * Top-level render: fetch all data, assemble the full office HTML, and inject it into #office-content.
 * Orchestrates fetchOnce, fetchDay, season resolution, form lookup, and all section renderers.
 * @param {string} dateStr - YYYY-MM-DD
 * @param {string} officeType - 'mp' | 'ep'
 * @param {string} translation - 'kjv' | 'nrsvue'
 */
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

  // Update nav date immediately (even for out-of-range dates, so the user
  // sees the date they navigated to, not the previous page's date).
  document.getElementById('nav-date').textContent = fmtNavDate(dateStr);

  // Bounds enforcement before attempting to fetch the day file.
  const boundsMax = offsetDate(bounds.christmas_ii, 6);
  if (dateStr > boundsMax) {
    contentEl.innerHTML = `<div class="out-of-range-msg">
      <p class="out-of-range-title">Readings not yet available</p>
      <p>Coverage extends through <strong>${esc(fmtFullDate(boundsMax))}</strong>.</p>
      <p class="out-of-range-note">Year A readings (Advent 2026 and beyond) are in preparation.</p>
      <p><a href="${hashFor(todayStr(), defaultOffice())}">Return to today</a></p>
    </div>`;
    return;
  }
  if (dateStr < bounds.advent_i) {
    contentEl.innerHTML = `<div class="out-of-range-msg">
      <p class="out-of-range-title">Outside coverage</p>
      <p>Daily Office data begins with Advent I, ${esc(bounds.advent_i.slice(0, 4))}.</p>
      <p><a href="${hashFor(todayStr(), defaultOffice())}">Return to today</a></p>
    </div>`;
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

  // FATS data is optional — absent in dev until extract_fats.py has been run.
  const fats = await fetchOnce('fats', `${DATA}/fats/saints.json`).catch(() => null);
  const fatsEntry = lookupFatsEntry(fats, day.name);
  const shared = offices._shared || {};

  // Sync date picker. Min = 12 months ago (rolling window matches lectionary coverage).
  const picker = document.getElementById('nav-date-picker');
  if (picker) {
    const today = new Date();
    const twelveMonthsAgo = new Date(today.getFullYear() - 1, today.getMonth(), 1);
    const pickerMin = `${twelveMonthsAgo.getFullYear()}-${String(twelveMonthsAgo.getMonth()+1).padStart(2,'0')}-01`;
    picker.min = pickerMin; picker.max = boundsMax; picker.value = dateStr;
  }

  const d = new Date(dateStr + 'T00:00:00Z');
  const weekday = d.getUTCDay();
  const season = seasonOf(dateStr, bounds);
  const fSeason = officeFormSeason(dateStr, bounds);
  const weekIdx = seasonWeekIndex(dateStr, fSeason, bounds);
  const key = formKey(fSeason, officeType, weekday);
  const form = offices[key] || null;

  document.documentElement.setAttribute('data-season', season);

  const officeData = officeType === 'mp' ? (day.morning || {}) : (day.evening || {});

  // Nav
  const prevEl = document.getElementById('nav-prev');
  const nextEl = document.getElementById('nav-next');
  const prevDate = offsetDate(dateStr, -1);
  const nextDate = offsetDate(dateStr, +1);
  if (prevDate < bounds.advent_i) { prevEl.removeAttribute('href'); prevEl.classList.add('nav-disabled'); }
  else { prevEl.href = hashFor(prevDate, officeType); prevEl.classList.remove('nav-disabled'); }
  if (nextDate > boundsMax) { nextEl.removeAttribute('href'); nextEl.classList.add('nav-disabled'); }
  else { nextEl.href = hashFor(nextDate, officeType); nextEl.classList.remove('nav-disabled'); }
  document.getElementById('nav-mp').href    = hashFor(dateStr, 'mp');
  document.getElementById('nav-ep').href    = hashFor(dateStr, 'ep');
  document.getElementById('nav-mp').classList.toggle('nav-active', officeType === 'mp');
  document.getElementById('nav-ep').classList.toggle('nav-active', officeType === 'ep');
  document.getElementById('nav-translation').value = translation;

  // Header
  const officeName = officeType === 'mp' ? 'Morning Prayer' : 'Evening Prayer';
  const activeObs = state.observance === 'alternate' && officeData.alternate ? 'alternate' : 'primary';
  const activeOfficeData = activeObs === 'alternate' ? officeData.alternate : officeData;
  const activeName = activeObs === 'alternate'
    ? (officeData.alternate.label || officeData.alternate.name || day.name)
    : day.name;
  document.title = `${officeName} — ${activeName}`;
  document.getElementById('day-office-name').textContent = officeName;
  document.getElementById('day-title').textContent = activeName;
  document.getElementById('day-subtitle').textContent = fmtFullDate(dateStr);

  const hexes = colourHexes(day.colour);
  const firstHex = hexes[0] || '#b5a882';
  document.documentElement.style.setProperty('--color-day', firstHex);
  const colourChip = hexes.length > 0
    ? `<span class="meta-item">`
      + `<span class="meta-lbl">Colour</span>`
      + (hexes.length > 1
          ? `<button class="colour-chip colour-chip-toggle" style="background:${firstHex}" data-hexes='${JSON.stringify(hexes)}' data-idx="0" title="Tap to cycle liturgical colour" aria-label="${esc(day.colour)} — tap to cycle"></button>`
          : `<span class="colour-chip" style="background:${firstHex}"></span>`)
      + `<span class="colour-name meta-val">${esc(day.colour)}`
      + (hexes.length > 1 ? ` <span class="colour-cycle-hint" aria-hidden="true">↺</span>` : '')
      + `</span>`
      + `</span>`
    : '';
  const seasonLabel = season === 'OrdinaryTime' ? 'Ordinary Time' : season;
  document.getElementById('day-meta').innerHTML =
    `<span class="meta-item meta-item--season">`
    + `<span class="meta-lbl">Season</span>`
    + `<span class="meta-val">${esc(seasonLabel)}</span>`
    + `</span>`
    + `<span class="meta-sep">·</span>`
    + `<span class="meta-item">${esc(formatRank(day.rank))}</span>`
    + colourChip;

  document.querySelectorAll('.day-note, .day-note-details').forEach(el => el.remove());

  // ── Office + Observance controls in day header ────────────────────────────
  const ctrlEl = document.getElementById('day-office-controls');
  if (ctrlEl) {
    let ctrlHtml = `<div class="day-ctrl-group">
      <div class="day-ctrl-seg">
        <a href="${hashFor(dateStr, 'mp')}" class="day-ctrl-btn${officeType === 'mp' ? ' is-active' : ''}">Morning Prayer</a>
        <a href="${hashFor(dateStr, 'ep')}" class="day-ctrl-btn${officeType === 'ep' ? ' is-active' : ''}">Evening Prayer</a>
      </div></div>`;
    if (officeData.alternate) {
      const altLabel = officeData.alternate.label || 'Alternate';
      const primaryLabel = day.name.length > 26 ? day.name.slice(0,24)+'\u2026' : day.name;
      ctrlHtml += `<div class="day-ctrl-group day-ctrl-group--obs">
        <div class="day-ctrl-cap">Observance \u00b7 whose readings <span class="day-ctrl-obs-mark">\u25c6</span></div>
        <div class="day-ctrl-seg day-ctrl-seg--obs">
          <a href="${hashFor(dateStr, officeType, 'primary')}" class="day-ctrl-btn${activeObs === 'primary' ? ' is-active' : ''}">
            ${esc(primaryLabel)}</a>
          <a href="${hashFor(dateStr, officeType, 'alternate')}" class="day-ctrl-btn${activeObs === 'alternate' ? ' is-active' : ''}">
            ${esc(altLabel)}</a>
        </div></div>`;
    }
    ctrlEl.innerHTML = ctrlHtml;
  }
  const SUPPRESS_NOTE_TYPES = new Set(['ember_crossref', 'rogation_crossref', 'precedence_rule', 'reconciliation_propers']);
  if (day.notes && day.notes.length) {
    const headerEl = document.getElementById('day-header');

    // Convert bare URLs in a string to clickable links, returned as a DocumentFragment.
    const renderNoteText = t => {
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

    day.notes.forEach(n => {
      if (typeof n === 'object' && SUPPRESS_NOTE_TYPES.has(n.type)) return;
      const type = typeof n === 'object' ? (n.type || 'pastoral') : 'pastoral';
      const text = typeof n === 'object' ? n.text : n;

      // ── O Antiphon — liturgical block with Latin title ──────────────────────
      if (type === 'o_antiphon') {
        // Text format: "O Sapientia: O Wisdom, coming forth…"
        const colonIdx = text.indexOf(': ');
        const latinName = colonIdx > 0 ? text.slice(0, colonIdx) : 'O Antiphon';
        const body = colonIdx > 0 ? text.slice(colonIdx + 2) : text;
        const block = document.createElement('div');
        block.className = 'day-note day-note--antiphon';
        const label = document.createElement('span');
        label.className = 'note-antiphon-label';
        label.textContent = latinName;
        const bodyP = document.createElement('p');
        bodyP.className = 'note-antiphon-body';
        bodyP.appendChild(renderNoteText(body));
        block.appendChild(label);
        block.appendChild(bodyP);
        headerEl.appendChild(block);
        return;
      }

      // ── Civil day / Week of Prayer — muted informational note ───────────────
      if (type === 'civil_day' || type === 'week_of_prayer') {
        const colonIdx = text.indexOf(': ');
        const title = colonIdx > 0 ? text.slice(0, colonIdx) : '';
        const body  = colonIdx > 0 ? text.slice(colonIdx + 2) : text;
        const p = document.createElement('p');
        p.className = `day-note day-note--info`;
        if (title) {
          const strong = document.createElement('strong');
          strong.textContent = title + ': ';
          p.appendChild(strong);
        }
        p.appendChild(renderNoteText(body));
        headerEl.appendChild(p);
        return;
      }

      // ── Default: pastoral / office_note — existing expand-on-read behaviour ─
      const p = document.createElement('p');
      p.className = 'day-note';
      if (text.length > 100) {
        const cut = text.lastIndexOf(' ', 80) || 80;
        const short = text.slice(0, cut) + '…';
        p.appendChild(renderNoteText(short));
        const expandBtn = document.createElement('button');
        expandBtn.className = 'note-expand-btn';
        expandBtn.textContent = 'Read more';
        p.appendChild(expandBtn);
        expandBtn.addEventListener('click', () => {
          p.innerHTML = '';
          p.appendChild(renderNoteText(text));
        });
      } else {
        p.appendChild(renderNoteText(text));
      }
      headerEl.appendChild(p);
    });
  }

  const seasonalSegs = form ? filterSeasonalCollects(form.seasonal_collects || [], weekIdx) : [];

  let html = renderObservanceCard(officeData, activeObs);

  // ── FATS biographical notice ───────────────────────────────────────────────
  if (fatsEntry && fatsEntry.bio) {
    const bioParas = fatsEntry.bio.split(/\n\n+/).map(p => `<p>${esc(p.replace(/\n/g, ' '))}</p>`).join('');
    html += `<details class="fats-bio">
      <summary class="fats-bio-toggle">About ${esc(day.name)}</summary>
      <div class="fats-bio-body">${bioParas}</div>
    </details>`;
  }

  // ── Form title / subtitle ──────────────────────────────────────────────────
  // Suppress on ordinary-time: "Evening Prayer For Saturday" is redundant with
  // the day-office-name header. Show only for seasonal forms whose titles carry
  // liturgical meaning (e.g., "Advent Morning Prayer", "Easter Evening Prayer").
  if (form && form.title && fSeason !== 'OrdinaryTime') {
    const titleStr = form.title.replace(/\b\w/g, c => c.toUpperCase());
    html += `<div class="form-header"><p class="form-title">${esc(titleStr)}</p>`;
    if (form.subtitle) html += `<p class="form-subtitle">${esc(form.subtitle)}</p>`;
    html += `</div>`;
  }

  // ── Gathering ──────────────────────────────────────────────────────────────
  if (form && (form.opening_responses || form.thanksgiving_for_light || form.phos_hilaron || form.invitatory)) {
    html += `<h2 class="office-section-title">The Gathering of the Community</h2>`;
    let openingResponses = form.opening_responses;
    if (openingResponses?.type === 'shared' && shared)
      openingResponses = shared[openingResponses.key];
    if (openingResponses && openingResponses.length)
      html += renderSubsection('Introductory Responses', openingResponses, shared);
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
  html += `<div class="obs-readings${activeObs !== 'primary' ? ' obs-hidden' : ''}" data-obs="primary">`;
  if (officeData.label) html += `<h3 class="office-subsection-title">${esc(officeData.label)}</h3>`;
  html += proclamationHtml(officeData, form, shared);
  html += `</div>`;

  // Alternate readings.
  if (officeData.alternate) {
    const alt = officeData.alternate;
    html += `<div class="obs-readings${activeObs !== 'alternate' ? ' obs-hidden' : ''}" data-obs="alternate">`;
    if (alt.label) html += `<h3 class="office-subsection-title">${esc(alt.label)}</h3>`;
    html += proclamationHtml(alt, form, shared);
    html += `</div>`;
  }

  // Affirmation of Faith closes the Proclamation section (not Prayers).
  if (form && form.affirmation && form.affirmation.length) {
    const mpOrEp = (form.title || '').toLowerCase().startsWith('evening') ? 'Evening' : 'Morning';
    const hasLitany = form.litany && form.litany.length;
    const affirmTransition = hasLitany
      ? `${mpOrEp} Prayer continues with an Affirmation of Faith or the Litany.`
      : `${mpOrEp} Prayer continues with the Affirmation of Faith.`;
    html += `<p class="seg-rubric">${esc(affirmTransition)}</p>`;
    html += `<h3 class="office-subsection-title">Affirmation of Faith</h3>`;
    html += `<div class="liturgy">${renderSegments(form.affirmation, shared)}</div>`;
  }

  // ── Prayers ────────────────────────────────────────────────────────────────
  if (form && (form.intercessions || form.litany || form.lords_prayer_intro || (form.seasonal_collects && form.seasonal_collects.length) || officeData.collect || (fatsEntry && fatsEntry.collect))) {
    html += `<h2 class="office-section-title">The Prayers of the Community</h2>`;
    // Day-specific intercession prompts guide the free-prayer period before the formal litany.
    if (form.intercessions && form.intercessions.length)
      html += renderSubsection('Intercessions and Thanksgivings', form.intercessions, shared);
    if (form.litany && form.litany.length) {
      if (form.affirmation && form.affirmation.length) {
        const mpOrEp2 = (form.title || '').toLowerCase().startsWith('evening') ? 'Evening' : 'Morning';
        html += `<p class="seg-rubric">${esc(mpOrEp2 + ' Prayer continues with the Litany.')}</p>`;
      }
      html += renderSubsection('The Litany', form.litany, shared);
    }
    html += `<h3 class="office-subsection-title">The Collect</h3>`;
    html += `<div id="prayers-collect">${collectToggleHtml(collects, activeOfficeData.collect, seasonalSegs, shared, fatsEntry)}</div>`;
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

  html += `<p class="scripture-attr" id="scripture-attr">Translation: ${esc(translation.toUpperCase())}</p>`;

  contentEl.innerHTML = html;

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
        `<div class="scripture-verse"><span class="verse-num" aria-hidden="true">${v}</span><span class="verse-text">${esc(text)}</span></div>`
      ).join('');
      // UX-08: Inform the user when the preferred translation was unavailable.
      if (usedTranslation !== translation) {
        el.innerHTML += `<p class="scripture-fallback-note">[${usedTranslation.toUpperCase()} shown — ${translation.toUpperCase()} unavailable for this reading]</p>`;
      }
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

// ── Stale-date banner ─────────────────────────────────────────────────────────

function showStaleBanner(date) {
  if (sessionStorage.getItem('pwc-stale-banner-dismissed-' + date)) return;
  let banner = document.getElementById('stale-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'stale-banner';
    banner.className = 'stale-banner';
    const contentEl = document.getElementById('office-content');
    contentEl.parentNode.insertBefore(banner, contentEl);
  }
  banner.innerHTML = `<span>Viewing ${esc(fmtFullDate(date))}</span>`
    + ` <span class="stale-sep" aria-hidden="true">·</span> `
    + `<a class="stale-today" href="#">Jump to today →</a>`
    + `<button class="stale-close" aria-label="Dismiss">×</button>`;
  banner.hidden = false;
  banner.querySelector('.stale-today').addEventListener('click', e => {
    e.preventDefault();
    sessionStorage.setItem('pwc-stale-banner-dismissed-' + date, '1');
    hideStaleBanner();
    history.pushState({}, '', location.pathname);
    handleHashChange();
  });
  banner.querySelector('.stale-close').addEventListener('click', () => {
    sessionStorage.setItem('pwc-stale-banner-dismissed-' + date, '1');
    hideStaleBanner();
  });
}

function hideStaleBanner() {
  const banner = document.getElementById('stale-banner');
  if (banner) banner.hidden = true;
}

// ── Evaluation banner ─────────────────────────────────────────────────────────

function initEvalBanner() {
  if (localStorage.getItem('pwc-eval-dismissed')) return;
  const banner = document.createElement('div');
  banner.id = 'eval-banner';
  banner.className = 'eval-banner';
  banner.innerHTML = `<span>Private evaluation — please do not share or distribute.</span>`
    + `<button class="eval-banner-dismiss" aria-label="Dismiss">&#215;</button>`;
  document.getElementById('main').insertAdjacentElement('afterbegin', banner);
  banner.querySelector('.eval-banner-dismiss').addEventListener('click', () => {
    localStorage.setItem('pwc-eval-dismissed', '1');
    banner.remove();
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────

function handleHashChange() {
  const parsed = parseHash(location.hash);
  const prevDate = state.date;
  if (parsed) {
    state.date = parsed.date;
    state.office = parsed.office;
    state.observance = parsed.observance;
  } else {
    // No valid hash — render today in place without modifying the URL.
    state.date = todayStr();
    state.office = defaultOffice();
    state.observance = 'primary';
  }
  if (parsed && parsed.date < todayStr()) {
    showStaleBanner(parsed.date);
  } else {
    // Navigating to today or future — clear any sessionStorage dismissal for the
    // previous stale date so the banner resets on the next visit to that date.
    if (prevDate && prevDate < todayStr()) {
      sessionStorage.removeItem('pwc-stale-banner-dismissed-' + prevDate);
    }
    hideStaleBanner();
  }
  render(state.date, state.office, state.translation);
}

// ── Init ──────────────────────────────────────────────────────────────────────

function initScrollBehaviour() {
  const nav    = document.getElementById('nav');
  const spacer = document.getElementById('nav-spacer');
  // Stable nav: only sync height for the spacer; no compact collapse while praying.
  function syncNavPad() { spacer.style.height = nav.offsetHeight + 'px'; }
  syncNavPad();
  window.addEventListener('load', syncNavPad);
  new ResizeObserver(syncNavPad).observe(nav);
}

function activateTab(tab, idx) {
  const stateKey = tab.dataset.key;
  localStorage.setItem(stateKey, String(idx));
  // Update every alt-block sharing this key so linked blocks (e.g. doxology
  // after each psalm) stay in sync.
  const seen = new Set();
  document.querySelectorAll(`#office-content .alt-tab[data-key="${CSS.escape(stateKey)}"]`).forEach(t => {
    const b = t.closest('.alt-block');
    if (!b) return;
    const isActive = parseInt(t.dataset.idx) === idx;
    t.classList.toggle('alt-tab-active', isActive);
    t.setAttribute('aria-selected', String(isActive));
    if (!seen.has(b)) {
      seen.add(b);
      b.querySelectorAll(':scope > .alt-panel').forEach((p, i) => p.classList.toggle('alt-panel-hidden', i !== idx));
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initFontSize();
  initScrollBehaviour();

  document.getElementById('nav-brand').addEventListener('click', e => {
    e.preventDefault();
    history.pushState({}, '', location.pathname);
    handleHashChange();
  });

  // Settings sheet
  const settingsSheet = document.getElementById('settings-sheet');
  const settingsBtn = document.getElementById('nav-settings-btn');
  const settingsClose = document.getElementById('settings-close-btn');
  const settingsBackdrop = document.getElementById('settings-backdrop');

  function openSettings() {
    settingsSheet.setAttribute('aria-hidden', 'false');
    settingsBtn.setAttribute('aria-expanded', 'true');
  }
  function closeSettings() {
    settingsSheet.setAttribute('aria-hidden', 'true');
    settingsBtn.setAttribute('aria-expanded', 'false');
  }
  settingsBtn.addEventListener('click', openSettings);
  settingsClose.addEventListener('click', closeSettings);
  settingsBackdrop.addEventListener('click', closeSettings);

  // Book mode toggle — wired to both the header button and the settings seg
  const viewToggle = document.getElementById('view-toggle');
  const bookModeKey = 'pwc-book-mode';

  function syncViewModeUI(isBook) {
    if (viewToggle) {
      viewToggle.setAttribute('aria-pressed', String(isBook));
      viewToggle.innerHTML = viewToggle.innerHTML.replace(
        isBook ? 'Book view' : 'Interactive',
        isBook ? 'Interactive' : 'Book view'
      );
    }
    const offBtn = document.getElementById('view-mode-office');
    const bkBtn  = document.getElementById('view-mode-book');
    if (offBtn) { offBtn.classList.toggle('is-active', !isBook); offBtn.setAttribute('aria-pressed', String(!isBook)); }
    if (bkBtn)  { bkBtn.classList.toggle('is-active',  isBook);  bkBtn.setAttribute('aria-pressed', String(isBook)); }
  }

  if (localStorage.getItem(bookModeKey) === '1') {
    document.body.classList.add('book-mode');
    syncViewModeUI(true);
  }

  if (viewToggle) viewToggle.addEventListener('click', () => {
    const isBook = document.body.classList.toggle('book-mode');
    syncViewModeUI(isBook);
    localStorage.setItem(bookModeKey, isBook ? '1' : '0');
  });

  const viewModeOffice = document.getElementById('view-mode-office');
  const viewModeBook   = document.getElementById('view-mode-book');
  if (viewModeOffice) viewModeOffice.addEventListener('click', () => {
    if (document.body.classList.contains('book-mode')) {
      document.body.classList.remove('book-mode');
      syncViewModeUI(false);
      localStorage.setItem(bookModeKey, '0');
    }
  });
  if (viewModeBook) viewModeBook.addEventListener('click', () => {
    if (!document.body.classList.contains('book-mode')) {
      document.body.classList.add('book-mode');
      syncViewModeUI(true);
      localStorage.setItem(bookModeKey, '1');
    }
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSettings();
    if (e.key === 'b' && !e.target.matches('input,select,textarea')) {
      const isBook = document.body.classList.toggle('book-mode');
      syncViewModeUI(isBook);
      localStorage.setItem(bookModeKey, isBook ? '1' : '0');
    }
  });

  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('font-size-toggle').addEventListener('click', cycleFontSize);

  const sel = document.getElementById('nav-translation');
  sel.value = state.translation;
  sel.addEventListener('change', () => { switchTranslation(sel.value); });

  const picker = document.getElementById('nav-date-picker');
  picker.addEventListener('click', () => { try { picker.showPicker(); } catch (_) {} });
  picker.addEventListener('change', e => {
    if (e.target.value) location.hash = hashFor(e.target.value, state.office);
    picker.blur();
  });
  // Dismiss without selecting (Escape / tap-outside) — remove focus ring immediately.
  picker.addEventListener('cancel', () => { picker.blur(); });

  document.getElementById('day-meta').addEventListener('click', e => {
    const chip = e.target.closest('.colour-chip-toggle');
    if (!chip) return;
    const hexes = JSON.parse(chip.dataset.hexes);
    const idx = (parseInt(chip.dataset.idx) + 1) % hexes.length;
    chip.dataset.idx = String(idx);
    chip.style.background = hexes[idx];
    document.documentElement.style.setProperty('--color-day', hexes[idx]);
  });

  document.getElementById('office-content').addEventListener('click', e => {
    const tab = e.target.closest('.alt-tab');
    if (!tab) return;
    activateTab(tab, parseInt(tab.dataset.idx));
  });

  // Arrow key navigation within a tablist (ARIA keyboard pattern).
  document.getElementById('office-content').addEventListener('keydown', e => {
    const tab = e.target.closest('.alt-tab');
    if (!tab) return;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    e.stopPropagation();
    const tablist = tab.closest('.alt-tabs');
    if (!tablist) return;
    const tabs = Array.from(tablist.querySelectorAll('.alt-tab'));
    const cur = tabs.indexOf(tab);
    const next = e.key === 'ArrowRight'
      ? (cur + 1) % tabs.length
      : (cur - 1 + tabs.length) % tabs.length;
    activateTab(tabs[next], parseInt(tabs[next].dataset.idx));
    tabs[next].focus();
  });

  document.addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.isContentEditable) return;
    // Update state synchronously so rapid keypresses see the latest date.
    if (e.key === 'ArrowLeft'  || e.key === 'h') { state.date = offsetDate(state.date, -1); location.hash = hashFor(state.date, state.office); }
    if (e.key === 'ArrowRight' || e.key === 'l') { state.date = offsetDate(state.date, +1); location.hash = hashFor(state.date, state.office); }
    if (e.key === 'm') { state.office = 'mp'; location.hash = hashFor(state.date, 'mp'); }
    if (e.key === 'e') { state.office = 'ep'; location.hash = hashFor(state.date, 'ep'); }
    if (e.key === 't') { history.pushState({}, '', location.pathname); handleHashChange(); }
  });

  window.addEventListener('hashchange', handleHashChange);

  initEvalBanner();

  // Warm up static fetches.
  fetchOnce('offices',  `${DATA}/offices.json`);
  fetchOnce('collects', `${DATA}/collects.json`);
  fetchOnce('bounds',   `${DATA}/season_bounds.json`);
  fetchOnce('psalter',  `${DATA}/psalter.json`);

  handleHashChange();

  if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
});
