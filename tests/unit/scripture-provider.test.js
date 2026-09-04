import { describe, it, expect, vi } from 'vitest';
import {
  dayDifference,
  isWithinTemporalWindow,
  MemoryScriptureCache,
  LocalStorageScriptureCache,
  RemoteScriptureProvider,
  CachedScriptureProvider,
  FallbackScriptureProvider,
  BundledKjvProvider,
  collectDayCitations,
} from '../../web/scripture-provider.js';

describe('Temporal window calculations', () => {
  it('calculates calendar day differences across month boundaries', () => {
    expect(dayDifference('2026-09-02', '2026-09-02')).toBe(0);
    expect(dayDifference('2026-09-03', '2026-09-02')).toBe(1);
    expect(dayDifference('2026-09-01', '2026-09-02')).toBe(-1);
    expect(dayDifference('2026-10-02', '2026-09-02')).toBe(30);
    expect(dayDifference('2026-10-03', '2026-09-02')).toBe(31);
    expect(dayDifference('2026-10-04', '2026-09-02')).toBe(32);
    expect(dayDifference('2026-03-01', '2026-02-28')).toBe(1);
  });

  it('enforces temporal window with configurable maxDays buffer', () => {
    const today = '2026-09-02';
    expect(isWithinTemporalWindow('2026-09-02', today, 31)).toBe(true);
    expect(isWithinTemporalWindow('2026-10-03', today, 31)).toBe(true);
    expect(isWithinTemporalWindow('2026-08-02', today, 31)).toBe(true);
    expect(isWithinTemporalWindow('2026-10-04', today, 31)).toBe(false);
    expect(isWithinTemporalWindow('2026-08-01', today, 31)).toBe(false);
  });
});

describe('Scripture caching & 30-day purge', () => {
  it('MemoryScriptureCache stores, retrieves, and purges out-of-window entries', async () => {
    const cache = new MemoryScriptureCache();
    const today = '2026-09-02';

    await cache.set('2026-09-02', 'nrsvue', {
      date: '2026-09-02',
      translation: 'nrsvue',
      source: 'remote',
      readings: { 'Job 12:1': { citation: 'Job 12:1', book: 'Job', verses: [], html: '<p>text</p>', translation: 'nrsvue' } },
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 30 * 86400000,
    });

    await cache.set('2026-07-01', 'nrsvue', {
      date: '2026-07-01',
      translation: 'nrsvue',
      source: 'remote',
      readings: {},
      fetchedAt: Date.now() - 40 * 86400000,
      expiresAt: Date.now() - 10 * 86400000,
    });

    const item = await cache.get('2026-09-02', 'nrsvue');
    expect(item).not.toBeNull();
    expect(item?.readings['Job 12:1']).toBeDefined();
    expect(item?.source).toBe('cache');

    const purged = await cache.purge(today, 30);
    expect(purged).toBe(1);
    expect(await cache.get('2026-07-01', 'nrsvue')).toBeNull();
    expect(await cache.get('2026-09-02', 'nrsvue')).not.toBeNull();
  });

  it('LocalStorageScriptureCache handles QuotaExceededError via purge and memory fallback', async () => {
    const mockStorage = {
      _data: {},
      getItem(k) { return this._data[k] || null; },
      setItem(k, v) {
        if (Object.keys(this._data).length >= 1) {
          const err = new Error('Quota exceeded');
          err.name = 'QuotaExceededError';
          throw err;
        }
        this._data[k] = v;
      },
      removeItem(k) { delete this._data[k]; },
      key(i) { return Object.keys(this._data)[i] || null; },
      get length() { return Object.keys(this._data).length; },
    };

    const cache = new LocalStorageScriptureCache({ storage: mockStorage });

    // First write succeeds
    await cache.set('2026-09-02', 'nrsvue', {
      date: '2026-09-02',
      translation: 'nrsvue',
      source: 'remote',
      readings: { 'Job 12:1': { citation: 'Job 12:1', book: 'Job', verses: [], html: '', translation: 'nrsvue' } },
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 30 * 86400000,
    });

    // Second write hits quota, falls back to memory without throwing
    await cache.set('2026-09-03', 'nrsvue', {
      date: '2026-09-03',
      translation: 'nrsvue',
      source: 'remote',
      readings: { 'Acts 1:1': { citation: 'Acts 1:1', book: 'Acts', verses: [], html: '', translation: 'nrsvue' } },
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 30 * 86400000,
    });

    const hit = await cache.get('2026-09-03', 'nrsvue');
    expect(hit).not.toBeNull();
    expect(hit?.readings['Acts 1:1']).toBeDefined();
  });
});

describe('RemoteScriptureProvider', () => {
  it('enforces format validation and fast-fails out-of-window requests', async () => {
    const fetchFn = vi.fn();
    const provider = new RemoteScriptureProvider({ fetchFn, windowGraceDays: 35 });

    await expect(provider.getReadingsForDate('invalid-date')).rejects.toThrow('Invalid date format');

    // Date far in the future
    const result = await provider.getReadingsForDate('2099-01-01');
    expect(result).toBeNull();
    expect(fetchFn).not.toHaveBeenCalled();
  });

  it('fetches valid in-window dates from edge service', async () => {
    const mockPayload = {
      date: '2026-09-02',
      translation: 'nrsvue',
      readings: {
        'Job 12:1': { citation: 'Job 12:1', book: 'Job', verses: [{ ch: 12, v: 1, text: 'Then Job answered' }], html: '<p>verse</p>', translation: 'nrsvue' },
      },
    };

    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockPayload,
    });

    const provider = new RemoteScriptureProvider({
      apiBase: '/api/v1/readings',
      translation: 'nrsvue',
      fetchFn,
      windowGraceDays: 35,
    });

    const res = await provider.getReadingsForDate('2026-09-02');
    expect(fetchFn).toHaveBeenCalledWith('/api/v1/readings?date=2026-09-02&translation=nrsvue');
    expect(res).not.toBeNull();
    expect(res?.readings['Job 12:1'].citation).toBe('Job 12:1');
    expect(res?.source).toBe('remote');
  });

  it('defaults apiBase to /api/v1/readings', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ date: '2026-09-02', readings: {} }),
    });
    const provider = new RemoteScriptureProvider({ fetchFn });
    expect(provider.apiBase).toBe('/api/v1/readings');
    await provider.getReadingsForDate('2026-09-02');
    expect(fetchFn).toHaveBeenCalledWith('/api/v1/readings?date=2026-09-02&translation=nrsvue');
  });

  it('handles 403 Forbidden by returning null to trigger fallback', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: 'Temporal restriction' }),
    });

    const provider = new RemoteScriptureProvider({ fetchFn });
    const res = await provider.getReadingsForDate('2026-09-02');
    expect(res).toBeNull();
  });
});

describe('CachedScriptureProvider', () => {
  it('checks cache before querying inner provider, and saves fresh results to cache', async () => {
    const mockInner = {
      translation: 'nrsvue',
      getReadingsForDate: vi.fn().mockResolvedValue({
        date: '2026-09-02',
        translation: 'nrsvue',
        source: 'remote',
        readings: { 'Job 12:1': { citation: 'Job 12:1', book: 'Job', verses: [], html: '', translation: 'nrsvue' } },
        fetchedAt: Date.now(),
        expiresAt: Date.now() + 30 * 86400000,
      }),
    };

    const cache = new MemoryScriptureCache();
    const cachedProvider = new CachedScriptureProvider(mockInner, cache);

    // First call: cache miss, invokes inner
    const res1 = await cachedProvider.getReadingsForDate('2026-09-02');
    expect(mockInner.getReadingsForDate).toHaveBeenCalledTimes(1);
    expect(res1?.readings['Job 12:1']).toBeDefined();

    // Second call: cache hit, does not call inner
    const res2 = await cachedProvider.getReadingsForDate('2026-09-02');
    expect(mockInner.getReadingsForDate).toHaveBeenCalledTimes(1);
    expect(res2?.source).toBe('cache');
  });
});

describe('FallbackScriptureProvider & BundledKjvProvider', () => {
  it('seamlessly degrades to fallback provider when primary fails or returns null', async () => {
    const primary = {
      translation: 'nrsvue',
      getReadingsForDate: vi.fn().mockResolvedValue(null),
    };

    const fallback = {
      translation: 'kjv',
      getReadingsForDate: vi.fn().mockResolvedValue({
        date: '2026-09-02',
        translation: 'kjv',
        source: 'fallback',
        readings: {
          'Job 12:1': { citation: 'Job 12:1', book: 'Job', verses: [], html: '<p>KJV</p>', translation: 'kjv' },
        },
      }),
    };

    const composite = new FallbackScriptureProvider({ primary, fallback });
    const res = await composite.getReadingsForDate('2026-09-02');

    expect(primary.getReadingsForDate).toHaveBeenCalledWith('2026-09-02', {});
    expect(fallback.getReadingsForDate).toHaveBeenCalledWith('2026-09-02', {});
    expect(res).not.toBeNull();
    expect(res?.source).toBe('fallback');
    expect(res?.readings['Job 12:1'].isFallback).toBe(true);
  });

  it('collectDayCitations comprehensively extracts lessons across offices and choices', () => {
    const mockDay = {
      date: '2026-10-25',
      morning: {
        lessons: ['Sir 38:24-34', { citation: '1 Cor 1:18-31', optional: true }],
        alternate: {
          lessons: ['1 Kgs 8:22-30', 'Jn 10:22-30'],
        },
      },
      evening: {
        lessons: ['Rom 5:12-21 or Gal 4:1-7', 'Mt 5:1-12'],
      },
    };

    const citations = collectDayCitations(mockDay);
    expect(citations).toContain('Sir 38:24-34');
    expect(citations).toContain('1 Cor 1:18-31');
    expect(citations).toContain('1 Kgs 8:22-30');
    expect(citations).toContain('Jn 10:22-30');
    expect(citations).toContain('Rom 5:12-21');
    expect(citations).toContain('Gal 4:1-7');
    expect(citations).toContain('Mt 5:1-12');
  });

  it('BundledKjvProvider extracts verses locally without network calls', async () => {
    const mockBook = {
      '1': {
        '1': 'In the beginning God created the heaven and the earth.',
        '2': 'And the earth was without form, and void.',
      },
    };

    const provider = new BundledKjvProvider({
      fetchBook: vi.fn().mockResolvedValue(mockBook),
      parseCitation: vi.fn().mockReturnValue({ file: 'Genesis', rest: '1:1-2' }),
      parseRanges: vi.fn().mockReturnValue([{ startCh: 1, startV: 1, endCh: 1, endV: 2 }]),
      extractVerses: (b, _r) => [{ ch: 1, v: 1, text: b['1']['1'] }, { ch: 1, v: 2, text: b['1']['2'] }],
      buildHtml: (verses) => verses.map(v => `<p>${v.text}</p>`).join(''),
    });

    const res = await provider.getReadingsForDate('2026-09-02', { citation: 'Gen 1:1-2' });
    expect(res).not.toBeNull();
    expect(res?.translation).toBe('kjv');
    expect(res?.readings['Gen 1:1-2'].verses.length).toBe(2);
    expect(res?.readings['Gen 1:1-2'].verses[0].text).toContain('In the beginning');
  });

  it('routes directly to fallback when options.translation matches fallback translation', async () => {
    const primary = {
      translation: 'nrsvue',
      getReadingsForDate: vi.fn(),
    };
    const fallback = {
      translation: 'kjv',
      getReadingsForDate: vi.fn().mockResolvedValue({
        date: '2026-09-02',
        translation: 'kjv',
        source: 'fallback',
        readings: {
          'Gen 1:1': { citation: 'Gen 1:1', book: 'Gen', verses: [], html: '', translation: 'kjv' },
        },
      }),
    };
    const composite = new FallbackScriptureProvider({ primary, fallback });
    const res = await composite.getReadingsForDate('2026-09-02', { translation: 'kjv' });
    expect(primary.getReadingsForDate).not.toHaveBeenCalled();
    expect(fallback.getReadingsForDate).toHaveBeenCalled();
    expect(res?.translation).toBe('kjv');
    expect(res?.readings['Gen 1:1'].isFallback).toBeUndefined();
  });

  it('BundledKjvProvider synthesizes composite entries for " or " choices', async () => {
    const mockBook = {
      '1': { '1': 'v1' },
    };
    const provider = new BundledKjvProvider({
      fetchBook: vi.fn().mockResolvedValue(mockBook),
      parseCitation: vi.fn().mockImplementation((c) => ({ file: c.split(' ')[0], rest: '1:1' })),
      parseRanges: vi.fn().mockReturnValue([{ startCh: 1, startV: 1, endCh: 1, endV: 1 }]),
      extractVerses: () => [{ ch: 1, v: 1, text: 'text' }],
      buildHtml: () => '<p>verse</p>',
    });

    const day = {
      morning: { lessons: ['Rom 5:1-2 or Gal 4:1-2'] },
    };
    const res = await provider.getReadingsForDate('2026-09-02', { day });
    expect(res?.readings['Rom 5:1-2 or Gal 4:1-2']).toBeDefined();
    expect(res?.readings['Rom 5:1-2 or Gal 4:1-2'].html).toContain('class="seg-rubric">or</p>');
  });
});

describe('Anti-Scraping & Granularity Verification', () => {
  it('guarantees IScriptureProvider only accepts date queries and exposes no book endpoints', () => {
    const provider = new RemoteScriptureProvider();
    expect(typeof provider.getReadingsForDate).toBe('function');
    // @ts-expect-error verifying no arbitrary book query methods exist
    expect(provider.getBook).toBeUndefined();
    // @ts-expect-error verifying no all-books query methods exist
    expect(provider.getAllBooks).toBeUndefined();
    // @ts-expect-error verifying no raw citation endpoint exists
    expect(provider.getPassage).toBeUndefined();
  });
});
