/**
 * Scripture Provider contracts and data shapes (ADR 0023).
 *
 * Defines the vendor-neutral interface for requesting lectionary readings
 * strictly by date rather than by book or arbitrary passage, satisfying
 * copyright licensing covenants (NRSVue).
 */

/** A single scripture verse. */
export interface ScriptureVerse {
  ch: number;
  v: number;
  text: string;
}

/** An individual appointed reading with verse objects and formatted HTML. */
export interface ScriptureReading {
  citation: string;
  book: string;
  verses: ScriptureVerse[];
  html: string;
  translation: string;
  isFallback?: boolean;
}

/** Complete set of appointed scripture readings for a calendar date. */
export interface DayReadingsResult {
  date: string; // 'YYYY-MM-DD'
  translation: string;
  source: 'remote' | 'cache' | 'fallback' | (string & {});
  readings: Record<string, ScriptureReading>; // keyed by exact raw citation
  fetchedAt: number; // Unix epoch ms
  expiresAt: number; // Unix epoch ms
}

/** Pluggable local storage engine for CachedScriptureProvider. */
export interface IScriptureCache {
  get(date: string, translation: string): Promise<DayReadingsResult | null>;
  set(date: string, translation: string, data: DayReadingsResult): Promise<void>;
  purge(currentDate: string, maxAgeDays?: number): Promise<number>;
}

/** Core Scripture Provider contract. */
export interface IScriptureProvider {
  readonly translation: string;
  getReadingsForDate(date: string, options?: Record<string, unknown>): Promise<DayReadingsResult | null>;
}

