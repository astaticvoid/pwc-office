# PWC — Bug Tracker

_Last updated: 2026-06-07 (11 bugs closed)_

Severity scale: **P0** = data corruption / silent wrong output �� **P1** = incorrect content shown to user · **P2** = missing content / broken feature · **P3** = UX issue / cosmetic

---

## Open

### P0 — Silent wrong output / data integrity

**BUG-02: Season bounds detection uses brittle keyword matching**  
`convert_lectionary.py:detect_bounds()` scans CSV name strings for phrases like "fifth sunday in lent" and "baptism of the lord". If the ACC changes wording in a future CSV, bounds will be silently wrong. The missing-key assertion (added 2026-06-06) catches the failure loudly, but does not prevent it.  
_Fix:_ Maintain a canonical expected-wording list per key; warn when fuzzy-matched rather than exact-matched.  
_Files:_ `tools/convert_lectionary.py:detect_bounds`

---

### P1 — Incorrect content shown to user

**BUG-04: Collect 668 hardcoded; other Occasional Prayers not extracted**  
Occasional Prayers (BAS pp. 660+) are not extracted. The app hardcodes collect 668 for late-October dates that reference it. Any other date referencing an Occasional Prayer will silently show nothing or display the wrong collect.  
_Fix:_ Extract Occasional Prayers section from BAS PDF; add to `collects.json`.  
_Blocker:_ Requires the BAS PDF.  
_Files:_ `tools/extract_collects.py`, `data/collects.json`

**BUG-05: Cross-reference and garbled notes not fully suppressed**  
`SUPPRESS_NOTE_TYPES` covers all typed cross-refs (`ember_crossref`, `rogation_crossref`, `precedence_rule`, `reconciliation_propers`). One garbled parsing artifact (2026-06-03) requires a manual `CLEAR_NOTES` entry. Additional notes may exist in earlier years not yet audited.  
_Fix:_ Complete the `NOTE_TYPES` audit for all dates 2016–2026; fix any garbled entries upstream in `convert_lectionary.py`.  
_Files:_ `tools/convert_lectionary.py:CLEAR_NOTES`, `tools/convert_lectionary.py:NOTE_TYPES`

**BUG-06: Year A lectionary not available**  
Coverage ends at late December 2026. Navigation is blocked at the boundary with a "Readings not yet available / Year A in preparation" message, and the next-arrow is disabled. Year A (Advent 2026+) is not yet extracted.  
_Fix:_ Extract/convert Year A CSV when ACC publishes it.  
_Blocker:_ Waiting on ACC to publish Year A CSV.  
_Files:_ `web/app.js:render`, `tools/scrape_lectionary.py`

---

### P2 — Missing content / broken feature

**BUG-09: No offline download UI**  
The service worker pre-caches 3 upcoming months on idle, but there is no user-visible control to download a larger span. Users who want fully offline use for a retreat or travel have no way to pre-fetch ahead of time.  
_Fix:_ Add settings panel with "Download for offline" action using `Cache.put()` with progress.  
_Files:_ `web/app.js`, `web/sw.js`

**BUG-13: No first-run preference wizard**  
On first visit, users see NRSVUE by default with no prompt. KJV is available but undiscoverable from the settings sheet.  
_Fix:_ One-time inline banner on first visit: choose translation + optionally theme.  
_Files:_ `web/app.js`, `web/index.html`

---

### P3 — UX / cosmetic

**BUG-14: EP `opening_responses` duplicated in JSON across 7 seasonal offices**  
All 7 seasonal EP offices (`advent-ep` through `pentecost-ep`) contain identical `opening_responses` data. This is cosmetic JSON bloat; functionally harmless.  
_Fix:_ Extend `_dedup_shared()` to detect and deduplicate identical section-level arrays across offices.  
_Files:_ `data/offices.json`, `tools/extract_offices.py:_dedup_shared`

**BUG-15: Lectionary notes audit incomplete**  
Some `notes` fields contain book cross-references ("see entry for…") that are meaningless in the app. `NOTE_TYPES` has been set for all 2026 dates but earlier years (2016–2025) have not been fully audited.  
_Fix:_ Run audit script over all lectionary JSON; add `crossref` type for any remaining untyped cross-references.  
_Files:_ `tools/convert_lectionary.py:NOTE_TYPES`, `web/app.js:SUPPRESS_NOTE_TYPES`

---

## Closed

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
