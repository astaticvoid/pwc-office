/**
 * @file data-provider.js
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


