# PWC — Bug Tracker

_Last updated: 2026-06-14 (23 bugs closed)_

Severity scale: **P0** = data corruption / silent wrong output �� **P1** = incorrect content shown to user · **P2** = missing content / broken feature · **P3** = UX issue / cosmetic

---

## Open

### P1 — Incorrect content shown to user

**BUG-06: 2027 BAS lectionary not yet available**  
Coverage ends at late December 2026. Navigation shows "Readings not yet available" at the boundary; next-arrow disabled. Not a mobile beta blocker — will be added when ACC publishes the 2027 data.  
_Fix:_ When ACC provides the next lectionary CSV, add to `sources/` and run `make extract`.  
_Files:_ `web/app.js:render`, `tools/convert_lectionary.py`

---

---

## Closed

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
