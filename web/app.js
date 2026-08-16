'use strict';

import {
  esc, seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderAlternatives, renderSegments, renderSubsection,
  lessonHtml, lessonsPickRubricHtml, bindMidpoints, parseCitation, expandCitationForDisplay,
  SC_HEADER, SC_FOOTER,
  collectSecondaryPage, assembleSections, formatLiturgicalText, invitatorySegments, phosHilaronSegments,
  splitPsalmRubrics, splitReadingRubrics,
  parseRanges, extractVersesWithChapter, parsePsalmCitation,
  collectPageNum, lookupCollect,
} from './render.js';

// ── Data path ─────────────────────────────────────────────────────────────────
// Dev: python3 -m http.server 8080 from repo root, open /web/ — web/data symlink
// Prod: web/ synced to S3 bucket root, data/ at same root
const DATA = 'data';
const isNative = !!(window.__pwcPlugins?.Capacitor?.isNativePlatform?.());

// ── Storage (localStorage + Capacitor Preferences) ────────────────────────────

function storageGet(key) {
  return localStorage.getItem(key);
}

function storageSet(key, value) {
  localStorage.setItem(key, value);
  if (isNative) {
    window.__pwcPlugins.Preferences.set({ key, value }).catch(() => {});
  }
}

async function migrateStorageToPreferences() {
  if (!isNative) return;
  try {
    const { value: migrated } = await window.__pwcPlugins.Preferences.get({ key: 'pwc-storage-migrated' });
    if (migrated === '1') return;
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith('pwc-')) {
        await window.__pwcPlugins.Preferences.set({ key, value: storageGet(key) });
      }
    }
    await window.__pwcPlugins.Preferences.set({ key: 'pwc-storage-migrated', value: '1' });
  } catch (_) { /* Preferences unavailable */ }
}

async function restoreStorageFromPreferences() {
  if (!isNative) return;
  try {
    const { value: migrated } = await window.__pwcPlugins.Preferences.get({ key: 'pwc-storage-migrated' });
    if (migrated !== '1') return;
    if (localStorage.length > 0) return;
    const keys = ['pwc-translation', 'pwc-theme', 'pwc-font-size',
      'pwc-eval-dismissed', 'pwc-book-mode', 'pwc-alt-collect'];
    for (const key of keys) {
      const { value } = await window.__pwcPlugins.Preferences.get({ key });
      if (value) storageSet(key, value);
    }
  } catch (_) { /* Preferences unavailable */ }
}

// ── Native platform features ──────────────────────────────────────────────────

function updateNativeStatusBar() {
  if (!isNative) return;
  const { StatusBar, Style } = window.__pwcPlugins;
  StatusBar.setStyle({ style: Style.Dark });
  StatusBar.setBackgroundColor({ color: '#15382A' });
}

function initNativeFeatures() {
  if (!isNative) return;

  // Keyboard — hide accessory bar (no text inputs in the app)
  window.__pwcPlugins.Keyboard.setAccessoryBarVisible({ isVisible: false }).catch(() => {});

  // Back-button — minimize instead of exit
  window.__pwcPlugins.App.addListener('backButton', ({ canGoBack }) => {
    if (!canGoBack) {
      window.__pwcPlugins.App.minimizeApp().catch(() => {});
    }
  });

  // Offline detection
  window.__pwcPlugins.Network.getStatus().then(status => {
    window.__pwcOffline = !status.connected;
  }).catch(() => {});
  window.__pwcPlugins.Network.addListener('networkStatusChange', status => {
    window.__pwcOffline = !status.connected;
    if (status.connected && window.__pwcLastRoute) {
      initPage();
    }
  });

  // External links — open in device browser
  document.addEventListener('click', e => {
    const link = e.target.closest('a');
    if (link && link.href && !link.href.startsWith(window.location.origin) && link.href.startsWith('http')) {
      e.preventDefault();
      window.__pwcPlugins.Browser.open({ url: link.href }).catch(() => {});
    }
  });
}

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  date:        todayStr(),
  office:      defaultOffice(),
  observance:  'primary',
  translation: storageGet('pwc-translation') || 'nrsvue',
};

// Evening Prayer (and eve-of-feast observance) begins mid-afternoon in Anglican
// practice; 3pm is the traditional hinge (BUG-31).
function defaultOffice() {
  return new Date().getHours() >= 15 ? 'ep' : 'mp';
}

// ── Theme ─────────────────────────────────────────────────────────────────────

function initTheme() {
  const stored = storageGet('pwc-theme');
  if (stored) {
    document.documentElement.setAttribute('data-theme', stored);
  } else {
    // No explicit user preference — follow system
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (prefersDark) document.documentElement.setAttribute('data-theme', 'dark');
  }
  updateThemeButton();
  updateNativeStatusBar();

  // Listen for system theme changes when no stored override
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!storageGet('pwc-theme')) {
      document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
      updateThemeButton();
    }
  });
}

function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  storageSet('pwc-theme', next);
  updateThemeButton();
  updateNativeStatusBar();
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
  const raw = storageGet('pwc-font-size') || 'medium';
  const stored = raw === 'small' ? 'medium' : raw;
  document.documentElement.setAttribute('data-font-size', stored);
  updateFontSizeButton(stored);
}

function cycleFontSize() {
  const current = document.documentElement.getAttribute('data-font-size') || 'medium';
  const next = FONT_SIZES[(FONT_SIZES.indexOf(current) + 1) % FONT_SIZES.length];
  document.documentElement.setAttribute('data-font-size', next);
  storageSet('pwc-font-size', next);
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

/** Fetch JSON at `url` once; all callers share the same in-flight or resolved promise.
 *  A failed fetch clears its cache slot so a later retry actually re-fetches
 *  instead of replaying the same rejection forever. */
async function fetchOnce(key, url) {
  if (!_cache[key]) {
    _cache[key] = fetch(url)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .catch(err => { _cache[key] = null; throw err; });
  }
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
  if (!_cache.books[k]) {
    _cache.books[k] = fetch(`${DATA}/translations/${translation}/${filename}.json`)
      .then(r => { if (!r.ok) throw new Error(`${filename}: ${r.status}`); return r.json(); })
      .catch(err => { delete _cache.books[k]; throw err; });
  }
  return _cache.books[k];
}

/** Fetch the lectionary entry for `dateStr` (YYYY-MM-DD) from the monthly JSON file. */
function fetchDay(dateStr) {
  const monthKey = dateStr.slice(0, 7);
  const cacheKey = `bas:${monthKey}`;
  if (!_cache.months[cacheKey]) {
    _cache.months[cacheKey] = fetch(`${DATA}/lectionary/${monthKey}.json`)
      .then(r => { if (!r.ok) throw new Error(`${monthKey}: ${r.status}`); return r.json(); })
      .catch(err => { delete _cache.months[cacheKey]; throw err; });
  }
  return _cache.months[cacheKey].then(month => {
    const day = month[dateStr];
    if (!day) throw new Error(`${dateStr}: not found in ${monthKey}.json`);
    return day;
  });
}

// ── Load-error fallback ───────────────────────────────────────────────────────

/** Map a fetch failure to a short, non-technical message — never surface raw error text. */
function friendlyLoadError(err) {
  if (window.__pwcOffline || (typeof navigator !== 'undefined' && navigator.onLine === false)) {
    return 'You appear to be offline. Check your connection and try again.';
  }
  // Browsers reject fetch() with a TypeError for network failures (DNS, CORS, connection drop).
  if (err instanceof TypeError) {
    return 'Unable to load — check your internet connection and try again.';
  }
  // fetchOnce/fetchBook/fetchDay throw `new Error(status)` on a non-OK HTTP response.
  if (/^\d{3}$/.test(String(err && err.message))) {
    return 'This content isn’t available right now.';
  }
  return 'Something went wrong loading this content. Please try again.';
}

/** Render a graceful error message with a "Try again" button into `container`. */
function showLoadError(container, err, onRetry) {
  container.innerHTML = `<div class="error-msg">
    <p>${esc(friendlyLoadError(err))}</p>
    <button type="button" class="error-retry-btn">Try again</button>
  </div>`;
  const btn = container.querySelector('.error-retry-btn');
  if (btn) btn.addEventListener('click', onRetry, { once: true });
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

// ── Navigation ────────────────────────────────────────────────────────────────
// All navigation stays at the root URL — no hash-based routing.
// Refreshing always returns to today with the default office.

function navigateTo(date, office, observance) {
  state.date = date;
  state.office = office;
  state.observance = observance || state.observance || 'primary';
  render(state.date, state.office, state.translation);
}

function initPage() {
  state.date = todayStr();
  state.office = defaultOffice();
  state.observance = 'primary';
  render(state.date, state.office, state.translation);
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

// Day-level observances the header shows as their own meta items (#128).
// `fast_day` and the plain `eve_of:` tags reached the data under ADR 0017 and
// stopped there. They are facts about the calendar day, so both offices carry
// them — but an eve already naming the office it governs is not repeated.
// What one slot of the observance toggle is called. The header title and the
// toggle's own buttons must agree, or the day reads as two different days.
function observanceName(slot, day, isAlternate) {
  if (slot.rank === 'eve') return slot.title || slot.label;
  if (isAlternate) return slot.label || slot.name || day.name;
  return day.name;
}

const MARKER_LABELS = { fast_day: 'Day of discipline and self-denial' };

function dayMarkers(day, activeName, isEve) {
  const markers = (day.observances || []).flatMap(tag => {
    if (tag.startsWith('eve_of:')) {
      const label = 'Eve of ' + tag.slice(7);
      return label === activeName ? [] : [label];
    }
    return MARKER_LABELS[tag] ? [MARKER_LABELS[tag]] : [];
  });
  // The eve took the title, so the day's own commemoration would otherwise
  // vanish from a header that still carries its fast and still opens its
  // biography. Each office names the other's day: the eve on the morning,
  // the commemoration on the evening.
  if (isEve && day.name && day.name !== activeName) markers.unshift(day.name);
  return markers;
}

// ── Psalm parsing and rendering ───────────────────────────────────────────────

// Section headings ("Part I", "Aleph", "Beth", … — see RE_SECTION in
// tools/extract_psalter.py) never carry a verse number or leading space;
// exclude them so they don't get glued onto the previous verse as running text.
const PSALM_SECTION_RE = /^(?:Part\s+[IVX]+\b|(?:Aleph|Beth|Gimel|Daleth|He\b|Waw|Zayin|Heth|Teth|Yodh|Kaph|Lamedh|Mem|Nun|Samekh|Ayin|Pe|Tsadhe|Qoph|Resh|Sin|Shin|Taw)\s+)/i;

function parsePsalmText(rawText) {
  const lines = rawText.split('\n');
  const verses = [];
  let cur = null;
  for (const line of lines) {
    const m = /^(\d+)\s{1,2}(.*)$/.exec(line);
    if (m) {
      if (cur) verses.push(cur);
      cur = { num: parseInt(m[1]), text: m[2] };
    } else if (cur && line.trim() && !PSALM_SECTION_RE.test(line)) {
      cur.text += '\n' + line;
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
  const titleHtml = `<p class="psalm-title">Psalm ${data.number}${data.title ? ` — <span lang="la">${data.title}</span>` : ''}</p>`;
  // Each verse is its own block. formatLiturgicalText emits block-level lines,
  // so a <br> join would add an empty line box between every verse, and the
  // number would sit on a line above its own text.
  const versesHtml = filtered.map(v => {
    const txt = bindMidpoints(formatLiturgicalText(v.text, `<sup>${v.num} </sup>`));
    return `<span class="psalm-verse">${txt}</span>`;
  }).join('');
  return `${titleHtml}<p class="psalm-block">${versesHtml}</p>`;
}

// ── Scripture citation parsing ────────────────────────────────────────────────
// parseRanges/parseVerseRange/parseChapterVerse/extractVersesWithChapter moved
// to render.js (2026-07-27) — pure logic, needed by validate_lectionary.cjs to
// verify every lectionary reading resolves to real verses, and render.js is the
// module non-browser tools can safely import (app.js touches `window` at
// module scope). See issue #19.

/**
 * Render a chapter's verses as HTML paragraphs.
 * @param {Array<{v:number, text:string}>} chVerses - verses in chapter order
 * @param {number} chNum - chapter number
 * @param {Array<number>|null} breaks - sorted first-verse of each paragraph
 * @returns {string} HTML paragraphs
 */
function renderChapterHtml(chVerses, chNum, breaks) {
  const firstV = chVerses[0].v;
  const renderVerse = (v) => {
    const num = (v.v === 1 && firstV === 1) ? '' : `<sup class="verse-num">${v.v}</sup>\u00A0`;
    return `${num}${esc(v.text)}`;
  };
  const chDrop = firstV === 1 ? `<span class="scripture-ch-num">${chNum}</span> ` : '';
  const blocks = [];

  if (!breaks || breaks.length === 0) {
    blocks.push(`<p class="scripture-block">${chDrop}${chVerses.map(renderVerse).join(' ')}</p>`);
    return blocks.join('\n');
  }

  const sortedBreaks = [...breaks].sort((a, b) => a - b);
  for (let i = 0; i < sortedBreaks.length; i++) {
    const paraStart = sortedBreaks[i];
    const paraEnd = i + 1 < sortedBreaks.length ? sortedBreaks[i + 1] - 1 : Infinity;
    const paraVerses = chVerses.filter(v => v.v >= paraStart && v.v <= paraEnd);
    if (paraVerses.length > 0) {
      const prefix = i === 0 ? chDrop : '';
      blocks.push(`<p class="scripture-block">${prefix}${paraVerses.map(renderVerse).join(' ')}</p>`);
    }
  }
  return blocks.join('\n');
}

/**
 * Build HTML for verses grouped by paragraph boundaries.
 * @param {Array<{ch:number, v:number, text:string}>} verses
 * @param {Object} paraMap - book-level map: {chapter: [firstVerseOfEachParagraph]}
 * @returns {string} HTML
 */
function buildParagraphHtml(verses, paraMap) {
  const byChapter = {};
  for (const v of verses) {
    (byChapter[v.ch] || (byChapter[v.ch] = [])).push(v);
  }

  const blocks = [];
  for (const [chStr, chVerses] of Object.entries(byChapter)) {
    blocks.push(renderChapterHtml(chVerses, parseInt(chStr), paraMap[chStr] || null));
  }
  return blocks.join('\n');
}

// ── Office HTML building ──────────────────────────────────────────────────────

// Monotonic ID salt: keeps tab/panel IDs unique when the same stateKey
// renders twice in one document — e.g. a primary and alternate observance
// with identical psalm/reading citations (render.js's renderAlternatives
// has the same _altUid for the same reason). stateKey/data-key stay shared
// so cross-block tab sync and localStorage persistence are unchanged.
let _tabUid = 0;

// Builds a tab widget from [label, htmlContent] pairs, restoring the
// selection saved under stateKey (ADR 0014's alternatives-tab convention,
// shared by the collect, psalm, and reading selectors).
function tabBlockHtml(stateKey, entries) {
  const idBase = stateKey.replace(/[^a-zA-Z0-9-]/g, '_') + '-' + (++_tabUid);
  const savedIdx = parseInt(storageGet(stateKey) || '0');
  const activeIdx = Math.min(Math.max(0, savedIdx), entries.length - 1);
  // Mirrors renderAlternatives in render.js — keep the two in step.
  const tabs = entries.map(([label], i) =>
    `<button class="alt-tab${i === activeIdx ? ' alt-tab-active' : ''}" role="tab" aria-selected="${i === activeIdx}" aria-controls="${idBase}-panel-${i}" id="${idBase}-tab-${i}" data-idx="${i}" data-key="${esc(stateKey)}">${esc(label)}</button>`
  ).join('');
  const panels = entries.map(([, content], i) =>
    `<div class="alt-panel${i !== activeIdx ? ' alt-panel-hidden' : ''}" role="tabpanel" id="${idBase}-panel-${i}" aria-labelledby="${idBase}-tab-${i}" data-idx="${i}">${content}</div>`
  ).join('');
  return `<div class="alt-block"><div class="alt-tabs" role="tablist">${tabs}</div>${panels}</div>`;
}

function gloriaHtml(shared, cue) {
  if (!shared || !shared.doxology) return '';
  // `cue` is the book's own "At the end of the Psalm…" / "After the Psalm…"
  // rubric, extracted per form (#84), replacing the single fixed string that
  // was wrong for 16 of the 30 forms. It introduces the Gloria, so it travels
  // with it into each tab panel rather than sitting above the psalms.
  return renderSegments(cue || [], shared, false)
    + `<div class="psalm-gloria">${renderAlternatives(shared.doxology, shared, 'doxology')}</div>`;
}

/**
 * Render the psalm section: rubric and a tab selector (All + one tab per
 * branch) over the appointed psalms, restored per ADR 0014. Each psalm's own
 * "Psalm N — Title" heading (from renderPsalm) introduces it individually.
 * Handles both psalm_sets (alternative groups) and plain psalms.
 * @param {object} officeData - morning|evening office object from lectionary JSON
 * @param {object} shared - offices._shared
 * @returns {string} HTML string
 */
function psalmHtml(officeData, shared, doxologyCue) {
  const psalms = officeData.psalms || [];
  const psalmSets = officeData.psalm_sets;
  // No introduction is emitted here. It used to be one of three registered
  // variants chosen by what the day appointed; the book prints one sentence
  // regardless (ADR 0019 item 6), and it is now extracted into
  // form.psalm_rubrics and rendered once, above this, by proclamationHtml.
  //
  // The doxology and the cue introducing it sit OUTSIDE the selector, once, for
  // the same reason: the selector chooses which psalms are said, and the
  // doxology follows whichever they were, so it is not part of the choice.
  // Inside the panels it printed once per branch — and book mode makes every
  // panel visible (`.alt-panel-hidden { display: block }`), so the reader saw
  // the whole thing N+1 times over. That repetition is the second half of what
  // ADR 0019 item 6 forbids; the three variants were the first.
  let html = '';
  if (psalmSets && psalmSets.length) {
    const allFlat = psalmSets.flat();
    const setLabels = psalmSets.map(set =>
      set.map(p => { const c = typeof p === 'object' ? p.citation : p; return (typeof p === 'object' && p.optional) ? `[${c}]` : c; }).join(', ')
    );
    const stateKey = 'pwc-psalmset-' + allFlat.map(p => typeof p === 'object' ? p.citation : p).join('-');
    const entries = [['All', allFlat.map(psalmPlaceholder).join('')]].concat(
      psalmSets.map((set, si) => [setLabels[si], set.map(psalmPlaceholder).join('')]));
    html += tabBlockHtml(stateKey, entries);
  } else if (psalms.length > 1) {
    const stateKey = 'pwc-psalm-' + psalms.map(p => typeof p === 'object' ? p.citation : p).join('-');
    const entries = [['All', psalms.map(psalmPlaceholder).join('')]].concat(psalms.map(p => {
      const c = typeof p === 'object' ? p.citation : p;
      return [`Psalm ${c}`, psalmPlaceholder(p)];
    }));
    html += tabBlockHtml(stateKey, entries);
  } else if (psalms.length) {
    html += psalmPlaceholder(psalms[0]);
  }
  if (html) html += gloriaHtml(shared, doxologyCue);
  return html;
}

// A run of extracted rubrics under its section heading. `heading` is omitted
// for the runs that continue a section already headed above.
function rubricRunHtml(segs, shared, heading) {
  if (!segs || !segs.length) return '';
  return (heading ? `<h3 class="office-subsection-title">${esc(heading)}</h3>` : '')
    + `<div class="liturgy">${renderSegments(segs, shared, false)}</div>`;
}

/**
 * Render the full Proclamation of the Word section: psalms → lesson 1 → responsory → lesson 2 → canticle.
 * With more than one appointed reading, offers a tab selector (All + one tab
 * per reading, ADR 0014) alongside the fixed head-of-section rubric; the
 * Responsory and Canticle are fixed-position liturgical elements tied to the
 * full sequence, not to any single reading, so an individual reading tab
 * shows just that reading on its own — matching the psalm selector's pattern.
 * @param {object} officeData - morning|evening office object
 * @param {object} form - office form from offices.json
 * @param {object} shared - offices._shared
 * @returns {string} HTML string
 */
function proclamationHtml(officeData, form, shared) {
  const lessons = (officeData.lessons || []);
  // The extracted Psalm/Reading rubrics (#84) print on both sides of the
  // lectionary content, so each block is split at the sentence that says which
  // side it belongs on — the same split cli/book.js uses, shared from render.js
  // so the two modes cannot drift. The doxology cue goes with the Gloria it
  // introduces, inside psalmHtml; the reading transitions follow the reading.
  //
  // Each run is guarded on the content it introduces, as cli/book.js guards
  // the same runs: a day entry with no psalms or no lessons would otherwise
  // print "…continues with the Reading", "…continues with the Responsory or
  // the Canticle or both" and the two-reading rule back to back, with nothing
  // between them. Unreachable with shipped lectionary data — all 794 office
  // entries have lessons — but the rubrics describe content, so they go when
  // it does.
  const psalms = (officeData.psalms || []).length
    || ((officeData.psalm_sets || []).length ? 1 : 0);
  const psalm = psalms ? splitPsalmRubrics(form && form.psalm_rubrics) : {};
  const reading = lessons.length ? splitReadingRubrics(form && form.reading_rubrics) : {};
  let html = rubricRunHtml(psalm.intro, shared, 'The Psalm');
  html += psalmHtml(officeData, shared, psalm.doxologyCue);
  html += rubricRunHtml(reading.handoff, shared);
  html += rubricRunHtml(reading.intro, shared, 'The Reading');
  if (officeData.lessons_pick) html += lessonsPickRubricHtml(officeData.lessons_pick, lessons.length);
  if (lessons.length > 1) {
    let allHtml = lessonHtml(lessons[0], shared, form);
    allHtml += rubricRunHtml(reading.after, shared);
    if (form) allHtml += renderSubsection('The Responsory', form.responsory, shared, true);
    allHtml += lessonHtml(lessons[1], shared, form);
    if (form) allHtml += renderSubsection('The Canticle', form.canticle, shared, true);
    for (const lesson of lessons.slice(2)) allHtml += lessonHtml(lesson, shared, form);

    const stateKey = 'pwc-reading-' + lessons.map(l => typeof l === 'object' ? l.citation : l).join('-');
    const entries = [['All', allHtml]].concat(lessons.map(l => {
      const c = typeof l === 'object' ? l.citation : l;
      const display = expandCitationForDisplay(c);
      const label = (typeof l === 'object' && l.optional) ? `(${display})` : display;
      return [label, lessonHtml(l, shared, form)];
    }));
    return html + tabBlockHtml(stateKey, entries);
  }
  if (lessons.length > 0) html += lessonHtml(lessons[0], shared, form);
  html += rubricRunHtml(reading.after, shared);
  if (form) html += renderSubsection('The Responsory', form.responsory, shared, true);
  if (form) html += renderSubsection('The Canticle', form.canticle, shared, true);
  return html;
}

// The BAS book collects (data/collects.json) print without a closing "Amen."
// (the reader supplies it), while the seasonal collects carry one rendered
// bold as a congregational response. For consistency we add it here too —
// a deliberate divergence from the printed source. See issue #8.
function collectTextHtml(text) {
  const m = text.match(/^([\s\S]+?)\s*Amen\.?\s*$/);
  const body = m ? m[1] : text;
  return `<p class="collect-text">${esc(body)}</p><p class="seg-response">Amen.</p>`;
}

function collectHtml(collects, ref) {
  if (!ref) return '';
  const col = lookupCollect(collects, ref);
  const name = col && col.name ? col.name : `p. ${collectPageNum(ref) || ref}`;
  return `<p class="alt-source">${esc(name)}</p>`
       + (col ? collectTextHtml(col.text)
              : `<p class="scripture-fallback-note">Collect not available.</p>`);
}

// Renders the collect section as a toggle between the daily collect and
// the seasonal alternatives, as the rubric directs: "either…or".
// collectInline: day-level {name, text} extracted from special-day propers
// (BUG-27) — used as the Collect of the Day when no BAS collect ref exists.
function collectToggleHtml(collects, collectRef, seasonalSegs, shared, fatsEntry, collectInline) {
  // Separate the general "Additional intercessions…" rubric (display above toggle)
  // from the actual seasonal collect content.
  let splitAt = 0;
  while (splitAt < seasonalSegs.length && seasonalSegs[splitAt].type === 'rubric'
         && SC_HEADER.test(seasonalSegs[splitAt].text)) splitAt++;
  const generalRubrics = seasonalSegs.slice(0, splitAt);
  const seasonalContent = seasonalSegs.slice(splitAt);

  if (collectRef) collectInline = null; // BAS ref wins when both exist
  const hasDaily      = !!collectRef || !!collectInline;
  const basResolvable = !!collectInline || (!!collectRef && !!lookupCollect(collects, collectRef));
  const hasSeasonal   = seasonalContent.some(s => s.type !== 'rubric');
  const dailyHtml = () => collectInline
    ? `<p class="alt-source">${esc(collectInline.name)}</p>${collectTextHtml(collectInline.text)}`
    : collectHtml(collects, collectRef);

  // Detect Occasional Prayer alternative in the collect ref (e.g. "344 or 8, 677 (The King)")
  const occPage = collectRef ? collectSecondaryPage(collectRef) : null;
  const occCollect = (occPage && collects[occPage]) || null;

  // FATS collect: shown as fallback when BAS collect is absent or unresolvable.
  const fatsCollect = (!hasDaily || !basResolvable) ? (fatsEntry && fatsEntry.collect) || null : null;

  let html = '';
  if (generalRubrics.length) html += `<div class="liturgy">${renderSegments(generalRubrics, shared)}</div>`;

  if (!hasDaily && !hasSeasonal && !fatsCollect) return html;

  const stateKey = 'pwc-alt-collect';
  const tabBlock = entries => tabBlockHtml(stateKey, entries);

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
    if (hasDaily) entries.push(['Collect of the Day', dailyHtml()]);
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
      ['Collect of the Day', dailyHtml()],
      ['Seasonal Collect', seasonalTitle + `<div class="liturgy">${renderSegments(displaySeasonal, shared)}</div>`],
    ];
    if (occCollect) entries.push([occCollect.name, occPanelHtml()]);
    html += tabBlock(entries);
  } else if (hasDaily) {
    if (occCollect) {
      html += tabBlock([
        ['Collect of the Day', dailyHtml()],
        [occCollect.name, occPanelHtml()],
      ]);
    } else {
      html += `<h3 class="office-subsection-title">Collect of the Day</h3>${dailyHtml()}`;
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
    showLoadError(contentEl, err, () => render(dateStr, officeType, translation));
    return;
  }

  // Update nav date immediately (even for out-of-range dates, so the user
  // sees the date they navigated to, not the previous page's date).

  // Bounds enforcement before attempting to fetch the day file.
  const boundsMax = offsetDate(bounds.christmas_ii, 6);
  const boundsMin = bounds.advent_i;
  if (dateStr > boundsMax) {
    contentEl.innerHTML = `<div class="out-of-range-msg">
      <p class="out-of-range-title">Readings not yet available</p>
      <p>Coverage extends through <strong>${esc(fmtFullDate(boundsMax))}</strong>.</p>
      <p class="out-of-range-note">Year A readings (Advent 2026 and beyond) are in preparation.</p>
    </div>`;
    return;
  }
  if (dateStr < boundsMin) {
    contentEl.innerHTML = `<div class="out-of-range-msg">
      <p class="out-of-range-title">Outside coverage</p>
      <p>Daily Office data begins with ${esc(fmtFullDate(boundsMin))}.</p>
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
    showLoadError(contentEl, err, () => render(dateStr, officeType, translation));
    return;
  }
  const [offices, collects, day] = result;

  // FATS data is optional — absent in dev until extract_fats.py has been run.
  const fats = await fetchOnce('fats', `${DATA}/fats/saints.json`).catch(() => null);
  const fatsEntry = lookupFatsEntry(fats, day.name);
  const shared = offices._shared || {};

  // Sync date picker sheet. Min = 12 months ago (rolling window matches lectionary coverage).
  const picker = document.getElementById('day-date-picker');
  if (picker) {
    const today = new Date();
    const twelveMonthsAgo = new Date(today.getFullYear() - 1, today.getMonth(), 1);
    const pickerMin = `${twelveMonthsAgo.getFullYear()}-${String(twelveMonthsAgo.getMonth()+1).padStart(2,'0')}-01`;
    picker.min = pickerMin; picker.max = boundsMax; picker.value = dateStr;
  }
  const pickerMpBtn = document.getElementById('day-picker-mp');
  const pickerEpBtn = document.getElementById('day-picker-ep');
  if (pickerMpBtn && pickerEpBtn) {
    pickerMpBtn.classList.toggle('is-active', officeType === 'mp');
    pickerMpBtn.setAttribute('aria-pressed', String(officeType === 'mp'));
    pickerEpBtn.classList.toggle('is-active', officeType === 'ep');
    pickerEpBtn.setAttribute('aria-pressed', String(officeType === 'ep'));
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
  document.getElementById('nav-translation').value = translation;

  // Header
  const officeName = officeType === 'mp' ? 'Morning Prayer' : 'Evening Prayer';

  if (!form) {
    contentEl.innerHTML = `<div class="out-of-range-msg">
      <p class="out-of-range-title">Office form not available</p>
      <p>No liturgical form found for <strong>${esc(officeName)}</strong> on ${esc(fmtFullDate(dateStr))}.</p>
    </div>`;
    return;
  }
  const activeObs = state.observance === 'alternate' && officeData.alternate ? 'alternate' : 'primary';
  const activeOfficeData = activeObs === 'alternate' ? officeData.alternate : officeData;
  // ADR 0018: the selected observance's own identity — name, colour and rank
  // — when it carries one; otherwise the day's. An eve carries one in either
  // slot (#128): it replaces the day's propers rather than alternating with
  // them, so on the office it governs it *is* the day being prayed.
  const activeName = observanceName(activeOfficeData, day, activeObs === 'alternate');
  const activeColour = activeOfficeData.colour || day.colour;
  const activeRank = activeOfficeData.rank || day.rank;
  document.title = `${officeName} — ${activeName}`;
  document.getElementById('day-office-name').textContent = officeName;
  document.getElementById('day-title').textContent = activeName;
  document.getElementById('day-date-label').textContent = fmtFullDate(dateStr);

  const hexes = colourHexes(activeColour);
  const firstHex = hexes[0] || '#b5a882';
  const colourChip = hexes.length > 0
    ? `<span class="meta-item">`
      + `<span class="meta-lbl">Colour</span>`
      + (hexes.length > 1
          ? `<button class="colour-chip colour-chip-toggle" style="background:${firstHex}" data-hexes='${JSON.stringify(hexes)}' data-idx="0" title="Tap to cycle liturgical colour" aria-label="${esc(activeColour)} — tap to cycle"></button>`
          : `<span class="colour-chip" style="background:${firstHex}"></span>`)
      + `<span class="colour-name meta-val">${esc(activeColour)}`
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
    + `<span class="meta-item">${esc(formatRank(activeRank))}</span>`
    + colourChip
    + dayMarkers(day, activeName, activeRank === 'eve').map(m =>
        `<span class="meta-item meta-item--marker">${esc(m)}</span>`).join('');

  document.querySelectorAll('.day-note, .day-note-details').forEach(el => el.remove());

  // ── Office + Observance controls in day header ────────────────────────────
  const ctrlEl = document.getElementById('day-office-controls');
  if (ctrlEl) {
    let ctrlHtml = '';
    // Office toggle. Always present: switching between Morning and Evening is
    // the app's most-used action and should not be hidden behind a sheet.
    // Same shape as the observance control below, so the two read as one family.
    ctrlHtml += `<div class="day-ctrl-group day-ctrl-group--office">
      <div class="day-ctrl-cap">Office</div>
      <div class="day-ctrl-seg" role="group" aria-label="Office">
        <button type="button" data-navigate="${esc(dateStr)}|mp|${esc(activeObs)}" aria-pressed="${officeType === 'mp'}" class="day-ctrl-btn${officeType === 'mp' ? ' is-active' : ''}">
          Morning Prayer</button>
        <button type="button" data-navigate="${esc(dateStr)}|ep|${esc(activeObs)}" aria-pressed="${officeType === 'ep'}" class="day-ctrl-btn${officeType === 'ep' ? ' is-active' : ''}">
          Evening Prayer</button>
      </div></div>`;
    if (officeData.alternate) {
      const altLabel = officeData.alternate.label || 'Alternate';
      // The primary slot is not always the day: on 2026-01-03 it is the Eve of
      // the Epiphany and the day is Christmas Feria (#128). Name it the same
      // way the title does.
      const primaryName = observanceName(officeData, day, false);
      const primaryLabel = primaryName.length > 26 ? primaryName.slice(0,24)+'\u2026' : primaryName;
      ctrlHtml += `<div class="day-ctrl-group day-ctrl-group--obs">
        <div class="day-ctrl-cap">Observance \u00b7 whose readings <span class="day-ctrl-obs-mark">\u25c6</span></div>
        <div class="day-ctrl-seg day-ctrl-seg--obs">
          <button data-navigate="${esc(dateStr)}|${esc(officeType)}|primary" class="day-ctrl-btn${activeObs === 'primary' ? ' is-active' : ''}">
            ${esc(primaryLabel)}</button>
          <button data-navigate="${esc(dateStr)}|${esc(officeType)}|alternate" class="day-ctrl-btn${activeObs === 'alternate' ? ' is-active' : ''}">
            ${esc(altLabel)}</button>
        </div></div>`;
    }
    ctrlEl.innerHTML = ctrlHtml;
    // The observance group only exists on a day with an alternate; the sheet
    // drops both captions when it is absent (#123).
    ctrlEl.classList.toggle('has-one-group', !officeData.alternate);
    ctrlEl.style.display = ctrlHtml ? '' : 'none';
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

    // ── Source notes — the compiler's apparatus, behind a disclosure ────────
    // These explain where a day's propers came from, to whoever assembles a
    // calendar; the reader is not being asked to decide anything. Reachable
    // rather than suppressed — the sourcing is real, it is just not part of
    // the office (#127).
    const sourceNotes = day.notes.filter(n => typeof n === 'object' && n.type === 'source_note');
    if (sourceNotes.length) {
      const det = document.createElement('details');
      det.className = 'day-note-details';
      const sum = document.createElement('summary');
      sum.className = 'day-note-details-toggle';
      sum.textContent = 'About these readings';
      det.appendChild(sum);
      const body = document.createElement('div');
      body.className = 'day-note-details-body';
      sourceNotes.forEach(n => {
        const p = document.createElement('p');
        p.appendChild(renderNoteText(n.text));
        body.appendChild(p);
      });
      // The source writes "DOL" and never expands it; the BAS names the
      // section in full and never abbreviates it. Gloss it as app chrome
      // rather than editing the note — the note is quoted, not authored here.
      if (sourceNotes.some(n => /\bDOL\b/.test(n.text))) {
        const gloss = document.createElement('p');
        gloss.className = 'day-note-gloss';
        gloss.textContent = 'DOL — the Daily Office Lectionary, BAS pp. 450–497.';
        body.appendChild(gloss);
      }
      det.appendChild(body);
      headerEl.appendChild(det);
    }

    day.notes.forEach(n => {
      if (typeof n === 'object' && SUPPRESS_NOTE_TYPES.has(n.type)) return;
      const type = typeof n === 'object' ? (n.type || 'pastoral') : 'pastoral';
      if (type === 'source_note') return;
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

  // Section visibility decisions shared with validators (ADR 0008).
  const asm = form ? assembleSections({
    form, shared, officeData: activeOfficeData, officeType, season, weekIdx,
    fatsEntry, collects, collectRef: activeOfficeData.collect,
    collectInline: day.collect_inline,
  }) : { sections: [] };

  let html = '';

  // ── FATS biographical notice ───────────────────────────────────────────────
  if (fatsEntry && fatsEntry.bio) {
    const bioParas = fatsEntry.bio.split(/\n\n+/).map(p => `<p>${esc(p.replace(/\n/g, ' '))}</p>`).join('');
    html += `<details class="fats-bio">
      <summary class="fats-bio-toggle">About ${esc(day.name)}</summary>
      <div class="fats-bio-body">${bioParas}</div>
    </details>`;
  }

  // No form title is rendered — but the reason below no longer holds, and the
  // decision is now open rather than settled. `form.title` used to be the first
  // *section* heading ("The Gathering of the Community" on all 30 forms) and
  // `form.subtitle` was never set, because the running-header filter was eating
  // the page's own title block. #84 fixed that filter: title is now "Morning
  // Prayer for Advent" etc., and all 16 seasonal forms carry their printed date
  // range as subtitle. cli/book.js prints the subtitle; this page prints
  // neither, so the two modes disagree. Whether the web page should show them
  // is a layout question this branch does not settle (#100).

  // ── Gathering ──────────────────────────────────────────────────────────────
  if (asm.sections.some(s => s.name === 'Gathering')) {
    html += `<h2 class="office-section-title">The Gathering of the Community</h2>`;
    let openingResponses = form.opening_responses;
    if (openingResponses?.type === 'shared' && shared)
      openingResponses = shared[openingResponses.key];
    if (openingResponses && openingResponses.length)
      html += renderSubsection('Introductory Responses', openingResponses, shared);
    if (form.thanksgiving_for_light && form.thanksgiving_for_light.length)
      html += renderSubsection('Thanksgiving', form.thanksgiving_for_light, shared, true);
    // Ordinary-time EP: evening hymn reference (Phos Hilaron).
    if (form.phos_hilaron && form.phos_hilaron.length)
      html += renderSubsection('Evening Hymn', phosHilaronSegments(form), shared, true);
    if (form.invitatory && form.invitatory.length)
      html += renderSubsection('Invitatory Psalm', invitatorySegments(form), shared, true);
  }

  // ── Proclamation ───────────────────────────────────────────────────────────
  html += `<h2 class="office-section-title">The Proclamation of the Word</h2>`;

  // Primary readings — psalms, lesson 1, responsory, canticle, lesson 2+ (if any).
  // The Psalm/Reading rubric blocks render inside proclamationHtml, each above
  // the content it introduces.
  html += `<div class="obs-readings${activeObs !== 'primary' ? ' obs-hidden' : ''}" data-obs="primary">`;
  if (officeData.label) html += `<p class="observance-label">${esc(officeData.label)}</p>`;
  html += proclamationHtml(officeData, form, shared);
  html += `</div>`;

  // Alternate readings.
  if (officeData.alternate) {
    const alt = officeData.alternate;
    html += `<div class="obs-readings${activeObs !== 'alternate' ? ' obs-hidden' : ''}" data-obs="alternate">`;
    if (alt.label) html += `<p class="observance-label">${esc(alt.label)}</p>`;
    html += proclamationHtml(alt, form, shared);
    html += `</div>`;
  }

  // Affirmation of Faith closes the Proclamation section (not Prayers).
  if (asm.sections.some(s => s.name === 'Proclamation')) {
    const proc = asm.sections.find(s => s.name === 'Proclamation');
    if (proc && proc.dynamic && proc.dynamic.hasAffirmation) {
      // No transition rubric is emitted here. It was authored from the office
      // type and a `form.litany` test, in two wordings, neither of which the
      // page could check against anything. The book prints it as the Canticle's
      // closing rubric, per form; #84 extracts it and ADR 0019 item 4's "…or
      // the Prayers" reaches it as a manifest correction, so it renders once,
      // from the canticle subsection above.
      html += renderSubsection('Affirmation of Faith', form.affirmation, shared);
    }
  }

  // ── Prayers ────────────────────────────────────────────────────────────────
  if (asm.sections.some(s => s.name === 'Prayers')) {
    html += `<h2 class="office-section-title">The Prayers of the Community</h2>`;
    // Day-specific intercession prompts guide the free-prayer period before the formal litany.
    if (form.intercessions && form.intercessions.length)
      html += renderSubsection('Intercessions and Thanksgivings', form.intercessions, shared);
    if (form.litany && form.litany.length) {
      // The pre-Litany transition ("{office} Prayer continues with the
      // Litany.") used to be authored here and is printed book text since #84,
      // closing the affirmation section per form. Emitting it here too printed
      // it twice, verbatim.
      html += renderSubsection('The Litany', form.litany, shared);
    }
    html += `<h3 class="office-subsection-title">The Collect</h3>`;
    html += `<div id="prayers-collect">${collectToggleHtml(collects, activeOfficeData.collect, seasonalSegs, shared, fatsEntry, day.collect_inline)}</div>`;
    if (form.lords_prayer_intro && form.lords_prayer_intro.length) {
      html += `<h3 class="office-subsection-title">The Lord's Prayer</h3>`;
      html += `<div class="liturgy">${renderSegments(form.lords_prayer_intro, shared, true)}</div>`;
    }
  }

  // ── Sending ────────────────────────────────────────────────────────────────
  if (asm.sections.some(s => s.name === 'Sending')) {
    html += `<h2 class="office-section-title">The Sending Forth of the Community</h2>`;
    html += `<h3 class="office-subsection-title">The Dismissal</h3>`;
    html += `<div class="liturgy">${renderSegments(form.dismissal, shared, true)}</div>`;
  }

  html += `<p class="scripture-attr" id="scripture-attr">Scripture: ${esc(translation.toUpperCase())}</p>`;

  contentEl.innerHTML = html;

  if (isNative) {
    window.__pwcPlugins.SplashScreen.hide().catch(() => {});
  }

  fillPsalms(contentEl);
  fillScripture(contentEl, translation);
  prefetchOtherOffice(day, officeType, translation);
}

// ── Background prefetch ───────────────────────────────────────────────────────
// Warm the scripture book cache for the other office so switching MP↔EP is instant.

function prefetchOtherOffice(day, officeType, translation) {
  const other = officeType === 'mp' ? day.evening : day.morning;
  if (!other) return;
  const schedule = window.requestIdleCallback
    ? cb => requestIdleCallback(cb, { timeout: 1000 })
    : cb => setTimeout(cb, 100);
  schedule(() => {
    [other.lesson1, other.lesson2].forEach(lesson => {
      if (!lesson) return;
      const citation = typeof lesson === 'object' ? lesson.citation : lesson;
      const parsed = parseCitation(citation);
      if (parsed) fetchBook(translation, parsed.file).catch(() => {});
    });
  });
}

// ── Async fillers ─────────────────────────────────────────────────────────────

async function fillPsalmEl(el) {
  const cit = el.dataset.citation;
  try {
    el.innerHTML = await renderPsalm(cit);
  } catch (e) {
    showLoadError(el, e, () => { el.innerHTML = '<p class="loading">Loading…</p>'; fillPsalmEl(el); });
  }
}

function fillPsalms(root) {
  root.querySelectorAll('.psalm-loading').forEach(fillPsalmEl);
}

async function fillScriptureEl(el, translation) {
  const rawCitation = el.dataset.citation;
  try {
    const parsed = parseCitation(rawCitation);
    if (!parsed) { el.innerHTML = `<p class="error-msg">Cannot parse: ${esc(rawCitation)}</p>`; return; }

    let bookData, usedTranslation = translation;
    if (window.__pwcOffline) {
      el.innerHTML = '<p class="scripture-offline">Unable to load Scripture (offline)</p>';
      return;
    }
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

    const allVerses = ranges.flatMap(r => extractVersesWithChapter(bookData, r));
    const paragraphs = await fetchOnce('paragraphs', `${DATA}/paragraphs.json`).catch(() => null);
    const paraMap = paragraphs ? (paragraphs[parsed.file] || null) : null;

    let html;
    if (paraMap) {
      html = buildParagraphHtml(allVerses, paraMap);
    } else {
      const byChapter = {};
      for (const v of allVerses) {
        (byChapter[v.ch] || (byChapter[v.ch] = [])).push(v);
      }
      const blocks = [];
      for (const [chStr, chVerses] of Object.entries(byChapter)) {
        blocks.push(renderChapterHtml(chVerses, parseInt(chStr), null));
      }
      html = blocks.join('\n');
    }
    el.innerHTML = html;

    if (usedTranslation !== translation) {
      el.innerHTML += `<p class="scripture-fallback-note">[${usedTranslation.toUpperCase()} shown — ${translation.toUpperCase()} unavailable for this reading]</p>`;
    }
  } catch (e) {
    showLoadError(el, e, () => { el.innerHTML = '<p class="loading">Loading…</p>'; fillScriptureEl(el, translation); });
  }
}

function fillScripture(root, translation) {
  root.querySelectorAll('.scripture-placeholder').forEach(el => fillScriptureEl(el, translation));
}

// ── Translation switch (no full re-render) ────────────────────────────────────

function switchTranslation(newTranslation) {
  state.translation = newTranslation;
  storageSet('pwc-translation', newTranslation);
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
  if (storageGet('pwc-eval-dismissed')) return;
  const banner = document.createElement('div');
  banner.id = 'eval-banner';
  banner.className = 'eval-banner';
  banner.innerHTML = `<span>Private evaluation — please do not share or distribute.</span>`
    + `<button class="eval-banner-dismiss" aria-label="Dismiss">&#215;</button>`;
  document.getElementById('main').insertAdjacentElement('afterbegin', banner);
  banner.querySelector('.eval-banner-dismiss').addEventListener('click', () => {
    storageSet('pwc-eval-dismissed', '1');
    banner.remove();
  });
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
  storageSet(stateKey, String(idx));
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

document.addEventListener('DOMContentLoaded', async () => {
  await migrateStorageToPreferences();
  await restoreStorageFromPreferences();
  initTheme();
  initFontSize();
  initScrollBehaviour();
  initNativeFeatures();

  document.getElementById('nav-brand').addEventListener('click', e => {
    e.preventDefault();
    navigateTo(todayStr(), defaultOffice());
  });

  // Bottom sheets — shared open/close, each parametrized by its sheet + trigger
  // button. closeSheet no-ops when already closed so Escape (which closes both
  // sheets unconditionally) never steals focus onto a sheet the user didn't open.
  function openSheet(sheet, btn) {
    sheet.setAttribute('aria-hidden', 'false');
    btn.setAttribute('aria-expanded', 'true');
    const firstCtrl = sheet.querySelector('button, select, input');
    if (firstCtrl) firstCtrl.focus();
  }
  function closeSheet(sheet, btn) {
    if (sheet.getAttribute('aria-hidden') === 'true') return;
    sheet.setAttribute('aria-hidden', 'true');
    btn.setAttribute('aria-expanded', 'false');
    btn.focus();
  }

  // Settings sheet
  const settingsSheet = document.getElementById('settings-sheet');
  const settingsBtn = document.getElementById('nav-settings-btn');
  const settingsClose = document.getElementById('settings-close-btn');
  const settingsBackdrop = document.getElementById('settings-backdrop');

  const openSettings = () => openSheet(settingsSheet, settingsBtn);
  const closeSettings = () => closeSheet(settingsSheet, settingsBtn);
  settingsBtn.addEventListener('click', openSettings);
  settingsClose.addEventListener('click', closeSettings);
  settingsBackdrop.addEventListener('click', closeSettings);

  // Date/office picker sheet
  const dayPickerSheet = document.getElementById('day-picker-sheet');
  const dayPickerBtn = document.getElementById('nav-cal-btn');
  const dayPickerClose = document.getElementById('day-picker-close-btn');
  const dayPickerBackdrop = document.getElementById('day-picker-backdrop');

  const openDayPicker = () => openSheet(dayPickerSheet, dayPickerBtn);
  const closeDayPicker = () => closeSheet(dayPickerSheet, dayPickerBtn);
  dayPickerBtn.addEventListener('click', openDayPicker);
  dayPickerClose.addEventListener('click', closeDayPicker);
  dayPickerBackdrop.addEventListener('click', closeDayPicker);

  // Book mode toggle — wired to the settings segmented control
  const bookModeKey = 'pwc-book-mode';

  function syncViewModeUI(isBook) {
    const offBtn = document.getElementById('view-mode-office');
    const bkBtn  = document.getElementById('view-mode-book');
    if (offBtn) { offBtn.classList.toggle('is-active', !isBook); offBtn.setAttribute('aria-pressed', String(!isBook)); }
    if (bkBtn)  { bkBtn.classList.toggle('is-active',  isBook);  bkBtn.setAttribute('aria-pressed', String(isBook)); }
  }

  if (storageGet(bookModeKey) === '1') {
    document.body.classList.add('book-mode');
    syncViewModeUI(true);
  }

  const viewModeOffice = document.getElementById('view-mode-office');
  const viewModeBook   = document.getElementById('view-mode-book');
  if (viewModeOffice) viewModeOffice.addEventListener('click', () => {
    if (document.body.classList.contains('book-mode')) {
      document.body.classList.remove('book-mode');
      syncViewModeUI(false);
      storageSet(bookModeKey, '0');
    }
  });
  if (viewModeBook) viewModeBook.addEventListener('click', () => {
    if (!document.body.classList.contains('book-mode')) {
      document.body.classList.add('book-mode');
      syncViewModeUI(true);
      storageSet(bookModeKey, '1');
    }
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeSettings(); closeDayPicker(); }
  });

  document.getElementById('theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('font-size-toggle').addEventListener('click', cycleFontSize);

  const sel = document.getElementById('nav-translation');
  sel.value = state.translation;
  sel.addEventListener('change', () => { switchTranslation(sel.value); });

  // Date/office picker
  const dayDatePicker = document.getElementById('day-date-picker');
  const dayPickerMpBtn = document.getElementById('day-picker-mp');
  const dayPickerEpBtn = document.getElementById('day-picker-ep');
  const todayBtn = document.getElementById('today-btn');

  // The date opens the picker; the title does not. A heading that silently
  // swallows taps is not discoverable, and office switching now has its own
  // visible control in the day header.
  document.getElementById('day-date-nav').addEventListener('click', openDayPicker);

  // Tapping the native date input only reliably opens its calendar UI when
  // the tap lands on the small calendar glyph itself (esp. mobile Chrome) —
  // call showPicker() explicitly so the whole row/label opens it.
  dayDatePicker.addEventListener('click', () => { try { dayDatePicker.showPicker(); } catch (_) {} });
  dayDatePicker.addEventListener('change', e => {
    if (e.target.value) navigateTo(e.target.value, state.office);
    closeDayPicker();
  });

  if (todayBtn) {
    todayBtn.addEventListener('click', () => {
      navigateTo(todayStr(), state.office);
      closeDayPicker();
    });
  }

  dayPickerMpBtn.addEventListener('click', () => { if (state.office !== 'mp') navigateTo(state.date, 'mp'); });
  dayPickerEpBtn.addEventListener('click', () => { if (state.office !== 'ep') navigateTo(state.date, 'ep'); });

  document.getElementById('day-meta').addEventListener('click', e => {
    const chip = e.target.closest('.colour-chip-toggle');
    if (!chip) return;
    const hexes = JSON.parse(chip.dataset.hexes);
    const idx = (parseInt(chip.dataset.idx) + 1) % hexes.length;
    chip.dataset.idx = String(idx);
    chip.style.background = hexes[idx];
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

  initEvalBanner();
  // Warm up static fetches.
  fetchOnce('offices',  `${DATA}/offices.json`);
  fetchOnce('collects', `${DATA}/collects.json`);
  fetchOnce('bounds',   `${DATA}/season_bounds.json`);
  fetchOnce('psalter',  `${DATA}/psalter.json`);
  fetchOnce('paragraphs', `${DATA}/paragraphs.json`).catch(() => {});

  // Global navigation delegation — buttons with data-navigate="date|office|observance"
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-navigate]');
    if (!btn) return;
    e.preventDefault();
    const parts = btn.dataset.navigate.split('|');
    navigateTo(parts[0], parts[1], parts[2]);
  });

  // Strip old hash routes — redirect bookmarked #/DATE/OFFICE to root
  if (location.hash) {
    history.replaceState({}, '', location.pathname);
  }

  initPage();

});
