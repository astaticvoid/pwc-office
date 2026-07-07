# PWC — Handoff

_Updated: 2026-07-06_

Session-to-session handoff. Claude Code owns planning, implementation, and verification end-to-end (the former Cowork review role is retired, 2026-07-05); specs are written here by planning sessions and implemented in order by later sessions.

---

## Verified — Batch 18 delivered (2026-07-06)

All nine field-trial fixes (A–I) implemented, committed one-per-fix, and pushed. Serving the built `dist/` at **http://localhost:8081**. **Not yet deployed — awaiting the owner's go-ahead.**

**Gates:** `make check-integrity` ✅ · `make test` (Vitest 113 + pytest 152) ✅ · `make check-text` ✅ · `make check-book` all **31/31 forms** ✅ · targeted E2E `tests/e2e/batch18.spec.js` **5/5** ✅ (real headless Chromium against :8081).

| Fix (bug) | What was verified | How |
|---|---|---|
| A (BUG-25) | "Holy One" restored in all 22 litany responses; 0 lowercase remain (grep 8/4/5/5) | data grep + browser (Wed litany shows "Holy One, accomplish…") |
| B (BUG-26) | No "Coll above/below" reading on 2026-06-20 EP, 06-21 MP/EP | data + browser (no such `.reading-heading`) |
| C (BUG-27) | Propers Collect surfaced as `collect_inline`; June 21 MP shows "National Indigenous Day of Prayer" / "Creator God…"; 06-20 EP resolves from next day | CLI + browser (`#prayers-collect`) |
| D (BUG-28) | "Two of the following three readings are read." shows on 06-23 MP, absent on 06-24 | browser + Vitest (load-bearing, not book-only) |
| E (BUG-32) | 2026-09-27 EP split into optional 2 Kgs + required Mt | data |
| F (BUG-33) | 14 "O Antiphon" pseudo-lessons dropped; `o_antiphon` notes retained; none render as readings | data + browser (Dec 17 EP) |
| G (BUG-29) | 0 collects and 0 seasonal-collect leaders with internal newlines; garbled pages reflowed | data + check-book 31/31 |
| H (BUG-30) | Placeholder N italic in exactly 2 litanies (tuesday-mp, saturday-ep); not inside words | browser + Vitest |
| I (BUG-31) | EP default from 15:00 | code + no test pinned 17 |

**Also fixed in passing:** BUG-34 (pre-existing `book.js` crash on 7 seasonal EP forms — shared-ref not resolved; unblocked check-book for all 31). **Found & logged, not fixed:** BUG-35 (legacy `office.spec.js` has ~12 stale failures — confirmed pre-existing, the pre-Batch-18 app fails 14 of the same; `make test-web` was also ESM-broken, now fixed).

**Next-session priority:** Batch 19 (casing oracle + prose-wrap detector), then mobile (ROADMAP §5.4). Consider refreshing BUG-35's legacy E2E selectors.

---

> **Context for implementing sessions (written 2026-07-05):** These specs were authored during a full project audit (see `docs/ASSESSMENT-2026-07.md` for reasoning and evidence). Follow them literally; where a spec says "verify", run the exact command and compare against the stated expected output. Every data-affecting fix ends with `make extract` + `make check-integrity` + `make test` — never edit `data/*.json` by hand. One commit per fix, push after each commit.

---

## Batch 18 spec — Field-trial correctness fixes (June 21/23/24 observations + audit)

Nine fixes, ordered so data-pipeline changes (A–G) come before render-only changes (H–I) and re-extraction happens once per extractor touched. Fixes A–G each change extractor output: after each, run `make extract && make check-integrity && make test && make check-text`. BUGS.md cross-references: A=BUG-25, B=BUG-26, C=BUG-27, D=BUG-28, E=BUG-32, F=BUG-33, G=BUG-29, H=BUG-30, I=BUG-31.

### Fix A — "Holy One" casing (BUG-25, P1) — `tools/extract_offices.py`

Two changes:

1. In `_DIVINE_FIXES` (≈line 260), add this entry **immediately after** the `holy ghost` entry (multi-word phrases must precede their components, and it must run before the standalone rules):
```python
    (re.compile(r'\bholy one\b', re.IGNORECASE), 'Holy One'),
```
2. In `_TEXT_PATCHES` (≈line 769), **delete** the one MP tuple (the BUG-18 entry that was based on a wrong premise):
```python
    ("ordinary-wednesday-mp", "litany",
     "Holy one, accomplish your purposes in us.",
     "holy one, accomplish your purposes in us."),
```
   **Keep** the four `ordinary-wednesday-ep` tuples ("to declare the mystery of Christ." etc.) — those are grammatical continuations, verified lowercase in the PDF (pdftotext lines 8031–8042).

**Safety notes:** `_fix_casing` only processes `type == "response"` segments, so canticle/psalm texts (where lowercase "holy one(s)" is legitimate, e.g. Ps 16 "nor let your holy one see the Pit") are untouched — they live in leader/psalm segments and in `psalter.json` (different extractor). The IGNORECASE pattern is safe *only* because of this response-segment scoping; do not copy it into a broader pass.

**Add pytest** in `tools/tests/` (follow the existing `_fix_casing` test style): a response segment `{"type": "response", "text": "holy one, accomplish your purposes in us."}` must come out `"Holy One, accomplish your purposes in us."`; a leader segment with the same text must be unchanged.

**Verify after re-extract** (expected counts exactly):
```bash
grep -o '"Holy One, accomplish your purposes in us."' data/offices.json | wc -l   # 8
grep -o '"Holy One, make all things new."' data/offices.json | wc -l              # 4
grep -o '"Holy One, shine upon us and hear us."' data/offices.json | wc -l        # 5
grep -o '"Holy One, hear and have mercy."' data/offices.json | wc -l              # 5
grep -c '"[Hh]oly one' data/offices.json                                           # 0
```
Also update the BUG-18 note in `docs/CORRECTNESS.md`: the MP half of BUG-18 is reversed (PDF says "Holy One"); the EP continuations stand.

### Fix B — Strip "Coll above/below" pseudo-lessons (BUG-26, P1) — `tools/convert_lectionary.py`

In the row-processing path where lessons are parsed (near the `LESSON_FIXES` application, ≈line 798), filter out any lesson whose citation matches `^Coll (above|below)\b` (case-sensitive; applies to both string lessons and `{"citation": …}` dicts). Do this **before** `LESSON_FIXES` is applied so future fixes see clean input. Affected entries — 2026-06-20 evening, 2026-06-21 morning, 2026-06-21 evening — currently carry the pseudo-lesson as their last element.

The dropped reference is not lost: Fix C surfaces the collect it points to.

**Add pytest**: a lessons list `["Num 14:26-45", "Acts 15:1-12", "Coll above"]` parses to 2 lessons.

**Verify after re-extract:**
```bash
grep -rn 'Coll above\|Coll below' data/lectionary/   # no matches in lessons arrays
```

### Fix C — Surface special-day propers Collect (BUG-27, P2) — `tools/convert_lectionary.py` + `web/app.js`

**Converter side.** For any day where a "Coll above/below" reference was stripped (Fix B), extract the Collect of the Day from that day's `eucharist` blob and attach it to the day entry:

- The blob format (see 2026-06-21) is: `… Collect of the Day: <collect text> Amen <next heading>: …` where subsequent headings are `Prayer over the Gifts:` and `Prayer after Communion:` and `Sentence:`.
- Regex: `r'Collect of the Day:\s*(.*?)\s*(?=Prayer over the Gifts:|Prayer after Communion:|Sentence:|$)'` with `re.DOTALL`.
- Store as `entry["collect_inline"] = {"name": entry["name"], "text": <captured text>}`. For a "Coll below" eve reference (2026-06-20 EP), the collect lives on the *next* day's blob — resolve it from the referenced day (the observance string names it: `eve_of:National Indigenous Day of Prayer`); if resolution is ambiguous, fall back to same-day blob and note it in the converter's stderr summary.
- Trim a trailing bare `Amen` into `Amen.` for consistency with `collects.json` texts.

**App side.** In `collectToggleHtml()` (`web/app.js:513`), the collect resolution currently starts from `collectRef` (`office.collect`). Add: when the office has no `collect` ref but the day entry has `collect_inline`, treat it as the Collect of the Day — same rendering path as a resolved BAS collect (`<p class="alt-source">` name + `<p class="collect-text">` text). Day-level data is already available at the call site (the day entry is what supplies `collectRef` today; pass `day.collect_inline` alongside).

**Verify:** `node cli/office.js mp 2026-06-21` shows the "Creator God, from you every family…" collect under Collect of the Day; June 21 EP likewise; 2026-06-20 EP shows it (or, if eve-resolution was skipped, the stderr note says so). Playwright not required for this batch; the batch-end self-review covers the browser check at :8081.

**Scope guard:** do NOT attempt a general propers/eucharist card in this batch. The `eucharist` field on ordinary ferias ("As Proper 12, except: …") is eucharist-specific noise for a Daily Office app. Only the collect extraction above is in scope; a general propers surface is a design decision for the owner (parked in ASSESSMENT §6).

### Fix D — Render `lessons_pick` rubric (BUG-28, P2) — `web/app.js`, `cli/book.js`, `cli/office.js`

21 days carry `lessons_pick: 2` with 3 lessons. Where the office's lessons are iterated for rendering (app.js lesson loop; both CLIs), if `office.lessons_pick` is present and `< lessons.length`, emit one rubric line **before the first lesson**:

> Two of the following three readings are read.

Generate the words from the numbers (`['one','two','three','four'][n-1]`) rather than hardcoding, but only 2-of-3 exists in current data. Use `class="seg-rubric"` (NOT `rubric-book-only` — this rubric is load-bearing in the interactive app precisely because the app does not implement pick-interaction). CLI: plain text line matching book-mode conventions.

**Verify:** `node cli/office.js mp 2026-06-23` shows the rubric before "Num 16:20-35"; a day without `lessons_pick` (2026-06-24) shows no rubric. Grep test data count: `grep -l lessons_pick data/lectionary/*.json | wc -l` → 12 files, 21 occurrences total.

### Fix E — 2026-09-27 merged citation (BUG-32, P2) — `tools/convert_lectionary.py`

Add to `LESSON_FIXES` (format precedent at line 44–50):
```python
    # CSV has "(2 Kgs 17:1-18), Mt 13:44-52" — optional citation merged with following lesson
    ("2026-09-27", "evening"): [{"citation": "2 Kgs 17:1-18", "optional": True}, "Mt 13:44-52"],
```
Check the raw CSV row first (`grep '2026-09-27' sources/bas_short_*.csv` — confirm there isn't a second non-optional lesson lost in the merge; if the CSV shows three items, include all three).

**Verify after re-extract:** the 2026-09-27 evening lessons array has 2+ entries, first optional.

### Fix F — Drop "O Antiphon" pseudo-lessons (BUG-33, P2) — `tools/convert_lectionary.py`

Same mechanism as Fix B: filter lessons whose citation is exactly `O Antiphon` (14 instances, Dec 17–23 both years). The antiphon content is already delivered as a typed `o_antiphon` note on the same dates and renders correctly (BUG-07/UX-09).

**Verify after re-extract:** `grep -c '"O Antiphon"' data/lectionary/2025-12.json data/lectionary/2026-12.json` — remaining matches are only inside `notes` text, none in `lessons` arrays. Spot-check `node cli/office.js ep 2025-12-17`.

### Fix G — Reflow collect prose (BUG-29, P3) — `tools/extract_offices.py`, `tools/extract_collects.py`

The PDF's column-width hard wraps are typographic, not semantic (evidence: breaks mid-clause, "…and who\nlives and reigns…"). Collects are prose; join their lines.

1. `extract_offices.py`: in the `seasonal_collects` block assembly, for segments of `type == "leader"` only, apply `text = re.sub(r'\s*\n\s*', ' ', text).strip()`. Do NOT touch `rubric` segments (they contain intentional bullet lists) or `response` segments.
2. `extract_collects.py`: apply the same join to every collect `text`. All 118 entries are single prose sentences ending in Amen — no intentional lineation exists (194 of their lines currently end mid-clause).

**Caution — golden files:** `make check-book` diffs CLI output against PDF-derived goldens which retain the PDF's hard wraps. After this fix, if `make check-book` fails on collect lines, regenerate goldens (`make generate-golden`) and eyeball the diff — only line-joining changes are acceptable. Mention the regeneration in the commit message.

**Verify:** `python3 -c "import json; c=json.load(open('data/collects.json')); print(sum(1 for v in c.values() if chr(10) in v['text']))"` → 0. In the app, a seasonal collect panel shows naturally wrapped prose.

### Fix H — Italicise placeholder N (BUG-30, P3) — `web/render.js`

In the segment-text render path (after `esc()`), replace standalone `N` with `<em>N</em>`: pattern `/\bN\b(?=[ ,.])/g`. Exactly 2 occurrences exist in `offices.json` (both "May N our bishop…"), verified safe — no legitimate standalone capital N elsewhere. Apply in `renderSegments` for leader/response text only (not rubrics, not scripture/psalm text, which come from different paths).

**Add Vitest case** in `tests/unit/render.test.js`: a leader segment `"May N our bishop and all bishops"` renders containing `May <em>N</em> our bishop`.

**Future (not this batch):** a settings field to substitute the diocesan bishop's name — parked in ASSESSMENT §6.

### Fix I — EP default from 15:00 (BUG-31, P3) — `web/app.js:26`

```js
return new Date().getHours() >= 15 ? 'ep' : 'mp';
```
Rationale: eve-of-feast EP begins the feast; mid-afternoon is the traditional hinge, and the field request was explicit ("Eve prayer should start at 3pm"). Check `tests/` for any test pinning 17 (none known).

### Batch 18 delivery

After all nine commits are pushed: `make check-integrity && make build && make serve-dist &`, then **self-review with browser tools at :8081** and record a "Verified" table in this file covering: June 21 MP (collect present, no "Coll above" reading, reflowed seasonal collect), June 23 MP (pick-2 rubric, italic N in Wednesday-style litany days), June 24 MP (litany "Holy One"), Dec 17 EP (no O Antiphon reading), form=ordinary-wednesday-mp (litany casing). Do not `make deploy` without the owner's go-ahead.

---

## Batch 19 spec — Data-confidence tooling (casing oracle + prose-wrap detector)

Do after Batch 18. Two additions to the quality harness; both advisory by default, `--strict` for gating. Full rationale in `docs/ASSESSMENT-2026-07.md` §4.

### 19.1 `tools/check_casing.py` — casing oracle against pdftotext

**Insight this encodes:** pdfplumber (extraction) decodes the small-caps font as lowercase; `pdftotext` (poppler) decodes the same glyphs with correct case. So `pdftotext` output is a free ground-truth oracle for casing — it would have caught all 22 BUG-25 errors *and* BUG-18's over-correction automatically.

Implementation:
1. Run `pdftotext sources/pray-without-ceasing.pdf -` once (subprocess), normalise whitespace (collapse runs, strip), keep as one big string plus a case-folded copy.
2. For every segment of type `leader`, `response`, `label` in `data/offices.json` (resolve `_shared` refs; recurse into `alternatives` groups): normalise its text the same way, then locate it in the case-folded PDF text. If found, compare the original-case slice character-by-character; report any mismatch as `office_key/section_key: "<data text>" vs PDF "<pdf text>"`.
3. Segments not found at all (edited by patches, `_TEXT_PATCHES`, or synthesized like `reading_response`) are listed under a separate "unmatched (informational)" count, not as errors. Expect the four EP BUG-18 continuation patches to appear as *mismatches* — add an explicit allowlist at the top of the script `KNOWN_INTENTIONAL = {…the four EP strings…}` with a comment pointing at BUG-18/BUG-25 evidence.
4. `make check-casing` target; wire into `make validate` chain like `check-text`. Exit 0 unless `--strict`.

**Acceptance:** running it on pre-Batch-18 data reports exactly the 22 BUG-25 strings; on post-Batch-18 data reports zero mismatches outside the allowlist.

### 19.2 Extend `tools/check_text_quality.py` — column-wrap detector

New rule: for prose-expected fields (collect texts in `collects.json`; `leader` segments inside `seasonal_collects`), any internal line ending without terminal punctuation (`,;:.!?—’”)`) is a suspected column wrap. After Batch 18 Fix G these should be zero; the rule prevents regression at the next re-extraction. Same warning/`--strict` convention as existing rules.

---

## Ready for Cowork review — Batch 17 (2026-06-17)

Serving at **http://localhost:8081** (cache: `pwc-4dda0ceb`).

### What to spot-check

| Fix | URL | Check |
|-----|-----|-------|
| Fix 1 — SC_FOOTER regex | `/?form=ordinary-sunday-ep` | Seasonal Collect II panel shows only collect text — no trailing "the Lord's Prayer" line |
| Fix 2 — Book-only rubrics (normal mode) | `/?form=ordinary-sunday-ep` | None of the listed navigation rubrics appear ("One of the following…", "The following Psalms…", "After the Canticle…", "Evening Prayer continues with…", "A Reading from the appointed lectionary…", "After a period of silent reflection…") |
| Fix 2 — Book-only rubrics (book mode) | Toggle book mode on `/?form=ordinary-sunday-ep` | All the above rubrics now appear |
| Fix 3 — Evening hymn label | `/?form=ordinary-sunday-ep` | Muted italic text `the evening hymn: "O Gladsome Light, O Grace"` appears before the Phos Hilaron stanzas (capital O in both "O Gladsome" and "O Grace") |
| Fix 4 — Collect Amen. bold | `/?form=ordinary-sunday-ep` → Seasonal Collect I or II | "Amen." at the end of the collect renders **bold** (same weight as a response line) |
| Fix 5 — Mobile scripture indentation | Any reading-heavy office at 375px viewport | Scripture verses sit flush with container edge (no left indent), same as psalm verses |

### What changed

- `web/render.js`: SC_FOOTER regex now includes U+2019 curly apostrophe; added `BOOK_ONLY_RUBRICS` constant; moved `continues with` from `SKIP_RUBRICS` to `BOOK_ONLY_RUBRICS`; updated `renderSegments` to emit `rubric-book-only` class; added `seg-label` render case; added Amen-splitting logic in leader render path; marked preamble/reflection rubrics in `lessonHtml` as `rubric-book-only`.
- `web/office.css`: Added `.seg-label` styling (muted italic subtitle); added `.rubric-book-only { display: none }` + `body.book-mode .rubric-book-only { display: block }`.
- `tools/extract_offices.py`: Extended `_apply_text_patches` to handle `label` type segments; added patch entry for `"O Gladsome Light, O Grace"` capitalisation. Re-extracted.
- Fix 5 (mobile scripture indentation): No code change — CSS already correct (`--indent: 0` at ≤520px zeroes `margin-left: var(--indent)` on `.scripture-verse`).

---

## Batch 17 spec — UI polish: rubrics, label type, collect Amen, apostrophe bug

Five fixes. Implement in order; one commit per fix.

---

### Fix 1 — SC_FOOTER regex apostrophe encoding bug (`render.js`)

`SC_FOOTER` at line 83 of `render.js` is:
```js
export const SC_FOOTER = /^the\s+Lord['']s\s+Prayer/i;
```
The two characters in `['']` are both U+0027 (straight apostrophe). The data text `"the Lord's Prayer"` uses U+2019 (right curly quote). The regex never matches, so the Lord's Prayer rubric is not stripped from Seasonal Collect II.

**Fix:** Replace the character class to include U+2019:
```js
export const SC_FOOTER = /^the\s+Lord['’]s\s+Prayer/i;
```

**Verify:** In the app on any ordinary weekday or Sunday EP, the Seasonal II collect panel should show only the collect text — no trailing "the Lord's Prayer" line.

---

### Fix 2 — Book-only rubrics: hide in normal mode, show in book mode (`render.js`, `app.js`, `office.css`)

Many rubric strings are procedural directions for reading the printed book. In the interactive app the UI already handles the "pick one" interaction via tabs; showing these rubrics is noise. In book mode (flat read-through, no tabs) they are needed.

**Pattern:** A rubric is "book-only" if it is an instruction to pick from alternatives, introduces a section that the app UI already presents structurally, or annotates the flow of the printed order.

The user identified these specific instances currently showing outside book mode:
- "One of the following may be said or sung."
- "The following Psalms from the appointed lectionary are said or sung."
- "At the end of the Psalm one of the following may be said or sung."
- "A Reading from the appointed lectionary is read."
- "After a period of silent reflection one of the following is said."
- `"The Song of Mary," "A Song of Praise," or "A Song of Christ's Glory" may be said or sung.`
- "After the Canticle one of the following may be said or sung."
- "Evening Prayer continues with an Affirmation of Faith or the Litany."
- "One of the following Affirmations of Faith may be said or sung."

**Mechanism — CSS gate (preferred over JS mode flag):**

Add a new CSS class `rubric-book-only`. In `office.css`:
```css
.rubric-book-only { display: none; }
body.book-mode .rubric-book-only { display: block; }
```

**In `render.js`:**

Add a `BOOK_ONLY_RUBRICS` constant:
```js
export const BOOK_ONLY_RUBRICS = /one of the following may be said or sung|the following psalms|at the end of the (psalm|canticle)|after the (psalm|canticle)|may be said or sung\.|one of the following affirmations|continues with|Evening Prayer continues/i;
```

In `renderSegments`, change the rubric render line to:
```js
if (seg.type === 'rubric') {
  const cls = BOOK_ONLY_RUBRICS.test(text) ? 'seg-rubric rubric-book-only' : 'seg-rubric';
  return `<p class="${cls}">${esc(text)}</p>`;
}
```

**In `app.js` / `render.js` `lessonHtml()`:**

The two hardcoded rubric strings are always emitted:
```js
const preambleRubric  = `<p class="seg-rubric">A Reading from the appointed lectionary is read.</p>`;
const reflectionRubric = `<p class="seg-rubric">After a period of silent reflection one of the following is said.</p>`;
```

Change both to use `rubric-book-only`:
```js
const preambleRubric  = `<p class="seg-rubric rubric-book-only">A Reading from the appointed lectionary is read.</p>`;
const reflectionRubric = `<p class="seg-rubric rubric-book-only">After a period of silent reflection one of the following is said.</p>`;
```

**Note:** Do NOT add these to `SKIP_RUBRICS` (which always hides). Book mode needs them.

**Verify:** Normal mode — none of the listed rubrics should appear. Book mode — all should appear.

---

### Fix 3 — Evening hymn label: render `type: "label"` + fix capitalisation (`render.js`, `offices.json` / extractor)

**Part A — renderer:** The `type: "label"` segment (evening hymn title) falls through to the default `seg-leader` render in `renderSegments`. It needs a dedicated case styled as a subtitle/label.

In `render.js` `renderSegments`, add before the default:
```js
if (seg.type === 'label') return `<p class="seg-label">${esc(text)}</p>`;
```

In `office.css`, add styling for `.seg-label`:
```css
.seg-label {
  font-family: var(--font-liturgy); font-style: italic;
  font-size: 0.95rem; color: var(--color-muted);
  margin: 0.75rem 0 0.25rem;
}
```

**Part B — capitalisation:** The data has:
```
"the evening hymn: \"o Gladsome Light, o Grace\""
```
Both `o` before `Gladsome` and `o` before `Grace` should be `O` (liturgical O of address). The fix belongs in `tools/extract_offices.py` `_TEXT_PATCHES`. Add a patch entry:

```python
('the evening hymn: "o Gladsome Light, o Grace"',
 'the evening hymn: "O Gladsome Light, O Grace"'),
```

After adding the patch, run `make extract` to regenerate and verify the label text in `offices.json`.

**Verify:** EP forms with phos_hilaron (ordinary-sunday-ep, ordinary-monday-ep through ordinary-saturday-ep, etc.) — the evening hymn heading should appear as muted italic text "the evening hymn: 'O Gladsome Light, O Grace'" before the hymn stanzas.

---

### Fix 4 — Seasonal collect "Amen." not bold (`render.js`)

Collect texts are rendered as a single `seg-leader` string. The trailing "Amen." is congregational — it should render bold like a `seg-response`.

In `render.js`, add a helper or inline logic in the collect rendering path: if a `leader` text ends with `\nAmen.` or ` Amen.`, split at the final `Amen.` and render the `Amen.` as a `<p class="seg-response">`.

The cleanest approach is a postprocessor on the collect text string, not a data change:
```js
function renderCollectText(text) {
  const amenMatch = text.match(/^([\s\S]+?)\n(Amen\.)$/);
  if (amenMatch) {
    return `<p class="seg-leader">${esc(amenMatch[1])}</p>`
         + `<p class="seg-response">Amen.</p>`;
  }
  return `<p class="seg-leader">${esc(text)}</p>`;
}
```

Apply this wherever collect text is rendered as a `leader` segment. Check both `collectHtml()` in `app.js` and anywhere `renderSegments` emits a `leader` segment whose text ends with `\nAmen.` — the latter is the more general fix.

**Verify:** Ordinary Sunday EP, Seasonal Collect I — "Amen." at the end should render bold.

---

### Fix 5 — Verify scripture indentation fixed on mobile

Cowork already added CSS (`web/office.css`):
```css
@media (max-width: 520px) {
  :root { --indent: 0; }
  .scripture-verse { grid-template-columns: 1.4rem 1fr; }
}
```

With `--indent: 0`, `margin: 0.4em 0 0.4em var(--indent)` on `.scripture-verse` becomes `margin-left: 0`. This should already be correct. Verify by loading a reading-heavy office at 375px viewport and confirming scripture verses sit flush with the container edge (same as psalm verses). If still indented, check if the scripture container has its own margin and fix accordingly.

---

### After all fixes: delivery

```bash
make check-integrity && make build && make serve-dist
```

Update `docs/HANDOFF.md` with "Ready for Cowork review — Batch 17" section listing URLs to spot-check.

---

## Ready for Cowork review — Batch 16 (2026-06-16)

**`make check-book` passes for all 31 BAS office forms.**

### What changed
- `tools/extract_form_text.py`: Added `_reclassify_headings()` — a post-merge step that re-types PDF heading lines ending with sentence punctuation as response lines, fixing page-break font artifacts in allsaints-mp (litany refrains) and christmas-mp (opening response refrains). Also fixed pentecost-mp/ep canticle doxology regex to match "At the end of either Canticle". The extractor stays PDF-only; no offices.json fallback.
- `tools/extract_manifest.json`: Updated to reflect offices.json corrections from the prior session (Apostles' Creed label, comma after "ascended into heaven", removal of `reading_response_seasonal` from `_shared`).
- `tests/fixtures/book/`: Golden files are gitignored (BAS copyright) — they live on disk locally but are not committed.

### What to spot-check at http://localhost:8081

| Form | URL | Check |
|------|-----|-------|
| All Saints MP | `/?form=allsaints-mp&date=2026-11-01` | Litany flows as one block — no spurious blank lines mid-litany |
| Christmas MP | `/?form=christmas-mp&date=2025-12-28` | "Let heaven and earth shout their praise." appears inline, not as a separate paragraph |
| Pentecost MP | `/?form=pentecost-mp&date=2026-05-24` | Canticle doxology present (Source → Trinity → Father/Son/HS order) |
| Pentecost EP | `/?form=pentecost-ep&date=2026-05-24` | Same |
| Ordinary Sunday MP | `/?form=ordinary-sunday-mp` | No regression in opening responses or litany |
| Ordinary Sunday EP | `/?form=ordinary-sunday-ep` | No regression |

### How `make check-book` works (for reference)
```
make check-book FORM=allsaints-mp    # diff golden vs book.js output
make check-book FORM=christmas-mp
# all 31:
for form in $(python3 -c "import sys; sys.path.insert(0,'tools'); from extract_offices import OFFICES; print(' '.join(r[0] for r in OFFICES))"); do python3 tools/compare_book.py $form; done
```

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
