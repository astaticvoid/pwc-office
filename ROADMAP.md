# PWC — Project Roadmap

_Last updated: 2026-06-13_

This roadmap organises work into four phases with a rough priority ordering within each. Items are linked to BUGS.md where a known defect is involved.

---

## Phase 0 — Redesign ✅ Complete (2026-06-10)

The full nav/UX redesign was implemented and reviewed at Synod on 10 June 2026:
- Nav redesign: minimal two-row chrome, settings bottom sheet (gear icon), MP/EP row
- Book mode: flat read-through view, all alternatives shown sequentially with "or" dividers
- Observance as content card (removed from nav)
- Seasonal accent colours (per `data-season` attribute)
- UX-03, 07, 08, 10, 11, 12, 13, 14, 16 all fixed
- Post-review tweaks: nav icon polish, Today button replaced by calendar icon, Trinity Sunday season fix

See `docs/HANDOFF.md` for what comes next.

---

## Phase 1 — Correctness & Hygiene (Now)

These are the highest-leverage changes: they close correctness gaps and reduce the ongoing maintenance burden.

### 1.1 Python extraction tooling

✅ **Add unit tests for extraction tools** (BUGS.md BUG-12, fixed 2026-06-07)  
`tools/tests/` created with 53 pytest tests covering `parse_name_meta`, `parse_psalm_field`, `parse_lesson`, `detect_bounds`, `_char_type`, `_fix_casing`, `_group_alternatives`. `make test-tools` wired up.

✅ **Fix `_BLOCK_SEP_ONLY` to capture canticle intro rubric natively** (BUGS.md BUG-10, fixed 2026-06-07)  
`_group_alternatives` now emits the canticle doxology intro rubric to `result` before starting unnamed groups. The `_dedup_shared` workaround that re-inserted hardcoded text is removed.

✅ **Add bounds validation assertion in `convert_lectionary.py`** (BUGS.md BUG-02, fixed 2026-06-06)  
After `detect_bounds()`, asserts all 8 required keys are present. Fails loudly with a list of missing keys.

✅ **Wire `validate_lectionary.py` into `make validate`** (BUGS.md BUG-11, fixed 2026-06-07)  
Added `make validate` target. Requires network access; run manually before a data re-extraction.

### 1.2 Correctness assurance

✅ **Go/JS season parity test** (BUGS.md BUG-01, fixed 2026-06-07)  
`TestFormSeasonOf` in `season_test.go` checks 24 boundary dates using `fullBounds2026`. Playwright `Season theming parity` block checks the same 11 dates via `html[data-season]`. Any future divergence fails the relevant suite.

✅ **Fix `READING_RESPONSE` fallback wording** (BUGS.md BUG-03, fixed 2026-06-06)  
Group III changed to ordinary-time form; `console.warn` added for regression visibility.

**Lectionary notes audit** (BUGS.md BUG-05, BUG-15)  
Systematically check all `notes` fields in the current lectionary JSON:
- Cross-references (pointless without the physical book) → add `crossref` type, suppress globally
- Garbled parsing artifacts → fix upstream in `convert_lectionary.py` or add to `CLEAR_NOTES`
- Complete the `NOTE_TYPES` audit for all dates 2016–2025 (2026 done)

**Collect coverage audit**  
Run through all `collect` field values in the lectionary JSON and verify each resolves to an entry in `collects.json`. Flag any that don't. At minimum, document the gaps.

### 1.3 Data model hygiene

**Data normalization** — write `tools/normalize_offices.py` to deduplicate `reading_response`, `lords_prayer_intro`, and seasonal EP `opening_responses` into `_shared`. No app change required (existing shared-ref mechanism handles it). Spec in `docs/HANDOFF.md`.

**Patch system** — `data/patches.json` + `tools/apply_patches.py` + `tools/validate_patches.py`. Makes text corrections versioned and re-extraction-safe. Convert BUG-18 litany fix into first patch entry. Spec in `docs/HANDOFF.md`.

### 1.4 Code hygiene

✅ **Remove `boneyard/`** (BUGS.md BUG-16, removed 2026-06-06)

✅ **Add startup CANTICLE_SOURCE completeness check** (BUGS.md BUG-17, fixed 2026-06-06)  
`renderAlternatives()` emits `console.warn` when a named canticle label has no entry in `CANTICLE_SOURCE`.

**Source fetch + extract pipeline** — `make fetch-sources` downloads all sources automatically (all PDFs + CSVs are publicly available from anglican.ca and commontexts.org). `make extract` runs the full pipeline. Spec in `docs/HANDOFF.md`.

**Trim lectionary to rolling window** — drop historical data beyond 12 months. Nobody uses 2016–2023 offices; trimming reduces `dist/` size and service worker cache. Spec in `docs/HANDOFF.md`.

**ARIA tab roles** (UX-15) — `renderAlternatives()` in `app.js`. Spec in `docs/HANDOFF.md`.

**JSDoc / module annotation** — JSDoc on major `app.js` function clusters. Spec in `docs/HANDOFF.md`.

**CONTRIBUTING.md** — developer guide: setup, data pipeline, test tiers, deploy, copyright constraints. Spec in `docs/HANDOFF.md`.

---

## Phase 2 — Feature Completeness (Soon)

### 2.1 Lectionary coverage

**Year A extraction** (BUGS.md BUG-06)  
When ACC publishes Year A CSVs (expected Advent 2026), run the full pipeline:
- `scrape_lectionary.py` to download
- `convert_lectionary.py` to convert — expect to add new correction dict entries
- `validate_lectionary.py` to cross-check
- Update `season_bounds.json` with Year A bounds
- Extend date picker `max` in the web app

**Year A/B/C cycle display**  
The web app should show the current BCP year (A/B/C) in the day metadata so users understand which lectionary year they're in. Derive from bounds.

### 2.2 Missing liturgical content

**Extract Occasional Prayers from BAS** (BUGS.md BUG-04)  
Add an `extract_occasional_prayers.py` (or extend `extract_collects.py`) to extract BAS pp. 660+. Replace the hardcoded Collect 668 with a properly extracted entry.

✅ **Distinctive note rendering by type** (BUGS.md BUG-07, fixed 2026-06-07)  
- `o_antiphon`: liturgical block with Latin title, accent border, italic body
- `civil_day` / `week_of_prayer`: muted informational row with bold day name
- Other types: existing expand-on-read behaviour

### 2.3 Print mode (BUGS.md BUG-08)

✅ Fixed 2026-06-06. `@media print` CSS added:
- All `.alt-panel-hidden` elements revealed
- `.alt-tabs` hidden; nav, buttons, colour chips suppressed
- Serif font at appropriate print sizing

A `?view=print` URL parameter for screen-based "full text" mode (useful for leading a service from a laptop) is still worth adding.

### 2.4 Offline improvements (BUGS.md BUG-09)

**Explicit offline download UI**  
Add a settings drawer with:
- Current offline coverage indicator (which months are cached)
- "Download next 3 months" / "Download full year" buttons
- Per-translation download (KJV vs. NRSVUE)
- Uses `Cache.put()` directly; shows progress

### 2.5 First-run experience (BUGS.md BUG-13)

One-time prompt on first visit (detected via `localStorage` flag):
1. Choose translation (NRSVUE / KJV)
2. Optionally set theme preference

Keep it to 2 choices, no modal — an inline banner that dismisses and sets the prefs.

### 2.6 ACC licence

Draft and send inquiry to Anglican Church of Canada about reproducing BAS/PWC liturgical text in an open-source Anglican worship app. This unblocks:
- Committing `data/` publicly
- Publishing the repo under MIT or Apache 2.0

---

## Phase 3 — Alternate Lectionaries

See `docs/DESIGN.md` §8 for the architectural requirements.

**Scope**: RCL daily readings only. BCP 1979 and BCP 2019 are explicitly out of scope.

### 3.1 Data model refactoring

- Namespace data paths: `data/<lectionary-id>/lectionary/YYYY-MM.json`
- Add `lectionary_id` to `season_bounds.json`
- Abstract `detect_bounds()` behind a source-agnostic interface
- Update app `fetchDay()` to accept `lectionaryId`

### 3.2 RCL Daily Readings

**Background**: General Synod 2023 authorized the "Revised Common Lectionary Daily Readings" (Consultation on Common Texts, 2005) as an alternative to the BAS daily office lectionary for use in the Anglican Church of Canada. This is the standard universal CCT publication — no Canadian variant exists.

**Data source**: The RCL daily data is copyright © 2005 CCT, administered by Augsburg Fortress (1517 Media). It is not available in open machine-readable form; the ACC site and dailylectio.net both display it under permission. The Synod is currently examining distribution rights for the official ACC app. In the interim, data is for private evaluation only and must be gitignored (consistent with all other copyrighted content in this project).

**Data acquisition**: Write `tools/extract_rcl_daily.py` to parse RTF/DOC files downloaded directly from `commontexts.org/publications/` — the canonical CCT source. No web scraping needed; CCT publishes the 2005 Daily Readings as free RTF downloads for all three years, plus a 2024 Expanded edition (Year A only as of 2026-06). Output goes to `data/rcl-daily/YYYY-MM.json`, gitignored. Script is checked in like all other extractors. Full spec in `docs/HANDOFF.md`.

**Feature gate**: All RCL daily code is behind a `FEATURE_RCL_DAILY` flag (const in `app.js`, default `false`). Setting it `false` removes all RCL UI and data-fetching with zero residual effect. This allows the feature to be enabled for evaluation and disabled cleanly if distribution rights do not resolve.

**Data model** (daily, per month file):
```json
[
  {
    "date": "2026-06-13",
    "week_label": "Proper 6 – Preparation 3",
    "track1": { "psalm": "Psalm 116:1-2, 12-19", "ot": "Genesis 24:10-52", "nt": "Mark 7:1-13" },
    "track2": { "psalm": "Psalm 100", "ot": "Exodus 6:28—7:13", "nt": "Mark 7:1-13" }
  }
]
```

**Daily Office mapping**: For MP — psalm + OT reading. For EP — (same) psalm + NT reading. Track selection (1 = semicontinuous, 2 = complementary) stored in `localStorage`.

**Full spec** in `docs/HANDOFF.md`.

### 3.3 UI

- Lectionary selector in settings drawer: BAS / RCL
- Track selector (for RCL): Semicontinuous / Complementary
- Season bounds: BAS bounds remain in force for seasonal colouring; RCL uses same Christian year so no separate bounds file needed
- Store selections in `localStorage`

---

## Phase 4 — BAS Extension & Long-term

### 4.1 Book of Alternative Services extension

- Extract additional BAS office forms (alternate Evening Prayer orders, special occasions)
- Extract the full Occasional Prayers section (BAS pp. 660+)
- Add BAS canticle options not currently in PWC
- Expand `offices.json` with a `bas/` sub-namespace

### 4.2 French BAS forms

BAS has French editions. Long-term internationalization goal. Requires both a translation of the liturgical forms and French-language lectionary data.

### 4.3 iCal / RSS feed

Generate machine-readable daily office readings for calendar integration. Could be a static build artifact (one ics per month) or a lightweight edge function.

### 4.4 Go CLI parity

Ensure the CLI renders all features available in the web app, including seasonal collect toggle, alternate observance, and optional lessons. Currently the CLI shares the data layer but may not render all alternatives.

---

## Phase 5 — Native Apps (iOS & Android)

PWC is being developed as an official Anglican Church of Canada distributed app. Distribution via the App Store and Google Play requires native (or hybrid-native) packaging. This is a large project; design decisions and technical choices need to be made before implementation begins.

### 5.1 Technical approach (decision required)

Three viable paths:

**Capacitor (recommended starting point)** — wraps the existing web SPA in a native shell with access to native APIs. Fastest path given the existing vanilla JS app. Capacitor is maintained by Ionic and widely used for exactly this pattern. The web app runs unchanged; native features (push notifications, offline storage, app icons) are layered on top.

**React Native / Flutter** — full rewrite of the frontend in a cross-platform framework. Produces better native UI fidelity but requires rewriting `app.js` (~1400 lines) in a new paradigm. Only justified if significant native UI is required or Capacitor proves inadequate.

**Progressive Web App (PWA) + App Store submission** — iOS now allows PWAs in the App Store via WKWebView wrappers. The service worker and offline support already in place make PWC a strong PWA candidate. Lowest effort but limited access to native APIs.

### 5.2 Scope

- Offline-first: all data pre-bundled or aggressively cached (lectionary, offices, psalter)
- Push notifications: optional daily reminder at configurable time
- App Store (Apple) and Google Play distribution
- Distribution managed by/through the Anglican Church of Canada

### 5.3 Prerequisites before native work begins

- ACC licence resolved (Phase 2.6) — needed to distribute data
- Year A lectionary complete (Phase 2.1) — app should launch with full coverage
- RCL daily rights resolved (Phase 3) — should be in-app at launch if possible
- CONTRIBUTING.md and architecture docs complete — native work may involve new contributors
- Bug 6 and Bug 7 fixes committed — no known regressions before a public release

### 5.4 Milestones (to be detailed in HANDOFF.md when work begins)

1. Technical spike: Capacitor proof-of-concept with existing web app
2. Evaluate result (offline behaviour, performance, native feel)
3. If adequate: add native features (notifications, icon, splash screen)
4. App Store and Google Play submissions
5. ACC distribution agreement and listing

---

## Metrics & Correctness Goals

By the end of Phase 1, the following should be true:

- [x] `make test` passes with zero failures
- [x] `make test-full` passes (every day in the lectionary year has a valid office)
- [x] Python tools have >80% unit test coverage on parsing functions (53 tests, 2026-06-07)
- [x] Season bounds validated automatically on every `convert_lectionary.py` run
- [x] Go and JS season logic produce identical output for all dates in a golden table
- [ ] All lectionary notes audited and properly typed/suppressed
- [x] `CANTICLE_SOURCE` verified complete

By the end of Phase 2:

- [ ] Year A lectionary data integrated
- [x] Print mode functional
- [ ] Occasional Prayers extracted
- [ ] ACC licence inquiry sent
