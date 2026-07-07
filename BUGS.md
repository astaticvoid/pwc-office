# PWC — Bug Tracker

_Last updated: 2026-07-05 (23 bugs closed; 9 opened from field-trial observations and audit — see docs/ASSESSMENT-2026-07.md)_

Severity scale: **P0** = data corruption / silent wrong output · **P1** = incorrect content shown to user · **P2** = missing content / broken feature · **P3** = UX issue / cosmetic

---

## Field observations — inbox

_Drop dated observations from real use here; they get triaged into numbered bugs next session. (June 21/23/24 observations triaged 2026-07-05 → BUG-25…31.)_

_(empty)_

---

## Open

### P1 — Incorrect content shown to user

**BUG-06: 2027 BAS lectionary not yet available**  
Coverage ends at late December 2026. Navigation shows "Readings not yet available" at the boundary; next-arrow disabled. Not a mobile beta blocker — will be added when ACC publishes the 2027 data.  
_Fix:_ When ACC provides the next lectionary CSV, add to `sources/` and run `make extract`.  
_Files:_ `web/app.js:render`, `tools/convert_lectionary.py`

### P2 — Missing content / broken feature

### P3 — UX / cosmetic

**BUG-29: Collect prose renders with PDF column-width line breaks**  
Field-reported 2026-06-21 ("Seasonal collection has weird line breaks"). Extraction preserves hard wraps from the PDF column (`"…and who\nlives and reigns…"` — mid-clause, so typographic not semantic); `.seg-leader` and `.collect-text` use `white-space: pre-wrap`, so every viewport ≠ PDF column width shows ragged breaks. Affects `seasonal_collects` leader segments in `offices.json` AND `collects.json` (194 lines end mid-clause).  
_Fix:_ HANDOFF.md Batch 18 Fix G (reflow prose at extraction).  
_Files:_ `tools/extract_offices.py`, `tools/extract_collects.py`

**BUG-30: Litany placeholder "N" renders as bare literal**  
Field-reported 2026-06-23 ("N our Bishop"). Data is faithful to the PDF ("May N our bishop…") but the printed book italicises *N*; the app shows a plain "N" that reads as a typo. Exactly 2 standalone-N occurrences in `offices.json`, so a render-level italic is safe.  
_Fix:_ HANDOFF.md Batch 18 Fix H.  
_Files:_ `web/render.js`

**BUG-31: MP→EP default switches at 17:00; should be 15:00**  
Field-reported 2026-06-24 ("Eve prayer should start at 3pm"). `defaultOffice()` at `web/app.js:26` uses `getHours() >= 17`. Evening Prayer (and eve-of-feast observance) should be the default from mid-afternoon.  
_Fix:_ HANDOFF.md Batch 18 Fix I.  
_Files:_ `web/app.js:26`

---

---

## Closed

**BUG-33: "O Antiphon" emitted as a pseudo-lesson on Dec 17–23 evenings**  
Fixed 2026-07-06 (Batch 18 Fix F). `parse_single_office` now drops any lesson whose citation is exactly "O Antiphon" (RE_O_ANTIPHON), alongside the existing Coll filter. Removed 14 pseudo-lessons across 2025-12 and 2026-12; the antiphons remain as typed `o_antiphon` notes. 1 new pytest.  
_Files:_ `tools/convert_lectionary.py`, `tools/tests/test_convert_lectionary.py`

**BUG-32: 2026-09-27 EP first lesson is a merged citation**  
Fixed 2026-07-06 (Batch 18 Fix E). Added `LESSON_FIXES[("2026-09-27","evening")]` splitting `"(2 Kgs 17:1-18), Mt 13:44-52"` into an optional 2 Kgs citation + required Mt (CSV confirmed only two items). Verified after re-extract.  
_Files:_ `tools/convert_lectionary.py`

**BUG-28: `lessons_pick` unimplemented — "two of the following three readings" shows all 3 with no rubric**  
Fixed 2026-07-06 (Batch 18 Fix D). Added `lessonsPickText`/`lessonsPickRubricHtml` to `render.js` (number-word generated, e.g. "Two of the following three readings are read."). Wired into `proclamationHtml` (app), `cli/book.js`, and `cli/office.js` — emitted before the first lesson when `lessons_pick < lessons.length`. Uses `seg-rubric` (load-bearing, NOT book-only) since the app has no pick-interaction. Render-only, no data change (12 files / 21 occurrences unchanged). 3 new Vitest cases.  
_Files:_ `web/render.js`, `web/app.js`, `cli/book.js`, `cli/office.js`, `tests/unit/render.test.js`

**BUG-27: Special-day propers Collect never surfaced**  
Fixed 2026-07-06 (Batch 18 Fix C). `convert_lectionary.py` now extracts the "Collect of the Day" from the propers `eucharist` blob (RE_COLLECT_OF_DAY) for any day whose offices referenced it via "Coll above/below", and attaches it as a day-level `collect_inline: {name, text}`. A "Coll below" eve resolves the collect from the *next* day's blob (2026-06-20 EP → 2026-06-21 propers, verified). `collectToggleHtml()` renders `collect_inline` as the Collect of the Day when no BAS collect ref exists; `cli/office.js` prints it too. Scope held to the collect only — a general propers/`eucharist` surface, and a consumer for the `observances` field, remain parked (ASSESSMENT §6).  
_Files:_ `tools/convert_lectionary.py`, `web/app.js`, `cli/office.js`

**BUG-26: "Coll above"/"Coll below" rendered as lesson citations**  
Fixed 2026-07-05 (Batch 18 Fix B). `parse_single_office` now drops any lesson matching `^Coll (above|below)\b` (RE_COLL_REF) before it reaches the lessons list. Removed the pseudo-lessons from 2026-06-20 EP and 2026-06-21 MP/EP; the collect they point at is surfaced by Fix C (BUG-27). 2 new pytest tests.  
_Files:_ `tools/convert_lectionary.py`, `tools/tests/test_convert_lectionary.py`

**BUG-25: "Holy One" divine title lowercased in 22 litany responses (incl. wrong BUG-18 "fix")**  
Fixed 2026-07-05 (Batch 18 Fix A). Added `holy one → Holy One` to `_DIVINE_FIXES` (response segments only); deleted BUG-18's wrong MP lowercasing tuple from `_TEXT_PATCHES` (its four EP continuation tuples stand — pdftotext-verified). Re-extracted; all 22 instances now "Holy One" (grep counts 8/4/5/5, zero lowercase). 2 new pytest tests. Root cause and lesson recorded in `docs/CORRECTNESS.md` (BUG-18 note).  
_Files:_ `tools/extract_offices.py`, `tools/tests/test_extract_offices.py`

**BUG-02: Season bounds detection uses brittle keyword matching**  
Fixed 2026-06-14. Added `CANONICAL_BOUNDS_PHRASES` dict; `detect_bounds()` now matches exactly first and emits a `sys.stderr` warning on fuzzy fallback. 4 new pytest tests added. 147 total tool tests passing.  
_Commits:_ `tools/convert_lectionary.py`, `tools/tests/`

**BUG-09: No offline download UI**  
Closed 2026-06-14. Won't fix for Synod private beta — SW auto-caches upcoming months; manual download UI not needed at this stage.

**BUG-04: Occasional Prayer alternate collect not displayed**  
Closed 2026-06-14. Already fixed — `collectSecondaryPage()` and `collectToggleHtml()` in `app.js` already parse "or N, PAGE" refs and display the Occasional Prayer as an additional tab. Data (`collects.json`) and UI both implemented. Bug description was stale.

**BUG-14: EP `opening_responses` duplicated in JSON across 7 seasonal offices**  
Closed 2026-06-14. Fixed as part of BUG-23 — `_dedup_shared()` extended; all 7 seasonal EP forms now reference `_shared.opening_responses_ep_seasonal`.

**BUG-15: Lectionary notes audit incomplete (pre-2025 years)**  
Closed 2026-06-14. Won't fix — pre-2025 lectionary data removed from the app. Rolling window starts at 2025-06.

**BUG-05: Cross-reference notes audit (pre-2025 years)**  
Closed 2026-06-14. Won't fix — same reason as BUG-15. Pre-2025 data no longer exists.

**BUG-13: No first-run preference wizard**  
Closed 2026-06-14. Won't fix — not applicable. NRSVUE is the standard for this Synod private beta; no translation choice needed on first launch.

**BUG-24: Node CLI silently drops Psalm on feast days with `psalm_sets`**  
Fixed 2026-06-14. Feast-day morning psalms use `psalm_sets` (array of arrays); CLI now falls back to `psalm_sets?.[0]` when `psalms` is absent.  
_Commits:_ `cli/office.js`

**BUG-23: All 7 seasonal EP forms silently missing Opening Responses**  
Fixed 2026-06-14. BUG-14's deduplication stored `opening_responses` as a shared ref dict; `app.js` `.length` check returned undefined → falsy → section skipped. Added shared-ref resolution in `app.js` and `cli/office.js`. Added render-level Vitest tests and pytest regression for all shared-ref fields. All 30 forms now pass correctness audit.  
_Commits:_ `web/app.js`, `cli/office.js`, `tests/unit/render.test.js`, `tools/tests/test_form_completeness.py`

**BUG-22: Service worker caches stale `index.html` on deploy → blank page**  
Fixed 2026-06-14. Removed `self.skipWaiting()`; removed `'/'` from SHELL precache; SW never intercepts index.html; removed `controllerchange` reload from `app.js`.  
_Commits:_ `web/sw.js`, `web/app.js`

**BUG-14: EP `opening_responses` duplicated in JSON across 7 seasonal offices**  
Fixed 2026-06-14. Extended `_dedup_shared()` to detect and deduplicate identical section-level arrays; all 7 seasonal EP forms now reference `_shared.opening_responses_ep_seasonal`.  
_Commits:_ `tools/normalize_offices.py`, `data/offices.json`, `tools/extract_manifest.json`

**BUG-21: Node CLI uses wrong lectionary field names**  
Fixed 2026-06-14. Updated `cli/office.js` to use `psalms`/`lessons` arrays and call `lessonHtml()` per lesson.  
_Commits:_ `cli/office.js`

**BUG-19: `normalize_offices.py` breaks reading response (all forms) and Lord's Prayer (ordinary-time), and crashes Go CLI**  
Fixed 2026-06-14. Removed lords_prayer_ordinary normalization block from `normalize_offices.py`; restored `lords_prayer_intro` as inline array in all ordinary-time forms (fixes Go CLI crash and Lord's Prayer rendering). Added shared-ref resolution in `lessonHtml()` / `render.js` before `renderAlternatives()` call (fixes reading response on all forms). Re-extracted data. Added pytest form completeness test and Playwright regression tests.  
_Commits:_ `tools/normalize_offices.py`, `web/render.js`, `data/offices.json`, `tools/tests/test_form_completeness.py`, `tests/e2e/office.spec.js`

**BUG-20: "Morning Prayer continues" shown in Evening Prayer**  
Fixed 2026-06-07. `_shared.doxology` segments contained hardcoded "Morning Prayer continues with…" rubrics (PDF artifact). These showed 3× verbatim in EP. Broadened `SKIP_RUBRICS` from `continues with the Lit` to `continues with` so all such navigational rubrics from raw data are stripped. Transitions are emitted programmatically with the correct office name at app.js:1080 and 1096.  
_Commits:_ `web/app.js`

**BUG-18: Wednesday litany response capitalisation**  
Fixed 2026-06-07. `_fix_casing` was uppercasing responses that are intentionally lowercase in the PDF. Added `_TEXT_PATCHES` table and `_apply_text_patches()` to `extract_offices.py`; Wednesday MP (×8) and EP (×4) responses corrected. Noted in CORRECTNESS.md.  
_Commits:_ `tools/extract_offices.py`, `CORRECTNESS.md`

**BUG-12: Python extraction tools had no unit tests**  
Fixed 2026-06-07. Created `tools/tests/` with 53 pytest tests covering `parse_name_meta`, `parse_psalm_field`, `parse_lesson`, `detect_bounds`, `_char_type`, `_fix_casing`, `_group_alternatives`. Added `make test-tools` target.  
_Commits:_ `tools/tests/`, `Makefile`

**BUG-11: `validate_lectionary.py` not wired into make**  
Fixed 2026-06-07. Added `make validate` target.  
_Commits:_ `Makefile`

**BUG-10: `_BLOCK_SEP_ONLY` consumed canticle doxology intro rubric**  
Fixed 2026-06-07. `_group_alternatives` now emits the canticle doxology intro as a plain rubric segment before starting the unnamed groups. Removed the `_dedup_shared` workaround that re-inserted hardcoded text.  
_Commits:_ `tools/extract_offices.py`

**BUG-07: Lectionary notes not rendered by type**  
Fixed 2026-06-07. O Antiphons render as a liturgical block with Latin title accent and italic body. Civil day and week-of-prayer notes render as muted informational rows with bold day name. Other types use the existing expand-on-read behaviour.  
_Commits:_ `web/app.js`, `web/office.css`

**BUG-01: JS/Go season logic could diverge silently**  
Fixed 2026-06-07. Added `TestFormSeasonOf` (24 boundary dates, `season_test.go`) using `fullBounds2026` mirroring `data/season_bounds.json`. Added 11 Playwright `data-season` checks for the same dates. Any future divergence fails whichever side changed.  
_Commits:_ `season_test.go`, `tests/e2e/office.spec.js`

**BUG-08: Print mode showed only active alt panel**  
Fixed 2026-06-06. Added `@media print` rules: `.alt-panel-hidden { display: block !important }`, tabs hidden, interactive chrome suppressed.  
_Commits:_ `web/office.css`

**BUG-17: CANTICLE_SOURCE gaps were silent**  
Fixed 2026-06-06. Added `console.warn` in `renderAlternatives()` when a named canticle label has no entry in `CANTICLE_SOURCE`.  
_Commits:_ `web/app.js`

**BUG-16: `boneyard/` directory in repo root**  
Removed 2026-06-06. Was local-only (not git-tracked).

**BUG-03: READING_RESPONSE fallback used seasonal wording**  
Fixed 2026-06-06. Group III changed to ordinary-time form. Added `console.warn` for future regression visibility.  
_Commits:_ `web/app.js`

**BUG-02: Season bounds detection had no validation**  
Fixed 2026-06-06. Added assertion after `detect_bounds()` — exits loudly if any of 8 required keys are missing.  
_Commits:_ `tools/convert_lectionary.py`
