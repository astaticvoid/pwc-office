import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  dayDifference,
  isWithinTemporalWindow,
  DayCacheManager,
  createDefaultDayCacheManager,
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
});

