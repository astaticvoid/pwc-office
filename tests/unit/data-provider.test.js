import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  dayDifference,
  isWithinTemporalWindow,
  DayCacheManager,
  createDefaultDayCacheManager,
  defaultFetch,
} from '../../web/data-provider.js';

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

describe('DayCacheManager (ADR 0025)', () => {
  beforeEach(() => {
    try {
      if (typeof localStorage !== 'undefined') localStorage.clear();
    } catch (e) {}
  });

  it('creates default instance via factory', () => {
    const manager = createDefaultDayCacheManager();
    expect(manager).toBeInstanceOf(DayCacheManager);
    expect(manager.apiBase).toBe('/api/v2/calendar');
  });

  it('stores and retrieves cached unified day payload', async () => {
    const manager = new DayCacheManager();
    const dayData = {
      date: '2026-09-03',
      name: 'Gregory the Great',
      translation: 'nrsvue',
      readings: { 'Job 1:1': { citation: 'Job 1:1', verses: [], html: '<p>text</p>' } },
    };

    await manager.set('2026-09-03', dayData, 'nrsvue');
    const cached = await manager.get('2026-09-03', 'nrsvue');
    expect(cached).not.toBeNull();
    expect(cached?.name).toBe('Gregory the Great');
    expect(cached?.readings['Job 1:1']).toBeDefined();
  });

  it('purges entries older than 30 days', async () => {
    const manager = new DayCacheManager();
    const today = '2026-09-03';

    await manager.set('2026-09-03', {
      date: '2026-09-03',
      fetchedAt: Date.now(),
      expiresAt: Date.now() + 30 * 86400000,
    });

    await manager.set('2026-07-01', {
      date: '2026-07-01',
      fetchedAt: Date.now() - 40 * 86400000,
      expiresAt: Date.now() - 10 * 86400000,
    });

    const purged = await manager.purge(today, 30);
    expect(purged).toBe(1);
    expect(await manager.get('2026-07-01')).toBeNull();
    expect(await manager.get('2026-09-03')).not.toBeNull();
  });

  it('throws "Network connection required" on offline cache miss', async () => {
    const manager = new DayCacheManager({
      fetchFn: vi.fn().mockRejectedValue(new Error('Failed to fetch')),
    });

    // Simulate window.__pwcOffline
    // @ts-expect-error test mock
    globalThis.__pwcOffline = true;
    try {
      await expect(manager.getDay('2026-09-03')).rejects.toThrow('Network connection required');
    } finally {
      // @ts-expect-error test mock
      delete globalThis.__pwcOffline;
    }
  });

  it('fetches from API when not cached and stores result', async () => {
    const mockPayload = {
      date: '2026-09-03',
      name: 'Gregory the Great',
      translation: 'nrsvue',
      readings: {},
    };
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    });

    const manager = new DayCacheManager({ fetchFn });
    const result = await manager.getDay('2026-09-03');
    expect(fetchFn).toHaveBeenCalledWith('/api/v2/calendar?date=2026-09-03&translation=nrsvue');
    expect(result.name).toBe('Gregory the Great');

    // Subsequent call should hit cache without calling fetch
    fetchFn.mockClear();
    const cachedResult = await manager.getDay('2026-09-03');
    expect(fetchFn).not.toHaveBeenCalled();
    expect(cachedResult.name).toBe('Gregory the Great');
  });

  it('prefetches batch and populates cache for all days in batch', async () => {
    const mockBatch = {
      start: '2026-09-03',
      end: '2026-09-04',
      days: {
        '2026-09-03': { date: '2026-09-03', name: 'Day 1', translation: 'nrsvue' },
        '2026-09-04': { date: '2026-09-04', name: 'Day 2', translation: 'nrsvue' },
      },
    };
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockBatch,
    });

    const manager = new DayCacheManager({ fetchFn });
    await manager.prefetchBatch('2026-09-03', '2026-09-04');

    expect(fetchFn).toHaveBeenCalledWith('/api/v2/calendar?start=2026-09-03&end=2026-09-04&translation=nrsvue');
    const day1 = await manager.get('2026-09-03');
    const day2 = await manager.get('2026-09-04');
    expect(day1?.name).toBe('Day 1');
    expect(day2?.name).toBe('Day 2');
  });

  it('clearAll removes all pwc-day keys from cache', async () => {
    const manager = new DayCacheManager();
    await manager.set('2026-09-03', { date: '2026-09-03', name: 'Day 1' });
    await manager.set('2026-09-04', { date: '2026-09-04', name: 'Day 2' });

    expect(await manager.get('2026-09-03')).not.toBeNull();
    expect(await manager.get('2026-09-04')).not.toBeNull();

    const count = await manager.clearAll();
    expect(count).toBeGreaterThanOrEqual(2);
    expect(await manager.get('2026-09-03')).toBeNull();
    expect(await manager.get('2026-09-04')).toBeNull();
  });

  it('retries background prefetch on transient 502/503 errors', async () => {
    const mockBatch = {
      start: '2026-09-03',
      end: '2026-09-03',
      days: { '2026-09-03': { date: '2026-09-03', name: 'Day 1' } },
    };
    const fetchFn = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 502 })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => mockBatch });

    const manager = new DayCacheManager({ fetchFn });
    const result = await manager.prefetchBatch('2026-09-03', '2026-09-03');
    expect(fetchFn).toHaveBeenCalledTimes(2);
    expect(result).not.toBeNull();
  });

  it('does not retry background prefetch on 404 client error', async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    const manager = new DayCacheManager({ fetchFn });
    const result = await manager.prefetchBatch('2026-09-03', '2026-09-03');
    expect(fetchFn).toHaveBeenCalledTimes(1);
    expect(result).toBeNull();
  });

  it('handles corrupted JSON response in prefetchBatch gracefully without throwing', async () => {
    const fetchFn = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => { throw new Error('Invalid JSON'); },
    });
    const manager = new DayCacheManager({ fetchFn });
    const result = await manager.prefetchBatch('2026-09-03', '2026-09-03');
    expect(result).toBeNull();
  });

  it('clearAll dedupes count if keys are present in both storage and memory fallback', async () => {
    const manager = new DayCacheManager();
    await manager.set('2026-09-03', { date: '2026-09-03', name: 'Day 1' });
    // Intentionally populate the memory fallback with the same key
    manager.memoryFallback.set('pwc-day:nrsvue:2026-09-03', { date: '2026-09-03' });

    const count = await manager.clearAll();
    expect(count).toBe(1);
  });
});

describe('defaultFetch', () => {
  it('injects client telemetry headers and AbortSignal timeout', async () => {
    const origFetch = globalThis.fetch;
    const mockFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    globalThis.fetch = mockFetch;

    try {
      await defaultFetch('/api/v2/calendar?date=2026-09-03');
      expect(mockFetch).toHaveBeenCalledTimes(1);

      const [calledUrl, calledInit] = mockFetch.mock.calls[0];
      expect(calledUrl).toBe('/api/v2/calendar?date=2026-09-03');
      expect(calledInit.headers.get('X-Client-Version')).toBeDefined();
      expect(calledInit.headers.get('X-Client-Platform')).toBe('web');
      expect(calledInit.signal).toBeDefined();
    } finally {
      globalThis.fetch = origFetch;
    }
  });

  it('detects native mobile platforms when running under Capacitor', async () => {
    const origFetch = globalThis.fetch;
    const mockFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true })));
    globalThis.fetch = mockFetch;

    // Simulate Capacitor iOS environment
    // @ts-expect-error mock window plugins
    globalThis.window = {
      // @ts-expect-error mock window plugins
      __pwcPlugins: {
        Capacitor: {
          isNativePlatform: () => true,
          getPlatform: () => 'ios',
        },
      },
    };

    try {
      await defaultFetch('/api/v2/calendar?date=2026-09-03');
      const [, calledInit] = mockFetch.mock.calls[0];
      expect(calledInit.headers.get('X-Client-Platform')).toBe('ios');
    } finally {
      globalThis.fetch = origFetch;
      // @ts-expect-error mock window plugins
      delete globalThis.window;
    }
  });
});


