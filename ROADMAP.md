# PWC — Project Roadmap

_Last updated: 2026-06-07_

This roadmap organises work into four phases with a rough priority ordering within each. Items are linked to BUGS.md where a known defect is involved.

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

### 1.3 Code hygiene

✅ **Remove `boneyard/`** (BUGS.md BUG-16, removed 2026-06-06)

✅ **Add startup CANTICLE_SOURCE completeness check** (BUGS.md BUG-17, fixed 2026-06-06)  
`renderAlternatives()` emits `console.warn` when a named canticle label has no entry in `CANTICLE_SOURCE`.

**JSDoc / module annotation**  
`app.js` is ~61 KB of dense vanilla JS. Add JSDoc comments to the major function clusters and section headers to make maintenance tractable.

**CONTRIBUTING.md**  
Document: how to set up the dev environment, how to re-extract data (pipeline order), how to run all test tiers, how to deploy, and the copyright constraints.

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

See DESIGN.md §8 for the architectural requirements.

### 3.1 Data model refactoring

- Namespace data paths: `data/<lectionary-id>/lectionary/YYYY-MM.json`
- Add `lectionary_id` to `season_bounds.json`
- Abstract `detect_bounds()` behind a source-agnostic interface
- Update app `fetchDay()` to accept `lectionaryId`

### 3.2 RCL support (highest priority)

The Revised Common Lectionary is freely available and used by most Anglican, Lutheran, Methodist, and Presbyterian churches. Implementation path:
1. Find or build a machine-readable RCL data source
2. Write `convert_rcl.py` to produce the same monthly JSON format
3. Add `rcl/` namespace in data
4. Wire into app as a third lectionary option (alongside BAS Morning / BAS Evening)

### 3.3 BCP 1979 / BCP 2019

ECUSA (BCP 1979) and ACNA (BCP 2019) have structured lectionary data. Both use the same JSON schema target. Implementation is independent of RCL; can be parallelized once the data-path refactoring is complete.

### 3.4 UI

- Lectionary selector in nav (or settings drawer): BAS / RCL / BCP 1979 / BCP 2019
- Store selection in `localStorage`
- Season bounds are lectionary-specific; load the correct `season_bounds.json` per selection

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
