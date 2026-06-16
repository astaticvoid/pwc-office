# PWC — Handoff

_Updated: 2026-06-15_

Active handoff between Cowork (planning) and Claude Code (implementation). Cowork writes specs here; Code implements in order.

---

## Ready for Cowork review — Batch 15 (2026-06-15)

No web UI changes — data and renderer fixes only. Spot-check via terminal:

### `make check-book FORM=ordinary-sunday-ep DATE=2026-06-14`

Should exit **0** (PASS) — all 9 data-quality gaps from the Batch 13/14 diff are now closed.

### `make test`

Should pass: Vitest (108) + pytest. No Go.

### What changed

All 9 discrepancies between `cli/book.js` output and `tests/fixtures/book/ordinary-sunday-ep.txt` are fixed:

| # | Issue | Fix |
|---|-------|-----|
| 1 | Collect text had PDF line-break artefacts (multi-line) | `cli/book.js`: `joinLines` option flattens to single line |
| 2 | `(After the Psalm one of the following may be said or sung.)` missing | `cli/book.js`: emit directly before post-psalm doxology |
| 3 | `Alleluia.` missing after each EP opening doxology alternative | `cli/book.js`: split EP opening_responses render; inject per alternative |
| 4 | `(One of the following may be said or sung.)` missing before EP opening doxology | `extract_offices.py`: emit all `_BLOCK_SEP_ONLY` rubrics (was only canticle-doxology-intro ones) |
| 5 | Canticle intro rubric missing (`"Song of Mary," "A Song of the Lamb,"…`) | `extract_offices.py`: emit intro text before `_CANTICLE_INTRO` named alternatives |
| 6 | `(One of the following Affirmations of Faith may be said or sung.)` missing | `extract_offices.py`: emit intro text before `_GENERAL_INTRO` named alternatives |
| 7 | `Apostles' Creed` → `The Apostles' Creed`; `he ascended into heaven` missing comma | `extract_offices.py`: new `_fix_shared_affirmation()` post-dedup step |
| 8 | `Song of the Lamb` / `Song of the Heavenly City` missing `A ` prefix; wrong citations | `extract_offices.py`: stop stripping `A ` in `_alt_label`; add entries in `web/render.js` CANTICLE_SOURCE |
| 9 | `The Evening Hymn: "O Gladsome Light, O Grace"` heading missing | `extract_offices.py`: store heading as `{type:"label"}` segment; `cli/book.js`: render label type as plain block |

---

## Ready for Cowork review — Batch 14 (2026-06-15)

Serving at **http://localhost:8081** (cache: `pwc-95240ba1`).

This batch is tooling-only — no web UI or data changes. Spot-check via terminal:

### `make test-full`

Should run ~1100 structural checks (550 dates × MP+EP) in ~25 seconds and print:

```
Checking 1100 offices (550 dates × 2)...
All 1100 checks passed.
```

### `make test-smoke`

Should run 4 smoke cases (Easter MP/EP, Lent MP, Feast Day MP). Each prints structural pass. Citation checks may print `SKIP citation check` if lectionary.anglican.ca doesn't have data for 2026 dates yet — that is expected and is a skip, not a failure. Should exit 0.

### `make test-seasonal`

Same as above — 26 cases. Should exit 0.

### `make test`

Should run Vitest (108) + pytest — no Go tests any more. Should pass.

### Go is gone

`go.mod`, `go.sum`, and all `*.go` files deleted. `go test` is no longer in `make test`. No other functional changes.

---

## Ready for Cowork review — Batch 13 (2026-06-15)

Serving at **http://localhost:8081** (cache: `pwc-95240ba1`).

This batch is CLI-only — no web UI changes. Spot-check via terminal:

### `node cli/book.js ordinary-sunday-ep 2026-06-14`

Should print clean plain text of Evening Prayer in order:
- "The Gathering of the Community" → Introductory Responses (3 versicle alternatives) → doxology alternatives → Phos Hilaron hymn text (no heading — data gap)
- "The Proclamation of the Word" → Psalm 34 text (with `*` midpoints, verse numbers stripped) → doxology → [Reading: Sirach 46:11-20] → reading response → The Responsory → [Reading: Luke 12:41-48] → reading response → canticle (3 alternatives with labels+citations) → post-canticle doxology
- "Affirmation of Faith" → Apostles' Creed / Hear O Israel alternatives
- "The Prayers of the Community" → condensed intercessions rubric → litany → [Collect of the Day: 2026-06-14] → two collect alternatives
- "The Sending Forth of the Community" → Lord's Prayer → Dismissal

### `make check-book FORM=ordinary-sunday-ep DATE=2026-06-14`

Should exit 1 with a unified diff showing exactly the known data gaps (Batch 14 work list):
- Missing rubric "(One of the following may be said or sung.)" before opening doxology
- Missing "Alleluia." after each opening doxology alternative
- Missing "The Evening Hymn: 'O Gladsome Light, O Grace'" section heading
- Missing "(After the Psalm one of the following may be said or sung.)" rubric
- Missing canticle intro rubric
- "Song of the Lamb" / "Song of the Heavenly City" missing "A " prefix and wrong citations
- Missing "(One of the following Affirmations of Faith may be said or sung.)" rubric
- "Apostles' Creed" vs "The Apostles' Creed" label
- "he ascended into heaven" missing trailing comma
- Collect text has PDF line-break artifacts (multi-line vs single line)

**Pre-existing Go test failures** (`make test`): two Go unit tests fail with `cannot unmarshal array into Go value of type lectionary.sharedBlock` — introduced in Batch 11 when `opening_responses_ep_seasonal` was added as an array to `_shared`. Not caused by Batch 13. Vitest (108) and pytest pass.

---

## Batch 13 — Book-mode renderer + golden-file diff tool

**Goal**: TDD for data quality. `make check-book FORM=ordinary-sunday-ep` renders the office as clean plain text, diffs against a PDF-sourced golden file, and exits 1 on any discrepancy. This replaces manual visual diffing against the PDF.

The current `cli/office.js` is not suitable: it is missing Phos Hilaron, Affirmation of Faith, Collect, and Psalms are citation-only. Scripture shows "Loading…". The `IIIIII` artifacts are Roman-numeral tab-button labels ("I"+"II"+"III") from `renderAlternatives` bleeding through `strip()`.

---

### Commit 1 — `cli/book.js` — clean book-mode text renderer

New file. Uses the same data layer as `cli/office.js` but produces clean, complete plain text suitable for diffing against the PDF. No HTML, no markdown markers, no artifacts.

#### Output format (canonical)

Section headings: plain text line, followed by a blank line.
Subsection headings: plain text line, followed by a blank line.
Rubrics: plain text line in parentheses: `(Rubric text.)`, followed by a blank line.
Leader lines: plain text.
Response lines: plain text.
Alternatives separated by a blank line containing only `or`.
Psalm text: inline from `data/psalter.json`, one verse per line with midpoint `*`.
Scripture: single placeholder line `[Reading: Citation]` (fetching not in scope).
Blank line between each segment group.

Example output excerpt:

```
The Gathering of the Community

Introductory Responses

O Lord, I call to you; come to me quickly;
hear my voice when I cry to you.
Let my prayer be set forth in your sight as incense,
the lifting up of my hands as the evening sacrifice.

or

O God, make speed to save us.
O Lord, make haste to help us.
In your resurrection, O Christ,
let heaven and earth rejoice. Alleluia.

or

O God, be not far from us.
Come quickly to help us, O God.
Christ has triumphed over death:
O come let us worship.

(One of the following may be said or sung.)

Glory to God, Source of all being, eternal Word, and Holy Spirit:
as it was in the beginning, is now, and will be for ever. Amen.

or

Glory to the holy and undivided Trinity, one God:
as it was in the beginning, is now, and will be for ever. Amen.

or

Glory to the Father, and to the Son, and to the Holy Spirit:
as it was in the beginning, is now, and will be for ever. Amen.

The Evening Hymn: "O Gladsome Light, O Grace"

O gladsome Light, O grace of God the Father's face,
the eternal splendour wearing; celestial, holy, blest,
our Saviour Jesus Christ, joyful in your appearing.
As day fades into night, we see the evening light,
our hymn of praise outpouring, Father of might unknown,
Christ, your incarnate Son, and Holy Spirit adoring.
To you of right belongs all praise of holy songs,
O Son of God, life-giver; you, therefore, O Most High,
the world will glorify, and shall exalt for ever.
```

#### Sections to render (EP, in order)

1. **Gathering of the Community** — heading
   - Opening responses (from `form.opening_responses`, resolve shared refs)
   - Opening doxology alternatives (from data — currently missing, see data gap below)
   - Phos Hilaron / Thanksgiving for Light (`form.phos_hilaron` or `form.thanksgiving_for_light`) — render its heading from the data (the `label` or first rubric that names the hymn)
2. **Proclamation of the Word** — heading
   - Psalm heading + rubric + psalm text from `data/psalter.json` + post-psalm doxology
   - Lesson 1: `[Reading: Citation]` placeholder + reading response
   - Responsory
   - Lesson 2 (if present): same pattern
   - Canticle + post-canticle doxology
3. **Affirmation of Faith** — heading
   - `form.affirmation` content (Apostles' Creed + Hear O Israel)
4. **Prayers of the Community** — heading
   - Intercessions rubric (condensed: one rubric line)
   - Litany
   - Collect section (daily collect + seasonal + occasional if present)
5. **Sending Forth of the Community** — heading
   - Lord's Prayer (with intro)
   - Dismissal

For MP, render instead: invitatory, psalm, lessons, responsory, canticle, affirmation, prayers, dismissal (same pattern, no phos hilaron).

#### Implementation notes

- Do NOT use `renderSegments` / `renderAlternatives` from `render.js` — those produce HTML with tab UI. Write a new `textSegments(segs, shared)` function directly in `cli/book.js`.
- `textSegments` walks segments: `leader`/`response` → plain text lines; `rubric` → `(text)` parenthesised line; `alternatives` → recurse each group's segments, join groups with `\nor\n`; `shared` → resolve from `offices._shared` and recurse.
- Psalm rendering: load `data/psalter.json`, look up each psalm number, render verse text with midpoint `*`. Join multiple psalms with a blank line.
- Heading for Phos Hilaron: the `ordinary-sunday-ep` form has `phos_hilaron` as an array that begins with a `rubric` segment whose text is the hymn title (e.g., `"O Gladsome Light"`) — or a `label` field on the alternatives group. Inspect the actual data and use whatever is there. If the heading string isn't in the data, it must be added to the data (extraction fix — note in commit message as a data gap to fix in Batch 14).

---

### Commit 2 — `tests/fixtures/book/ordinary-sunday-ep.txt` — golden file ✅ Done 2026-06-14

`tests/fixtures/book/ordinary-sunday-ep.txt` written from BAS PDF (pp. 138–144). Format:

- Page headers/footers removed
- Scripture as `[Reading: Sirach 46:11-20]` / `[Reading: Luke 12:41-48]` (2026-06-14 lectionary)
- Rubrics in `(parentheses)`
- Alternatives separated by `or` on its own line
- PDF wording preserved exactly — e.g. `(After the Psalm one of the following may be said or sung.)`
- PDF capitalisation preserved — response lines after semicolons start lowercase

**Data gaps found while writing the golden file** (these are what `make check-book` will flag; fixes are Batch 14):

| # | Gap | Location in golden file |
|---|-----|------------------------|
| 1 | `(One of the following may be said or sung.)` rubric before the opening doxology alternatives is not in `_shared.doxology` data | After versicle alternatives, before doxology |
| 2 | `The Evening Hymn: "O Gladsome Light, O Grace"` section heading not in `phos_hilaron` data (only the text segments exist) | After doxology alternatives |
| 3 | `Alleluia.` after each doxology alternative in EP opening context not in data | Lines 34, 40, 46 of golden file |
| 4 | Post-psalm doxology rubric wording — needs to match `(After the Psalm one of the following may be said or sung.)` | After Psalm 34 |
| 5 | Post-canticle doxology rubric wording — needs to match `(After the Canticle one of the following may be said or sung.)` | After canticle alternatives |

The golden file is the ground truth. If `cli/book.js` disagrees, the renderer (or data) is wrong — not the golden file.

---

### Commit 3 — `tools/compare_book.py` + `make check-book`

```python
# tools/compare_book.py
# Usage: python3 tools/compare_book.py FORM [DATE]
# FORM: e.g. ordinary-sunday-ep
# DATE: YYYY-MM-DD (defaults to today)
# Runs cli/book.js, diffs against tests/fixtures/book/FORM.txt
# Exits 0 if identical (after normalisation), 1 with unified diff if not.
```

Normalisation before diff:
- Strip leading/trailing whitespace per line
- Collapse 3+ consecutive blank lines to 2
- Normalise curly quotes to straight quotes (`'` → `'`, `"` → `"`)
- Lowercase comparison only for the diff display (not for the file output itself)

The date for `ordinary-sunday-ep` is any Sunday in ordinary time — use `2026-06-14`.

Wire into `Makefile`:
```makefile
check-book:
	python3 tools/compare_book.py $(FORM) $(DATE)
```

Add `make check-book FORM=ordinary-sunday-ep` to `make test` or at minimum document it.

---

### What this batch does NOT fix

Batch 13 only builds the tool and the first golden file. The diff output from `make check-book FORM=ordinary-sunday-ep` will enumerate all remaining issues (missing sections, wrong rubric text, capitalisation, artifacts). Those become the Batch 14 work list.

---

## Batch 14 — Drop Go; port tests to Node

Go is now a fork. `internal/office/office.go` is a separate Markdown renderer that has diverged from `web/render.js` + `cli/book.js`. Two renderers means bugs live in the gap. Go tests are broken. Drop Go entirely; port coverage to Node + existing Playwright/Vitest.

**What exists in Go and what it maps to:**

| Go test | Coverage | Port to |
|---------|----------|---------|
| `golden_test.go` | Snapshot diff | Already replaced by `make check-book` |
| `full_test.go` | All dates × MP+EP structural check | `tools/test_full.js` |
| `smoke_test.go` | 4 key dates: structural + reading citation check vs lectionary.anglican.ca | `tools/test_eval.js --smoke` |
| `seasonal_test.go` | 28 seasonal cases: structural + reading citation check | `tools/test_eval.js --seasonal` |
| `season_test.go` / `forms_test.go` | Season/form unit logic | Already covered by Playwright `data-season` checks in `tests/e2e/office.spec.js` — no new tests needed |

Note: despite the Makefile comment, `verifyReadings()` does NOT call an LLM. It string-matches citations fetched from `lectionary.anglican.ca` against renderer output. `ANTHROPIC_API_KEY` comment in Makefile is stale — remove it.

---

### Commit 1 — `tools/test_full.js`

Port `e2e/full_test.go`. Walks all lectionary JSON files in `data/lectionary/`, runs `node cli/book.js <form> <date>` for each date (MP and EP), checks required sections are present in stdout.

Required sections to check (plain text, not Markdown):
- `The Gathering of the Community`
- `The Proclamation of the Word`
- `The Psalm`
- `The Prayers of the Community`
- `The Lord's Prayer`
- `The Sending Forth of the Community`

Exit 0 if all pass, exit 1 with a summary of failures.

Wire into Makefile:
```makefile
test-full:
	node tools/test_full.js
```

---

### Commit 2 — `tools/test_eval.js`

Port `e2e/smoke_test.go` + `e2e/seasonal_test.go` + `e2e/lectionary_fetch_test.go`.

Fetches `https://lectionary.anglican.ca/?date=YYYY-MM-DD`, parses the `id='lectionary_MP'` / `id='lectionary_EP'` elements for psalm and reading citations, checks they appear in `cli/book.js` output. Skip (not fail) if the site is unreachable.

Smoke cases (4):
- Easter MP/EP: `2026-04-05`
- Lent MP: `2026-03-08` — also assert "alleluia" absent
- Feast day MP: `2026-05-15` (Saint Matthias)

Seasonal cases: copy `seasonalCases` array from `e2e/seasonal_test.go` verbatim (28 cases, dates already verified).

Usage:
```
node tools/test_eval.js --smoke      # 4 cases, fast
node tools/test_eval.js --seasonal   # 28 cases
```

Wire into Makefile:
```makefile
test-smoke:
	node tools/test_eval.js --smoke

test-seasonal:
	node tools/test_eval.js --seasonal
```

---

### Commit 3 — Delete Go; update Makefile

Delete:
- All `*.go` files in repo root, `internal/`, `cmd/`, `e2e/`, `tools/diag_citations.go`
- `go.mod`, `go.sum`

Update `Makefile`:
- `test` target: remove `go test ./...` — becomes just `npm test` + `make test-tools`
- Remove `update-golden` target (replaced by `make check-book`)
- Remove stale `ANTHROPIC_API_KEY` comment from `test-smoke` / `test-seasonal`
- Update `.PHONY` line to remove `update-golden`

Update `CLAUDE.md`:
- Remove Go package table
- Remove `go test -run TestName ./...` from Commands section
- Update architecture section: CLI is now `cli/book.js` and `cli/office.js` (Node); no Go
- Remove `kjv_embed.go` reference (KJV is out of scope for this contemporary prayer app)

---

## Batch 16 — Programmatic golden files for all 31 forms

**Goal**: Replace the hand-copied `tests/fixtures/book/ordinary-sunday-ep.txt` with programmatically extracted golden files for all 31 forms. Golden files are generated from the source PDF (never committed — gitignored), so `make check-book` works for any form without manual transcription.

---

### Commit 1 — `tools/extract_form_text.py`

New tool. Extracts the plain-text golden file for a given form directly from the PDF, using the existing `OFFICES` page-range table and `_page_styled_lines` classifier from `extract_offices.py`.

**Usage**:
```
python3 tools/extract_form_text.py <form>
# e.g. python3 tools/extract_form_text.py ordinary-sunday-ep
# Writes tests/fixtures/book/<form>.txt
```

**Implementation**:

Import `_page_styled_lines`, `_char_type`, and `OFFICES` from `extract_offices.py` (move them to `extract_lib.py` if not already there to avoid circular imports). Open `sources/pray-without-ceasing.pdf` with pdfplumber, walk only the pages for the given form.

**Line-by-line rendering rules** (produce the same format as the hand-written golden file):

| Classified type | Output |
|----------------|--------|
| `footer` | skip |
| `heading` (major section) | strip via `_MAJOR_HDRS` regex; if a sub-section heading remains, emit as plain line + blank line |
| `heading` (sub-section only) | emit as plain line + blank line |
| `rubric` where text matches `^Or$` (case-insensitive) | emit as blank line + `or` + blank line (alternatives separator) |
| `rubric` | emit as `(text)` + blank line |
| `leader` | emit as plain line |
| `response` | emit as plain line |
| blank separator between content blocks | emit as blank line |

**Special sections**:
- **Psalm**: when the heading `The Psalm` is encountered, emit the heading, then emit the rubric, then look up the psalm number in the following text and render from `data/psalter.json` (same as `cli/book.js` — verse text with `*` midpoints, no verse numbers). This ensures the golden file matches the renderer's psalm format, not the PDF's.
- **Scripture readings**: when a line matches a lectionary citation pattern (e.g. `Sirach 46:11-20`, `Luke 12:41-48`), emit as `[Reading: Citation]`. The script takes an optional `--date YYYY-MM-DD` argument to look up the actual citations from the lectionary JSON; defaults to `2026-06-14` for `ordinary-sunday-ep`, or the form's representative date from `SEASONAL_DATES` (see below).
- **Collect**: emit as `[Collect of the Day: DATE]` placeholder.

**`SEASONAL_DATES`** — default date per form (for lectionary lookup):
```python
SEASONAL_DATES = {
    "advent-mp":             "2026-11-29",
    "advent-ep":             "2026-11-29",
    "christmas-mp":          "2025-12-28",
    "christmas-ep":          "2025-12-28",
    "epiphany-mp":           "2026-01-11",
    "epiphany-ep":           "2026-01-11",
    "lent-mp":               "2026-03-08",
    "lent-ep":               "2026-03-08",
    "passiontide-mp":        "2026-03-29",
    "passiontide-ep":        "2026-03-29",
    "easter-mp":             "2026-04-19",
    "easter-ep":             "2026-04-19",
    "pentecost-mp":          "2026-05-24",
    "pentecost-ep":          "2026-05-24",
    "allsaints-mp":          "2026-11-01",
    "allsaints-ep":          "2026-11-01",
    "ordinary-sunday-mp":    "2026-06-14",
    "ordinary-sunday-ep":    "2026-06-14",
    "ordinary-monday-mp":    "2026-06-15",
    "ordinary-monday-ep":    "2026-06-15",
    "ordinary-tuesday-mp":   "2026-06-16",
    "ordinary-tuesday-ep":   "2026-06-16",
    "ordinary-wednesday-mp": "2026-06-17",
    "ordinary-wednesday-ep": "2026-06-17",
    "ordinary-thursday-mp":  "2026-06-18",
    "ordinary-thursday-ep":  "2026-06-18",
    "ordinary-friday-mp":    "2026-06-19",
    "ordinary-friday-ep":    "2026-06-19",
    "ordinary-saturday-mp":  "2026-06-20",
    "ordinary-saturday-ep":  "2026-06-20",
}
```

---

### Commit 2 — Gitignore golden files; remove committed file

Add to `.gitignore`:
```
tests/fixtures/book/
```

Remove `tests/fixtures/book/ordinary-sunday-ep.txt` from git tracking:
```
git rm --cached tests/fixtures/book/ordinary-sunday-ep.txt
```

The file stays on disk (gitignored) but is no longer committed. BAS copyright is no longer in the repo.

---

### Commit 3 — Update `tools/compare_book.py` + `make check-book`

Update `compare_book.py` to auto-generate the golden file if it doesn't exist:

```python
golden = Path(f"tests/fixtures/book/{form}.txt")
if not golden.exists():
    subprocess.run(
        ["python3", "tools/extract_form_text.py", form, "--date", date],
        check=True
    )
```

Update `Makefile` — add a `generate-golden` target for bulk generation:
```makefile
generate-golden:
	for form in $(shell python3 -c "from tools.extract_offices import OFFICES; print(' '.join(o[0] for o in OFFICES))"); do \
		python3 tools/extract_form_text.py $$form; \
	done
```

---

### Commit 4 — Verify all 31 forms pass

Run `make generate-golden` then `make check-book` for all 31 forms. Fix any normalisation mismatches between `extract_form_text.py` output and `cli/book.js` output — these are real bugs. One commit per fix, clearly labelled as renderer or extractor.

The target: all 31 forms exit 0.

---

### What this batch does NOT do

Does not change `offices.json`, the web app, or any rendering logic. All fixes in Commit 4 are normalisation issues in the new extraction tool or genuine bugs in the renderer — not in the data pipeline.

---

## Batch 15 — Data quality fixes from `make check-book` diff

Run `make check-book FORM=ordinary-sunday-ep DATE=2026-06-14`. The diff output is the work list. Fix each discrepancy — either in the renderer (`cli/book.js`) or in the source data (via `tools/extract_offices.py` `_TEXT_PATCHES`, or `data/patches.json` if wording-only). Re-run until diff is clean.

Known gaps from golden file authoring (Batch 13 Commit 2 notes):

| # | Gap | Fix location |
|---|-----|-------------|
| 1 | `(One of the following may be said or sung.)` rubric before opening doxology missing from data | Add as rubric segment to `_shared.doxology` in `extract_offices.py`, re-extract |
| 2 | `The Evening Hymn: "O Gladsome Light, O Grace"` heading missing from `phos_hilaron` | Add `label` or leading rubric to phos hilaron data in extractor; if wording-only, use `_TEXT_PATCHES` |
| 3 | `Alleluia.` after each EP opening doxology alternative not in data | EP-context only — either add to `_shared.doxology` as EP variant or emit in renderer when rendering EP opening responses |
| 4 | Post-psalm doxology rubric wording | Inspect data; if missing, add rubric segment to psalm doxology in extractor |
| 5 | Post-canticle doxology rubric wording | Same pattern |

**Approach**: Run diff first. Fix only what the diff flags — don't speculate. One commit per logical fix. Re-run `make check-book` after each commit. Stop when diff exits 0.

**Constraint**: Never edit `data/*.json` directly. All fixes go through `tools/extract_offices.py` (`_TEXT_PATCHES` list) or `data/patches.json`. Re-extract after any extractor change.

---

## Follow-up investigation — Extraction pipeline portability

**Question**: Can the full extraction pipeline (`make extract`) be made self-contained and portable — runnable by any contributor without manual PDF acquisition or system-specific Python setup?

**Current state**: Requires Homebrew Python 3, manual PDF downloads, possibly system deps. `make fetch-sources` exists but may not cover everything. PDFs are copyrighted and can't be committed.

**Investigate**:
- What does `make fetch-sources` actually download? Is it sufficient for a clean run?
- What Python packages are required? Can a `requirements.txt` or `pyproject.toml` make this reproducible?
- Are there any macOS-specific assumptions (path, encoding, `sed -i ''`)?
- Could a `Dockerfile` or `devcontainer.json` wrap the pipeline for portability without committing copyrighted sources?

Output of investigation: a short write-up in this HANDOFF or a new `docs/EXTRACTION.md` listing blockers and recommended approach.

---

## Batch 12 — BUG-02 season bounds hardening

One commit. No app change — Python tooling only.

### Context

`detect_bounds()` in `tools/convert_lectionary.py` uses `in` substring matching to find liturgical season boundaries in ACC CSV rows (e.g., `"first sunday of advent" in desc`). If ACC changes wording in a future CSV export, bounds silently fail to set. The existing assertion catches a completely missing key, but not a subtle wording shift.

### Commit 1: Canonical expected-wording list in `detect_bounds()`

Replace the ad-hoc `in` checks with a `CANONICAL_BOUNDS` dict. For each bound key, define the exact lowercase substring(s) expected to appear in the CSV name field. Match exactly first; if only a fuzzy match is found, record the bound but emit a `sys.stderr` warning so future re-extractions surface the change.

**`tools/convert_lectionary.py`** — at module level, add:

```python
# Expected lowercase substrings in CSV name field for each season boundary.
# If ACC changes wording, detect_bounds() will warn rather than silently accept.
CANONICAL_BOUNDS_PHRASES = {
    "advent_i":      ["first sunday of advent"],
    "christmas":     ["birth of the lord"],
    "epiphany":      ["baptism of the lord"],
    "presentation":  ["presentation of the lord", "presentation of our lord"],
    "ash_wednesday": ["ash wednesday"],
    "passiontide":   ["fifth sunday in lent"],
    "palm_sunday":   ["palm sunday"],
    "easter":        ["easter day", "sunday of the resurrection"],
    "ascension":     ["ascension of the lord"],
    "pentecost":     ["day of pentecost"],
    "trinity_sunday":["trinity sunday"],
    "all_saints":    ["all saints"],
}
```

Rewrite `detect_bounds()` to use this dict. Logic per row:
1. `desc = first_line(clean(row[1])).lower()`
2. For each key not yet in `bounds`, check if any canonical phrase is an exact `==` match to `desc`, or `desc.startswith(phrase)`. If yes → set bound, move on.
3. If no exact match, fall back to `in` check. If that matches → set bound AND `print(f"WARNING: detect_bounds: '{key}' matched via fuzzy substring; expected one of {phrases!r}, got {desc!r}", file=sys.stderr)`.
4. Advent counter logic (two occurrences for `advent_i` / `advent_ii`) preserved.

Keep the existing `_REQUIRED_BOUNDS` assertion after the function — it's still the hard stop.

Add a pytest test in `tools/tests/` that constructs synthetic rows with exact canonical strings and asserts all 12 keys are found without warnings. Add a second test with a slightly-off wording string and asserts the key is found AND a warning was emitted (capture `sys.stderr`).

---

## Ready for Cowork review — Batch 11 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-c46c42f1`).

### What to spot-check

**BUG-23 — Seasonal EP opening responses restored**

- `http://localhost:8081/#/2025-12-03/ep` (Advent EP) — "Introductory Responses" subsection must appear under "The Gathering of the Community"
- `http://localhost:8081/#/2026-02-25/ep` (Lent EP) — same, Introductory Responses visible
- `http://localhost:8081/#/2026-05-20/ep` (Pentecost EP) — same
- `node cli/office.js ep 2025-12-03` — "## Opening Responses" section present in CLI output

**BUG-24 — CLI feast-day morning psalms**

- `node cli/office.js mp 2026-06-11` (Saint Barnabas — a feast with `psalm_sets`) — "## Psalm" line shows psalm citations, not "[object Object]" or empty

**Tests**

- `make test` — should pass: 108 Vitest + 143 pytest + Go
- New Vitest describe `all forms: shared-ref fields render non-empty HTML` — 62 tests covering `opening_responses` and `reading_response` for all 31 forms
- New pytest `test_opening_responses_resolves` — 31 parametrized cases, all passing

---

## Batch 11 — BUG-23 + BUG-24 hot-fix — Done

**BUG-23 (P0):** All 7 seasonal EP forms (`advent-ep` through `pentecost-ep`) silently drop Opening Responses. BUG-14 moved `opening_responses` to a shared ref dict; `app.js` line ~919 checks `.length` on it → undefined → section skipped. Same failure mode as BUG-19.

### Commit 1: Fix shared-ref resolution for `opening_responses` — `web/app.js` + `cli/office.js`

**`web/app.js`** — find the opening_responses block (~line 919):

```js
// Before:
if (form.opening_responses && form.opening_responses.length)
  html += renderSubsection('Introductory Responses', form.opening_responses, shared);

// After:
let openingResponses = form.opening_responses;
if (openingResponses?.type === 'shared' && shared)
  openingResponses = shared[openingResponses.key];
if (openingResponses && openingResponses.length)
  html += renderSubsection('Introductory Responses', openingResponses, shared);
```

**`cli/office.js`** — update the `section()` helper to resolve shared refs:

```js
// Before:
function section(title, segs) {
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}

// After:
function section(title, segs) {
  if (segs?.type === 'shared' && shared) segs = shared[segs.key];
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}
```

**Commit message:** `fix(ui): resolve shared ref for opening_responses in seasonal EP — BUG-23`

---

### Commit 2: Fix CLI psalm_sets fallback — `cli/office.js` (BUG-24)

Feast days store morning psalms as `psalm_sets` (array of arrays) not `psalms`. Update the psalm rendering line:

```js
// Before:
if (officeData?.psalms) out += `\n## Psalm\n${officeData.psalms.join(', ')}\n`;

// After:
const psalms = officeData?.psalms ?? officeData?.psalm_sets?.[0];
if (psalms) out += `\n## Psalm\n${(Array.isArray(psalms[0]) ? psalms[0] : psalms).map(p => typeof p === 'object' ? p.citation : p).join(', ')}\n`;
```

**Commit message:** `fix(cli): fall back to psalm_sets[0] for feast-day morning psalms — BUG-24`

---

### Commit 3: Add render-level Vitest test — `tests/unit/render.test.js`

The existing form-completeness test accepted shared refs as valid data without verifying the rendering code handles them. Add a render-level test for every field that can be a shared ref:

```js
describe('all forms: shared-ref fields render non-empty HTML', () => {
  test.each(forms)('%s opening_responses', (name, form) => {
    let or = form.opening_responses;
    if (or?.type === 'shared') or = shared[or.key];
    const html = renderSubsection('Introductory Responses', or, shared);
    expect(html, `${name} opening_responses rendered empty`).toBeTruthy();
  });

  test.each(forms)('%s reading_response', (name, form) => {
    // lessonHtml already tested elsewhere but confirm shared ref resolves
    let rr = form.reading_response;
    if (rr?.type === 'shared') rr = shared[rr.key];
    expect(Array.isArray(rr) ? rr.length : rr?.groups?.length,
      `${name} reading_response resolves to empty`).toBeGreaterThan(0);
  });
});
```

**Rule going forward:** any field that can hold a shared ref needs a render-level test, not just a data-structure check.

**Commit message:** `test(unit): render-level tests for shared-ref fields — catches BUG-23 class`

---

### Commit 4: Add regression test to `tools/tests/test_form_completeness.py`

Add a test that catches shared refs that fail to resolve:

```python
@pytest.mark.parametrize('name,form', forms)
def test_opening_responses_resolves(name, form):
    or_val = form.get('opening_responses')
    if isinstance(or_val, dict):
        assert or_val.get('type') == 'shared', f'{name}.opening_responses has unexpected dict type'
        key = or_val.get('key')
        assert key in shared, f'{name}.opening_responses refs missing shared key: {key}'
        assert isinstance(shared[key], list) and len(shared[key]) > 0, \
            f'{name}.opening_responses shared[{key!r}] is empty or not a list'
    else:
        assert isinstance(or_val, list) and len(or_val) > 0, \
            f'{name}.opening_responses must be non-empty list, got {type(or_val).__name__}'
```

Also add `shared` to the module-level setup:
```python
shared = offices.get('_shared', {})
```

**Commit message:** `test(tools): assert opening_responses resolves — catches BUG-23 class`

---

## Ready for Cowork review — Batch 10 + BUG-21 + BUG-14 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-4d284323`).

### What to spot-check

**Batch 10 — SW hot-fix**

- `http://localhost:8081/sw.js` — confirm `skipWaiting` is gone and `'/'` is not in the SHELL array
- `http://localhost:8081/` — app loads normally; no JS errors in console
- Check that the SW registers (DevTools → Application → Service Workers): status should be "activated and running" after page load
- On a second visit (no `?reset`), confirm the app still loads (not a blank page)

**BUG-21 — CLI field names fixed**

- `node cli/office.js mp 2026-06-17` — should show `## Psalm` and `## Lesson 1` / `## Lesson 2` sections with reading heading ("The Reading: …") and reading response (I / II / III tabs)
- `node cli/office.js ep 2026-06-17` — same structure for EP

**BUG-14 — EP opening_responses deduplicated**

- `make check-integrity` passes (already confirmed)
- `node cli/office.js ep 2025-12-03` (Advent EP) — confirm office renders; opening responses shown
- In offices.json `_shared`, confirm key `opening_responses_ep_seasonal` now exists with the 7 identical EP forms sharing it; advent-ep through pentecost-ep all reference it; allsaints-ep still has its own inline array

---

## Batch 10 — SW hot-fix (P0, deploy broken) — Done

**Deploy is currently broken.** Users who had the site open before the June 14 deploy see a blank "Loading…" page. Only `?reset` recovers them. Future deploys will reproduce this unless fixed.

### Root cause

`self.skipWaiting()` in `sw.js` causes the new SW to activate immediately, bypassing the normal wait-for-tabs-close lifecycle. During its `install` event, the new SW runs `addAll([..., '/', ...])` — fetching and caching `index.html` from the CloudFront edge. CloudFront invalidation takes 30–60+ seconds to propagate; during that window, the edge may still serve the **old** `index.html` (without `type="module"`). The new SW caches this stale HTML.

Once cached:
1. `clients.claim()` fires → `controllerchange` → `location.reload()`
2. Reload: new SW serves `'/'` from its cache → **old index.html** (no `type="module"`)
3. Old index.html loads `app.js` as a classic script
4. New `app.js` has `import { … } from './render.js'` at line 3 → `SyntaxError` in classic-script context
5. JS execution halts before the `controllerchange` listener is registered
6. Page stays in the initial "Loading…" DOM state forever
7. Refreshing makes it worse: SW keeps serving the stale cached `index.html`

### Fix (2 commits)

#### Commit 1: Remove `skipWaiting`, remove `'/'` from precache — `web/sw.js`

Replace entire `sw.js` with:

```js
'use strict';

const CACHE = 'pwc-v1'; // make build stamps this with a content hash

// Shell files cached on install. index.html ('/')  is intentionally excluded —
// it must always be fetched from the network so a stale CF edge never poisons
// the SW cache with an old HTML structure (e.g. missing type="module").
const SHELL = [
  '/app.js',
  '/render.js',
  '/office.css',
  '/manifest.json',
  '/data/offices.json',
  '/data/collects.json',
  '/data/season_bounds.json',
  '/data/psalter.json',
  '/data/fats/saints.json',
];

self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL))
  );
  // No self.skipWaiting() — new SW waits until all tabs running the old SW
  // are closed. This prevents the stale-HTML / module-import race on deploy.
});

self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', evt => {
  if (evt.request.method !== 'GET') return;
  const url = new URL(evt.request.url);
  if (url.origin !== location.origin) return;

  // Never intercept index.html — let the browser fetch it fresh every time.
  if (url.pathname === '/' || url.pathname === '/index.html') return;

  // Everything else: network-first with cache fallback (offline support).
  evt.respondWith(networkFirst(evt.request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('Offline', { status: 503 });
  }
}
```

**Commit message:** `fix(sw): remove skipWaiting and '/' from precache — prevents blank page on deploy`

---

#### Commit 2: Remove `controllerchange` → reload hack from `app.js`

In `web/app.js`, find the SW registration block (around line 1349):

```js
// Before:
if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  navigator.serviceWorker.addEventListener('controllerchange', () => location.reload());
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// After:
if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
```

The `controllerchange` reload was compensating for `skipWaiting`. Without `skipWaiting`, the new SW never takes over a live page mid-session, so the reload is both unnecessary and harmful (could cause reload loops if `controllerchange` fires at other times).

**Commit message:** `fix(ui): remove controllerchange reload — was compensating for skipWaiting`

---

### How to reproduce the old bug (for verification)

Before fixing, to confirm the bug:
1. Temporarily add `// location.hostname !== 'localhost' &&` to disable the localhost SW guard
2. `make build && make serve-dist` → visit `localhost:8081`, confirm SW registers
3. Make any trivial change (e.g. add a comment to `app.js`), rebuild → new cache hash
4. Refresh `localhost:8081` without doing `?reset` → blank "Loading…" page
5. Revert the localhost guard change

After fixing, steps 3–4 should show the old (working) version rather than blank page. Users see last-known-good content until they close all tabs and reopen.

### Post-deploy recovery for stuck users

Stuck users need `?reset`. The escape hatch (`/?reset`) already exists and works. No changes needed. Update help text or add a visible link in the error state if desired.

---

## Code work queue

Do in this order. Do not skip ahead.

| Batch | What | Status |
|-------|------|--------|
| **11** | BUG-23 + BUG-24 — seasonal EP opening responses + CLI psalm_sets | **Ready for Code** |
| **10** | SW hot-fix — blank page on deploy | Done |
| **7** | BUG-19 critical fix — reading response + Lord's Prayer + Go CLI | Done |
| **8** | JS render module + Node CLI + Vitest | Done |
| **9** | Rubrics redesign | Done |

---

## Ready for Cowork review — Batches 7 + 8 + 9 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-7740deb7`).

### What to spot-check

**Batch 7 — BUG-19 reading response + Lord's Prayer fix**

- `http://localhost:8081/#/2026-06-17/mp` (ordinary-time, Wednesday)
  - ✓ Reading response tab strip (I / II / III) appears after each lesson
  - ✓ "The Lord's Prayer" subsection visible in the Prayers section
- `http://localhost:8081/#/2026-02-25/mp` (Lent, seasonal)
  - ✓ Reading response tabs present after lesson
- Go CLI no longer crashes: `node cli/office.js mp 2026-06-17`

**Batch 8 — render.js module + Node CLI + Vitest**

- `http://localhost:8081/render.js` — served (should not 404)
- `http://localhost:8081/#/2026-05-17/mp` (Seventh Sunday of Easter)
  - ✓ App loads normally — no JS errors in console
  - ✓ All tabs, alternatives, readings render as before
- `http://localhost:8081/#/2026-06-17/ep` (ordinary-time EP)
  - ✓ Phos hilaron, canticle, readings all render
- Node CLI: `node cli/office.js ep 2026-02-25` should print Lent EP in plain text
- `make test` passes (vitest 48 + pytest 113 + Go)

**Batch 9 — Rubrics redesign**

- `http://localhost:8081/#/2026-06-17/mp` (ordinary-time, Wednesday)
  - ✓ "The Responsory is said or sung." rubric is suppressed
  - ✓ "The Litany is said or sung." rubric is suppressed
  - ✓ Intercessions block replaced with single italic line: "Offer intercessions, petitions, and thanksgivings, silently or aloud."
- `http://localhost:8081/#/2026-06-17/ep` (ordinary-time, Wednesday EP)
  - ✓ Same intercessions condensing visible
- `http://localhost:8081/#/2025-12-03/mp` (Advent MP)
  - ✓ "Morning Prayer may conclude with the following Sentence." suppressed
  - ✓ "The Responsory is said or sung." suppressed

---

## Code work queue

Do in this order. Do not skip ahead.

| Batch | What | Status |
|-------|------|--------|
| **7** | BUG-19 critical fix — reading response + Lord's Prayer + Go CLI | Done |
| **8** | JS render module + Node CLI + Vitest | Done |
| **9** | Rubrics redesign | Done |

---

## Batch 7 — BUG-19 critical fix

**All three issues are caused by `normalize_offices.py` converting inline segment arrays to shared ref dicts without corresponding support in the rendering layer. Fix all three before any other work.**

Confirmed broken on `localhost:8080/#/2026-06-17/mp` (2026-06-14): reading response absent after lesson, Lord's Prayer absent before Collect.

### Commit 1: Remove lords_prayer normalization

**File:** `tools/normalize_offices.py`

Delete the entire lords_prayer block (currently lines ~67–82):

```python
# ── lords_prayer_ordinary ─────────────────────────────────────────────────
ordinary_forms = {k: v for k, v in forms.items() if 'ordinary' in k and 'lords_prayer_intro' in v}
if ordinary_forms:
    vals = list(ordinary_forms.values())
    canonical = vals[0]['lords_prayer_intro']
    if all(blocks_equal(f['lords_prayer_intro'], canonical) for f in vals):
        key = 'lords_prayer_ordinary'
        if key not in shared:
            shared[key] = canonical
            print(f'  + shared.{key} ({len(ordinary_forms)} forms)')
        for k in ordinary_forms:
            if not isinstance(data[k].get('lords_prayer_intro'), dict) or data[k]['lords_prayer_intro'].get('type') != 'shared':
                data[k]['lords_prayer_intro'] = {'type': 'shared', 'key': key}
                changed += 1
    else:
        print('  WARNING: lords_prayer_intro not identical across ordinary forms — skipping')
```

After deletion: `lords_prayer_ordinary` disappears from `_shared`; `lords_prayer_intro` stays as an inline segment array in all ordinary-time forms.

**Why this fixes things:**
- Removes the raw JSON array from `_shared` → Go's `sharedBlock` can now parse `_shared` → CLI works
- Restores `lords_prayer_intro` to an array in all forms → `.length` check passes → Lord's Prayer renders

**Commit message:** `fix(tools): remove lords_prayer_ordinary normalization — breaks Go CLI and web rendering`

---

### Commit 2: Resolve shared ref in `lessonHtml()`

**File:** `web/app.js`, in `lessonHtml()` (around line 844)

```js
// Before:
const readingResponse = (form && form.reading_response) || READING_RESPONSE;

// After:
let readingResponse = (form && form.reading_response) || READING_RESPONSE;
if (readingResponse?.type === 'shared' && shared) {
  readingResponse = shared[readingResponse.key] || READING_RESPONSE;
}
```

**Why:** `form.reading_response` is always `{type:'shared', key:'...'}` (set by normalize). `renderAlternatives()` checks `seg.groups` — a shared ref has no `groups` → returns `''`. Adding resolution here passes the actual `{type:'alternatives', groups:[...]}` block to `renderAlternatives()`.

**Commit message:** `fix(ui): resolve shared ref in lessonHtml so reading response renders`

---

### Commit 3: Re-extract data

```bash
make extract
```

Verify before committing:
- `data/offices.json` `_shared` no longer has `lords_prayer_ordinary`
- All ordinary-time forms have `lords_prayer_intro` as an inline array (not dict)
- `make check-integrity` passes
- `make check-text` zero findings

**Commit messages:**
1. `chore(data): re-extract after removing lords_prayer normalization`
2. `chore(tools): update extract manifest`

---

### Commit 4: Data-layer form completeness test

**New file:** `tools/tests/test_form_completeness.py`

```python
"""Verify every office form in offices.json has all required sections.

BUG-19 was caused by normalize_offices.py converting lords_prayer_intro
from an array to a shared ref dict, silently breaking .length checks.
This test catches that class of regression immediately.
"""
import json, pytest
from pathlib import Path

DATA = Path(__file__).parent.parent.parent / 'data' / 'offices.json'

with open(DATA) as f:
    offices = json.load(f)

forms = [(k, v) for k, v in offices.items() if not k.startswith('_')]

@pytest.mark.parametrize('name,form', forms)
def test_required_sections_are_arrays(name, form):
    for field in ('opening_responses', 'lords_prayer_intro', 'dismissal'):
        assert isinstance(form.get(field), list), \
            f'{name}.{field} must be a list, got {type(form.get(field)).__name__}'
        assert len(form[field]) > 0, f'{name}.{field} is empty'

@pytest.mark.parametrize('name,form', forms)
def test_reading_response_present(name, form):
    rr = form.get('reading_response')
    assert rr is not None, f'{name} missing reading_response'
    # After BUG-19 fix, may be a shared ref dict OR inline alternatives — both ok
    # What's NOT ok is None
```

Wire into `make test-tools`:
```makefile
test-tools:
	python3 -m pytest tools/tests/ -v
```

(Already wired — just drop the new file in `tools/tests/`.)

**Commit message:** `test(tools): form completeness test — catches BUG-19 class of regression`

---

### Commit 5: Playwright regression test

**File:** `tests/e2e/office.spec.js`

Add a test block:

```js
test.describe('Reading response renders after lesson', () => {
  for (const [label, date, office] of [
    ['seasonal (Lent)', '2026-02-25', 'mp'],
    ['ordinary-time', '2026-06-17', 'mp'],
  ]) {
    test(label, async ({ page }) => {
      await page.goto(`/#/${date}/${office}`);
      // Wait for scripture to load (replaces placeholder)
      await page.waitForSelector('.scripture-placeholder:not(:has(.loading))', { timeout: 10000 });
      // Reading response tab strip must exist after the lesson
      const tabs = page.locator('.alt-tabs').first();
      await expect(tabs).toBeVisible();
      // Must have 3 options (I / II / III)
      await expect(page.locator('.alt-tab')).toHaveCount(3);
    });
  }
});

test('Lord\'s Prayer present in ordinary-time office', async ({ page }) => {
  await page.goto('/#/2026-06-17/mp');
  await expect(page.locator('.office-subsection-title', { hasText: "The Lord's Prayer" })).toBeVisible();
});
```

**Commit message:** `test(e2e): verify reading response and Lord's Prayer render`

---

## Batch 8 — JS render module + Node CLI + Vitest

**Goal:** shared rendering code between browser and Node; unit-testable rendering without Playwright; enables systematic correctness audit via CLI in the sandbox.

The rendering functions in `app.js` are already pure (data in → HTML string out, no browser APIs). This batch extracts them into a module so the Node CLI and Vitest tests can import them.

### Commit 1: Extract `web/render.js`

Create `web/render.js` as an ES module. Move these functions out of `app.js` and into it as named exports:

- `esc(s)` — HTML escape
- `parseDate(s)` — string to Date
- `seasonOf(dateStr, bounds)`
- `officeFormSeason(dateStr, bounds)`
- `seasonWeekIndex(dateStr, season, bounds)`
- `formKey(season, officeType, weekday)`
- `filterSeasonalCollects(segs, weekIdx)`
- `renderSegments(segs, shared)`
- `renderAlternatives(seg, shared, contextKey)`
- `renderSubsection(label, segs, shared)`
- `lessonHtml(lesson, shared, form)` — with the BUG-19 shared-ref fix already applied
- `READING_RESPONSE` — the hardcoded fallback constant
- `CANTICLE_SOURCE` — the canticle citation map
- `SKIP_RUBRICS` — the rubric suppression regex

In `app.js`, replace each definition with `import { ... } from './render.js'`. No behavior change to the browser — the module is a peer script, not a separate bundle.

**Commit message:** `refactor(web): extract rendering functions to web/render.js`

---

### Commit 2: Node CLI `cli/office.js`

```js
#!/usr/bin/env node
/**
 * Usage: node cli/office.js [mp|ep] [YYYY-MM-DD]
 * Renders a Daily Office to stdout using the same render.js as the browser.
 */
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderSegments, renderSubsection, lessonHtml
} from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(__dir, '..', p), 'utf8'));

const offices = load('data/offices.json');
const bounds  = load('data/season_bounds.json');

const officeType = process.argv[2] || 'mp';
const dateStr    = process.argv[3] || new Date().toISOString().slice(0, 10);

// Load lectionary for the month
const [year, month] = dateStr.split('-');
let lectionaryDay = null;
try {
  const lect = load(`data/lectionary/${year}-${month}.json`);
  lectionaryDay = lect.find(d => d.date === dateStr) || null;
} catch {}

const fSeason = officeFormSeason(dateStr, bounds);
const weekday = new Date(dateStr + 'T12:00:00Z').getUTCDay();
const weekIdx = seasonWeekIndex(dateStr, fSeason, bounds);
const key     = formKey(fSeason, officeType, weekday);
const form    = offices[key];
const shared  = offices._shared || {};

if (!form) {
  console.error(`No form found for key: ${key}`);
  process.exit(1);
}

const officeData = lectionaryDay ? lectionaryDay[officeType === 'mp' ? 'morning' : 'evening'] : null;

// Minimal text render (HTML tags stripped for readability)
function strip(html) { return html.replace(/<[^>]+>/g, '').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'); }
function section(title, segs) {
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}

let out = `# ${officeType.toUpperCase()} — ${dateStr}\n`;
out += `Season: ${fSeason} | Form: ${key}\n`;
if (lectionaryDay) out += `Day: ${lectionaryDay.name}\n`;

out += section('Opening Responses', form.opening_responses);
if (officeData?.psalm) out += `\n## Psalm\n${JSON.stringify(officeData.psalm)}\n`;
if (officeData?.lesson1) out += `\n## Lesson 1\n${officeData.lesson1}\n`;
out += section('Responsory', form.responsory);
if (officeData?.lesson2) out += `\n## Lesson 2\n${officeData.lesson2}\n`;
out += section('Canticle', form.canticle);
out += section('Intercessions', form.intercessions);
out += section('Litany', form.litany);
out += section("Lord's Prayer", form.lords_prayer_intro);
out += section('Dismissal', form.dismissal);

console.log(out);
```

**Commit message:** `feat(cli): Node CLI renders any office using same render.js as browser`

---

### Commit 3: Vitest unit tests

**New file:** `tests/unit/render.test.js`

```js
import { describe, test, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import {
  formKey, officeFormSeason, renderSegments, lessonHtml, filterSeasonalCollects
} from '../../web/render.js';

const offices = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/offices.json'), 'utf8'));
const bounds  = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/season_bounds.json'), 'utf8'));
const shared  = offices._shared || {};
const forms   = Object.entries(offices).filter(([k]) => !k.startsWith('_'));

// ── Form selection ───────────────────────────────────────────────────────────

describe('formKey', () => {
  test.each([
    ['OrdinaryTime', 'mp', 0, 'ordinary-sunday-mp'],
    ['OrdinaryTime', 'mp', 3, 'ordinary-wednesday-mp'],
    ['OrdinaryTime', 'ep', 5, 'ordinary-friday-ep'],
    ['Advent',       'mp', 3, 'advent-mp'],
    ['Easter',       'ep', 6, 'easter-ep'],
  ])('%s %s weekday=%i → %s', (season, type, day, expected) => {
    expect(formKey(season, type, day)).toBe(expected);
  });
});

describe('officeFormSeason', () => {
  test.each([
    ['2026-06-17', 'OrdinaryTime'],
    ['2025-12-03', 'Advent'],
    ['2025-12-25', 'Christmas'],
    ['2026-04-08', 'Easter'],
    ['2026-02-25', 'Lent'],
    ['2026-03-25', 'Passiontide'],
    ['2026-05-20', 'Pentecost'],
    ['2026-11-04', 'AllSaints'],
  ])('%s → %s', (date, expected) => {
    expect(officeFormSeason(date, bounds)).toBe(expected);
  });
});

// ── Form completeness (data-layer, duplicates pytest but faster) ─────────────

describe('all forms have required sections as arrays', () => {
  test.each(forms)('%s', (name, form) => {
    for (const field of ['opening_responses', 'lords_prayer_intro', 'dismissal']) {
      expect(Array.isArray(form[field]), `${name}.${field} must be array`).toBe(true);
      expect(form[field].length, `${name}.${field} must be non-empty`).toBeGreaterThan(0);
    }
    expect(form.reading_response, `${name} missing reading_response`).toBeTruthy();
  });
});

// ── Rendering ────────────────────────────────────────────────────────────────

describe('renderSegments', () => {
  test('renders leader and response', () => {
    const segs = [
      { type: 'leader',   text: 'Lord, open our lips,' },
      { type: 'response', text: 'and our mouth shall proclaim your praise.' },
    ];
    const html = renderSegments(segs, shared);
    expect(html).toContain('Lord, open our lips');
    expect(html).toContain('and our mouth shall proclaim');
  });

  test('resolves shared ref', () => {
    const segs = [{ type: 'shared', key: 'doxology' }];
    const html = renderSegments(segs, shared);
    expect(html).toContain('alt-tabs'); // doxology is an alternatives block
  });
});

describe('lessonHtml', () => {
  test('reading response renders for ordinary-time form', () => {
    const form = offices['ordinary-wednesday-mp'];
    const html = lessonHtml('Genesis 1:1-5', shared, form);
    expect(html).toContain('alt-tabs'); // response tabs present
    expect(html).toContain('The word of the Lord');
  });

  test('reading response renders for seasonal form', () => {
    const form = offices['lent-mp'];
    const html = lessonHtml('Isaiah 55:1-9', shared, form);
    expect(html).toContain('alt-tabs');
  });

  test("Lord's Prayer present in ordinary-time form", () => {
    const form = offices['ordinary-wednesday-mp'];
    const lpHtml = renderSegments(form.lords_prayer_intro, shared);
    expect(lpHtml).toContain('Our Father in heaven');
  });
});
```

**`package.json` addition** (if not already present — add vitest):
```json
{
  "type": "module",
  "devDependencies": {
    "vitest": "^1.0.0"
  },
  "scripts": {
    "test": "vitest run"
  }
}
```

**Makefile addition:**
```makefile
test-unit:
	npm test
```

**Commit message:** `test(unit): Vitest suite for rendering functions and form completeness`

---

### Commit 4: Wire into CI / Makefile

Add `test-unit` to the default `make test` chain so it runs with `make test`:

```makefile
test: test-go test-unit test-tools
```

Also run vitest in `make check-dist` before deploy.

**Commit message:** `chore: wire test-unit into make test and check-dist`

---

## Batch 9 — Rubrics redesign

**Goal:** Reduce the wall of red rubric text in Office mode. Three targeted changes to `app.js` — no data changes.

**Confirmed rubrics in the app (from offices.json audit, 2026-06-14):**

| Rubric text (truncated) | Current | Target |
|-------------------------|---------|--------|
| "Morning Prayer continues with…" | Shown | Suppress |
| "Evening Prayer continues with…" | Shown | Suppress |
| "Morning Prayer may conclude with the following Sentence." | Shown | Suppress |
| "Evening Prayer may conclude with the following Sentence." | Shown | Suppress |
| "The Responsory is said or sung." | Shown | Suppress |
| "The Litany is said or sung." | Shown | Suppress |
| "The community may offer its intercessions…" + 5 bullets | Shown in full | Condense |
| "Additional intercessions…" + 5 bullets (seasonal) | Shown in full | Condense |
| "After the Canticle one of the following may be said or sung." | Shown | Keep |
| "Either the Collect of the Day or…" | Shown | Keep |
| "The following verses may be added." | Shown | Keep |
| Period labels: "Advent 1", "Week of Easter", etc. | Shown | Keep |

Note: "continues with" variants are already partially suppressed by existing `SKIP_RUBRICS`. The gaps are "may conclude with", the two instrument rubrics, and the intercessions block.

### Commit 1: Expand `SKIP_RUBRICS`

**File:** `web/app.js`

```js
// Before:
const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$|continues with/i;

// After:
const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$|continues with|may conclude with|^The (Responsory|Litany) is said or sung\./i;
```

This suppresses:
- "Morning Prayer may conclude with the following Sentence."
- "Evening Prayer may conclude with the following Sentence."
- "The Responsory is said or sung."
- "The Litany is said or sung."

**Commit message:** `fix(ui): suppress navigation rubrics — conclude/responsory/litany`

---

### Commit 2: Condense intercessions rubric

**File:** `web/app.js`

Add a constant and update `renderSegments` to detect and condense the intercessions rubric. The intercessions rubric text always starts with "The community may offer" (ordinary-time) or "Additional intercessions" (seasonal).

Add near the top of the Office rendering section:

```js
const INTERCESSIONS_RE = /^(The community may offer|Additional intercessions)/;
const INTERCESSIONS_CONDENSED = '<p class="seg-rubric"><em>Offer intercessions, petitions, and thanksgivings, silently or aloud.</em></p>';
```

In `renderSegments`, in the segment map function, add before the existing type checks:

```js
if (seg.type === 'rubric' && INTERCESSIONS_RE.test(seg.text || '')) {
  return INTERCESSIONS_CONDENSED;
}
```

This replaces the full multi-line intercessions block (preamble + 5 weekly prayer bullets + nav text) with a single condensed italic line. Works for both ordinary-time and seasonal forms.

**Commit message:** `fix(ui): condense intercessions rubric to one line in Office mode`

---

## Completed — Batch 6 + mobile fix (deployed 2026-06-14)

Five items delivered and deployed to S3:
1. ✅ Removed "Today" text from nav (kept calendar icon)
2. ✅ Fixed stale-date banner not dismissing on navigate-to-today
3. ✅ Fixed "OrdinaryTime" → "Ordinary Time" display label
4. ✅ Added pdftotext version check to `check_data_integrity.py`
5. ✅ Fixed 5 FATS extraction artifacts (Chad, Maurice, Visitation, Boniface, Reformation Era)
6. ✅ Suppressed `#day-brand` duplicate header in mobile view

Spot-checked 2026-06-14 via computer-use screenshot on localhost:8080:
- ✓ "Ordinary Time" displays with space
- ✓ Reading section loads
- ✓ BUG-19 confirmed visually (batch 7 fixes this)

---

## Completed — Batch 5 (deployed 2026-06-07)

1. ✅ Fixed garbled collects (BAS pages 356, 358, 392, 396) — txt-fallback in `extract_collects.py`
2. ✅ Extraction manifest + data integrity guard (`tools/update_extract_manifest.py`, `tools/check_data_integrity.py`, `make check-integrity`)
3. ✅ Text quality checker (`tools/check_text_quality.py`, `make check-text`)
4. ✅ pdftotext version pinning in integrity guard

---

## Design: Notes on remaining open items

### Correctness audit (Milestone 2)

Defer until after Batch 8. The Node CLI (`cli/office.js`) makes this tractable — run it for all 30 form types and review Markdown output. Without the CLI it requires browser screenshots for each form.

### FATS minor feast readings

Design decision pending: do FATS readings show as an alternative to the BAS lectionary reading, or replace it? Check a specific minor feast live first to see what BAS prescribes (if anything) vs what FATS provides.

### RCL Daily extractor

Spec complete (see ROADMAP.md Phase 3). Unblocked but low priority until milestone 2 is done.
