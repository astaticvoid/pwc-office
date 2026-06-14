# PWC — Handoff

_Updated: 2026-06-13_

Active handoff between Cowork (planning) and Claude Code (implementation). Cowork writes specs here; Claude Code implements and marks done.

---

## Completed this session (2026-06-13)

All "Ready for Code" items implemented and committed. Summary for Cowork:

**Implemented:**
- `tools/fetch_sources.py` + `make fetch-sources` / `make extract` pipeline targets (P1)
- Rolling 12-month lectionary window in `convert_lectionary.py --window` + date picker `min` update + `full_test.go` date range computed dynamically (P2)
- Bug 6: gloria/doxology rendered once after full psalm set in "All" panel, not after each psalm (P2)
- Bug 7: 3-tab collect layout for ordinary time (Collect of the Day / Seasonal I / Seasonal II); rubric bleed stripped (P2)
- LLM test removal: deleted `e2e/llm_test.go`, stripped `evalOffice`/`reportEval` calls from smoke and seasonal tests (P2)
- Golden snapshot tests: `e2e/golden_test.go` (build tag `e2e_full`) + `make update-golden` target; golden files gitignored (copyrighted content) (P2)
- ARIA tab roles + keyboard navigation: `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls`, ArrowLeft/ArrowRight nav in `renderAlternatives()` and `activateTab()` (P2)
- `tools/normalize_offices.py`: normalizes repeated blocks into `_shared` (P3)
- Patch system: `tools/validate_patches.py` + `tools/apply_patches.py` + `data/patches.json` with 14 BUG-18 entries (P3)
- JSDoc on all priority function clusters in `web/app.js` (P3)
- `CONTRIBUTING.md`: dev setup, pipeline, test tiers, deploy, copyright notes (P3)

**Surprises / things Cowork should know:**

1. **Golden files are gitignored.** `e2e/testdata/` is gitignored because golden snapshot files contain rendered liturgical text derived from copyrighted source data. The flow is: run `make extract` locally, then `make test-full` once to generate goldens, then subsequent runs catch regressions. CI can't run these without the data files.

2. **`data/patches.json` is now committed** (added `!data/patches.json` to `.gitignore`). The file contains only short text snippets used for verification. The 14 BUG-18 patches have `old` values = what `extract_offices.py` would produce (uppercase), `new` = the corrected lowercase. Validate will fail on the currently-patched local data; it's designed to run after a fresh extraction.

3. **Psalm "All" panel**: Bug 6 fix only touches the `allHtml` loop in both `psalmSets` and plain `psalms` branches. Individual set panels (e.g. Set 1, Set 2) still call `psalmWithGloria` since a set can contain 1–2 psalms; if a set has multiple psalms, it would still show gloria after each. Cowork may want to extend the fix to individual set panels too.

4. **ARIA tabs scope**: The spec said "one function change in `renderAlternatives()`". ARIA attributes were added there; the inline tab builders in `psalmHtml()` and `collectToggleHtml()` do NOT yet have ARIA. Keyboard nav works for the alternatives tab system (doxology, canticle, reading response, etc.) but not for psalm or collect tabs.

5. **3-tab collect**: The `stateKey` `'pwc-alt-collect'` now accepts values 0/1/2 for ordinary time (was 0/1). Users with the old `1` stored may see "Seasonal I" selected on first load; harmless, just worth knowing.

6. **`make fetch-sources`** currently has no test coverage — it downloads from external URLs which can't be tested offline. Consider a `--dry-run` flag or mock test if CI coverage matters.

---

## Immediate: git housekeeping (do this first)

```bash
git rm CORRECTNESS.md UX_AUDIT.md
git add .gitignore ROADMAP.md CLAUDE.md docs/
git commit -m "chore: move design docs to docs/, track CLAUDE.md, gitignore redesign/"
```

---

## Ready for Code

### ✅ Source fetch + extract pipeline (P1)

**Goal**: a developer can go from a clean clone to a running app with two commands: `make fetch-sources` then `make extract`. Currently both phases require manual steps and separate tool invocations.

**`tools/fetch_sources.py`** (new, replaces the existing `scrape_lectionary.py` call as the single entry point):

All sources are publicly available and can be downloaded with a single script:

```python
SOURCES = {
    # ACC liturgical PDFs (anglican.ca)
    'sources/pray-without-ceasing.pdf': 'https://www.anglican.ca/wp-content/uploads/pray-without-ceasing.pdf',
    'sources/BAS.pdf':                  'https://www.anglican.ca/wp-content/uploads/BAS.pdf',
    'sources/For-All-The-Saints.pdf':   'https://www.anglican.ca/wp-content/uploads/For-All-The-Saints.pdf',
    # RCL Daily Readings (commontexts.org)
    'sources/rcl/rcl_year_a.rtf':          'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearA.rtf',
    'sources/rcl/rcl_year_b.rtf':          'https://www.commontexts.org/wp-content/uploads/2015/11/dailyreadingsB.rtf',
    'sources/rcl/rcl_year_c.doc':          'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearC.doc',
    'sources/rcl/rcl_year_a_expanded.pdf': 'https://www.commontexts.org/wp-content/uploads/2025/12/RCL-Expanded-Daily-Readings-Year-A.pdf',
}
```

- Skip files that already exist unless `--force` is passed
- Rate-limit to 1 req/s; print progress
- The BAS CSV is handled separately by `scrape_lectionary.py` (needs ETag/conditional logic for updates)

**New Makefile targets:**

```makefile
# Download all source files. Everything is publicly available — no manual steps.
fetch-sources:
	python3 tools/fetch_sources.py
	python3 tools/scrape_lectionary.py

# Run the full extraction pipeline after sources are present.
extract:
	python3 tools/extract_offices.py
	python3 tools/extract_psalter.py
	python3 tools/extract_collects.py
	python3 tools/convert_lectionary.py --accept
	python3 tools/validate_lectionary.py
```

Also update the `.PHONY` line to include `fetch-sources extract`.

**Full workflow from clean clone:**
```bash
make fetch-sources   # ~30s — downloads all source files
make extract         # ~2min — runs full extraction pipeline
make build           # assembles dist/
make deploy BUCKET=... CF_DISTRIBUTION_ID=...
```

**Update CONTRIBUTING.md** once written: document this workflow. Note that all `sources/` and `data/` output is gitignored (copyrighted content).

**Commit order:**
1. `tools: add fetch_sources.py (downloads all source files from public URLs)`
2. `make: add fetch-sources and extract pipeline targets`

---

### ✅ Trim lectionary coverage to a rolling window (P2)

**What:** The current data pipeline generates `data/lectionary/YYYY-MM.json` files going back to 2016 (~120 monthly files). Nobody looks up a daily office from 2017. All those files are included in `dist/` and could be cached by the service worker, bloating the build for no user benefit.

**Decision:** Keep a rolling window of **12 months back + current + 12 months forward** (i.e. ~24–25 files at any time). For the current moment (mid-2026) that means approximately Jan 2025 – Dec 2026.

**Changes required:**

1. **`tools/scrape_lectionary.py`**: Default `--years` range already limits downloads; no change needed — old CSVs just stay in `sources/` (harmless).

2. **`tools/convert_lectionary.py`**: Add a `--window N` flag (default `12`) that trims output to only emit monthly JSON files within N months of today. Existing files outside the window are deleted from `data/lectionary/`.

3. **`make extract`**: Pass `--window 12` to `convert_lectionary.py`:
   ```makefile
   extract:
       python3 tools/extract_offices.py
       python3 tools/extract_psalter.py
       python3 tools/extract_collects.py
       python3 tools/convert_lectionary.py --accept --window 12
       python3 tools/validate_lectionary.py
   ```

4. **`web/app.js` date picker**: Update the `min` attribute on `#nav-date-picker` to 12 months ago (computed dynamically, same as `todayStr()` logic). Currently it's probably set to a hardcoded 2016 date.

5. **`e2e/full_test.go`**: Update `start` and `end` to be computed from the current year rather than hardcoded 2026. This makes the test meaningful on every re-run.

**Test:** `make build` — verify `dist/data/lectionary/` contains only files within the window. Check that navigating to a date > 12 months ago shows the "outside coverage" message.

**Commit message:** `data: trim lectionary to rolling 12-month window; update date picker min`

---

### ✅ Bug 6: Gloria/doxology after full psalm set, not after each psalm (P2)

**What:** `psalmWithGloria()` is called once per psalm, so when multiple psalms are displayed in the "all psalms" panel, each psalm gets its own gloria rubric and doxology alternatives block. Liturgically the doxology is said once at the end of the complete psalm set.

**Where:** `psalmHtml()` in `web/app.js`. The two `allHtml` loops (one in the `psalm_sets` branch, one in the plain `psalms` branch) call `psalmWithGloria(p, shared)` for each psalm.

**Fix:**

Extract a helper:
```js
function gloriaHtml(shared) {
  if (!shared || !shared.doxology) return '';
  return `<p class="seg-rubric">At the end of the Psalm one of the following may be said or sung.</p>`
       + `<div class="psalm-gloria">${renderAlternatives(shared.doxology, shared, 'doxology')}</div>`;
}
```

In the "all psalms" panels (both branches), replace:
```js
allFlat.forEach(p => { allHtml += psalmWithGloria(p, shared); });
// and:
psalms.forEach(p => { allHtml += psalmWithGloria(p, shared); });
```
with:
```js
allFlat.forEach(p => { allHtml += psalmPlaceholder(p); });
allHtml += gloriaHtml(shared);
// and:
psalms.forEach(p => { allHtml += psalmPlaceholder(p); });
allHtml += gloriaHtml(shared);
```

Individual psalm panels (single-psalm tabs) keep `psalmWithGloria` unchanged — the gloria is correct there since only one psalm is displayed.

**Test:** Load any weekday office with multiple psalms, switch to "All" panel — gloria should appear once at the end, not after each psalm. `make test-web`.

**Commit message:** `fix(psalm): doxology rendered once after full psalm set, not after each psalm`

---

### ✅ Bug 7: Collect tabs — 3 not 2; strip rubric bleed (P2)

**What:** Ordinary time office forms have two seasonal collect alternatives (I and II) stored as an `alternatives` segment in `seasonal_collects`. Currently `collectToggleHtml()` wraps both inside a single "Seasonal Collect" tab, producing 2 outer tabs with a nested I/II toggle inside. Should be 3 flat tabs: "Collect of the Day", "Seasonal I", "Seasonal II".

Also: Group I's segments contain a rubric "Either the Collect of the Day or one of the following collects may be said or sung." and Group II's segments end with a "the Lord's Prayer" rubric marker — both are structural markers that bleed through as visible text inside the tabs.

**Data structure** (ordinary time forms only):
```json
// form.seasonal_collects:
[{
  "type": "alternatives",
  "groups": [
    {"label": "I", "segments": [
      {"type": "rubric", "text": "Either the Collect of the Day or one of the following..."},
      {"type": "leader", "text": "<collect text>"}
    ]},
    {"label": "II", "segments": [
      {"type": "leader", "text": "<collect text>"},
      {"type": "rubric", "text": "the Lord’s Prayer"}
    ]}
  ]
}]
```

Seasonal forms (Advent, Lent, etc.) have rubric-delimited week collections — those produce a single seasonal collect and keep 2 tabs. Only the `alternatives` case needs the 3-tab expansion.

**Fix in `collectToggleHtml()`:**

After computing `seasonalContent`, detect the single-alternatives case:
```js
const isSingleAlt = seasonalContent.length === 1 && seasonalContent[0].type === 'alternatives';
```

If `isSingleAlt && hasDaily`:
- Extract `altGroups = seasonalContent[0].groups`
- For each group, filter segments: strip rubrics matching `SC_HEADER` ("Either the Collect of the Day…") and `SC_FOOTER` ("the Lord's Prayer")
- Build tabs: `tab('Collect of the Day', 0)` + `tab('Seasonal ' + g.label, i+1)` for each group
- Build panels: `panel(collectHtml(collects, collectRef), 0)` + per-group `panel(renderSegments(cleanedSegs, shared), i+1)`
- `stateKey` stays `'pwc-alt-collect'` — valid values now 0/1/2

If `isSingleAlt && !hasDaily` (no daily collect assigned), render as flat 2-tab "Seasonal I" / "Seasonal II" with no "Collect of the Day" tab.

All other cases (non-alternatives seasonal content) keep the existing 2-tab logic.

**Test:** Load any ordinary time office. The collect section should show 3 tabs with no rubric text inside any panel. Load any seasonal office (Advent, Lent) — should still show 2 tabs. `make test-web`.

**Commit message:** `fix(collect): 3-tab seasonal collect for ordinary time; strip rubric bleed`

---

### ✅ LLM test removal (P2)

**What:** `e2e/llm_test.go` calls the `claude` CLI via `exec.Command` to evaluate rendered offices. This creates a hard runtime dependency on Claude Code being installed and authenticated. Replace LLM evaluation with deterministic golden-file snapshot tests.

**Keep:** `checkStructure()` in `helpers_test.go` and `verifyReadings()` in `lectionary_fetch_test.go` — these are fast, deterministic, and valuable.

**Remove:** `e2e/llm_test.go` entirely. Also remove `evalOffice()` and `reportEval()` calls from `smoke_test.go` and `seasonal_test.go`.

**Add: golden snapshot tests** in a new `e2e/golden_test.go` (build tag `e2e_full`):
- For each of the 4 smoke dates and ~8 seasonal dates, render the office and compare against a committed golden file
- Golden files live in `e2e/testdata/golden/<date>-<mp|ep>.md`
- On first run (no golden file): write the file and pass
- On subsequent runs: diff against golden; fail if changed
- Add a `make update-golden` target: `go test ./e2e/... -tags e2e_full -run TestGolden -update`

**Build tags after change:**
- `e2e_smoke` / `e2e_seasonal` still run `checkStructure` + `verifyReadings` (fast, no LLM)
- `e2e_full` runs structural check on all lectionary dates + golden snapshot comparison

**Commit order:**
1. `test: remove LLM evaluation from e2e suite (delete llm_test.go)`
2. `test: add golden snapshot tests for office rendering (e2e_full)`

---

### ✅ ARIA tab roles (UX-15, P2)

Full spec in `UX_AUDIT.md`. One function change in `web/app.js`.

**What:** Add `role="tablist"` / `role="tab"` / `role="tabpanel"` + `aria-selected` + `aria-controls` to the alternatives tab system. Add left/right arrow navigation within each tablist group.

**Where:** `renderAlternatives()` in `web/app.js`. The `.alt-tabs` container and each `.alt-tab` button and `.alt-panel` div.

**Test:** `make test-web` — Playwright suite. May need to add a new a11y test for tab keyboard nav.

**Commit message:** `fix(a11y): ARIA tab roles and keyboard navigation for alternatives`

---

### ✅ Data model normalization (P3)

**What:** `data/offices.json` stores redundant copies of four shared blocks across 30 forms. Normalize them into `_shared` to reduce file size ~15–20% and eliminate copy-paste drift risk.

**Blocks to normalize:**

| Key | Distinct values | Affected forms |
|-----|----------------|---------------|
| `reading_response_seasonal` | 1 | All 16 seasonal forms |
| `reading_response_ordinary` | 1 | All 14 ordinary forms |
| `lords_prayer_ordinary` | 1 | All 14 ordinary forms |
| `opening_responses_ep_seasonal` | 1 | 7 of 8 seasonal EP forms (not Advent) |

**How:**
1. Write `tools/normalize_offices.py`: reads `data/offices.json`, deduplicates the four blocks into `_shared`, replaces per-form copies with `{"type": "shared", "key": "..."}` references, writes output in-place (or to a temp file + replace).
2. `app.js` already handles `{type: "shared"}` lookups — no app change needed.
3. Add `normalize_offices.py` call to Makefile after `extract_offices.py` in the data pipeline.

**Verify:** After normalization, run `make test` + `make test-full` + `make test-web`. All should pass without changes.

**Constraint:** Do not touch `tools/extract_offices.py`. Normalization is a post-extraction step.

**Commit message:** `data: normalize shared office blocks (reading_response, lords_prayer, ep_opening_responses)`

---

### ✅ Patch system (P3)

**What:** A mechanism to store text corrections as versioned patches rather than editing extracted JSON directly. Prevents corrections from being silently lost on re-extraction.

**Design:**

`data/patches.json` — list of patch objects:
```json
[
  {
    "id": "patch-001",
    "description": "Correct Wednesday litany response capitalisation",
    "reason": "Extraction pipeline normalises case; PDF uses lowercase for responses",
    "target": "offices.json",
    "path": ["ordinary-wednesday-mp", "litany", 0, "text"],
    "op": "replace",
    "old": "Holy one, accomplish your purposes in us.",
    "new": "holy one, accomplish your purposes in us."
  }
]
```

**Tools to write:**
- `tools/apply_patches.py`: reads `data/patches.json`, applies each patch to the target JSON file (by JSON path), writes output.
- `tools/validate_patches.py`: verifies each patch's `old` value matches the current file content at the specified path. Run before `apply_patches.py`.

**Makefile integration:** After extraction and normalization: `extract → normalize → apply_patches → assemble dist`.

**Note:** BUG-18 (Wednesday litany capitalisation) is currently patched directly in `data/offices.json`. Once this system exists, convert it to a `patches.json` entry and revert the direct edit.

**Commit order:**
1. `tools: add patch system (apply_patches.py, validate_patches.py)`
2. `tools: convert BUG-18 litany fix to patch entry`

---

### ✅ JSDoc annotation for app.js (P3)

`web/app.js` is ~1400 lines of dense vanilla JS with section banners but no inline documentation. Add JSDoc to the major exported function clusters to make future maintenance tractable.

**Priority functions to document:**
- `fetchOnce`, `fetchDay`, `fetchBook`
- `seasonOf`, `officeFormSeason`, `formKey`
- `renderSegments`, `renderAlternatives`
- `psalmHtml`, `lessonHtml`, `proclamationHtml`
- `parseCitation`, `parseRanges`, `extractVerses`
- `render` (top-level)

No behaviour changes. One commit.

---

### ✅ CONTRIBUTING.md (P3)

Write a developer contribution guide at the repo root. Cover:
- Dev environment setup (`make serve`, data symlink, `.env` requirements)
- Data pipeline: extraction order and when to re-run each tool
- All test tiers: `make test`, `test-full`, `test-smoke`, `test-seasonal`, `test-web`, `test-tools`, `validate`
- Deploy: `make build`, `make check-dist`, `make deploy`
- Copyright constraints: what's gitignored and why

---

### RCL Daily Lectionary (P1, feature-gated)

**Background**: GS2023 authorized the CCT 2005 "Revised Common Lectionary Daily Readings" as an alternative to the BAS daily office lectionary. It is the standard universal CCT publication (no Canadian variant). Copyright © 2005 CCT, admin. by Augsburg Fortress. The Synod is currently examining distribution rights for the official PWC app; data is for private evaluation only — gitignored, not committed. Same model as all other copyrighted data in this project.

**Data acquisition**: `tools/extract_rcl_daily.py` — checked in, output gitignored. Output: `data/rcl-daily/YYYY-MM.json`.

**Source**: CCT publishes the Daily Readings as free downloads directly from `commontexts.org/publications/`. No web scraping required — the extractor downloads structured files from the canonical source.

**Two editions — tiered priority:**

| Edition | ACC status | Coverage | Format |
|---------|-----------|----------|--------|
| 2005 Daily Readings | ✅ ACC-approved (GS2023 Res. A124) | Years A/B/C | RTF (A,B) + .doc (C) |
| 2024 Expanded Daily Readings | ⚠️ Not yet ACC-adopted | Year A only (B/C not freely published) | PDF |

**File URLs** (all `https://www.commontexts.org/` + path):

| File | Path | Format |
|------|------|--------|
| 2005 Year A | `wp-content/uploads/2015/11/RCLDailyReadings_YearA.rtf` | RTF |
| 2005 Year B | `wp-content/uploads/2015/11/dailyreadingsB.rtf` | RTF |
| 2005 Year C | `wp-content/uploads/2015/11/RCLDailyReadings_YearC.doc` | Word .doc |
| 2024 Expanded Year A | `wp-content/uploads/2025/12/RCL-Expanded-Daily-Readings-Year-A.pdf` | PDF |

**Strategy**: implement 2005 as primary (ACC-approved, all years). Optionally layer in 2024 Expanded for Year A once 2005 baseline works. The Expanded edition's richer structure (OT + NT + Gospel + psalm vs. 2005's psalm + 2 readings) is better for MP/EP balance, but it's not ACC-authorized yet and Year B/C aren't freely available. Revisit at ACC General Synod 2025/2026.

**Structural facts about the 2005 Daily Readings** (from the CCT overview PDF):
- 2 readings per day (first = OT or epistle, second = epistle or gospel)
- One psalm per week: Sunday's psalm is used Thu–Sun; a new psalm Mon–Wed
- Thursday–Saturday readings prepare for the coming Sunday; Mon–Wed reflect on the prior Sunday
- In ordinary time ("time after Pentecost"), two tracks: **semicontinuous** (Track 1) and **complementary** (Track 2) — different OT + psalm pairings; same epistle and gospel
- In all other seasons, a single track

**Extractor design** (`tools/extract_rcl_daily.py`):

Step 1 — Download source files:
```python
SOURCES = {
    'A': 'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearA.rtf',
    'B': 'https://www.commontexts.org/wp-content/uploads/2015/11/dailyreadingsB.rtf',
    'C': 'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearC.doc',
}
```
Use `requests` to download; cache locally in `tools/cache/`. For Year C `.doc`, use LibreOffice (`soffice --headless --convert-to txt`) to produce plain text, then parse identically to the RTF output.

Step 2 — Strip RTF markup:
Use `striprtf` (`pip install striprtf`) to convert RTF to plain text, then parse the plain text.

Step 3 — Parse plain text:
**Code must inspect the downloaded files first** to determine the exact table layout before writing the parser. The documents are known to be organized by liturgical week and day of week. Expected column structure (to be verified): period/week label | day | psalm | reading 1 | reading 2 (× 2 for semicontinuous/complementary in ordinary time).

Step 4 — Map to calendar dates:
The RCL "week" is anchored to Sunday. Given the Sunday date (from `data/lectionary/YYYY-MM.json` or `season_bounds.json`), compute:
- Thursday = Sunday − 3 days
- Friday = Sunday − 2 days
- Saturday = Sunday − 1 day
- Monday = Sunday + 1 day
- Tuesday = Sunday + 2 days
- Wednesday = Sunday + 3 days

Step 5 — Output `data/rcl-daily/YYYY-MM.json`:
```json
[
  {
    "date": "2026-06-13",
    "week_label": "Proper 6 – Preparation 3",
    "track1": {"psalm": "Psalm 116:1-2, 12-19", "ot": "Genesis 24:10-52", "nt": "Mark 7:1-13"},
    "track2": {"psalm": "Psalm 100", "ot": "Exodus 6:28—7:13", "nt": "Mark 7:1-13"}
  }
]
```
For non-ordinary-time days where there's only one track, `track1` and `track2` are identical.

**Important**: extract only citation strings (e.g. "Psalm 22:1-11"), not scripture text. The text carries separate Bible translation copyright.

**Data format** (monthly file, array of daily entries):
```json
[
  {
    "date": "2026-06-13",
    "week_label": "Proper 6 – Preparation 3",
    "track1": {
      "psalm": "Psalm 116:1-2, 12-19",
      "ot": "Genesis 24:10-52",
      "nt": "Mark 7:1-13"
    },
    "track2": {
      "psalm": "Psalm 100",
      "ot": "Exodus 6:28—7:13",
      "nt": "Mark 7:1-13"
    }
  }
]
```

**Feature gate**: At the top of the config section in `web/app.js`:
```js
const FEATURE_RCL_DAILY = false; // set true for evaluation builds
```
All RCL-related code (data fetching, UI rendering, settings option) is wrapped in `if (FEATURE_RCL_DAILY)` blocks. Setting `false` is a complete clean removal.

**Daily Office mapping**:
- MP: psalm + OT reading
- EP: (same) psalm + NT reading
- Track (1 = semicontinuous / 2 = complementary): stored in `localStorage` as `rcl_track`

**Integration points in `app.js`**:
1. `fetchDay()` — after resolving the BAS lectionary, if `FEATURE_RCL_DAILY && lectionaryPref === 'rcl'`, fetch from `data/rcl-daily/YYYY-MM.json`
2. `proclamationHtml()` — branch on lectionary source to render RCL readings in place of BAS
3. Settings sheet — add Lectionary selector (BAS / RCL Daily) and RCL Track selector (Semicontinuous / Complementary), both gated on `FEATURE_RCL_DAILY`
4. Service worker (`sw.js`) — include `data/rcl-daily/` in cache manifest when flag is true

**Commit order**:
1. `tools: add extract_rcl_daily.py (parses CCT RTF downloads, outputs data/rcl-daily/)`
2. `data: gitignore data/rcl-daily/`
3. `feat(rcl): feature-gated RCL daily lectionary (disabled by default)`
4. Internal evaluation build: flip flag to true

**Test**: `TestRCLDailyStructure` in `e2e/` (build tag: `e2e_full`) — verifies each loaded month file has entries for all dates, track1/track2 fields non-empty, psalm non-empty.

---

## Needs Cowork design first

### MP/EP label wording (quick fix)

The Morning Prayer / Evening Prayer selector should display only "Morning Prayer" and "Evening Prayer" — not any clock time or time-of-day mapping (e.g. "Morning Prayer (6am–noon)"). The label describes the *office*, not the time of day. One-line copy change in `app.js`.

**Commit message:** `fix(ui): MP/EP selector labels — office name only, no time mapping`

---

### Day selection and URL design (P2)

**Current state**: Routing is already hash-based — `#/YYYY-MM-DD/mp|ep`. No hash → today + auto-selected office. Date picker and arrow keys update the hash. Nav brand click + `t` key both strip the hash to return to today. This is the right architecture. No routing refactor needed.

**The actual problem**: "Return to today" is not discoverable. The nav brand click is not obvious, and `t` is a hidden shortcut. A user who lands on a stale dated URL (from a shared link, a browser history entry, or a mis-saved bookmark) has no visible way to get to today.

**Fix: stale-date banner**

When the app loads with a hash date that is **earlier than today**, show a single-line dismissible banner above the office content:

```
Viewing [formatted date]  ·  Jump to today →
```

- Only on load, not while navigating (navigating backwards is intentional, no banner needed)
- "Jump to today →" calls the existing today-reset logic (strip hash, same as brand click)
- Banner is dismissed by clicking "today" or by clicking an ✕ close button; remember dismissal in `sessionStorage` so it doesn't reappear on the same day's session
- No banner if hash date is today or in the future (future dates are valid for advance planning)

**Implementation:**

In `handleHashChange()`, after parsing the hash:
```js
// Show stale-date banner if loaded URL is an older date
if (parsed && parsed.date < todayStr()) {
  showStaleBanner(parsed.date);
} else {
  hideStaleBanner();
}
```

`showStaleBanner(date)`: checks `sessionStorage.getItem('pwc-stale-banner-dismissed-' + date)`; if not dismissed, injects a `<div class="stale-banner">` before `#office-content`.

**Also add: visible "Today" button**

The calendar icon in the nav currently opens the date picker. Add a small "Today" text link or button alongside it — visible at all times, making the reset affordance explicit. Tapping it calls the same today-reset logic.

**MP/EP selector wording** (from item 4 above): the toggle labels should read "Morning Prayer" and "Evening Prayer" only, with no time-of-day annotation. The auto-selection of morning vs. evening at page load is fine; only the label copy needs changing.

**Midnight auto-advance**: no change needed. The app already computes `todayStr()` fresh on every page load and on every hash navigation. A user who leaves the app open past midnight and then navigates (arrow key, date picker, brand click) will see the correct new date.

**Commit order:**
1. `fix(ui): stale-date banner when loading a past dated URL`
2. `fix(ui): add visible Today button to nav`
3. `fix(ui): MP/EP selector labels — Morning Prayer / Evening Prayer only`

(Item 3 can be its own one-line commit — it's a copy change in the defaultOffice label rendering.)

---

### Offline download UI (BUG-09, P2)

The service worker pre-caches 3 upcoming months on idle but there's no user control to pre-fetch more. Needed for retreats or travel without connectivity.

**Design questions for Cowork:**
- Where in the UI: settings sheet panel? Separate drawer?
- What granularity: months / translations / all-at-once?
- Progress feedback: inline progress bar, or toast?

**Once designed:** Cowork writes a spec in this file, hands off to Code.

---

### First-run preference wizard (BUG-13, P2)

No prompt on first visit — users default to NRSVUE without knowing KJV is available. Theme preference also undiscoverable.

**Design questions for Cowork:**
- Two choices (translation + theme) or just translation?
- Inline banner (preferred — no modal) or bottom sheet?
- When to show: on first ever render, or after the first office loads?

**Once designed:** Cowork writes a spec in this file, hands off to Code.

---

### Full correctness audit: remaining 27 office forms (P2)

Saturday MP, Wednesday MP, Wednesday EP are clean (see `CORRECTNESS.md`). All seasonal forms and remaining weekday forms are unaudited.

**Method:** For each form, load the app at a representative date, compare rendering against the `sources/pray-without-ceasing.pdf` source, record discrepancies in `CORRECTNESS.md` and `BUGS.md`.

**Remaining to audit:**

| Form | Test date | PDF pages |
|------|-----------|-----------|
| Advent MP | 2026-12-01 | 14–21 |
| Advent EP | 2026-12-02 | 22–28 |
| Christmas MP | 2026-12-27 | 29–35 |
| Christmas EP | 2026-12-28 | 36–42 |
| Epiphany MP | 2026-01-11 | 43–49 |
| Epiphany EP | 2026-01-12 | 50–56 |
| Lent MP | 2026-03-02 | 57–64 |
| Lent EP | 2026-03-03 | 65–71 |
| Passiontide MP | 2026-03-30 | 72–78 |
| Passiontide EP | 2026-03-31 | 79–85 |
| Easter MP | 2026-04-13 | 86–92 |
| Easter EP | 2026-04-14 | 93–99 |
| Pentecost MP | 2026-05-25 | 100–106 |
| Pentecost EP | 2026-05-26 | 107–113 |
| All Saints MP | 2026-11-01 | 114–120 |
| All Saints EP | 2026-11-02 | 121–128 |
| OrdinaryTime Sunday MP+EP | 2026-06-07 | 132–152 |
| OrdinaryTime Monday MP+EP | 2026-06-08 | 146–166 |
| OrdinaryTime Tuesday MP+EP | 2026-06-09 | 160–180 |
| OrdinaryTime Thursday MP+EP | 2026-06-11 | 189–209 |
| OrdinaryTime Friday MP+EP | 2026-06-12 | 203–223 |

Any bugs found go in `BUGS.md`; confirmed text corrections become entries in `data/patches.json` (once patch system exists).

---

### For All The Saints — feast day enrichment (P3)

**Source**: `sources/For-All-The-Saints.pdf` — 399-page ACC supplement (© 2007 ACC, gitignored). Contains propers for every BAS calendar feast day plus appendix of recent additions.

**What it provides per feast day** (consistent structure throughout the document):
- Rank and canonical date
- Biographical notice (narrative, 2–5 paragraphs)
- Sentence (scripture sentence)
- Collect
- Readings: Psalm (with refrain), OT, NT/epistle (Holy Days), Gospel
- Eucharistic material (Prayer over Gifts, Preface, Prayer after Communion — not needed for Daily Office)

**What PWC needs from FATS:**
1. **Biographical notices** — display in the observance card for feast days (currently the card just shows the name from the lectionary)
2. **Collect and readings** for saints whose propers aren't in the BAS lectionary CSV (primarily the Appendix saints added after the BAS was published)

**Extractor** (`tools/extract_fats.py` → `data/fats/saints.json`, gitignored):
- Parse PDF text with `pdftotext` piped through Python
- Each entry starts with a saint name line followed by a date line and rank line
- Split on these header patterns to identify entry boundaries
- Within each entry: extract the biographical block (everything before "Sentence"), the Collect block, the Readings block (Psalm, then citations)
- Output keyed by normalized feast name: `{"John Horden": {"date": "January 12", "rank": "commemoration", "bio": "...", "collect": "...", "psalm": "98", "readings": ["Isaiah 49.1–9", "Matthew 28.16–20"]}}`

**Matching to lectionary**: The observance name in `data/lectionary/YYYY-MM.json` uses the same names as FATS but may differ in punctuation or brevity. Use case-insensitive substring matching as the primary lookup; fall back to a manually maintained alias dict for known mismatches.

**App integration:**
- In `render()`, after loading `officeData`, if the day has an observance with a FATS entry: fetch `data/fats/saints.json` lazily (cached), look up the entry, display bio notice in the observance card
- If the day's `collect` field is empty and a FATS collect exists, use the FATS collect
- Service worker: add `data/fats/saints.json` to the cache manifest

**Commit order:**
1. `tools: add extract_fats.py (biographical notices and collect/readings for feast days)`
2. `data: gitignore data/fats/`
3. `feat(fats): display biographical notice in observance card for feast days`
4. `feat(fats): use FATS collect and readings for saints not in BAS lectionary`

---

## Blocked externally

### Year A lectionary (BUG-06, P1)

Coverage ends late December 2026 (Year B). Year A begins Advent 2026. Waiting on ACC to publish Year A CSV.

**When unblocked:** Run full pipeline (`scrape_lectionary.py` → `convert_lectionary.py` → `validate_lectionary.py`). Update `season_bounds.json`. Extend date picker `max` in app.

### Occasional Prayers extraction (BUG-04, P1)

BAS pp. 660+ not extracted. Three late-October dates reference Collect 668 which is hardcoded. Other dates referencing Occasional Prayers get nothing or the wrong collect.

**Source:** `sources/BAS.pdf` is present. Unblocked — needs extraction work.
**To do:** Write `tools/extract_occasional_prayers.py` (or extend `extract_collects.py`) for BAS pp. 660+. Replace hardcoded Collect 668.

### ACC licence inquiry

Contact Anglican Church of Canada about reproducing BAS/PWC liturgical text in an open-source worship app. Unblocks committing `data/` files publicly and publishing under MIT or Apache 2.0.

**Action:** Dustin drafts and sends email to ACC licensing contact.
