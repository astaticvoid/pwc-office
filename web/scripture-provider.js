/**
 * @file scripture-provider.js
 * Scripture Provider architecture and caching layer (ADR 0023).
 *
 * Implements date-grained scripture fetching, client-side temporal gating,
 * local storage caching with automatic 30-day rolling window purges,
 * and graceful fallback to bundled public domain translations (KJV).
 */

/**
 * @typedef {import('./scripture-types.d.ts').ScriptureVerse} ScriptureVerse
 * @typedef {import('./scripture-types.d.ts').ScriptureReading} ScriptureReading
 * @typedef {import('./scripture-types.d.ts').DayReadingsResult} DayReadingsResult
 * @typedef {import('./scripture-types.d.ts').IScriptureCache} IScriptureCache
 * @typedef {import('./scripture-types.d.ts').IScriptureProvider} IScriptureProvider
 */

/**
 * Calculate the difference in calendar days between two YYYY-MM-DD dates.
 * Positive if dateStr1 is after dateStr2.
 * @param {string} dateStr1 - 'YYYY-MM-DD'
 * @param {string} dateStr2 - 'YYYY-MM-DD'
 * @returns {number} Integer day difference
 */
export function dayDifference(dateStr1, dateStr2) {
  const [y1, m1, d1] = dateStr1.split('-').map(Number);
  const [y2, m2, d2] = dateStr2.split('-').map(Number);
  const t1 = Date.UTC(y1, m1 - 1, d1);
  const t2 = Date.UTC(y2, m2 - 1, d2);
  return Math.round((t1 - t2) / 86400000);
}

/**
 * Check whether targetDate is within maxDays of referenceDate.
 * @param {string} targetDate - 'YYYY-MM-DD'
 * @param {string} referenceDate - 'YYYY-MM-DD'
 * @param {number} [maxDays=31]
 * @returns {boolean}
 */
export function isWithinTemporalWindow(targetDate, referenceDate, maxDays = 31) {
  return Math.abs(dayDifference(targetDate, referenceDate)) <= maxDays;
}

/**
 * Returns today's date formatted as YYYY-MM-DD in UTC.
 * @returns {string}
 */
export function todayUtcString() {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
}

/**
 * In-memory scripture cache implementation (ideal for tests and fallback).
 * @implements {IScriptureCache}
 */
export class MemoryScriptureCache {
  constructor() {
    /** @type {Map<string, DayReadingsResult>} */
    this.store = new Map();
  }

  _key(date, translation) {
    return `${translation}:${date}`;
  }

  async get(date, translation) {
    const item = this.store.get(this._key(date, translation));
    if (!item) return null;
    if (item.expiresAt && Date.now() > item.expiresAt) {
      this.store.delete(this._key(date, translation));
      return null;
    }
    return { ...item, source: 'cache' };
  }

  async set(date, translation, data) {
    this.store.set(this._key(date, translation), {
      ...data,
      source: 'cache',
      fetchedAt: data.fetchedAt || Date.now(),
      expiresAt: data.expiresAt || Date.now() + 30 * 86400000,
    });
  }

  async purge(currentDate, maxAgeDays = 30) {
    let purged = 0;
    const now = Date.now();
    for (const [key, item] of this.store.entries()) {
      const diffDays = Math.abs(dayDifference(item.date, currentDate));
      const ageDays = (now - item.fetchedAt) / 86400000;
      if (diffDays > maxAgeDays || ageDays > maxAgeDays) {
        this.store.delete(key);
        purged++;
      }
    }
    return purged;
  }
}

/**
 * LocalStorage scripture cache with automatic 30-day purge and quota fallback.
 * @implements {IScriptureCache}
 */
export class LocalStorageScriptureCache {
  /**
   * @param {object} [options]
   * @param {string} [options.prefix='pwc-readings']
   * @param {Storage|null} [options.storage]
   */
  constructor({ prefix = 'pwc-readings', storage = null } = {}) {
    this.prefix = prefix;
    this.storage = storage || (typeof localStorage !== 'undefined' ? localStorage : null);
    this._memoryFallback = new MemoryScriptureCache();
  }

  _key(date, translation) {
    return `${this.prefix}-${translation}-${date}`;
  }

  async get(date, translation) {
    if (!this.storage) return this._memoryFallback.get(date, translation);
    try {
      const raw = this.storage.getItem(this._key(date, translation));
      if (!raw) return this._memoryFallback.get(date, translation);
      /** @type {DayReadingsResult} */
      const item = JSON.parse(raw);
      if (item.expiresAt && Date.now() > item.expiresAt) {
        this.storage.removeItem(this._key(date, translation));
        return null;
      }
      item.source = 'cache';
      return item;
    } catch (_) {
      return this._memoryFallback.get(date, translation);
    }
  }

  async set(date, translation, data) {
    const payload = JSON.stringify({
      ...data,
      source: 'cache',
      fetchedAt: data.fetchedAt || Date.now(),
      expiresAt: data.expiresAt || Date.now() + 30 * 86400000,
    });

    if (!this.storage) {
      await this._memoryFallback.set(date, translation, data);
      return;
    }

    try {
      this.storage.setItem(this._key(date, translation), payload);
    } catch (err) {
      // QuotaExceededError handling: purge old entries and retry
      try {
        await this.purge(todayUtcString(), 30);
        this.storage.setItem(this._key(date, translation), payload);
      } catch (_2) {
        // If storage is completely full or disabled (private browsing), fallback to memory
        await this._memoryFallback.set(date, translation, data);
      }
    }
  }

  async purge(currentDate, maxAgeDays = 30) {
    let purged = 0;
    const now = Date.now();
    await this._memoryFallback.purge(currentDate, maxAgeDays);

    if (!this.storage) return purged;

    const keysToRemove = [];
    const prefixWithSep = `${this.prefix}-`;

    try {
      for (let i = 0; i < this.storage.length; i++) {
        const k = this.storage.key(i);
        if (k && k.startsWith(prefixWithSep)) {
          const parts = k.slice(prefixWithSep.length).split('-');
          // Key format: {prefix}-{translation}-{YYYY}-{MM}-{DD}
          const dateStr = parts.slice(-3).join('-');
          if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            const diffDays = Math.abs(dayDifference(dateStr, currentDate));
            if (diffDays > maxAgeDays) {
              keysToRemove.push(k);
              continue;
            }
          }
          // Also check recorded timestamp
          try {
            const val = this.storage.getItem(k);
            if (val) {
              const item = JSON.parse(val);
              if (item.fetchedAt && (now - item.fetchedAt) / 86400000 > maxAgeDays) {
                keysToRemove.push(k);
              }
            }
          } catch (_) {
            keysToRemove.push(k);
          }
        }
      }

      for (const k of keysToRemove) {
        this.storage.removeItem(k);
        purged++;
      }
    } catch (_) {
      /* Storage access failed */
    }

    return purged;
  }
}

/**
 * Remote scripture provider making date-grained requests to the edge service.
 * @implements {IScriptureProvider}
 */

/**
 * Wraps global fetch to optionally inject auth tokens and absolute origins at build time.
 */
async function defaultFetch(url, init = {}) {
  /** @type {RequestInit} */ const newInit = { ...init };
  const authPlaceholder = '__EVAL_AUTH_TOKEN__';
  if (authPlaceholder.startsWith('Basic ')) {
    newInit.headers = new Headers(newInit.headers);
    newInit.headers.set('Authorization', authPlaceholder);
  }

  let targetUrl = url;
  const originPlaceholder = '__API_ORIGIN__';
  if (originPlaceholder.startsWith('http') && targetUrl.startsWith('/api/')) {
    targetUrl = originPlaceholder + targetUrl;
  }

  return fetch(targetUrl, newInit);
}

export class RemoteScriptureProvider {
  /**
   * @param {object} [options]
   * @param {string} [options.apiBase='/api/v1/readings']
   * @param {string} [options.translation='nrsvue']
   * @param {typeof fetch} [options.fetchFn]
   * @param {number} [options.windowGraceDays=35]
   */
  constructor({
    apiBase = '/api/v1/readings',
    translation = 'nrsvue',
    fetchFn = null,
    windowGraceDays = 35,
  } = {}) {
    this.apiBase = apiBase;
    this.translation = translation;
    this.fetchFn = fetchFn
      ? (url, init) => (init !== undefined ? fetchFn(url, init) : fetchFn(url))
      : null;
    this.windowGraceDays = windowGraceDays;
  }

  async getReadingsForDate(dateStr, options = {}) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
      throw new Error(`Invalid date format: ${dateStr}. Expected YYYY-MM-DD.`);
    }

    // Client-side generous fast-fail to save bandwidth on large calendar jumps
    const today = todayUtcString();
    if (!isWithinTemporalWindow(dateStr, today, this.windowGraceDays)) {
      return null;
    }

    if (!this.fetchFn) {
      throw new Error('No fetch implementation available.');
    }

    const targetTranslation = options.translation || this.translation;
    const url = `${this.apiBase}?date=${dateStr}&translation=${encodeURIComponent(targetTranslation)}`;
    const res = await this.fetchFn(url);

    if (res.status === 403 || res.status === 404) {
      return null;
    }

    if (!res.ok) {
      throw new Error(`Remote scripture fetch failed with status ${res.status}`);
    }

    const data = await res.json();
    return {
      date: dateStr,
      translation: targetTranslation,
      source: 'remote',
      readings: data.readings || {},
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 30 * 86400000,
    };
  }
}

/**
 * Decorator adding local caching and automatic 30-day purge around an inner provider.
 * @implements {IScriptureProvider}
 */
export class CachedScriptureProvider {
  /**
   * @param {IScriptureProvider} innerProvider
   * @param {IScriptureCache} cache
   */
  constructor(innerProvider, cache) {
    this.innerProvider = innerProvider;
    this.cache = cache;
    this.translation = innerProvider.translation;

    // Purge expired records on initialization
    this.cache.purge(todayUtcString(), 30).catch(() => {});
  }

  async getReadingsForDate(dateStr, options = {}) {
    const targetTranslation = options.translation || this.translation;

    // 1. Check cache
    const cached = await this.cache.get(dateStr, targetTranslation);
    if (cached && cached.readings && Object.keys(cached.readings).length > 0) {
      return cached;
    }

    // 2. Fetch from inner provider
    const fresh = await this.innerProvider.getReadingsForDate(dateStr, options);
    if (fresh && fresh.readings && Object.keys(fresh.readings).length > 0) {
      // 3. Save to cache and trigger background purge
      await this.cache.set(dateStr, targetTranslation, fresh);
      return fresh;
    }

    return null;
  }
}

/**
 * Fallback provider decorator: delegates to fallback provider if primary fails or returns null.
 * @implements {IScriptureProvider}
 */
export class FallbackScriptureProvider {
  /**
   * @param {object} config
   * @param {IScriptureProvider} config.primary
   * @param {IScriptureProvider} config.fallback
   */
  constructor({ primary, fallback }) {
    this.primary = primary;
    this.fallback = fallback;
    this.translation = primary.translation;
  }

  async getReadingsForDate(dateStr, options = {}) {
    // If the caller explicitly requested another translation (e.g. KJV), route directly to fallback
    if (options.translation && options.translation !== this.primary.translation) {
      if (this.fallback && (options.translation === this.fallback.translation || !options.translation)) {
        return this.fallback.getReadingsForDate(dateStr, options);
      }
    }

    let result = null;
    try {
      result = await this.primary.getReadingsForDate(dateStr, options);
    } catch (_) {
      result = null;
    }

    if (result && result.readings && Object.keys(result.readings).length > 0) {
      return result;
    }

    // Fall back gracefully
    if (!this.fallback) return null;

    const fallbackResult = await this.fallback.getReadingsForDate(dateStr, options);
    if (!fallbackResult) return null;

    // Mark each reading as a fallback
    const markedReadings = {};
    for (const [k, r] of Object.entries(fallbackResult.readings || {})) {
      markedReadings[k] = {
        ...r,
        isFallback: true,
      };
    }

    return {
      ...fallbackResult,
      source: 'fallback',
      readings: markedReadings,
    };
  }
}

/**
 * Recursively collect all unique raw citations from a lectionary day object,
 * including morning, evening, alternate offices, and internal alternatives (" or ").
 * @param {any} day
 * @returns {string[]}
 */
export function collectDayCitations(day) {
  if (!day) return [];
  const citations = [];
  const add = (lesson) => {
    if (!lesson) return;
    const raw = typeof lesson === 'object' ? lesson.citation : lesson;
    if (typeof raw === 'string') {
      if (raw.includes(' or ')) {
        raw.split(' or ').forEach(part => {
          const trimmed = part.trim();
          if (trimmed && !citations.includes(trimmed)) citations.push(trimmed);
        });
      } else {
        if (!citations.includes(raw)) citations.push(raw);
      }
    }
  };

  const offices = [day.morning, day.evening, day.morning?.alternate, day.evening?.alternate];
  for (const off of offices) {
    if (off && Array.isArray(off.lessons)) {
      off.lessons.forEach(add);
    }
  }
  return citations;
}

/**
 * Local offline provider that extracts public domain KJV lectionary readings.
 * @implements {IScriptureProvider}
 */
export class BundledKjvProvider {
  /**
   * @param {any} [config]
   */
  constructor({
    fetchDay = null,
    fetchBook = null,
    parseCitation = null,
    parseRanges = null,
    extractVerses = null,
    buildHtml = null,
    fetchParagraphs = null,
  } = {}) {
    this.translation = 'kjv';
    this.fetchDay = fetchDay;
    this.fetchBook = fetchBook;
    this.parseCitation = parseCitation;
    this.parseRanges = parseRanges;
    this.extractVerses = extractVerses;
    this.buildHtml = buildHtml;
    this.fetchParagraphs = fetchParagraphs;
  }

  async getReadingsForDate(dateStr, options = {}) {
    let day = options.day;
    if (!day && this.fetchDay) {
      try {
        day = await this.fetchDay(dateStr);
      } catch (_) {
        day = null;
      }
    }

    const citations = collectDayCitations(day);
    if (!citations.length && options.citation) {
      citations.push(options.citation);
    }

    if (!citations.length || !this.fetchBook || !this.parseCitation || !this.parseRanges || !this.extractVerses) {
      return null;
    }

    let paragraphs = null;
    if (this.fetchParagraphs) {
      try {
        paragraphs = await this.fetchParagraphs();
      } catch (_) {
        paragraphs = null;
      }
    }

    /** @type {Record<string, ScriptureReading>} */
    const readings = {};

    for (const rawCitation of citations) {
      try {
        const parsed = this.parseCitation(rawCitation);
        if (!parsed) continue;

        const bookData = await this.fetchBook('kjv', parsed.file);
        if (!bookData) continue;

        const ranges = this.parseRanges(parsed.rest);
        if (!ranges || !ranges.length) continue;

        const allVerses = ranges.flatMap(r => this.extractVerses(bookData, r));
        const paraMap = paragraphs ? (paragraphs[parsed.file] || null) : null;

        let html = '';
        if (this.buildHtml) {
          html = this.buildHtml(allVerses, paraMap);
        }

        readings[rawCitation] = {
          citation: rawCitation,
          book: parsed.file,
          verses: allVerses,
          html,
          translation: 'kjv',
        };
      } catch (_) {
        /* Continue with next reading if one fails */
      }
    }

    // Generate composite entries for choice citations containing " or "
    if (day) {
      const offices = [day.morning, day.evening, day.morning?.alternate, day.evening?.alternate];
      for (const off of offices) {
        if (!off || !Array.isArray(off.lessons)) continue;
        for (const l of off.lessons) {
          const raw = typeof l === 'object' ? l.citation : l;
          if (typeof raw === 'string' && raw.includes(' or ') && !readings[raw]) {
            const parts = raw.split(' or ').map(s => s.trim());
            const subReadings = parts.map(p => readings[p]).filter(Boolean);
            if (subReadings.length > 0) {
              readings[raw] = {
                citation: raw,
                book: subReadings[0].book,
                verses: subReadings.flatMap(r => r.verses),
                html: subReadings.map(r => `<div class="scripture-option"><p class="scripture-choice-rubric"><strong>${r.citation}</strong></p>${r.html}</div>`).join('<p class="seg-rubric">or</p>'),
                translation: 'kjv',
              };
            }
          }
        }
      }
    }

    return {
      date: dateStr,
      translation: 'kjv',
      source: 'fallback',
      readings,
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 365 * 86400000,
    };
  }
}

/**
 * Helper factory to assemble the standard production ScriptureProvider stack.
 * @param {any} config
 * @returns {IScriptureProvider}
 */
export function createDefaultScriptureProvider({
  apiBase = '/api/v1/readings',
  primaryTranslation = 'nrsvue',
  fetchBook,
  fetchDay,
  parseCitation,
  parseRanges,
  extractVerses,
  buildHtml,
  fetchParagraphs,
  storage = null,
}) {
  const remote = new RemoteScriptureProvider({
    apiBase,
    translation: primaryTranslation,
    fetchFn: defaultFetch,
  });

  const cache = new LocalStorageScriptureCache({ storage });
  const cachedRemote = new CachedScriptureProvider(remote, cache);

  const fallback = new BundledKjvProvider({
    fetchBook,
    fetchDay,
    parseCitation,
    parseRanges,
    extractVerses,
    buildHtml,
    fetchParagraphs,
  });

  return new FallbackScriptureProvider({
    primary: cachedRemote,
    fallback,
  });
}

/**
 * Calculate date offset by n calendar days.
 * @param {string} dateStr - 'YYYY-MM-DD'
 * @param {number} n - Number of days to offset
 * @returns {string} - 'YYYY-MM-DD'
 */
export function offsetDate(dateStr, n) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, '0')}-${String(dt.getUTCDate()).padStart(2, '0')}`;
}

/**
 * Offline & rolling window Day Cache Manager (ADR 0025).
 * Pre-fetches and caches unified calendar + scripture payloads,
 * actively purges payloads older than 30 days to enforce licensing limits,
 * and detects offline cache misses.
 */
export class DayCacheManager {
  /**
   * @param {object} [options]
   * @param {string} [options.apiBase]
   * @param {Storage|null} [options.storage]
   * @param {typeof fetch} [options.fetchFn]
   */
  constructor({
    apiBase = '/api/v2/calendar',
    storage = null,
    fetchFn = null,
  } = {}) {
    this.apiBase = apiBase;
    this.storage = storage || (typeof localStorage !== 'undefined' ? localStorage : null);
    this.fetchFn = fetchFn || (typeof fetch !== 'undefined' ? (url, init) => fetch(url, init) : null);
    /** @type {Map<string, object>} */
    this.memoryFallback = new Map();
  }

  _key(dateStr, translation = 'nrsvue') {
    return `pwc-day:${translation || 'nrsvue'}:${dateStr}`;
  }

  async get(dateStr, translation = 'nrsvue') {
    const t = translation || 'nrsvue';
    const key = this._key(dateStr, t);
    let item = null;

    if (this.storage) {
      try {
        const raw = this.storage.getItem(key) || (t === 'nrsvue' ? this.storage.getItem(`pwc-day:${dateStr}`) : null);
        if (raw) {
          item = JSON.parse(raw);
        }
      } catch (e) {
        // Fallback to memory
      }
    }

    if (!item) {
      item = this.memoryFallback.get(key) || (t === 'nrsvue' ? this.memoryFallback.get(`pwc-day:${dateStr}`) : null);
    }

    if (!item) return null;

    if (item.expiresAt && Date.now() > item.expiresAt) {
      await this.delete(dateStr, t);
      return null;
    }

    return item;
  }

  async set(dateStr, data, translation = 'nrsvue') {
    const t = translation || data.translation || 'nrsvue';
    const key = this._key(dateStr, t);
    const entry = {
      ...data,
      fetchedAt: data.fetchedAt || Date.now(),
      expiresAt: data.expiresAt || (Date.now() + 30 * 86400000),
    };

    let storedInStorage = false;
    if (this.storage) {
      try {
        this.storage.setItem(key, JSON.stringify(entry));
        storedInStorage = true;
      } catch (e) {
        // Handle QuotaExceeded by purging and using memory fallback
        await this.purge(todayUtcString(), 30);
        try {
          this.storage.setItem(key, JSON.stringify(entry));
          storedInStorage = true;
        } catch (e2) {
          // Fall through to memory fallback
        }
      }
    }

    if (!storedInStorage) {
      this.memoryFallback.set(key, entry);
    }
  }

  async delete(dateStr, translation = 'nrsvue') {
    const t = translation || 'nrsvue';
    const key = this._key(dateStr, t);
    if (this.storage) {
      try {
        this.storage.removeItem(key);
        this.storage.removeItem(`pwc-day:${dateStr}`);
      } catch (e) {}
    }
    this.memoryFallback.delete(key);
    this.memoryFallback.delete(`pwc-day:${dateStr}`);
  }

  async purge(currentDate = todayUtcString(), maxAgeDays = 30) {
    const now = Date.now();
    const isExpired = (item, key) => {
      if (!item) return false;
      const targetDate = item.date || key.split(':').pop();
      const diffDays = Math.abs(dayDifference(targetDate, currentDate));
      const ageDays = (now - (item.fetchedAt || now)) / 86400000;
      return diffDays > maxAgeDays || ageDays > maxAgeDays || (item.expiresAt && now > item.expiresAt);
    };

    const purgedKeys = new Set();

    if (this.storage) {
      try {
        const keysToPurge = [];
        for (let i = 0; i < this.storage.length; i++) {
          const key = this.storage.key(i);
          if (key && key.startsWith('pwc-day:')) {
            try {
              const raw = this.storage.getItem(key);
              const item = raw ? JSON.parse(raw) : null;
              if (isExpired(item, key)) {
                keysToPurge.push(key);
              }
            } catch (e) {
              keysToPurge.push(key);
            }
          }
        }
        for (const k of keysToPurge) {
          this.storage.removeItem(k);
          purgedKeys.add(k);
        }
      } catch (e) {}
    }

    for (const [key, item] of this.memoryFallback.entries()) {
      if (key.startsWith('pwc-day:') && isExpired(item, key)) {
        this.memoryFallback.delete(key);
        purgedKeys.add(key);
      }
    }

    return purgedKeys.size;
  }

  async getDay(dateStr, options = {}) {
    const translation = options.translation || 'nrsvue';

    // 1. Check local cache
    const cached = await this.get(dateStr, translation);
    if (cached) {
      return cached;
    }

    // 2. Check offline status
    const isOffline = (typeof window !== 'undefined' && window.__pwcOffline) ||
      (typeof navigator !== 'undefined' && navigator.onLine === false);

    if (isOffline) {
      const err = /** @type {Error & { isOfflineMiss?: boolean }} */ (new Error('Network connection required'));
      err.isOfflineMiss = true;
      throw err;
    }

    // 3. Fetch from API
    if (!this.fetchFn) {
      const err = /** @type {Error & { isOfflineMiss?: boolean }} */ (new Error('Network connection required'));
      err.isOfflineMiss = true;
      throw err;
    }

    const url = `${this.apiBase}?date=${dateStr}&translation=${encodeURIComponent(translation)}`;
    let res;
    try {
      res = await this.fetchFn(url);
    } catch (netErr) {
      const err = /** @type {Error & { isOfflineMiss?: boolean, cause?: unknown }} */ (new Error('Network connection required'));
      err.isOfflineMiss = true;
      err.cause = netErr;
      throw err;
    }

    if (!res.ok) {
      throw new Error(`Failed to fetch day: ${res.status}`);
    }

    const dayData = await res.json();
    await this.set(dateStr, dayData, translation);
    return dayData;
  }

  async prefetchBatch(startStr, endStr, translation = 'nrsvue') {
    const isOffline = (typeof window !== 'undefined' && window.__pwcOffline) ||
      (typeof navigator !== 'undefined' && navigator.onLine === false);
    if (isOffline || !this.fetchFn) return null;

    const url = `${this.apiBase}?start=${startStr}&end=${endStr}&translation=${encodeURIComponent(translation)}`;
    let res;
    try {
      res = await this.fetchFn(url);
    } catch (e) {
      return null;
    }

    if (!res || !res.ok) return null;
    const batchData = await res.json();
    if (batchData && batchData.days) {
      for (const [dateKey, dayObj] of Object.entries(batchData.days)) {
        await this.set(dateKey, dayObj, translation);
      }
    }
    return batchData;
  }

  async prefetchRollingWindow(todayStr = todayUtcString(), daysCount = 14, translation = 'nrsvue') {
    const endStr = offsetDate(todayStr, daysCount - 1);
    return this.prefetchBatch(todayStr, endStr, translation);
  }
}

/**
 * Factory to create DayCacheManager
 * @param {object} [options]
 * @param {string} [options.apiBase]
 * @param {Storage|null} [options.storage]
 * @param {typeof fetch} [options.fetchFn]
 * @returns {DayCacheManager}
 */
export function createDefaultDayCacheManager(options = {}) {
  const {
    apiBase = '/api/v2/calendar',
    storage = null,
    fetchFn = null,
  } = options;

  return new DayCacheManager({ apiBase, storage, fetchFn: fetchFn || defaultFetch });

}


