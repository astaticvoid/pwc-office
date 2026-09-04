# ADR 0023: ScriptureProvider abstraction, date-grained lectionary delivery, and temporal cache purging

## Status
Accepted

## Context
The Pray Without Ceasing (PWC) liturgical application renders daily office services (Morning and Evening Prayer) along with appointed Scripture lessons. Historically, scripture readings were extracted from local book files or bundled offline JSON sources (`data/translations/nrsvue/`).

To include modern copyrighted Bible translations—specifically the **New Revised Standard Version Updated Edition (NRSVue)**—the application must satisfy strict licensing and digital distribution requirements imposed by the copyright holder (National Council of Churches of Christ in the USA / Friendship Press):
1. **No Bulk or Whole-Book Distribution**: The application cannot bundle full Bible books or allow clients to systematically scrape or download complete books or chapters.
2. **Date Granularity**: Scripture must be queried and delivered strictly as lectionary readings appointed for a specific liturgical date, not as arbitrary passage or chapter lookups.
3. **Strict Temporal Restriction**: The service must only deliver readings within a narrow rolling window around the current date ($\pm 30$ days). Requests for dates outside this window must be rejected.
4. **Local Retention Limit & Automatic Purge**: Client-side offline caching is permitted only for temporary rolling operational use; readings stored locally must be evicted when outside the rolling $\pm 30$-day temporal window or older than 30 days.
5. **Offline Reliability**: Readers in rural or offline parishes must not be left stranded without scripture when offline or out-of-window; public-domain fallback (King James Version) must be transparently available.

## Decision

We establish a vendor-neutral client scripture abstraction layer rooted in an `IScriptureProvider` interface, coupled with an automatic temporal cache and graceful public-domain fallback.

### 1. Vendor-Neutral Client Interface (`web/scripture-types.d.ts`, `web/scripture-provider.js`)

All client-side components query scripture solely through the `IScriptureProvider` abstraction:

```typescript
export interface ScriptureReading {
  citation: string;
  book: string;
  verses: Array<{ ch: number; v: number; text: string }>;
  html: string;
  translation: string;
  isFallback?: boolean;
}

export interface DayReadingsResult {
  date: string; // YYYY-MM-DD
  translation: string;
  source: 'remote' | 'cache' | 'fallback';
  readings: Record<string, ScriptureReading>;
  fetchedAt: number;
  expiresAt: number;
}

export interface IScriptureProvider {
  readonly translation: string;
  getReadingsForDate(date: string, options?: { day?: any; translation?: string }): Promise<DayReadingsResult | null>;
}
```

#### Invariants:
- **Date-Grained Only**: No methods exist for `getBook(book)`, `getChapter(book, ch)`, or `getPassage(cit)`. Scraping whole books through the provider is architecturally impossible.
- **Normalized Keys**: Readings are returned as a map keyed by the exact raw citation string (`data-citation`) appointed in the lectionary, including em-dashes and multi-lesson options.

### 2. Temporal Gating & Timezone Grace Window

The legal window is $\pm 30$ calendar days from the user's current date. Because the Earth spans 26 standard timezones (UTC-12 to UTC+14):
- A user near midnight in UTC-10 (Hawaii) or UTC+13 (New Zealand) requesting a reading at the 30-day boundary could be separated from server UTC by up to 26 hours.
- A rigid 30-day UTC comparison would reject legitimate same-day requests near midnight.
- **Decision**: The temporal check operates on UTC calendar dates with a **$\pm 31$ day buffer** at the network edge and a generous $\pm 35$ day buffer in the client fast-fail check.

### 3. Local Caching & Rolling Purge Engine (`LocalStorageScriptureCache`)

To support offline prayer and snappy navigation while honoring the 30-day retention limit:
- Sliced day results are stored under the key prefix `pwc-scripture:${translation}:${date}`.
- Every cache entry stores `fetchedAt`, `expiresAt`, and `date`.
- **Automatic Purge**: On cache initialization and every write, `purge(todayStr, 30)` is executed:
  1. Deletes any cached entry where `Math.abs(dayDifference(entryDate, today)) > 30`.
  2. Deletes any cached entry where `now - fetchedAt > 30 * 86400000`.
- **Quota Robustness**: If `localStorage` throws a `QuotaExceededError`, the cache executes an immediate emergency purge of all expired or distant records and falls back gracefully to an in-memory session cache (`MemoryScriptureCache`) without throwing or crashing the UI.
- **Storage Isolation**: The cache uses browser `localStorage` directly and avoids native preference stores (`NSUserDefaults`) to prevent storage ceiling issues.

### 4. Transparent Fallback to Bundled KJV (`BundledKjvProvider` & `FallbackScriptureProvider`)

Public-domain KJV remains permanently bundled with the application:
1. When the primary provider (`CachedScriptureProvider` wrapping `RemoteScriptureProvider`) returns `null` (e.g. out-of-window date, offline with empty cache, or network failure), `FallbackScriptureProvider` seamlessly delegates to `BundledKjvProvider`.
2. Fallback readings are tagged with `isFallback: true`. The UI displays the scripture text with an unobtrusive note:
   `[KJV shown — NRSVUE unavailable for this reading]`.
3. If the reader explicitly selects KJV in the translation dropdown, `FallbackScriptureProvider` routes directly to `BundledKjvProvider` without requesting or returning fallback notices.

### 5. API Contract, Payload Schema, and Versioning Strategy (`v1`)

As client applications evolve across web and native mobile wrappers (Capacitor), client and backend deployments decouple. To maintain long-term interoperability without breaking installed mobile clients or cached web apps, the edge lectionary API uses path-based versioning and enforces an immutable API contract.

#### Endpoint Specification
- **URL Path**: `/api/v1/readings`
- **Method**: `GET` (with `OPTIONS` for CORS preflight)
- **Query Parameters**:
  - `date`: `YYYY-MM-DD` (required, calendar date within $\pm 31$ days)
  - `translation`: Bible translation code (default: `nrsvue`)

#### Payload Schema (`v1`)
The response payload is a JSON object fulfilling `DayReadingsResult`:

```typescript
export interface ScriptureReadingV1 {
  citation: string;
  book: string;
  verses: Array<{
    ch: number;
    v: number;
    text: string;
  }>;
  html: string;
  translation: string;
  isFallback?: boolean;
}

export interface DayReadingsPayloadV1 {
  date: string; // YYYY-MM-DD
  translation: string; // e.g. "nrsvue"
  source: 'remote';
  readings: Record<string, ScriptureReadingV1>; // Keyed by raw lectionary citation
  fetchedAt: number; // UTC timestamp ms
  expiresAt: number; // UTC timestamp ms (fetchedAt + 30 days)
}
```

Example JSON response (`/api/v1/readings?date=2026-09-02&translation=nrsvue`):
```json
{
  "date": "2026-09-02",
  "translation": "nrsvue",
  "source": "remote",
  "readings": {
    "Jn 8:47-59": {
      "citation": "Jn 8:47-59",
      "book": "John",
      "verses": [
        { "ch": 8, "v": 47, "text": "Whoever is from God hears the words of God..." }
      ],
      "html": "<p class=\"scripture-block\"><sup class=\"verse-num\">47</sup> Whoever is from God...</p>",
      "translation": "nrsvue"
    }
  },
  "fetchedAt": 1788467489812,
  "expiresAt": 1791059489812
}
```

#### Backward Compatibility: The "Additive Changes Only" Rule
For a given major API version (such as `v1`):
1. **Additive Changes Only**: New optional properties may be added to top-level objects, `readings`, or `verses` without bumping the API version. Clients must ignore unrecognized fields.
2. **Immutable Existing Fields**: Existing fields (`date`, `translation`, `source`, `readings`, `fetchedAt`, `expiresAt`, `citation`, `book`, `verses`, `html`) must not be deleted, renamed, or altered in type or semantics.
3. **Breaking Changes Require a Version Bump**: Any non-additive change (e.g. altering the shape of `verses`, removing `html`, or changing key serialization) constitutes a breaking change and requires introducing a new versioned endpoint (e.g. `/api/v2/readings`) backed by `.build/private/readings/v2/`. Prior versions (e.g. `v1`) must remain hosted and operational to support existing client installations.

## Consequences

### Positive
- **Full Legal Compliance**: Protects copyright holders against wholesale extraction, book scraping, and indefinite client caching.
- **Offline Resilience**: Anglican daily prayer remains fully usable offline and anywhere in the world via KJV fallback.
- **Clean Architecture**: Decouples UI rendering from transport and storage mechanics.

### Negative / Trade-Offs
- Historical or advance liturgical study beyond $\pm 30$ days displays KJV rather than NRSVue.
- Client requires periodic network connectivity to refresh NRSVue readings.
