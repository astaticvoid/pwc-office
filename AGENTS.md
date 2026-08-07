# AGENTS.md

Instructions for automated tooling working in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and stored as JSON.

## One-time setup

```bash
npm install
npx playwright install              # Chromium browser for Playwright E2E tests
make venv                           # .venv with pymupdf (PDF extraction) + pytest
```

Every Python target runs through `$(PYTHON)`, which resolves to `.venv/bin/python3`
when the venv exists and falls back to the ambient `python3` otherwise (CI). No
shell activation is needed. Installing directly into Homebrew's python3 is not
supported — it is an externally-managed environment (PEP 668).

Required environment variables in `.env` (gitignored):
- No keys required. KJV scripture is bundled in `data/translations/kjv/` and works offline.
- NRSVUE scripture is not distributable — if a local copy is placed at `data/translations/nrsvue/` the app will use it.
- `make deploy-staging` / `promote` / `rollback` need `BUCKET` and `CF_DISTRIBUTION_ID`.
- `make test-staging` needs `STAGING_DOMAIN`; it is only used to build `BASE_URL` for Playwright.
- `STAGING_CF_ID` is not read by anything today — staging freshness comes from the short cache-control headers `deploy-staging` sets, not from an invalidation.
- Also provide `AWS_PROFILE` in `.env` so AWS CLI credentials resolve automatically.

**All build, test, and deploy operations should be run through `make`.**
The Makefile includes `.env` at line 1 (`-include .env`), so environment
variables are loaded automatically. Running `aws` CLI commands directly will
fail with "Unable to locate credentials" because the shell environment does
not source `.env`. Use `make deploy-staging`, `make serve-dist`, etc.

## Commands

```bash
# Development
make serve                        # http://localhost:8080 (no build, data symlink followed live)

# Data pipeline
make fetch-sources                # download ACC PDFs + CSVs → sources/
make extract                      # full pipeline → data/*.json + data/lectionary/

# Testing
make test                         # Vitest (fast, no network) — go-to test command
make test-full                    # structural check: every day × MP+EP in lectionary
make test-smoke                   # 4 cases: citation check vs lectionary.anglican.ca
make test-seasonal                # 26 cases: one MP+EP per liturgical form
make test-web                     # Playwright E2E — auto-starts web/ server on :8080

# Quality assurance
node tools/validate_office.cjs    # 20 liturgical rules across 3 tiers, all 30 forms
node tools/validate_css.cjs       # structural CSS validity (web/*.css)
node tools/validate_lectionary.cjs # every date × office: citation syntax + resolution
node tools/audit_office.cjs       # cross-form statistical outlier detection (z-score)
node tools/compare_staging.cjs [date] [mp|ep]  # A/B diff staging vs production rendered DOM
node tools/review_form.cjs FORM   # line-numbered text renderer for manual review

# Quality gates
make check-text                   # scan for PDF extraction artifacts
make check-text --strict          # same but exits non-zero on findings
make check-integrity              # verify data/ hashes match extract manifest — fails if any
# NOTE: after changing any extractor, re-run `make extract`. The manifest stores
# hashes of the committed data, so stale hashes after a code change fail this —
# which is the point, and why it also gates `make test`.

# Build & verify
make build                        # assemble dist/ (copies web/, dereferences data symlink)
make check-dist                   # build + tools/check_dist.py validation
make serve-dist                   # serve dist/ on :8081 (required for E2E pre-deploy)

# Mobile (Capacitor shell)
make mobile-sync                  # build + npx cap sync
make mobile-ios                   # mobile-sync + open Xcode
make mobile-android               # mobile-sync + open Android Studio

# Deploy (needs AWS creds + BUCKET + CF_DISTRIBUTION_ID + STAGING_DOMAIN in .env)
make deploy-staging               # upload to releases/vTIMESTAMP/ + staging/
make test-staging                 # Playwright smoke tests against staging
make promote                      # CloudFront origin-path swap to production
make rollback                     # revert to previous release

# Page bounds detection (content-based, not hardcoded)
python3 tools/detect_office_bounds.py --strict  # verify committed bounds
python3 tools/detect_office_bounds.py --write   # regenerate after PDF change
```

### Focused test commands

```bash
npx vitest run -t "pattern"       # run a single Vitest test
```

## Architecture

### Data flow

```
PDFs  →  PyMuPDF (fitz)  →  data/*.json + data/lectionary/YYYY-MM.json
                                        ↓
              web/render.js (shared rendering: HTML + text + structured output)
              ├── web/app.js (SPA)
              ├── cli/book.js (plain-text CLI)
              └── cli/office.js (debug CLI)
```

Copyrighted content in `data/` is permanently gitignored. Only `data/translations/kjv/`, `data/corrections.json`, and `data/paragraphs.json` are committed. `web/data` is a symlink to `../data` — `make build` dereferences it via `cp -rL` into `dist/`; `make serve` follows the symlink live.

### Web SPA (`web/`)

`web/render.js` contains all office rendering functions and is imported by the browser SPA (`web/app.js`), the Node CLI (`cli/book.js`, `cli/office.js`), QA tools, and Vitest tests. A change to `render.js` affects all consumers.

`web/app.js` handles routing, lectionary lookup, form selection (season + weekday → one of 30 office forms), and Scripture fetching (NRSVUE from local `data/translations/`, KJV bundled). No framework, no build step.

**Leaders & responses are rendered by `web/render.js`.** The shared module provides:
- `renderSegments` — HTML output (browser SPA)
- `renderSegmentsText` — structured text blocks (CLI, QA tools)
- `segmentsToJSON` — structured JSON output (validators, cross-form audit)

**No service worker.** `sw.js` is a kill-switch only — it unregisters itself and clears all caches to clean up old installs. Do not add SW caching back.

### Node CLI (`cli/`)

| File | Role |
|------|------|
| `cli/book.js` | Book-mode plain-text renderer. Uses `renderSegmentsText` from render.js. `node cli/book.js FORM [DATE]`. |
| `cli/office.js` | Structured text renderer. Uses `renderSegmentsText`. `node cli/office.js [mp\|ep] [DATE]`. |

### Python tools (`tools/`)

Extraction pipeline (run via `make extract`):

Each stage reads a named input and writes its own output; nothing is mutated in
place. Intermediates live in `.build/` — outside `data/`, which is the tree that
ships via the `web/data` symlink. Only the right-hand column is published.

| Stage | Writes |
|---|---|
| `extract_offices.py` (30 forms, PyMuPDF span-level) | `.build/offices.1-extract.json` |
| `extract_office_styles.py` — span classification by font flags + sRGB colour | *(library)* |
| `normalize_offices.py` — hoists shared blocks into `_shared` | `.build/offices.2-normalized.json` |
| `extract_psalter.py` | `.build/psalter.1-extract.json` |
| `extract_fats.py` | `.build/fats-saints.1-extract.json` |
| `convert_lectionary.py` (from `sources/bas_short_*.csv`) | `.build/lectionary/YYYY-MM.json` |
| `extract_collects.py` | `data/collects.json` |
| `corrections_lib.py` — shared matching for `office_text`, used by both scripts below | *(library)* |
| `validate_corrections.py` — checks corrections against the pre-correction artifacts | *(read-only)* |
| `apply_corrections.py` — applies `data/corrections.json` | `data/offices.json`, `data/psalter.json`, `data/fats/saints.json`, `data/lectionary/` |
| `update_extract_manifest.py` | `tools/extract_manifest.json` (committed) |

`apply_corrections.py` writes **every** file it publishes on every run —
`offices.json`, `psalter.json`, `fats/saints.json`, `lectionary/` — including
when the matching correction list is empty or `data/corrections.json` is absent
entirely. It is the stage that *derives* those files from their `.build/`
artifacts, not merely the stage that patches them. Never make a derivation
conditional on there being a correction to apply: that guard shipped on all four
chains, and on the offices chain it left the published file stale after an
extractor change through a `make extract` that reported success and a
`check-integrity` that passed, because the manifest was rehashed from the same
stale file. It also turned CI red for four days with `missing data files`, since
there the file is absent rather than stale.

Correction lists are *meant* to drain — "Data correction locations" below directs
systemic problems into the extractor — so an empty list is the expected steady
state, not a signal that there is no work to do.

Every stage input is checked before the first write, and a missing one exits 1
with the remediation. For `.build/lectionary/` "missing" includes *empty*:
`_seed_lectionary` mirrors it exactly, so an empty source deletes every published
month rather than copying none.

Because each stage names its input, the order is a data dependency rather than a
rule to remember: `convert_lectionary.py` cannot discard published corrections,
and `validate_corrections.py` cannot see corrected output, whenever they run
(#49, closing the #37 failure mode).

**Data integrity guard:** `check_data_integrity.py` compares current `data/*.json` hashes against `tools/extract_manifest.json`. Exits 1 if any file was edited outside the pipeline, or if an extractor changed without a re-run. Gates both `make test` and `make deploy-staging`.

**Verse sections — one list, in the validator only.** `VERSE_SECTIONS` in `tools/validate_office.cjs` asks *"does this section contain any intentional line breaks?"*, so `no-prose-line-breaks` won't flag a `\n`. There is no longer a Python counterpart: extraction decides every break from the page (see below), so nothing needs a section-level exemption. `_VERSE_SECTIONS` and the `_LINE_JOIN` regex it gated were removed once the geometry reproduced the extraction exactly without them. When adding a verse-like section, update the JS list and the line-count assertions in `tests/unit/render.test.js`.

### Changing an extractor

Extraction output is copyrighted text nobody diffs by eye, and the test suite
cannot see most of what can go wrong with it — the coherence score sat at 100/100
through a change that collapsed every evening hymn into prose. So the diff is the
verification, and it is not optional.

```bash
make extract-baseline          # full pipeline, snapshot
# ...edit tools/extract_*.py...
make extract-diff EXPECT=0     # a refactor must change nothing
make extract-diff              # or read what actually moved
```

**Upgrading PyMuPDF is changing an extractor.** It supplies every coordinate the
line-break decision reads, against a window documented below as sitting 0.5pt
off a false positive, so treat a version bump exactly like an edit to
`extract_offices.py`: re-extract and `make extract-diff EXPECT=0`. The file
hashes will not tell you — `make extract` rewrites them and the recorded version
together, so they agree with whatever produced them. `make check-integrity`
prints a `VERSION WARN` when the installed PyMuPDF differs from the manifest,
and that warning is the only automatic signal for this (ADR 0011). It warns
rather than fails only because `make test` depends on check-integrity, and
failing would lock out any contributor whose PyMuPDF differs until they re-run a
network extraction.

State the expected node count before running it, and make the change explain the
number. "0 nodes" is the target for anything meant to be behaviour-preserving;
a real fix should change exactly the nodes it claims and no others.

**Each stage writes its own artifact.** `.build/*.1-extract.json` and friends are
inputs to the next stage; only `data/` is published. Never treat an intermediate
as final, and never point a diff at one — that comparison is meaningless and
looks authoritative. Running a single extractor cannot corrupt `data/` any more
(#48, #49), but it also does not produce it.

**`_heading_to_key` is not a list of sections.** `seasonal_collects` and
`lords_prayer_intro` are carved out of the litany block afterwards, so anything
walking typed lines and assigning sections by heading reports zero for them
rather than failing. Walk `SECTION_ORDER` or `sections_of(form)` instead. This
has produced confidently wrong measurements more than once.

**Count only what can exhibit the defect.** A paragraph-break count went 47 → 30
→ 14 in one session because the first two included segment-type transitions that
`_merge` already separates. Narrow the population before reporting a number, and
say which population it is.

**Deciding a break: measure the page, never a proxy.** Whether a line break is deliberate or a PDF column wrap is a physical question — did the line run out of horizontal room? Answer it from geometry (`gap`, the unused space at the end of the line, and `lead`, the leading opened up below it), both carried out of `spans_to_typed_lines`. Two attempts to use a proxy instead have shipped broken text: a "terminal punctuation" rule produced 46 false breaks (#9), and classifying by the trailing space PyMuPDF leaves on a span collapsed every evening hymn stanza into prose (#38, reverted in 0ac1b86) — that space marks "this line does not end the block", not "this line was wrapped". `litany` is the only section mixed enough to need per-break judgement; `_reflow_litany` does it, with the handful of ambiguous breaks adjudicated explicitly and anything new warned about rather than guessed at. See #39.

**Page bounds:** `detect_office_bounds.py` detects office form page ranges from PDF content (title patterns). Output is committed as `tools/office_bounds.json`. No hardcoded page numbers.

**Design review process (ADR 0010):** Visual changes to UI elements (layout, typography, interactive controls) are prototyped on a static design-options page before touching production CSS. See `web/_design-options.html` for the current example. The workflow is:
1. Create a self-contained HTML file in `web/` (e.g. `_design-foo.html`) with inline CSS using the same custom properties as `office.css`.
2. For each variant, render a desktop (58rem) and mobile (390px) mockup stacked vertically.
3. Review, pick a direction, then implement the real CSS change.
4. Delete the design page after merging — it served its purpose.

### QA tools (`tools/`)

| File | Role |
|------|------|
| `validate_css.cjs` | Structural CSS validity for every file in `web/*.css`: no style rule nested inside another style rule's declaration block (only `@media`/`@supports`/etc. and `@keyframes` bodies may nest), and brace-balance at end of file. Catches an unclosed/stray rule silently swallowing the rest of the stylesheet — this happened for real (see issue #22) and nothing else in this project's test suite validates CSS syntax at all. |
| `validate_office.cjs` | 6 liturgical rules checked against all 30 forms (Amen presence, line breaks, stray spaces, section completeness) |
| `validate_lectionary.cjs` | Every date × office (397 × 2) in the lectionary: syntax checks (well-formed citations) **and** resolution checks (collect page/psalm number/lesson citation actually resolves to real data in collects.json/psalter.json/translations — not just a well-formed reference). Reuses the exact runtime resolution functions from `web/render.js`, not reimplementations. Run this after any re-extraction, especially a new lectionary year. |
| `audit_office.cjs` | Cross-form statistical audit — 14 metrics, 4 peer groups, 2σ z-score outlier detection |
| `compare_staging.cjs` | A/B rendered DOM diff between staging and production (use before `make promote`) |
| `review_form.cjs` | Line-numbered text renderer for manual review (`node tools/review_form.cjs advent-mp`) |

### Mobile shell (`ios/`, `android/`)

Capacitor wraps `dist/` as a native app (`capacitor.config.json`, `webDir: dist`). `make mobile-sync` rebuilds dist + runs `npx cap sync`. The web build is the source of truth — no native-only code paths.

---

## Bug tracking

All task tracking lives in [GitHub Issues](https://github.com/astaticvoid/pwc-office/issues) — there is no in-repo tracker. `BUGS.md` was retired 2026-07-30 and its full history migrated: every resolved entry is a closed issue, so a `see issue #N` comment in the source resolves to the original writeup.

- **Triaging a user report** — open an issue rather than noting it in a file. Label `bug`; leave it unlabelled for severity until investigated.
- **Fixing a bug** — close its issue with the findings in the closing comment. That writeup is the durable record; keep it detailed enough that a future session can reconstruct *why*, not just *what*.
- **Citing rationale from code** — reference the issue number (`see issue #13`), not a date or a file. Issue numbers are stable; the tracker file was not.
- **Parked work** — an open issue with no milestone, not a "Parked" list.

## Hard constraints

- **Never edit `data/*.json` directly.** All corrections go through `data/corrections.json` (committed single manifest) or the extraction pipeline. `make check-integrity` validates this — it fails if any data file was touched outside the pipeline.
- **One logical change per commit.** Push after each commit — don't batch.
  Each commit should contain a single atomic change that can be understood,
  reverted, and tested independently. Group related files by concern:
  - Docs (ADRs, specs) in their own commit
  - Shared code changes (render.js) with their consumers
  - Tooling changes in their own commit
  - Configuration (Makefile) in its own commit
  - Data pipeline changes (extractor, manifest) in their own commit
  Never accumulate unrelated changes into a "ball of mud" commit. Each commit
  message should explain what changed at the concern level, not file-by-file.
- **Subagent code review before commit.** Every change must be reviewed by a hostile subagent before committing. The subagent checks for bugs, edge cases, silent failures, performance issues, and integration problems. Fix all high-severity findings before committing.
- **Deploy requires user go-ahead.** Never run `make promote` unprompted. Staging deploys are always safe.
- **Systemic fixes over patches.** When a bug is found, categorize it: systemic (fix in extractor/renderer), pattern (multiple forms), or data (single form). Fix the root cause so all instances are resolved, not just the one found.

## Data correction locations

**There is one correction manifest: `data/corrections.json`** (ADR 0005). Extractors extract; they no longer patch their own output. Every editorial correction goes in the manifest under the category matching its data type, is checked for staleness by `validate_corrections.py`, and is applied by `apply_corrections.py` after extraction in `make extract`.

| Correction type | Manifest category | Target locator |
|----------------|-------------------|----------------|
| Office text (wording, casing, whitespace) | `office_text` | `{office, field}` + substring replace |
| Psalter: missing/incorrect verse text | `psalter` | psalm number + substring replace |
| Saint biographies | `fats` | saint + field + substring replace |
| Lectionary: wrong citation | `lectionary_citations` | date + office + lesson index |
| Lectionary: wrong lesson list | `lectionary_lessons` | date + office (whole-list replace) |
| Lectionary: name / rank / colour | `lectionary_names`, `lectionary_ranks`, `lectionary_colours` | date (whole-value replace) |
| Lectionary: garbled note | `lectionary_notes` | date (`clear` action only) |

`office_text` takes two shapes, chosen by the type of `old` (see
`tools/corrections_lib.py`, which both the validator and the applier call so
they cannot disagree):

- **Substring** — `old`/`new` are strings. Every occurrence in every
  text-bearing segment of the field is replaced. `count` states how many
  occurrences are expected and defaults to 1; a mismatch fails the run rather
  than applying partially. This is what almost everything wants — the
  alternative is restating an entire canticle to change one word.
- **Whole-field** — `old`/`new` are lists/dicts. The field must equal `old`.
  For structural edits only: deleting segments, reordering, retyping a segment.

The walk does **not** follow `{"type": "shared"}` references. A shared block is
reachable from many forms, so correcting it through one form would silently
rewrite the others; address `_shared` directly instead. One correction to
`_shared.reading_response_ordinary` fixes all 14 Ordinary forms at once.

Editorial errata from the ACC live in `docs/errata/` — see the README there for
which items became corrections, which the extraction already handles, and which
of the errata's own transcription slips must not be propagated.

Systemic parsing problems are **not** corrections — fix those in the extractor (`_normalize_whitespace()` and friends in `tools/extract_offices.py`) so every instance resolves at once. The hardcoded fix dicts that used to live in `extract_psalter.py`, `extract_fats.py`, and `convert_lectionary.py` were migrated into the manifest and deleted; don't reintroduce that pattern (see issue #13).

## Delivery workflow

Before merging to main:
```bash
make check-integrity && make test
node tools/validate_office.cjs && node tools/audit_office.cjs
```

Before promoting staging to production:
```bash
make deploy-staging && make test-staging
node tools/compare_staging.cjs [date] [mp]   # review diff
node tools/compare_staging.cjs [date] [ep]   # review diff
# → human review of diffs
make promote
```

## Key constraints

- Lectionary coverage: rolling 12-month window, currently 2025–2026 (Year B)
- Office forms: 30 in `data/offices.json`; form selection is season- and weekday-aware
- PyMuPDF (fitz) is the sole PDF extraction dependency.
