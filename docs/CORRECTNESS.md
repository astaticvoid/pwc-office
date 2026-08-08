# PWC — Correctness Audit

_Updated: 2026-06-06. Forms audited: Saturday MP (pp. 217–223), Wednesday MP (pp. 174–181), Wednesday EP (pp. 182–188)._

_Historical record. This audit predates the pdfplumber→fitz migration, and its findings are framed in terms of mechanisms that no longer exist — the `pdftotext` casing oracle (`check_casing.py`), `_DIVINE_FIXES`, and `_TEXT_PATCHES` were all removed once fitz was shown to decode the source correctly without them (ADR 0011, issue #4). Preserved as written in June 2026; see [GitHub Issues](https://github.com/astaticvoid/pwc-office/issues) for current state._

---

## Result: ✅ Liturgical text is faithful to the source

The web app correctly renders every section of the Saturday Morning Prayer form. No errors in liturgical text were found.

---

## Section-by-section comparison

### THE GATHERING OF THE COMMUNITY

#### Introductory Responses

PDF has three alternative sets labelled "or". Web renders them correctly as three tabs (I / II / III). Content of each alternative is exact. ✓

#### Doxology options (after Responses)

PDF lists three alternatives (Source of all being / undivided Trinity / Father Son Holy Spirit). Web renders as three tabs. ✓

#### Invitatory Psalm: Psalm 100

Web text matches PDF exactly. ✓

---

### THE PROCLAMATION OF THE WORD

#### The Psalm

PDF: directs user to "A Psalm from the Daily Office Lectionary…" — no psalm text printed.  
Web: fetches and renders the actual lectionary psalm (today: Ps 55). **This is correct and the app's key value-add.**

#### After-psalm Doxology

Three alternatives rendered as tabs. ✓

#### The Reading

PDF: directs user to "A Reading from the Daily Office Lectionary…" — no reading text.  
Web: fetches and renders actual lectionary readings (Ecclesiastes 5:8–20, Galatians 3:23–4:11). **Correct.**

#### Reading Response

PDF: three alternatives ("The word of the Lord" / "Hear what the Spirit…" / "Holy Word, Holy Wisdom.").  
Web: three tabs. ✓

#### The Responsory

Full call-and-response text matches PDF exactly, including all four versicle/antiphon pairs. ✓

#### The Canticle

PDF: three alternatives (Song of Zechariah / Song of Jerusalem Our Mother / Song of Pilgrimage).  
Web: three tabs. Song of Zechariah text matches PDF exactly. ✓

#### After-canticle Doxology

Three alternatives rendered as tabs. ✓

---

### AFFIRMATION OF FAITH

PDF: two alternatives (Apostles' Creed / Hear, O Israel).  
Web: two tabs. Text of both matches PDF exactly. ✓

**Note:** Web defaults to "Hear, O Israel" on Saturday. This appears to be an intentional per-form default in `app.js`; not a bug.

---

### THE PRAYERS OF THE COMMUNITY

#### Intercessions and Thanksgivings

Bullet list and framing text match PDF exactly. ✓

#### Transitional note

PDF (within Intercessions): "The Prayers continue with the Litany and a concluding collect."  
PDF (after Affirmation): "Morning Prayer continues with the Prayers."  
Web: "Morning Prayer continues with the Litany." (within Intercessions block)

**Minor wording variation.** The PDF uses "the Prayers" (the parent section heading) then clarifies to "the Litany" in the sub-note. The web collapses to one note pointing directly to the Litany. Functionally identical; could be made to match more closely.

#### The Litany

All six versicle/response pairs match PDF exactly, including "Strengthen Charles our King" (correctly updated from Elizabeth II, as the PDF was 2024 edition). ✓

#### The Collect

PDF: "Either the Collect of the Day or one of the following collects…" followed by two seasonal collects (I, II).  
Web: three tabs — **Collect of the Day** (fetched from lectionary data), **Seasonal I**, **Seasonal II**. Both seasonal collect texts match PDF exactly. ✓

The "Collect of the Day" tab is a correct enhancement: the PDF references it but cannot print it since it varies daily.

---

### THE LORD'S PRAYER

Introductory line and prayer text match PDF exactly. ✓

*Note:* PDF typographically lowercases the Lord's Prayer text (e.g., "our father in heaven"). Web renders with standard sentence capitalisation. This is a deliberate editorial choice in the web app, not an error.

---

### THE SENDING FORTH

#### The Dismissal

"Let us bless the Lord. / Thanks be to God." — matches. ✓

#### Concluding Sentence

"May Christ, who has opened the gates of heaven, bring us to reign with him in glory. Amen." — matches. ✓

---

## Non-issues / expected differences

| Difference | Assessment |
|------------|------------|
| Tabs for alternatives instead of "or" | Correct rendering of interactive media |
| Actual psalm + readings rendered | Correct; PDF only provides placeholders |
| Collect of the Day tab added | Correct; faithful to PDF instruction |
| Lord's Prayer capitalised | Editorial improvement; not a doctrinal error |
| "Hear, O Israel" as default on Saturday | Intentional default; both tabs available |

---

---

## Wednesday MP — 2026-06-10 (pp. 174–181) ✅ Correct with one systematic note

All sections verified: Invitatory Psalm 145:1-10, Responsory, three canticle options (Zechariah / Lord's Anointed / Bride), intercessions bullet list, litany, both seasonal collects, Lord's Prayer, dismissal sentence. All match.

**One systematic issue — litany response capitalisation:**  
PDF uses lowercase for congregation responses in the Wednesday litany: `"holy one, accomplish your purposes in us."` The app renders `"Holy one, accomplish your purposes in us."` This is a PDF extraction artefact — the extractor normalises response capitalisation. Affects all 8 litany responses in Wednesday MP. See BUG-18 below.

---

## Wednesday EP — 2026-06-10 (pp. 182–188) ✅ Correct with same systematic note

All sections verified: Evening Hymn "O Light, whose splendour thrills" (both stanzas) ✓, Responsory ✓, three canticle options (Mary / Praise / Christ's Glory) ✓, intercessions ✓, Lord's Prayer ✓, dismissal sentence ✓.

**Same litany capitalisation issue:** EP Wednesday litany responses are also capitalised in the app vs lowercase in PDF. e.g. `"To declare the mystery of Christ."` vs PDF `"to declare the mystery of Christ."` Same BUG-18.

**Evening Hymn confirmed rendering correctly** — this clears the earlier risk item.

---

## Known bugs found

**BUG-19 (P1): Bare verse-range psalm citations parsed as wrong psalm** ✅ Fixed  
Source CSV uses `Ps 139:1-17, (18-23)` where `(18-23)` is an optional extension of Psalm 139, not a separate psalm. The converter stored the inner citation as `"18-23"` (no psalm number); `parsePsalmCitation("18-23")` called `parseInt("18-23")` → 18, loading all 50 verses of Psalm 18.  
**Scope**: 535 occurrences across 86 lectionary files (entire 2016–2026 range), 14 distinct recurring patterns (e.g. `Ps 139:1-17, (18-23)`, `Ps 68:1-20, (21-23), 24-36`).  
**Fix**: `_psalm_group` in `tools/convert_lectionary.py` now tracks the last psalm number and prefixes bare verse ranges: `(18-23)` after `139:1-17` → `{"citation": "139:18-23", "optional": true}`. All existing JSON files patched via migration script.  
_Severity:_ P1 — shows entirely wrong psalm (sometimes 50 verses instead of 6).

**BUG-18 (P3): Litany response capitalisation — Wednesday MP and EP** ⚠️ Half-reversed by BUG-25 (2026-07-05)  
The PDF source uses lowercase for congregation responses in the Wednesday litany (following ACC typographic convention). The extraction pipeline normalised these to sentence case. Originally "fixed" by lowercasing 8 MP responses and 4 EP responses via `_TEXT_PATCHES`.  
**Revision (BUG-25):** the MP half was wrong. The premise "PDF uses lowercase" came from pdfplumber, which decodes the PDF's small-caps font as lowercase; `pdftotext` (poppler) decodes the same glyphs correctly and shows **"Holy One"** — a capitalised divine title. The MP patch is deleted and "holy one → Holy One" is now a `_DIVINE_FIXES` rule (response segments only). The 4 EP tuples stand: they are grammatical continuations of the leader line, verified lowercase via pdftotext (lines 8031–8042).  
_Severity:_ P3 — invisible to most users; not a doctrinal error. _Lesson:_ casing corrections require the pdftotext oracle (Batch 19), not visual inspection of pdfplumber output.

---

## Potential correctness risks (as identified in June 2026)

Status added 2026-08-07. Three of the five have since been answered; the table
is kept because what a past audit thought was risky is worth knowing, not
because it is a live worklist.

| Item | Risk as stated | Status |
|------|----------------|--------|
| Seasonal forms (Advent, Lent, etc.) | Different canticles, litanies, and collects | **Largely answered.** The ACC errata pass (2026-08) applied 46 corrections across the seasonal and ordinary forms, and `make audit-errata` now checks every errata block against the published data on demand. Not a line-by-line audit of unerrata'd text, so not closed outright. |
| Other weekday litany capitalisation | BUG-18 may affect other weekdays | **Moot.** BUG-18's premise came from pdfplumber decoding small-caps as lowercase. fitz decodes the glyphs correctly and the casing corrections were removed wholesale (ADR 0011). |
| O Antiphons (Dec 17–23) | Render as plain italic; liturgically significant | **Open.** They are present and typed (14 `o_antiphon` notes in the published lectionary); how they render is still a UX question. The tracker referenced here as "UX-09" is gone — see GitHub Issues. |
| Collect of the Day accuracy | Verify collected text matches lectionary source | **Answered mechanically.** `validate_lectionary.cjs` resolves every collect reference for all 397 dates × 2 offices against `collects.json`, using the runtime resolution functions rather than a reimplementation. |
| Year B → Year A transition | Coverage ends Dec 2026 | **Open and approaching.** The window is 2025-11 → 2026-12. Gated by `boundsMax`, so it degrades safely rather than silently, but new source CSVs are needed before the rollover. |

---

## Verdict

**The app is liturgically correct** for all three forms audited (Saturday MP, Wednesday MP, Wednesday EP). No substantive text errors found. One systematic extraction artefact (BUG-18, P3) affects litany response capitalisation on Wednesday — not a doctrinal issue and unlikely to be noticed in use. Seasonal forms remain to be audited post-review.
