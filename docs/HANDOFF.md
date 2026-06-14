# PWC — Handoff

_Updated: 2026-06-14_

---

## Ready for Cowork review (batch 6 + mobile fix)

Build serving at **http://localhost:8081**. `make check-integrity` passes. `make check-text` reports zero findings.

### What to spot-check

**1. Nav header — "Today" button removed**
- Load http://localhost:8081 — the nav should show: `[PWC logo] [← 📅 →] [⚙]` with no "Today" text button
- The brand link ("Pray Without Ceasing") still navigates to today when clicked
- The `t` keyboard shortcut still works

**2. Stale-date banner — dismisses when navigating to today**
- Visit http://localhost:8081/#/2026-02-15/mp — banner should appear: "Viewing Sunday, 15 February 2026"
- Click the brand link (or press `t`) to return to today — banner should disappear
- Root cause was CSS `display: flex` overriding the HTML `hidden` attribute; fixed with `.stale-banner[hidden] { display: none }`
- Also: navigating to today now clears the sessionStorage dismissal key so the banner resets on the next visit to that stale date

**3. Season label — "Ordinary Time" with space**
- Visit any weekday in Ordinary Time (e.g., http://localhost:8081/#/2026-06-14/mp)
- The day header metadata should read: `Season · Ordinary Time` (not "OrdinaryTime")
- The `data-season` HTML attribute remains `OrdinaryTime` (for CSS theming) — only the display label changed

**4. Integrity guard — pdftotext version check**
- Run `make check-integrity` — should show `VERSION OK   pdftotext version 26.04.0 (matches manifest)` before the file OK lines
- On version mismatch it prints `VERSION WARN` with remediation steps (exit 0 — warning only)

**5. FATS text quality — zero findings**
- Run `make check-text` → `No text quality issues found.`
- The five FATS artifacts (Chad "among among", Maurice "midVictorian", Visitation "these these", Boniface "who who", Reformation "NinetyFive") are all fixed in `extract_fats.py` via `_clean_text()`

**6. Mobile layout — no duplicate app name (narrow viewport)**
- At ~400px viewport width, the content area should NOT show "PRAY WITHOUT CEASING" above "Morning Prayer"
- The nav brand remains visible at all widths; `#day-brand` in the content area is now permanently suppressed

---

## Ready for Code (batch 6)

This batch clears all known issues before the next larger design change (rubrics redesign / FATS minor feast readings). Five commits; `make check-text` should report zero findings when done.

### 1. Bug: "Today" text in nav header (P1)

The "Today" text label appears in the nav header alongside the calendar icon — a regression. In the minimal nav redesign these should be one element, not two. Inspect `app.js` nav rendering: either the Today button was re-added as a text label alongside the existing calendar icon, or the calendar icon was meant to serve today-navigation and the text button is redundant. Remove the spurious text instance; keep whichever element is the intended today-navigation control.

**Commit message:** `fix(ui): remove duplicate "Today" text from nav header`

---

### 2. Bug: Stale-date banner doesn't dismiss on navigate-to-today (P1)

Confirmed live: banner reads "Viewing Sunday, 15 February 2026" while the page shows today's office. `hideStaleBanner()` is not being called on navigation away from the stale date. Fix: in `handleHashChange()`, call `hideStaleBanner()` whenever `parsed.date >= todayStr()`. Also clear the sessionStorage dismissal key on navigate-away so it resets cleanly for future visits to that date.

**Commit message:** `fix(ui): hide stale-date banner when navigating to today or future`

---

### 3. Bug: "OrdinaryTime" missing space (P2)

Season metadata renders as `OrdinaryTime` — should be `Ordinary Time`. Find where the season value is rendered in the day header and add the space. Check whether this is a data issue (the season string in the JSON) or a display issue (the label in `app.js`). If it's in the data, fix in the appropriate extractor or season bounds file; if it's in the display layer, fix the label mapping in `app.js`.

**Commit message:** `fix(ui): render "Ordinary Time" with space in season label`

---

### 4. pdftotext version check in integrity guard (P2)

Add to `check_data_integrity.py`: compare installed `pdftotext` version (from `pdftotext -v 2>&1`) against `tool_versions.pdftotext` in the manifest. Print `VERSION OK` or `VERSION WARN` with remediation message. Exit 0 on version mismatch (warning only). Full spec in the batch 5 "Ready for Code" section below.

**Commit message:** `chore(tools): warn on pdftotext version change in integrity check`

---

### 5. Fix FATS extraction quality findings (P2)

Five findings from `make check-text` in `data/fats/saints.json` — fix in `tools/extract_fats.py`, then re-run `make extract` to update the data and manifest:

| Saint | Finding | Fix |
|-------|---------|-----|
| Chad | "among among" (duplicate word) | Fix extraction parsing — likely a repeated line |
| Frederick Denison Maurice | "midVictorian" (missing space) | Should be "mid-Victorian" — add to NAME_FIXES or post-process |
| The Visitation | "these these" (duplicate word) | Fix repeated line in extraction |
| Boniface | "who who" (duplicate word) | Fix repeated line in extraction |
| Saints of the Reformation Era | "NinetyFive" (merged token) | Should be "Ninety-Five" — add text fix |

After fixing `extract_fats.py`, run `make extract`. Then run `make check-text` — should report zero findings. Commit the extractor fix and the updated manifest separately.

**Commit messages:**
1. `fix(tools): fix FATS extraction artifacts (duplicate words, merged tokens)`
2. `chore(data): re-extract after FATS extraction fixes`

---

## Design: Rubric visibility (Cowork — needs planning before Code)

**Synod feedback:** Too much text. Rubrics in Office mode largely duplicate the section headings and interrupt the flow. The intercessions block in particular is a wall of red text. Book mode is the right place for full rubric fidelity — Office mode should be streamlined.

### Rubric taxonomy

Rubrics in the BAS Daily Office fall into three categories with different treatment per mode:

| Type | Example | Office mode | Book mode |
|------|---------|-------------|-----------|
| **Navigation** — tells reader what comes next | "Morning Prayer continues with the Lord's Prayer" | **Suppress** — section order is already visible | Show |
| **Participatory** — who says what, posture | "Said by all", "All stand/kneel" | **Keep** — genuinely needed | Show |
| **Optional** — invites something | "You may offer intercessions…", "Here may follow a homily" | **Condense** to one italic line | Show in full |

### Intercessions/Thanksgivings specifically

Currently a wall of rubric text before open prayer. In Office mode, condense the entire preamble to:

> *Offer intercessions, petitions, and thanksgivings, silently or aloud.*

In Book mode, show the full BAS rubric text as printed.

### Implementation approach

Do **not** change `offices.json` data — classify at render time in `app.js`. Pattern-match against known navigation rubric phrases:

- Starts with `"Morning Prayer continues"` / `"Evening Prayer continues"` → suppress in Office mode
- Starts with `"Here follow"` / `"Here may follow"` → condense
- Starts with `"You may"` → condense  
- Starts with `"Said by all"` / `"All stand"` / `"All kneel"` → keep always

The intercessions block gets a special render path: detect the intercessions section by its form key and substitute the condensed line when not in book mode.

### What Code needs from Cowork first

Before speccing this for Code, Cowork should:
1. Browse the Office mode on a typical weekday and list every rubric that appears
2. Classify each as navigation / participatory / optional
3. Confirm the condensed intercessions text ("Offer intercessions, petitions, and thanksgivings, silently or aloud.")
4. Decide whether "Here may follow a homily" stays (it's a useful reminder) or goes

This audit is Cowork work. Once done, a concrete Code spec can be written.

---

## Ready for Cowork review (batch 5)

Build serving at **http://localhost:8081**. `make check-integrity` passes.

### What to spot-check

**Garbled collects — the four previously-broken pages:**

| Date | URL | Expected text |
|------|-----|---------------|
| 2026-02-15 (7th Sun after Epiphany) | http://localhost:8081/#/2026-02-15/mp | "your Son revealed in signs and miracles" |
| 2026-02-22 (8th Sun after Epiphany) | http://localhost:8081/#/2026-02-22/mp | "grant us the Spirit to think and do always" |
| 2026-11-15 (Proper 33) | http://localhost:8081/#/2026-11-15/mp | "to be the light of the world" |
| 2026-10-04 (Rogation Days / Harvest) | Visit any Rogation/Harvest date | "Creator of the fruitful earth" |

Load each date → open the Collect section → verify text is readable (no merged words like "AlmightyGod,").

**Integrity guard:**
- Run `make check-integrity` — should pass with all OK lines.
- Run `make deploy BUCKET=... CF_DISTRIBUTION_ID=...` — the deploy gate will call `check-integrity` first, then fail loudly if any data drift is detected.

**Text quality checker:**
- Run `make check-text` → should report 5 findings (all in `data/fats/saints.json`, residual FATS extraction artifacts — noted below, not blocking deploy).

**Common of a Martyr fix (p.432):**
- Check http://localhost:8081/#/2026-11-01/mp (All Saints Day, uses Proper 31 collect, not martyr) — any saint's day that uses Common of a Martyr should show "servant N courage" with a space before N.

### Known remaining findings from `make check-text`

5 findings in `data/fats/saints.json` — FATS extraction artifacts, not in scope for batch 5:
- `Chad` collect: "among among" (duplicate word)
- `Frederick Denison Maurice` bio: "midVictorian" (missing space, should be "mid-Victorian")
- `The Visit of the Blessed Virgin Mary to Elizabeth` bio: "these these" (duplicate word)
- `Boniface` bio: "who who" (duplicate word)
- `Saints of the Reformation Era` bio: "NinetyFive" (merged, should be "Ninety-Five")

These are real issues but require fixes in `tools/extract_fats.py`. Not blocking deploy.

---

Active handoff between Cowork (planning) and Claude Code (implementation). Cowork writes specs here; Claude Code implements and marks done.

---

## Extract audit (2026-06-14)

Baseline: S3 prod (`pwc-office-85464`), deployed 2026-06-07. Current: freshly extracted data/.

**Verdict: ⛔ NOT SAFE TO DEPLOY — garbled collects regression (see below).**

### Blocking: garbled text in `collects.json` — 4 pages

pdftotext 26.04.0 strips word spaces for these specific BAS pages. They are NOT in the extractor's txt-fallback list so they regressed since the June 7 deploy:

| Page | Feast | Symptom |
|------|-------|---------|
| p.356 | Seventh Sunday after Epiphany * | `AlmightyGod,\nyourSonrevealed…` |
| p.358 | Eighth Sunday after Epiphany * | `AlmightyGod,\ngrantustheSpirit…` |
| p.392 | Proper 33 (Nov 13–19) | `…JesusChrist\ntobethelightoftheworld…` |
| p.396 | Rogation Days / Harvest Thanksgiving | `Creatorofthefruitfulearth,…` |

**Fix options:**
- A: Add `[356, 358, 392, 396]` to the txt-fallback list in `extract_collects.py` (needs investigation of why the fallback works for other pages)
- B: Add 4 entries to `data/patches.json` with the correct text (available from prod — all verified against BAS PDF)

### Expected changes (all explained by post-June-7 commits)

- **offices.json** (31 forms): `normalize_offices.py` (commit `d80be4b`, 2026-06-13) added 3 new `_shared` keys — `reading_response_seasonal`, `reading_response_ordinary`, `lords_prayer_ordinary`. Content unchanged, just moved from inline to shared references.
- **collects.json**: Patches 003–006 (Canada Day / Saint Peter / Saint Thomas), plus Occasional Prayers extraction (pp.677, 680) — both expected from batch 3/4.
- **lectionary**: 103 pre-window files (2016–2025-05) removed. Of the 19 current-window files, 18 are identical to prod; `2026-06.json` has 2 dates where a Corpus Christi alternate EP psalm citation was normalised from `'6-7'` (relative) to `'110:6-7'` (fully qualified) — a correct improvement.

### Minor / cosmetic

- **psalter.json psalm 118**: One verse refrain has `" The mercy…"` (extra leading space) vs prod `"The mercy…"`. pdftotext rendering artifact; not semantically meaningful. Recommend adding to `psalter_corrections.py`.
- **season_bounds.json**: Trailing newline difference only.

### Pipeline fixes made this session

- `validate_lectionary.py` line 237: added `if html_entry is None:` guard — `parse_day_html()` can return None when the ACC HTML page parses to nothing; previously crashed with `AttributeError`.

Full report: `tools/extract_audit_report.txt`

---

## Ready for Code (batch 5)

### 1. Fix garbled collects — **BLOCKING DEPLOY** (P0)

The extract audit (above) found 4 BAS pages where `pdftotext` 26.04.0 strips inter-word spaces. These pages are not in the txt-fallback list in `extract_collects.py` and regressed since the June 7 deploy.

| Page | Feast |
|------|-------|
| 356  | Seventh Sunday after Epiphany |
| 358  | Eighth Sunday after Epiphany |
| 392  | Proper 33 (Nov 13–19) |
| 396  | Rogation Days / Harvest Thanksgiving |

**Fix (option A — preferred):** Add `[356, 358, 392, 396]` to the txt-fallback page list in `extract_collects.py`. Re-run `make extract`. Verify the four pages now produce readable text with spaces.

**Fix (option B — fallback):** If the txt-fallback mechanism doesn't cover `extract_collects.py` pages (only `extract_offices.py` may use it), add 4 `patches.json` entries with the correct text taken verbatim from the current prod `collects.json` (accessible via `aws s3 cp s3://$BUCKET/data/collects.json /tmp/prod_collects.json` or the local backup from the audit session).

Run `make extract` after fixing, re-run audit (`diff data/collects.json.bak data/collects.json`), confirm garbled text is gone before proceeding to deploy.

**Commit message:** `fix(collects): restore word spacing for garbled BAS pages (356, 358, 392, 396)`

---

### 2. Extraction manifest + data integrity guard (P2)

**Problem:** An agent session might edit `data/*.json` directly ("monkey patching") instead of going through the proper correction pipeline (extractors or `patches.json`). That fix looks correct in the app but is silently overwritten the next time `make extract` runs, destroying the dev session's work. The manifest must detect this.

**Design:** The manifest records hashes of what the extractor last produced. The integrity check compares current `data/` hashes to the manifest. If they diverge and `make extract` wasn't just run, something modified data files outside the pipeline — that's the alert.

**New script: `tools/update_extract_manifest.py`**

Run at the very end of `make extract` (after `apply_patches.py` — must reflect the final patched state). Writes `tools/extract_manifest.json`:

```json
{
  "extracted_at": "2026-06-14T18:32:00Z",
  "tool_versions": {
    "pdftotext": "26.04.0"
  },
  "files": {
    "data/offices.json":      { "sha256": "...", "entries": 31 },
    "data/collects.json":     { "sha256": "...", "entries": 127 },
    "data/psalter.json":      { "sha256": "...", "entries": 150 },
    "data/fats/saints.json":  { "sha256": "...", "entries": 173 },
    "data/lectionary":        { "sha256": "...", "months": 25 }
  }
}
```

For `data/lectionary`, compute a composite hash from sorted filenames + their individual hashes.

**New script: `tools/check_data_integrity.py`**

Reads `tools/extract_manifest.json`, computes current hashes for each listed file, and compares:

```
OK   data/offices.json (abc123...)
OK   data/collects.json (def456...)
DRIFT data/psalter.json
      expected: ghi789...
      actual:   zzz999...
      → File was modified outside the extraction pipeline.
      → Migrate the change to extract_psalter.py or patches.json, then re-run make extract.
```

Exit 0 if all match. Exit 1 if any diverge. Include a clear remediation message.

**Wire into deploy gate:**
```makefile
check-integrity:
	python3 tools/check_data_integrity.py

deploy: check-integrity build
	# ... existing deploy steps
```

This makes it impossible to accidentally deploy monkey-patched data — `make deploy` fails loudly with a specific file and instructions.

`tools/extract_manifest.json` must be committed to git (un-ignore it). `git log -- tools/extract_manifest.json` then gives a complete history of every extraction run; `git diff tools/extract_manifest.json` shows which files changed by hash/count.

**Local versioned extractions (separate concern)**

The manifest tells you *that* `collects.json` changed but not *which collects* or *how*. For full content diff and rollback, initialise a local git repo inside `data/`:

```bash
# First time only — after make extract succeeds
git init data/
git -C data/ add -A
git -C data/ commit -m "initial extraction"
```

Then wire into `make extract` (end of target, after manifest update):
```makefile
	git -C data/ add -A && git -C data/ commit -m "extraction $(shell date +%Y-%m-%d)" || true
```

`|| true` prevents the target failing if data/ has no changes. The `data/.git/` directory is local only — `data/` is already gitignored so it never gets pushed. Use `git -C data/ log` for history, `git -C data/ diff HEAD~1` for the exact text diff between the last two extractions.

The two mechanisms serve distinct purposes:
- **Local data git** — full content diff between extraction runs; rollback to previous extraction
- **Integrity guard (manifest)** — deploy gate: was data/ touched outside the pipeline?

**Commit messages:**
1. `chore(tools): add extract manifest and data integrity guard`
2. `chore(tools): init local git repo in data/ for extraction versioning` (run manually, not a code commit)

---

### 2b. PDF tool version check in integrity guard (P2)

The manifest already records `tool_versions.pdftotext` (batch 5). Extend `check_data_integrity.py` to also compare the currently-installed `pdftotext` version against the manifest at the top of its output:

```
VERSION OK   pdftotext 26.04.0 (matches manifest)
```

or, on mismatch:

```
VERSION WARN pdftotext 26.05.0 (manifest recorded 26.04.0)
             → Version changed since last extraction. Run make extract then
               make check-text to catch any new garbled-text regressions
               before deploying.
```

Get the installed version via `pdftotext -v 2>&1` (pdftotext writes version to stderr). Parse the version string from the output. Exit 0 on version mismatch (warning only — intentional upgrades are valid); exit 1 only on data hash drift as before.

This closes the silent-regression gap: the exact scenario that caused the batch 5 garbling (pdftotext upgraded, extraction not re-run) will now produce a visible warning at every `make check-integrity` and `make deploy`.

**Commit message:** `chore(tools): warn on pdftotext version change in integrity check`

---

### 3. Text quality checker (P2)

**Goal:** Catch PDF extraction artifacts (missing spaces, merged words, duplicate words) with a fast rule-based scan — no LLM needed.

**New script: `tools/check_text_quality.py`**

Scans all text fields in `data/offices.json`, `data/collects.json`, `data/psalter.json`, `data/fats/saints.json`. Reports flagged issues with file, key path, and the suspicious snippet.

**Checks to implement:**

| Check | Pattern | Example |
|-------|---------|---------|
| Missing space (merged lines) | `[a-z][A-Z]` mid-word | `AlmightyGod` → catches `yG` |
| Duplicate adjacent word | `\b(\w{3,})\s+\1\b` (case-insensitive) | `the the` |
| Probable merged token | `\b\w{30,}\b` | `almightygodwhohastgiven` |
| Hanging hyphen | `\w-\s*\n` in raw text | `ever-\ngiven` |

Exclude false-positive patterns specific to liturgical text:
- All-caps tokens (rubric labels like `MINISTER`, `PEOPLE`) — skip
- Known hyphenated liturgical words: `ever-living`, `ever-blessed`, `well-beloved`, etc. — add a small allowlist
- Scripture citation patterns like `John 3:16` — skip

**Output format:**
```
data/collects.json [392][text]: missing_space near "JesusChristto" (offset 42)
data/collects.json [356][text]: missing_space near "yourSonrevealed" (offset 18)
```

Exit 0 always (warnings only — don't block the pipeline). Optionally accept `--strict` flag to exit 1 on any finding.

**Makefile targets:**
```makefile
check-text:
	python3 tools/check_text_quality.py

validate: check-text validate-lectionary
```

Wire `check-text` into `make validate` so it runs alongside the lectionary check.

**Test:** After fixing the garbled collects (batch 5 item 1), run `make check-text` — the 4 previously-garbled pages should produce zero findings. If any other pages have issues, investigate and fix.

**Commit message:** `chore(tools): add text quality checker for PDF extraction artifacts`

---

## Completed this session (2026-06-14 batch 4)

All four "Ready for Code (batch 4)" items implemented and committed.

**Implemented:**

- **Civic collect corrections** (`data/patches.json`): Six patches added.
  - p.677 name updated "For the Queen" → "For the Sovereign"; text updated to King Charles / "him".
  - p.412 mislabeled "Canada Day 1 July" → "Saint Peter and Saint Paul 29 June"; date fixed.
  - p.413 mislabeled "Saint Thomas 3 July" → "Canada Day 1 July"; date fixed.
  (Root cause: `_feast_name_from_page()` in `extract_collects.py` reads the NEXT entry's heading from the bottom of the preceding page. Canada Day's collect is on BAS p.413, correctly extracted text-wise, just mis-labeled.)

- **Secondary collect UI** (`web/app.js`): Added `collectSecondaryPage()` to parse Occasional Prayer page numbers from refs like `"344 or 8, 677 (The King)"` → `"677"`. Refactored `collectToggleHtml()` to use an internal `tabBlock([[label, html], …])` helper. Both the regular and seasonal-alt branches now show the Occasional Prayer as an extra tab.

- **Dead CSS** (`web/office.css`): Removed unused `.day-ctrl-sub` rule (line 722).

- **FATS extractor** (`tools/extract_fats.py`): New script. Runs `pdftotext` on `sources/For-All-The-Saints.pdf`, parses 173 saints (main section pp.37–385 + Appendix pp.388–392). Output: `data/fats/saints.json` (already covered by `data/*` gitignore; no gitignore change needed). Handles: garbage printer headers (Appendix pages), names wrapping across date lines (Annunciation, Visitation, Founders/Benefactors), multi-line rank descriptions (Hannah Grier Coome, Charles Henry Brent), entries with no repeated date in header (Jan Hus). Three NAME_FIXES entries for PDF layout artifacts.

- **FATS app integration** (`web/app.js`, `web/office.css`, `web/sw.js`):
  - Phase 1: `lookupFatsEntry(fats, name)` does case-insensitive substring match with `FATS_ALIASES` override dict. If a FATS entry exists for `day.name`, a collapsible `<details>` bio block appears below the observance card. `data/fats/saints.json` added to service worker CACHE_FIRST list.
  - Phase 2: `collectToggleHtml()` now accepts a `fatsEntry` parameter. If the BAS collect ref is absent or the page isn't in `collects.json`, and a FATS collect exists, it's shown as the Collect of the Day (fallback). Applies to Appendix saints not in BAS.

**Commits (in order):**
1. `fix(collects): update sovereign collect to King Charles and correct Canada Day/saints page labeling` (17461be)
2. `feat(collect): display occasional prayer as additional collect tab` (84ad20a)
3. `chore(css): remove unused day-ctrl-sub class` (c9a81e7)
4. `tools: add extract_fats.py (biographical notices and propers for feast days)` (a5844cd)
5. `feat(fats): show bio notice and FATS collect fallback for feast days` (ad9bd47)

**Surprises / things Cowork should know:**

1. **Canada Day collect is on BAS p.413, not in Occasional Prayers**: The HANDOFF hypothesised Canada Day collect was "almost certainly in the Occasional Prayers section (BAS pp.660+)". Investigation showed it's in the saints range at p.413 (correctly extracted text, just mislabeled). Confirmed by FATS p.211 which has identical text. Corrected via patches.json, not extractor fix.

2. **`data/fats/` already covered by gitignore**: `data/*` in `.gitignore` already covers `data/fats/`. No separate entry was needed or added. Commit 2 from the spec ("data: gitignore data/fats/") was a no-op and skipped.

3. **FATS name lookup may need aliases**: The lectionary uses names like "Florence Li Tim-Oi, Priest, 1992" while FATS keys them as "Florence Li Tim-Oi". The substring match handles this case (lectionary name includes FATS name). The empty `FATS_ALIASES` dict in `app.js` is the extension point for cases where substring match fails — populate after testing against actual lectionary entries.

4. **Commits 3+4 from spec combined**: The FATS bio display (Phase 1) and collect fallback (Phase 2) share the same FATS fetch infrastructure in `render()`. Splitting them would have left an orphaned `fatsEntry` variable between commits. Combined as one commit with both phases described in the message.

---

## Completed this session (2026-06-14 batch 3)

All "Ready for Code (batch 3)" items implemented and committed.

**Implemented:**

- **Scraper retirement**: `tools/scrape_lectionary.py` moved to `boneyard/scrape_lectionary.py` (gitignored, local reference only). `tools/.daily_cache/` deleted. `make fetch-sources` now calls only `fetch_sources.py`. Error message in `convert_lectionary.py` updated to "Add a bas_short_YYYY.csv file to sources/". BUG-06 in `BUGS.md` and Phase 2.1 in `ROADMAP.md` reframed from "waiting on ACC to publish" to "add CSV to sources/ and run make extract". `CLAUDE.md` pipeline updated. `sources/bas_short_2026.csv` committed (`!sources/bas_short_*.csv` added to `.gitignore` using `sources/*` pattern, not `sources/`).

- **Occasional Prayers extraction**: `extract_collects.py` extended with `_extract_occasional_prayers()`. Reads BAS pp.676-683 (the actual prayer content pages; p.675 is the TOC), parses all 33 numbered prayers using `_OCC_HEADER` regex, stores lectionary-referenced ones under their BAS page keys via `_OCC_PAGE_ALIASES`. After extraction, `collects.json` now contains: p.677 = "For the Queen" (For the Sovereign / Victoria Day), p.680 = "For Industry and Commerce" (Labour Day). `section_from_page()` updated to return "Occasional Prayers" for pages beyond the Common Propers range. Six new spot checks pass.

**Commits (in order):**
1. `chore: retire scrape_lectionary.py (replaced by direct CSV workflow)`
2. `chore: commit lectionary CSV; unignore sources/bas_short_*.csv`
3. `feat(collects): extract Occasional Prayers section (BAS pp. 660+)`

**Surprises / things Cowork should know:**

1. **`.gitignore` pattern change**: The existing `.gitignore` had `sources/` (directory rule), which blocks git re-include rules entirely. Changed to `sources/*` (glob rule) to allow `!sources/bas_short_*.csv` to work. The effect is identical — all sources content is ignored except the named CSVs — but Cowork should know this changed so future gitignore additions for `sources/` are written as `sources/filename` not `sources/filename/`.

2. **App cannot currently display p.677/p.680 as alternatives**: The app's `collectPageNum()` extracts the FIRST number from a collect ref string. For a ref like `"344 or 8, 677 (The King)"`, it returns `"344"` and shows the regular Easter collect — the Occasional Prayer is never looked up. The data is now in `collects.json` but the UI change to show it as an alternative requires a separate app fix (parse the "or N, PAGE" secondary format). This is different from the p.668 case, where the collect ref is just `"668"` alone (so `collectPageNum` returns `"668"` correctly). Cowork should spec the UI enhancement separately.

3. **BAS p.677 contains prayer 8 "For the Queen"** — the original BAS text still uses "Queen Elizabeth" rather than "The King". The `_OCC_PAGE_ALIASES` comment and extract say "For the Sovereign" as context, but the extracted text preserves the literal BAS wording. If a future correction is needed (updating to "The King"), it should go in `data/patches.json`.

4. **The hardcoded p.668 entry remains**: Its dates (late October) were in 2017–2021 which are now outside the 12-month rolling window. It does no harm; left as-is per HANDOFF guidance.

---

## Completed this session (2026-06-13 batch 2)

All "Ready for Code (batch 2)" items implemented and committed.

**Implemented:**
- Bug 6b: gloria/doxology rendered once at the end of each individual set panel (Set 1, Set 2) in `psalmHtml()`, mirroring the batch 1 "All" panel fix — `psalmPlaceholder()` per psalm, `gloriaHtml(shared)` appended once per set.
- ARIA on psalm tabs: `role="tablist"` on `.alt-tabs`, `role="tab"` + `aria-selected` + `aria-controls` + `id` on each tab button, `role="tabpanel"` + `aria-labelledby` on each panel — applied in both `psalm_sets` and plain multi-psalm branches of `psalmHtml()`.
- ARIA on collect tabs: same treatment in both `isSingleAlt` and `hasDaily && hasSeasonal` branches of `collectToggleHtml()`. `idBase = 'pwc-alt-collect'` used for stable panel/tab IDs. ArrowLeft/ArrowRight keyboard nav already handled globally by `activateTab()`.
- Stale-date banner: `showStaleBanner(date)` / `hideStaleBanner()` added; called from `handleHashChange()` when `parsed.date < todayStr()`. Banner injects before `#office-content`, shows formatted date + "Jump to today →" link + ✕ close. Dismissal stored in `sessionStorage` key `pwc-stale-banner-dismissed-<date>`.
- Today button: `<button id="nav-today">Today</button>` added to nav top row (between date nav and settings). Wired to same today-reset logic as brand click / `t` key. CSS in `office.css` matches existing nav pill style.
- MP/EP selector labels: removed `<span class="day-ctrl-sub">` time-of-day annotations and "Office · by time of day" caption. Buttons now read "Morning Prayer" / "Evening Prayer" only. `day-ctrl-sub` class is now dead CSS (safe to clean up separately).

**Commits (in order):**
1. `fix(psalm): extend doxology fix to individual set panels`
2. `fix(a11y): ARIA tab roles on psalm and collect tab systems`
3. `fix(ui): stale-date banner when loading a past dated URL`
4. `fix(ui): add visible Today button to nav`
5. `fix(ui): MP/EP selector labels — office name only`

**Surprises / things Cowork should know:**

1. **`day-ctrl-sub` CSS class** (`.day-ctrl-sub { display: block; font-size: 0.6rem; ... }` in `office.css`) is now unused — the only elements that used it were the "Said in the morning" / "Said from ~5 pm" sub-labels that were removed. Safe to delete in a cleanup pass.

2. **Stale banner shows on any navigation to a past date**, not just on initial page load. Per the HANDOFF spec example, the check runs in `handleHashChange()` on every hash change. The `sessionStorage` dismissal means it only annoys once per date per session. If Cowork wants it truly "load-only", we'd need a `firstLoad` flag — consider speccing that.

3. **ARIA IDs for collect tabs** are stable (`pwc-alt-collect-tab-0` etc.) because `stateKey` is hardcoded `'pwc-alt-collect'`. Psalm tab IDs are dynamic (built from psalm citation list) and will change when the lectionary changes — this is correct since each day's psalms get unique IDs.

---

## Ready for Code (batch 4)

### Civic collect corrections (P1)

**1. Update "For the Queen" to "For the King" (patches.json)**

p.677 in `collects.json` still contains the original BAS wording naming Queen Elizabeth. Add two `patches.json` entries:

```json
[
  {
    "id": "patch-001",
    "description": "Update sovereign collect name from Queen to King",
    "target": "collects.json",
    "path": ["677", "name"],
    "op": "replace",
    "old": "For the Queen",
    "new": "For the Sovereign"
  },
  {
    "id": "patch-002",
    "description": "Update sovereign collect text from Queen Elizabeth to King Charles",
    "target": "collects.json",
    "path": ["677", "text"],
    "op": "replace",
    "old": "Almighty God, fountain of all goodness, bless our Sovereign\nLady, Queen Elizabeth, and all who are in authority under her;",
    "new": "Almighty God, fountain of all goodness, bless our Sovereign\nLord, King Charles, and all who are in authority under him;"
  }
]
```

Verify the exact `old` text by running `python3 tools/validate_patches.py` after adding — it will tell you if the string doesn't match. Add `apply_patches.py` to the `make extract` pipeline if it isn't already wired for `collects.json` (it may currently only handle `offices.json`).

**Commit message:** `fix(collects): update sovereign collect to King Charles (patches.json)`

---

**2. Canada Day collect reference audit**

The lectionary CSV references `Coll 413` for Canada Day (July 1) but:
- `collects.json` p.413 = Saint Thomas (3 July) — wrong saint entirely
- `collects.json` p.412 = labeled "Canada Day 1 July" but text is Peter & Paul collect — extraction bug
- The actual Canada Day collect is almost certainly in the Occasional Prayers section (BAS pp. 660+), not in the saints' range

**Code must inspect `sources/BAS.pdf`** around pp. 660–695 to find the Canada Day collect. If found there, add it to `_extract_occasional_prayers()` in `extract_collects.py` with its correct page key.

Also inspect what is actually on BAS pp. 411–413 to determine if the extraction labeled those entries correctly. The text starting "Almighty God, your blessed apostles Peter and Paul" should be on the Peter & Paul page (June 29, around p.408–410), not p.412.

If p.412 is confirmed as a mis-extracted entry, add a `patches.json` correction once the right text is identified.

**Commit message:** `fix(collects): correct Canada Day collect reference and extraction`

---

### Secondary collect UI fix (P1)

Code noted in batch 3: `collectPageNum()` only extracts the first number from a collect ref string. For refs like `"344 or 8, 677 (The King)"` it returns `344` — the Occasional Prayer alternative is never displayed.

**Current format patterns in collect refs (all must be parsed):**
- `"387"` — single page, already works
- `"340 (Com: 435 or FAS 171) or Coll 8, 677 (The King)"` — primary + occasional alternative
- `"377 or Coll 17, 680 (Labour Day)"` — primary + occasional alternative
- `"365 or Coll 413 or FAS 211 (Canada Day)"` — primary + two alternatives (FAS handled separately)
- `"426 or FAS 319"` — primary + FATS reference (FAS handled by FATS feature)

**Fix:** Extend the collect rendering to detect and display the Occasional Prayer alternative as an additional tab option (alongside Collect of the Day / Seasonal I / Seasonal II). The occasional prayer is the page after `Coll N,` in the ref string.

Parse secondary collect page from refs matching `Coll\s*\d+,\s*(\d+)` or `or\s+\d+,\s+(\d+)\s+\(`.

If an Occasional Prayer page is found AND that key exists in `collects.json`, add a fourth tab to the collect toggle with the occasion name as the label (from `collects[page].name`). If the key is missing from `collects.json`, silently omit the tab (graceful degradation).

**Test dates:**
- `2025-05-19` (Dunstan / Victoria Day) — should show "Collect of the Day" + optional "For the Sovereign" tab
- `2025-09-01` (Labour Day) — should show "Collect of the Day" + "For Industry and Commerce"
- `2025-07-01` (Canada Day) — only shows primary collect until Canada Day collect is fixed

**Commit message:** `feat(collect): display occasional prayer as additional collect tab`

---

### Dead CSS cleanup (P3)

The `day-ctrl-sub` CSS class (noted in batch 2 completion) is now unused — the time-of-day sublabels were removed. Find and delete the rule from `office.css`. Also check for any other rules referencing `.day-ctrl-sub` and remove them.

**Commit message:** `chore(css): remove unused day-ctrl-sub class`

---

### For All The Saints extractor + app integration (P2)

**Source:** `sources/For-All-The-Saints.pdf` — 399-page ACC supplement (gitignored). Contains propers for every BAS calendar feast day plus an Appendix of recent additions. Available via `make fetch-sources`.

**What Code must do first — inspect the PDF:**

```bash
pdftotext sources/For-All-The-Saints.pdf - | head -200
```

Then sample a few entries to understand the exact heading and section structure before writing the parser. Expected pattern per entry (verify against actual text):

```
[SAINT NAME]
[Date], [Rank]

[Biographical notice — prose paragraphs]

Sentence
[scripture sentence]

Collect
[collect text]

Psalm [citation] with refrain [optional refrain]
[lesson citations...]

Prayer over the Gifts / Preface / Prayer after Communion
[skip these — Daily Office doesn't use them]
```

**Extractor: `tools/extract_fats.py`** (new file)

Output: `data/fats/saints.json` (gitignored — add `data/fats/` to `.gitignore`)

Schema:
```json
{
  "John Horden": {
    "date": "January 12",
    "rank": "commemoration",
    "bio": "John Horden was born...",
    "sentence": "Isaiah 49.6",
    "collect": "Almighty God...",
    "psalm": "96",
    "readings": ["Isaiah 49.1-9", "Matthew 28.16-20"]
  }
}
```

Key by the canonical saint name as it appears in FATS (e.g. `"John Horden"`). The app will fuzzy-match against lectionary observance names.

**Matching logic:** Lectionary `observance` field uses same names as FATS but may differ in punctuation/abbreviation. Use case-insensitive substring match as primary lookup; maintain a `FATS_ALIASES` dict in `app.js` for known mismatches found during testing.

**App integration (two phases):**

Phase 1 — biographical notice in observance card:
- In `render()`, after loading `officeData`, if `day.observance` has a FATS entry: fetch `data/fats/saints.json` lazily (cached like other data files), look up by name, display the biographical notice beneath the observance name in the observance card section
- Service worker: add `data/fats/saints.json` to the cache manifest

Phase 2 — fallback collect and readings:
- If the day's `collect` field is empty or unresolvable AND a FATS collect exists, use the FATS collect
- This primarily benefits Appendix saints added after BAS was published who have no BAS collect entry

**Commit order:**
1. `tools: add extract_fats.py (biographical notices and propers for feast days)`
2. `data: gitignore data/fats/`
3. `feat(fats): display biographical notice in observance card for feast days`
4. `feat(fats): use FATS collect as fallback for saints not in BAS lectionary`

---

## Ready for Code (batch 3)

### Scraper retirement + CSV commit (P1)

**Background**: `tools/scrape_lectionary.py` was built to scrape `lectionary.anglican.ca` and download historical CSVs. PWC is developed at ACC's request; the CSV is provided directly. The scraper is dead weight. The model going forward: one CSV per liturgical year lives in `sources/`, committed to the repo. When ACC publishes a new year, add the CSV and run `make extract`.

**Changes:**

1. **Boneyard `tools/scrape_lectionary.py`** — move to `boneyard/scrape_lectionary.py`. Do not delete outright (historical reference value).

2. **Delete `tools/.daily_cache/`** — the scraper's HTML cache directory. It's gitignored but the directory is present locally. Remove it: `rm -rf tools/.daily_cache/`.

3. **Commit the CSV** — add to `.gitignore`:
   ```
   !sources/bas_short_*.csv
   ```
   Then `git add sources/bas_short_2026.csv`.

4. **Update `make fetch-sources`** — remove the `scrape_lectionary.py` call:
   ```makefile
   fetch-sources:
       python3 tools/fetch_sources.py
   ```

5. **Update `convert_lectionary.py`** — the error message on line ~690 currently says `"Run: python3 tools/scrape_lectionary.py"`. Replace with: `"Add a bas_short_YYYY.csv file to sources/ and re-run."`.

6. **Update `BUGS.md` BUG-06** — reframe from "waiting on ACC to publish" to: "When ACC provides a Year A CSV, add it to `sources/` and run `make extract`."

7. **Update `ROADMAP.md` Phase 2.1** — same reframe.

8. **Update `CLAUDE.md` tools list** — remove `scrape_lectionary.py` from the pipeline description (already done by Cowork for the `extract` pipeline; check `fetch-sources` description too).

**Commit order:**
1. `chore: retire scrape_lectionary.py (replaced by direct CSV workflow)`
2. `chore: commit lectionary CSV; unignore sources/bas_short_*.csv`

---

### Occasional Prayers extraction — civic collects (BUG-04, P1)

**Background**: `extract_collects.py` scans BAS pages 262–447 (Proper of the Church Year through Common Propers). BAS pp. 660+ contain "Occasional Prayers and Thanksgivings" — a separate section with civic and special-occasion collects. These are not extracted except for a single hardcoded entry (p.668, Feast of Dedication).

**What's actually missing in the current rolling window** (verified by Cowork):

| Page | Occasion | Dates it appears |
|------|----------|-----------------|
| 677 | For the Sovereign (The King) | Victoria Day, King's Birthday, Nativity of Our Lady, others |
| 680 | Labour Day | Labour Day |

These appear as **secondary alternatives** in the collect field (e.g. `"340 or Coll 8, 677 (The King)"`). The primary collect (p.340) renders; p.677 is silently absent. The hardcoded p.668 entry is now outside the rolling window and can remain as-is.

**Approach**: Extend `extract_collects.py` to also scan a second page range covering the Occasional Prayers section.

**Code must inspect `sources/BAS.pdf` first** to determine:
- The exact book-page range for "Occasional Prayers and Thanksgivings" (expected ~pp. 660–690)
- The heading structure (same as the main section, or different?)
- Which specific pages contain p.677 and p.680 entries

Then extend the extractor:

```python
# Add a second pass after the main scan
OCCASIONAL_FIRST_PAGE = 660   # verify against PDF
OCCASIONAL_LAST_PAGE  = 695   # verify against PDF

# Run the same per-page extraction logic over this range
# Entries go into the same `collects` dict, keyed by book page number
```

The existing `_find_collect_body()` and `section_from_page()` helpers should work unchanged; just update `section_from_page()` to return `"Occasional Prayers"` for pages in this range.

**Remove the hardcoded p.668 entry** once the page scan covers it (the scan will produce the same text automatically).

**Test**: After extraction, `collects.json` should contain entries for keys `"677"` and `"680"`. Load `2025-05-19` (Victoria Day) and `2025-09-01` (Labour Day) in the app — the Occasional Prayer collect should appear as an alternative in the collect section.

**Commit message:** `feat(collects): extract Occasional Prayers section (BAS pp. 660+)`

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

0. **`data/patches.json` was broken and has been cleared (Cowork fix, 2026-06-13).** The 14 BUG-18 entries Code added had `old` = uppercase text, but `_TEXT_PATCHES` in `extract_offices.py` already lowercases those responses during extraction — so `validate_patches.py` failed all 14 and `make extract` was broken. The fix: emptied `patches.json` to `[]`. BUG-18 is correctly handled by `_TEXT_PATCHES` in the extractor and does not need a patch entry. See CLAUDE.md "Manual data corrections" for the canonical map of where every correction lives.

1. **Golden files are gitignored.** `e2e/testdata/` is gitignored because golden snapshot files contain rendered liturgical text derived from copyrighted source data. The flow is: run `make extract` locally, then `make test-full` once to generate goldens, then subsequent runs catch regressions. CI can't run these without the data files.

2. **`data/patches.json` is now committed** (added `!data/patches.json` to `.gitignore`). The file contains only short text snippets used for verification. The 14 BUG-18 patches have `old` values = what `extract_offices.py` would produce (uppercase), `new` = the corrected lowercase. Validate will fail on the currently-patched local data; it's designed to run after a fresh extraction.

3. **Psalm "All" panel**: Bug 6 fix only touches the `allHtml` loop in both `psalmSets` and plain `psalms` branches. Individual set panels (e.g. Set 1, Set 2) still call `psalmWithGloria` since a set can contain 1–2 psalms; if a set has multiple psalms, it would still show gloria after each. Cowork may want to extend the fix to individual set panels too.

4. **ARIA tabs scope**: The spec said "one function change in `renderAlternatives()`". ARIA attributes were added there; the inline tab builders in `psalmHtml()` and `collectToggleHtml()` do NOT yet have ARIA. Keyboard nav works for the alternatives tab system (doxology, canticle, reading response, etc.) but not for psalm or collect tabs.

5. **3-tab collect**: The `stateKey` `'pwc-alt-collect'` now accepts values 0/1/2 for ordinary time (was 0/1). Users with the old `1` stored may see "Seasonal I" selected on first load; harmless, just worth knowing.

6. **`make fetch-sources`** currently has no test coverage — it downloads from external URLs which can't be tested offline. Consider a `--dry-run` flag or mock test if CI coverage matters.

---

## Ready for Code (batch 2)

### Bug 6b: Gloria after each psalm in individual set panels

Code fixed the "All" panel but individual set panels (Set 1, Set 2) still call `psalmWithGloria()` per psalm. If a set contains more than one psalm, the gloria appears after each. The fix mirrors what was done for the "All" panel — swap to `psalmPlaceholder()` per psalm and append `gloriaHtml(shared)` once at the end of each set's HTML.

**Where:** The per-set HTML loop inside `psalmHtml()` in `web/app.js` (look for the loop that builds the set panel content — distinct from the `allHtml` loop that was already fixed).

**Test:** Load any weekday office that has multiple psalms in a single set, switch to "Set 1" — gloria should appear once at the end.

**Commit message:** `fix(psalm): extend doxology fix to individual set panels`

---

### ARIA on psalm and collect tabs

Code added ARIA to `renderAlternatives()` but the inline tab builders in `psalmHtml()` and `collectToggleHtml()` were not touched. These tab systems need the same treatment: `role="tablist"` on the container, `role="tab"` / `aria-selected` on each button, `role="tabpanel"` / `aria-labelledby` on each panel, ArrowLeft/ArrowRight keyboard nav.

**Where:** `psalmHtml()` builds the psalm set tabs (All / Set 1 / Set 2 / Psalm 1 / Psalm 2). `collectToggleHtml()` builds the collect tabs (Collect of the Day / Seasonal I / Seasonal II or Collect of the Day / Seasonal). The `activateTab()` helper added for ARIA in `renderAlternatives()` can likely be reused or extracted to a shared utility.

**Test:** `make test-web` — add a Playwright a11y test that checks `role="tab"` attributes are present on psalm and collect tab buttons.

**Commit message:** `fix(a11y): ARIA tab roles on psalm and collect tab systems`

---

### Stale-date banner + visible Today button

Already fully specced below (see "Day selection" under "Needs Cowork design first" — that label is stale; the spec is complete). Moving here so Code can implement it.

**Summary of spec (full detail below):**
- When hash date < today on page load: show dismissible single-line banner `"Viewing [date] · Jump to today →"`
- Dismiss remembers via `sessionStorage` key `pwc-stale-banner-dismissed-<date>`
- Add a visible "Today" text button in the nav alongside the calendar icon — always visible, calls the today-reset logic (same as brand click / `t` key)

**Commit order:**
1. `fix(ui): stale-date banner when loading a past dated URL`
2. `fix(ui): add visible Today button to nav`

---

### MP/EP label copy (one-line fix)

The MP/EP selector should read "Morning Prayer" and "Evening Prayer" only — no time-of-day annotation. Find and remove any clock-time or time mapping from the toggle label in `app.js`.

**Commit message:** `fix(ui): MP/EP selector labels — office name only`

---

## Immediate: git housekeeping (do this first)

```bash
git rm CORRECTNESS.md UX_AUDIT.md
git add .gitignore ROADMAP.md CLAUDE.md docs/
git commit -m "chore: move design docs to docs/, track CLAUDE.md, gitignore redesign/"
```

---

## Previously completed (all ✅)

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

### Day selection spec (reference — moved to batch 2)

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

### For All The Saints — feast day enrichment

Moved to "Ready for Code (batch 4)" above — fully specced.

---

## Blocked externally

### Year A lectionary (BUG-06, P1)

Coverage ends late December 2026 (Year B). Year A begins Advent 2026. When ACC provides the Year A CSV, add it to `sources/` as `bas_short_YYYY.csv` and run `make extract`.

### ACC distribution

PWC is developed at ACC's request; Dustin is in active conversation with ACC about licensing/funding. Development continues unblocked; data files remain gitignored per copyright until distribution is resolved.

**Action:** Dustin drafts and sends email to ACC licensing contact.
