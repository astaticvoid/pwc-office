# PWC — Tracker

_Last updated: 2026-07-24_

## Field observations

_User reports that need triage — move to the appropriate section after investigation._

_(none yet)_

---

## Active plan

The near-term goal is liturgical quality — ensuring every rendered office is coherent
and correct for a worshipper. We fixed extraction quality (PyMuPDF replacing pdfplumber).
Now we need to guarantee the rendered output is liturgically right.

### Done (this session)

- Paragraph-break aware scripture rendering — BibleGateway-style paragraph rendering, left-aligned section headings (2026-07-21, `7978854` + `b435069`)
- PyMuPDF replaces pdfplumber — single PDF dependency, 85 lines of heuristic code deleted
- Content-based page detection — no hardcoded page numbers
- Unified renderer — `render.js` has HTML + text + JSON output modes
- Correction consolidation — single `corrections.json` (1 active entry)
- Versioned deploy pipeline — `deploy-staging` → `test-staging` → `promote` → `rollback`
- Staging on `office-staging.k-sprawl.net`, production on `office.k-sprawl.net`
- Basic auth with persistent cookie (no per-refresh login)
- QA tools: `validate_office.cjs` (6 rules), `audit_office.cjs` (14 metrics, 4 peer groups)
- Compare tool: `compare_staging.cjs` — A/B diff before promotion
- Review tool: `review_form.cjs` — line-numbered text renderer
- Systemic fixes: "Amen ." (28/30 forms), Friday EP Phos Hilaron, rubric leakage in office mode
- NRSVUE fetcher (private repo)
- Stale docs cleaned: API.Bible, Go, SW caching references removed

### Done (2026-07-18 QA sprint)

- `renderOfficeJSON` — full-office structured output shared by validators and browser
- `assembleSections` — single source of truth for section ordering and visibility
- Expanded rule suite — 19 rules across 3 tiers (was 6)
- `coherence_score.cjs` — composite 0-100 score with promote gate
- CI gate — `make qa` wired into `make test`, GitHub Actions workflow
- PDF column-break artifacts fixed — systemic `_normalize_whitespace` regex
- CLI rendering fixes — canticle verse breaks, N placeholder text mode
- `collectSecondaryPage` moved to shared module
- CLI Lord's Prayer harmonized with web app section structure
- Sync test — Vitest verifies HTML and JSON paths produce matching output
- 8 expected audit outliers documented in `audit_expected.json`

### Next

- ~~Promote staging to production~~ — Promoted 2026-07-21.
- ~~`prefers-color-scheme` auto-detection~~ — System preference followed when no stored override 2026-07-21.
- ~~`#day-office-name` button semantics~~ — role="button", tabindex, Enter/Space key handler 2026-07-21.
- ~~Unify tab builders~~ — `collectToggleHtml` tabBlock now includes title + truncation matching `renderAlternatives` 2026-07-21.
- ~~Error-state consistency~~ — Missing form shows notice, unresolvable collect shows "not available" note 2026-07-21.
- ~~`CONTRIBUTING.md`~~ — Fixed stale references (patches→corrections, update-golden→generate-golden, deploy→deploy-staging/promote) 2026-07-21.
- ~~E2E staging test auth~~ — HTTP basic auth credentials added to playwright config 2026-07-21.
- Visual-regression testing: no screenshot/visual tests, dark mode untested in CI.

### Parked

- Mobile Capacitor build

---

## Open issues

### Rendering

- ~~Invitatory Psalm heading dropped its psalm number~~ — Fixed 2026-07-26. The web app rendered a bare "Invitatory Psalm" heading; the PDF's actual heading is `Invitatory Psalm: Psalm 95:1–7` (or 24, 63:1–8, 145:1–10, 67, 51:1–12, 100 depending on the weekday). `extract_offices.py` discarded that heading text — it only mapped it to the `invitatory` section key, same gap `extract_form_text.py` already flagged as "book.js known gap: form.invitatory not rendered." Fixed by extending the existing `phos_hilaron` heading-preservation path (which already solves this for the Evening Hymn title) to also capture `invitatory` headings as a `label` segment; `app.js`/`render.js` now render that label in place of the static heading, matching how Phos Hilaron already works. Re-ran `make extract` + `make qa` — coherence 100/100, no regressions.
- ~~Invitatory Psalm verse line-breaks silently collapsed; no verse-pair indent anywhere~~ — Fixed 2026-07-26, found while fixing the heading bug above. Two separate issues: (1) `_normalize_whitespace`'s `_VERSE_SECTIONS` allowlist (which exempts intentional verse line breaks from the PDF-column-wrap join heuristic) was missing `invitatory`, so any verse-pair whose first half didn't end in terminal punctuation — e.g. "in whose hands are the ends of the earth" / "and the heights of all the mountains." — got silently joined onto one line by `_LINE_JOIN`. (2) Separately, psalm/canticle/invitatory verse second-halves are physically indented ~18pt in the source PDF (confirmed via span x0 coordinates: 48pt → 66pt), but nothing captured that signal, so no section ever rendered it, even where line breaks were already correct (canticle, psalter). Fixed by: adding `invitatory` to `_VERSE_SECTIONS`; teaching `spans_to_typed_lines` (tools/extract_office_styles.py) to detect a sustained x0 jump between consecutive `leader` lines and mark the continuation with a leading-space indent marker (the same convention `data/psalter.json` already used); and adding a `formatLiturgicalText` render helper (now exported from `render.js`, reused by both the HTML segment renderer and `app.js`'s psalm renderer) that indents a line when it carries that leading-space marker *or* the previous line ends in the psalter's `*` caesura mark — covering canticle/psalm text where the marker survives via `*` rather than the extraction geometry pass. New CSS `.verse-cont { padding-left: 1.25em }`. Verified in-browser (Sunday MP invitatory + Psalm 24) and confirmed via full-file grep that the geometry marker appears nowhere outside the 7 invitatory sections — no bleed into litany/collects/rubrics. `make qa` + `npm test` clean (one test updated to expect the new `<span class="verse-cont">` wrapper).
  - Follow-up same day: the x0-jump marker only compared each line to the *previous* line, so a multi-line indented run (e.g. "Forty long years I loathed that generation and said, / 'These people go astray in their hearts. / They do not know my ways.") only indented the first continuation line — the third line sits at the same x0 as the second, so there's no further "jump" to detect relative to it. Changed `spans_to_typed_lines` to track a `baseline_x0` (the outer margin, reset on any non-leader line) and compare every line against that fixed baseline instead of the previous line, so a run of any length indents correctly. Verified against the exact 3-line PDF case (span x0: 78 / 96 / 96).
  - Follow-up same day: heading/label styling was inconsistent — "Invitatory Psalm" had no bold heading bar at all (it mirrored the Phos Hilaron pattern, which intentionally has no heading). Restored the `Invitatory Psalm` H3 (matching "Introductory Responses" etc.) via `renderSubsection`, and added `invitatorySegments()` (render.js) to strip the redundant "Invitatory Psalm:" prefix from the extracted label segment so only the citation ("Psalm 95:1–7") shows as the italic `seg-label` caption underneath — same visual pattern as `.alt-source` captions elsewhere, just not duplicating the heading text.
- ~~Ordinary-time doxology (after Introductory Responses) missing its "Alleluia."~~ — Fixed 2026-07-26. All 14 ordinary-time forms (7 MP + 7 EP) print "Alleluia." after *each* of the three doxology options in the PDF, said once after whichever is chosen — but `_dedup_shared` hoists the doxology's first-encountered occurrence into `_shared.doxology` (reused everywhere doxology appears — after every Psalm and Canticle too, where the PDF does *not* have an Alleluia) and replaces every other occurrence with a bare `{type:"shared"}` reference, so a seasonal form's Alleluia-less version (processed first, since ordinary forms are last in extraction order) became canonical and every ordinary form's own Alleluia was discarded on dedup. Fixed with `_split_doxology_alleluia`: strips the trailing "Alleluia." from each group's response text *before* the dedup/hoist check, and re-attaches it as one standalone trailing `response` segment on the per-form segment list (not inside the shared block), so it now shows once after the doxology only on the forms that actually have it. Verified in-browser and via `make qa` + `npm test` (128/128, no regressions). Casing on "as it was..." fixed as part of the systemic fix below.
- ~~`_fix_casing` force-capitalised every response's opening letter, wrongly overriding genuine lowercase continuations~~ — Fixed 2026-07-26, found via the doxology bug above ("as it was..." → "As it was...") and a second instance the user spotted ("let heaven and earth rejoice..." → "Let heaven..."). Traced to the actual root cause instead of patching each instance: `_fix_casing` capitalised the first letter of every `response` segment unless its first word was in an 8-word `_CONTINUATION_STARTS` allowlist (`who/which/that/and/or/but/nor/yet`) — a rule inherited from the pre-fitz pdfplumber extractor, which mis-decoded small-caps fonts as lowercase and needed correcting. Checked whether that's still true post-fitz by comparing fitz's *raw* per-span text (before any post-processing) against pdftotext for several of these lines: fitz already decodes the true casing correctly in both directions — "as it was..." is lowercase in fitz's raw output too (genuinely lowercase in the PDF), and "God of all the faithful, we thank you." (a litany reply, correctly capitalised) is capitalised in fitz's raw output too. The force-capitalise step was therefore pure liability once fitz replaced pdfplumber: harmless where the PDF was already capitalised, actively wrong wherever it wasn't. Removed the step (and the now-dead `_CONTINUATION_STARTS` constant) entirely rather than trying to enumerate more exception words — `tools/check_casing.py`'s pdftotext-oracle "first-letter differences" count dropped from 99 to 38 in one change, all 128 unit tests + `make qa` still pass, and `--strict` (0 internal mismatches) stays clean. Also removed 8 now-redundant `_TEXT_PATCHES` entries that existed solely to undo this over-capitalisation (4 Wednesday-EP litany lines, the doxology, and 3 "Let heaven" instances — confirmed each still resolves correctly without its patch) and the matching `KNOWN_INTENTIONAL` allowlist in `check_casing.py` (its 4 entries now classify as exact `match`, not `first_letter`, so the allowlist is dead).
  - Follow-up same day, prompted by the user asking "if source has it that way, keep it — what's the remaining 38 for?": rendered the actual PDF pages (not text-extraction, the pixmap) for two of the remaining categories to get real ground truth. (1) `lords_prayer_intro` "Gathering our prayers...": the printed page unambiguously shows a capital G — our data (and fitz) were already right; `pdftotext` alone decodes this one line as lowercase, a decoding quirk in the *oracle*, not our data. No change. (2) The 17 "responsory refrain" cases (e.g. "make haste to answer when I call.", repeated after every verse) looked at first like the same class of bug ("said this pattern is genuine, should match PDF exactly") — but rendering the actual page showed our existing capitalisation was *already correct*: the PDF really does print the antiphon lowercase only while it's being established (leader line + its immediate echoed response) and capitalised on every subsequent verse-response, which is exactly what our data already had. The 17 flags were a bug in `check_casing.py` itself: `pdf_low.find(text)` always returns the *first* occurrence of a string, so when the same response text repeats 4–5 times in one section, every repeat got compared against that same first (and differently-cased) occurrence instead of its own. Fixed the checker: added a position cursor that only moves forward, reset at each office/section boundary, so repeated segments are matched against the PDF's occurrences in the same left-to-right order they appear in our data (`tools/check_casing.py`). First-letter count dropped 38 → 14, and all 14 remaining are that one confirmed-false-positive `lords_prayer_intro` line repeated across the 14 ordinary-time forms that share it — zero unexplained differences left. `make qa` + `npm test` unaffected (checker-only change, no data touched).
  - Final follow-up same day: user asked "what do we still need pdftotext for," which surfaced that `_DIVINE_FIXES` (~14 divine-title capitalisation regexes: "holy spirit" → "Holy Spirit", etc.) and the 9 remaining `_TEXT_PATCHES` entries (6 phos_hilaron heading casing + 3 "Spirit" capitalisation, BUG-36) were the same inherited-from-pdfplumber pattern as the force-capitalise step above, never re-verified after the fitz migration. Tested empirically rather than assuming: ran the full 30-form extraction with each mechanism's rule list emptied out and diffed against the real baseline. `_DIVINE_FIXES` had exactly one live effect across the entire dataset (all 30 forms) — "creator" → "Creator" in the Apostles' Creed — and rendering that PDF page as a pixmap showed the print is genuinely lowercase ("the Father almighty, / creator of heaven and earth." — one continuous sentence across the comma, same pattern as the doxology). The other 13 patterns were pure no-ops; fitz already gets "Holy Spirit," "Holy One," "Israel," "Pilate," etc. right everywhere. The 9 remaining `_TEXT_PATCHES` entries (Spirit capitalisation + phos_hilaron heading casing) were *also* proven to be complete no-ops the same way — removing all of them changed zero bytes of output. So of ~23 total manual casing corrections carried over from the pdfplumber era, fitz alone now handles all of them correctly; the one still doing something (`creator`) was making it *wrong*. Removed `_DIVINE_FIXES`, `_TEXT_PATCHES`, `_patch_segments`, and `_apply_text_patches` entirely from `extract_offices.py` (re-extraction is byte-identical to the pre-removal baseline, confirming nothing else depended on them). Also removed `check_casing.py` itself at the user's request (weighed keeping it as the only independent cross-check against fitz in the pipeline, since it's what caught BUG-25/BUG-36 originally and what verified this whole cleanup was safe — but it's user-facing-zero-cost, manual-only tooling not wired into `make test`/`make qa`, and the user made the call to drop it) — along with its `make check-casing` target and its `validate` dependency. Removed the resulting dead `pdftotext` dependency: version-tracking code in `check_data_integrity.py` and `update_extract_manifest.py` (the manifest no longer records a `pdftotext` version field), and fixed stale "uses pdftotext" naming in `extract_collects.py`/`docs/adr/0001,0002,0003` that actually meant fitz (a leftover from before the pdfplumber→fitz migration that was never updated). `poppler-utils`/`pdftotext` is no longer a dependency of this project anywhere. `make qa` (100/100) + `npm test` (128/128) + `make check-integrity` clean throughout.
- ~~Mid-line breaks in prose collects from PDF column layout (affects ~14 dismissal blessings)~~ — Fixed 2026-07-18: `_normalize_whitespace` regex joins mid-sentence `\n` in leader/response segments. Validator confirms zero remaining.
- ~~"N" placeholder renders as bare text in CLI text mode~~ — Fixed 2026-07-18: `renderSegmentsText` wraps `N` as `(N)` in text mode.
- ~~Canticle verses join with spaces instead of line breaks in text mode~~ — Fixed 2026-07-18: CLI canticle rendering passes `verse: true`.

### Extraction

- ~~Litany leader segments split mid-sentence on ordinary commas~~ — Fixed 2026-07-26, found during a follow-up audit prompted by the user asking what other "don't trust the source" extraction heuristics needed re-verifying (same question that led to the canticle-line-break fix below and to ADR 0011). `_reflow_litany_prose` (`tools/extract_offices.py`) kept a hard line break wherever a PDF-wrapped litany line ended in "terminal punctuation" (comma/semicolon/colon/etc.), on the theory that this marked an intro-rubric → petition boundary. Checked against the source PDF directly: every litany leader segment is one continuous petition — the leader/response type alternation is already the real structural boundary — and ordinary mid-sentence commas/colons (extremely common in this prose) aren't a break signal at all. Produced 46 false breaks across the litany dataset, e.g. "Show your good will to all who live in this city, the poor and the rich," / "the elderly and the young, men and women." rendered as two lines when the book prints it as one sentence; the Advent "O Antiphons" were split into 2–3 spurious lines each the same way. Replaced with unconditional join (reusing `_reflow_leader_prose`, already used for seasonal_collects) — deleted `_reflow_litany_prose` and the now-unused `_TERMINAL_PUNCT` constant. `make qa` + `npm test` clean.
- ~~Collect text sometimes ends with a stray running-header word ("Christmas", "Holy Days", "Occasional Prayers", etc.)~~ — Fixed 2026-07-26, found during the same audit. `extract_collect()` (`tools/extract_collects.py`) appends the next PDF page's raw text (`overflow`) when a collect runs past a page boundary, to find its real terminator ("Readings", "Prayer over the Gifts", etc.). Every page in the collects range opens with its own running header (page number + section/season title, in either order, e.g. "Christmas\n269\n...", "Good Friday 315\n..."); `_clean()` only stripped the number half (matching on `\b\d{3}\b`), so whenever a collect's true end fell right at a page break, the *title* half of the next page's header rode along as bogus trailing (or, via the `extract_collect_from_txt` BAS.txt fallback used for 4 garbled pages, sometimes mid-sentence) text — e.g. "...one God, now and for ever. Christmas" for the Third Sunday of Advent. Confirmed 11 corrupted collects via full-book diff (`_TXT_FALLBACK_PAGES` path added a 12th, mid-sentence: "...Son Jesus Christ After Pentecost to be the light of the world..."), plus 1 in the separately-parsed Occasional Prayers section. Fixed by stripping the leading running header from `overflow` before concatenation (`_RUNNING_HEADER`, position-anchored on "start of a new page," not content-guessing) and the equivalent for the whole-document BAS.txt fallback (`_PAGE_BOUNDARY_HEADER`, anchored on the page-break marker fitz leaves behind). Verified zero remaining dangling-header endings or mid-text injections across the full dataset. `_clean()`'s original digit-line regex is now fully redundant (confirmed via disable+diff) but left in place as a harmless no-op defensive fallback rather than removed in the same pass. `make qa` + `npm test` clean.
- ~~Canticle line breaks reconstructed via a capitalization/asterisk heuristic, silently merging lines that should stay separate~~ — Fixed 2026-07-26. `_fix_canticle_breaks` (`tools/extract_offices.py`) discarded the geometry-derived leading-space continuation marker (`spans_to_typed_lines`, `tools/extract_office_styles.py` — the same mechanism `data/psalter.json` uses) and rebuilt verse-half line breaks from scratch using capitalisation and asterisk position. That heuristic joined a verse's second half into the *next* verse's first half whenever the second half didn't itself end in "*" — reported by the user against the Benedictus ("for you will go before the Lord to prepare the way," merged onto "to give God's people knowledge of salvation *", collapsing 4 printed lines into 3); a second, earlier instance in the same canticle ("you promised of old..."/"from the hands of all who hate us, *") was found the same way. Confirmed via the raw PDF that the pre-heuristic text (straight from `spans_to_typed_lines`) was *already* correct, and that no canticle anywhere in the source has a mid-line asterisk needing repair — the "PyMuPDF merges * onto the same line" premise the function was written for doesn't hold with the current fitz-based pipeline. Deleted the reconstruction entirely; canticle text now passes through untouched, matching how psalms are handled. `make qa` + `npm test` clean.
- BAS collect page 281: Ash Wednesday overlaps with Epiphany content (pre-existing)
- BAS collect page 407: Saint Matthias date parsing (pre-existing)

### Infrastructure

- ~~Staging cache headers need `make build` integration~~ — Done: `deploy-staging` already sets per-type cache headers.
- ~~Production still on pre-rubric-fix release (user testing staging)~~ — Promoted to production 2026-07-21.
- ~~No CI — tests are local only~~ — Done 2026-07-18: GitHub Actions runs `make test` (Vitest + QA gate + integrity check) on push/PR.
- ~~P0 alternate-observance crash + 5 validity bugs~~ — Fixed 2026-07-21 (Commits 1–6): dead observance card, duplicate ARIA IDs, `--font-body` token, `--color-day` token, StatusBar ternary, `@smoke` test gate.
- ~~Dead CSS/JS cleanup (~80 lines CSS, #view-toggle/#nav-date wiring)~~ — Purged 2026-07-21.
- ~~Missing font weights (Garamond 700, Plex 600/700)~~ — Added 2026-07-21.
- ~~Mobile line-height override~~ — Removed hardcoded 1.7, token flows through 2026-07-21.
- ~~Settings-sheet a11y~~ — Visibility hidden removes from tab order, aria-modal, focus management 2026-07-21.
- ~~Dark-mode gaps~~ — color-scheme meta/root, brass ink typo, seasonal accent dark variants 2026-07-21.
- ~~Chapter drop-num on mid-chapter readings~~ — Skip when firstV ≠ 1 2026-07-21.
- ~~Attribution label inconsistency~~ — Unified as "Scripture:" 2026-07-21.
- ~~ADRs stuck at Proposed~~ — Marked Accepted (0002 Superseded) 2026-07-21.
- ~~Stale DESIGN.md~~ — Deleted (all info in AGENTS.md + ADRs) 2026-07-21.
- ~~Throwaway prototype files~~ — Deleted _design-options.html, _cross-test.html 2026-07-21.
- Missing visual-regression coverage: no screenshot/visual tests, dark mode untested in CI.
- ~~Password re-prompts on every page refresh~~ — Fixed 2026-07-24. Two bugs in the `pwc-basic-auth` CloudFront Function (viewer-request only, no cookie-writing counterpart despite its own comment saying "Basic auth with cookie check"): (1) no `viewer-response` function ever existed to write `Set-Cookie`; (2) even so, its cookie *read* checked `request.headers.cookie`, which the `cloudfront-js-2.0` runtime never populates — cookies only ever appear under `request.cookies`, so the check was structurally always false. Added `pwc-set-auth-cookie` (viewer-response) to write `pwc-auth=1` (30-day, Secure/HttpOnly/SameSite=Lax) after a header-authenticated request, and fixed `pwc-basic-auth`'s read to use `request.cookies["pwc-auth"]`. Verified end-to-end on staging then production: Basic Auth → 200 + Set-Cookie; cookie-only refresh → 200, no reprompt; no credentials → still 401. Both functions are now version-controlled at `infra/cloudfront-functions/` (previously console-only, untracked — how the bug went unnoticed for ~2 months).
- ~~`make promote` silently failing~~ — Fixed 2026-07-24: the `jq` filter piped the whole `{ETag, DistributionConfig}` wrapper into `--distribution-config`, and `--if-match` was never passed. Every step was `;`-chained instead of `&&`, so the broken `aws cloudfront update-distribution` call failed silently and the recipe still printed a false "Promoted ... to production." Production had been stuck on the 2026-07-18 release for 3 days/5 releases with no visible error. Same bug (plus a trailing-slash `OriginPath` bug) fixed in `rollback`. Re-ran `make promote` after the fix — production confirmed serving the 2026-07-21 release (`index.html` hash matches S3 byte-for-byte).

---

## Deploy workflow

```bash
make deploy-staging          # upload to releases/vTIMESTAMP/ + staging/
make test-staging             # Playwright smoke
node tools/compare_staging.cjs [date] [mp|ep]  # eyeball diff
make promote                  # CloudFront origin-path swap
make rollback                 # revert to previous release
```

---

## QA gates

```bash
node tools/validate_office.cjs   # 6 liturgical rules (0 failures expected)
node tools/audit_office.cjs      # cross-form outlier detection (8 legit outliers)
make test                         # Vitest (117 tests)
make test-full                    # 794 structural checks
make check-integrity              # SHA-256 data integrity
```
