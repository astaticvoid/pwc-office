# PWC — Architecture & Design Document

_Last updated: 2026-06-13_

---

## 1. System Overview

**Pray Without Ceasing** is a static-first Anglican Daily Office app (Morning and Evening Prayer) with three user-facing surfaces:

| Surface | Entry point | Runtime |
|---------|-------------|---------|
| Web SPA | `web/index.html` + `web/app.js` | Browser (vanilla JS, no framework) |
| CLI | `cmd/dailyoffice/main.go` | Go binary |
| PWA (offline) | `web/sw.js` | Service worker, cache-first |

All three read the same JSON data files at runtime. The Go packages are the canonical data-model types; the web app re-implements a subset of the same logic in plain JavaScript.

---

## 2. Data Flow

```
Sources (copyrighted — gitignored)
  sources/pray-without-ceasing.pdf     ← PWC liturgical forms
  sources/bas_short_YYYY.csv           ← ACC lectionary CSVs
                    │
          Python tools/
                    │
        ┌───────────┼──────────────────┐
        ▼           ▼                  ▼
  data/offices.json  data/psalter.json  data/lectionary/YYYY-MM.json
  data/collects.json                   data/season_bounds.json
                    │
        ┌───────────┴──────────────────┐
        ▼                              ▼
  web/app.js (SPA)         cmd/dailyoffice/main.go (CLI)
  (fetches JSON at runtime) (loads JSON via embed.FS)
```

### Extraction pipeline (run once per source update)

1. `tools/extract_offices.py` → `data/offices.json`  
   PDF character-level extraction: classifies chars by font/color into `leader | response | rubric | heading | footer`, groups into sections, post-processes alternatives blocks.

2. `tools/extract_psalter.py` → `data/psalter.json`  
   Full psalter, KJV text with verse numbers and midpoint markers.

3. `tools/extract_collects.py` → `data/collects.json`  
   Collect of the Day entries keyed by BAS page number.

4. `tools/scrape_lectionary.py` → `sources/bas_short_YYYY.csv`  
   HTTP scraper with ETag/Last-Modified caching; diff tool for change detection.

5. `tools/convert_lectionary.py` → `data/lectionary/YYYY-MM.json` + `data/season_bounds.json`  
   CSV parser with manual correction dicts (LESSON_FIXES, RANK_FIXES, NAME_FIXES, COLOUR_FIXES, OBSERVANCES, NOTE_TYPES).

6. `tools/validate_lectionary.py`  
   Cross-validates CSV-converted data against HTML at `lectionary.anglican.ca`. Detects drift between sources.

### Data integrity

`tools/manifest.json` stores SHA-256 hashes of all pipeline output files. Each tool supports `--accept` to update the manifest after a deliberate re-extraction. Any unintended divergence from the committed baseline triggers a warning on the next run.

---

## 3. JSON Data Schemas

### `offices.json`

```
{
  "_shared": {
    "doxology":          <alternatives block>,
    "affirmation":       <alternatives block>,
    "berakah_blessings": <alternatives block>
  },
  "<season>-<mp|ep>": {
    "title": "...",
    "subtitle": "...",
    "reading_response":    <alternatives block>,
    "opening_responses":   [ <segment>... ],
    "thanksgiving_for_light": [...],
    "phos_hilaron":        [...],
    "invitatory":          [...],
    "responsory":          [...],
    "canticle":            [...],
    "affirmation":         [...],
    "intercessions":       [...],
    "litany":              [...],
    "seasonal_collects":   [...],
    "lords_prayer_intro":  [...],
    "dismissal":           [...]
  }
}
```

Segment types: `leader | response | rubric | alternatives | shared`

`alternatives` blocks: `{ type: "alternatives", groups: [{ label, segments }] }`  
`shared` references: `{ type: "shared", key: "doxology" | "affirmation" | "berakah_blessings" }`

### `lectionary/YYYY-MM.json`

```
{
  "YYYY-MM-DD": {
    "date": "YYYY-MM-DD",
    "name": "...",
    "rank": "feria | commemoration | memorial | holy_day | principal_feast",
    "colour": "White | Red | Green | ...",
    "observances": ["fast_day", "eve_of:Christmas", ...],
    "eucharist": "...",
    "morning": <Office>,
    "evening": <Office>,
    "notes": [{ "type": "...", "text": "..." }]
  }
}
```

Office: `{ label, psalms, psalm_sets, year_note, lessons, lessons_pick, collect, note, alternate? }`

### `season_bounds.json`

Keyed season boundary dates for the liturgical year span covered by the CSVs. Used by both the web app and Go CLI to resolve office forms and seasonal collects.

---

## 4. Web SPA (`web/app.js`)

Single 1289-line file; deliberately no build step, no framework. Routing is hash-based (`#/YYYY-MM-DD/mp|ep`).

### Key subsystems

| Function cluster | Responsibilities |
|-----------------|-----------------|
| `fetchOnce / fetchDay / fetchBook` | Lazy in-memory cache; monthly lectionary lazy-loaded on demand |
| `seasonOf / officeFormSeason / seasonWeekIndex` | Season + form resolution from bounds JSON |
| `formKey` | Maps (season, office type, weekday) → `offices.json` key |
| `renderSegments / renderAlternatives` | Recursive segment renderer; `localStorage` persists tab choices |
| `psalmHtml / lessonHtml / proclamationHtml` | Proclamation block assembly (psalm → lesson 1 → responsory → lesson 2 → canticle) |
| `collectToggleHtml` | Collect/seasonal-collect toggle |
| `parseCitation / parseRanges / extractVerses` | Scripture citation parser and verse extractor |
| `render(dateStr, officeType, translation)` | Top-level async render; orchestrates all fetches |

### localStorage key schema

| Pattern | Purpose |
|---------|---------|
| `pwc-alt-<contextKey>` | Alternatives tab choice (shared blocks use semantic name; inline use fingerprint) |
| `pwc-psalmset-<citations>` | Psalm set (All / Set 1 / Set 2) choice |
| `pwc-psalm-<citations>` | Multi-psalm (All / individual) choice |
| `pwc-alt-collect` | Collect of the Day vs. Seasonal Collect |
| `pwc-alt-reading_response` | Post-reading response form (I / II / III) |
| `pwc-translation` | `nrsvue` or `kjv` |
| `pwc-theme` | `light` or `dark` |
| `pwc-font-size` | `medium` or `large` |

### Service worker (`sw.js`)

Cache name `pwc-v1` is a placeholder; `make build` stamps it with a SHA-256 of the shell files. Strategy: cache-first for everything; 3 upcoming lectionary months prefetched on idle.

---

## 5. Go Packages

| Package | Role |
|---------|------|
| root `lectionary` | Core types: `Day`, `Season`, `Form`, `Psalter`, `Collects`, `Bible`. Both CLI and e2e tests load these. |
| `internal/office` | `office.Render()` — assembles a complete office as Markdown from a Day + data sources |
| `cmd/dailyoffice` | CLI entry point: flag parsing, date resolution, calls `office.Render()` |
| `e2e/` | LLM-evaluated tests (`e2e_smoke`, `e2e_seasonal`, `e2e_full` build tags) |

No external Go dependencies — stdlib only.

### Key design: Go/JS parity

The season computation logic (`SeasonOf`, `FormSeasonOf`) is implemented in both `season.go` and `app.js`. These must be kept in sync. The `forms_test.go` and `season_test.go` suites verify Go behaviour; the Playwright suite verifies the JS behaviour end-to-end.

**Risk:** divergence between Go and JS implementations is not automatically detected. A cross-check test (e.g., rendering the same date in both and comparing) would close this gap.

---

## 6. Testing Strategy

| Layer | Tool | Trigger |
|-------|------|---------|
| Go unit tests | `go test ./...` | `make test` (fast, no API key) |
| Structural full-year check | `e2e_full` build tag | `make test-full` |
| LLM-evaluated smoke (4 days) | `e2e_smoke` build tag | `make test-smoke` (needs `ANTHROPIC_API_KEY`) |
| LLM-evaluated seasonal (1 MP+EP per season) | `e2e_seasonal` | `make test-seasonal` |
| Playwright E2E (70+ tests, browser) | `playwright test` | `make test-web` |
| CSV vs HTML validation | `validate_lectionary.py` | Manual |
| Data integrity | `manifest.json` hash check | Every extraction run |

**Gaps (open):**
- LLM-evaluated smoke/seasonal tests depend on the `claude` CLI being installed — targeted for replacement with golden snapshot tests (see HANDOFF.md)

**Gaps (resolved):**
- ✅ Python tools now have 53 pytest tests (`make test-tools`) — BUG-12, 2026-06-07
- ✅ Go/JS season parity verified by `TestFormSeasonOf` + Playwright `Season theming parity` — BUG-01, 2026-06-07
- ✅ `validate_lectionary.py` wired into `make validate` — BUG-11, 2026-06-07

---

## 7. Deployment

Pure static hosting. `make build` assembles `dist/` from `web/` (dereferencing the `data/` symlink) and stamps the service worker cache key. `make deploy` syncs to S3 + CloudFront invalidation.

---

## 8. Alternate Lectionary Support (Design Target)

**Scope: RCL Daily Readings only.** BCP 1979 and BCP 2019 are explicitly out of scope. The ACC-authorized alternative to the BAS daily office lectionary is the CCT 2005 "Revised Common Lectionary Daily Readings" (GS2023 Resolution A124). That is the only alternate lectionary being implemented.

The current system is tightly coupled to the ACC BAS lectionary CSV format. Adding the RCL daily lectionary requires:

### Data layer
- Monthly JSON files at `data/rcl-daily/YYYY-MM.json` (gitignored; private evaluation pending ACC rights resolution)
- Source: `tools/extract_rcl_daily.py` parses RTF/DOC files downloaded from `commontexts.org/publications/`
- Citation format is the same as BAS (`book chapter:verse`) — no schema changes needed
- No separate `season_bounds.json` required — BAS bounds govern seasonal colouring; RCL weeks follow the same Christian year

### App layer
- `fetchDay()` branches on `localStorage` preference `pwc-lectionary` (`bas` | `rcl`)
- When `rcl`, loads from `data/rcl-daily/YYYY-MM.json` instead of `data/lectionary/YYYY-MM.json`
- All RCL code is behind `const FEATURE_RCL_DAILY = false` — setting false is a clean removal
- Track preference (`pwc-rcl-track`: `1` | `2`) selects semicontinuous vs. complementary in ordinary time

### Office forms
- PWC office forms (BAS/PWC) are unchanged — RCL provides only the readings (psalm + two lessons), not the liturgical form
- MP uses: psalm + first reading; EP uses: same psalm + second reading

### Full spec
See `docs/HANDOFF.md` — "RCL Daily Lectionary (P1, feature-gated)"

---

## 9. Book of Alternative Services Extension

BAS extends and supplements PWC for special occasions (e.g., Reconciliation, Marriage, Burial). The current app focuses exclusively on Daily Office. BAS extension means:

- Additional office forms not currently in PWC (e.g., alternate Evening Prayer orders)
- Additional collects (Occasional Prayers, BAS pp. 660+)
- Additional canticle options from BAS
- The Collect 668 hardcode is a stopgap for this

A BAS extension would require re-running `extract_offices.py` against the BAS PDF, adding a `bas/` sub-namespace in `offices.json`, and wiring up selection UI.

---

## 10. Copyright Status

| Asset | Status |
|-------|--------|
| `data/translations/kjv/` | Public domain — committed |
| `data/offices.json`, `data/psalter.json`, `data/collects.json` | ACC copyright — gitignored |
| `data/lectionary/` | ACC copyright — gitignored |
| `sources/` | ACC/BAS copyright — gitignored |
| `web/`, `*.go`, `tools/` | Original code — MIT/Apache eligible |

**Action required:** Contact ACC about a licence for liturgical text in an open-source app. This unblocks committing `data/` publicly and publishing under MIT or Apache 2.0.
