# AGENTS.md

Instructions for automated tooling working in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and stored as JSON.

## One-time setup

```bash
npm install
npx playwright install              # Chromium browser for Playwright E2E tests
python3 -m pip install pymupdf      # PDF extraction dependency (PyMuPDF)
```

Required environment variables in `.env` (gitignored):
- No keys required. KJV scripture is bundled in `data/translations/kjv/` and works offline.
- NRSVUE scripture is not distributable — if a local copy is placed at `data/translations/nrsvue/` the app will use it.
- Deploy targets need `BUCKET`, `CF_DISTRIBUTION_ID`, `STAGING_DOMAIN`, `STAGING_CF_ID`.
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
# NOTE: after changing extraction logic in extract_offices.py, re-run
# `make extract` before `make check-integrity`.  The manifest stores hashes of
# the committed data; stale hashes after a code change will fail the check.

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

1. `extract_offices.py` → `data/offices.json` (30 forms) — PyMuPDF span-level extraction
2. `extract_office_styles.py` — span classification via font flags + sRGB color
3. `normalize_offices.py` → deduplicates shared blocks into `_shared`
4. `extract_psalter.py` → `data/psalter.json`
5. `extract_collects.py` → `data/collects.json`
6. `validate_corrections.py` + `apply_corrections.py` → applies `data/corrections.json`
7. `convert_lectionary.py` → `data/lectionary/` (from `sources/bas_short_*.csv`)
8. `update_extract_manifest.py` → `tools/extract_manifest.json` (SHA-256 + counts, committed)

**Data integrity guard:** `check_data_integrity.py` compares current `data/*.json` hashes against `tools/extract_manifest.json`. Exits 1 if any file was edited outside the pipeline. Wired into `make deploy-staging` as a gate.

**Line-break handling.** Column wraps (PDF soft breaks) and intentional verse breaks are now distinguished per-line by the trailing-space signature in the PDF (see issue #38). `spans_to_typed_lines` detects trailing space on raw span text and threads a `wrap` flag through the extraction pipeline; `_merge` joins only wrapped lines. The former `_VERSE_SECTIONS` / `_LINE_JOIN` section-level allowlist is retired. `VERSE_SECTIONS` in `tools/validate_office.cjs` is the single list used by the validator's `no-prose-line-breaks` rule. When adding a verse-like section, update that list and the line-count assertions in `tests/unit/render.test.js`.

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
| Office text (wording, casing, whitespace) | `office_text` | `{office, field}` |
| Psalter: missing/incorrect verse text | `psalter` | psalm number + substring replace |
| Saint biographies | `fats` | saint + field + substring replace |
| Lectionary: wrong citation | `lectionary_citations` | date + office + lesson index |
| Lectionary: wrong lesson list | `lectionary_lessons` | date + office (whole-list replace) |
| Lectionary: name / rank / colour | `lectionary_names`, `lectionary_ranks`, `lectionary_colours` | date (whole-value replace) |
| Lectionary: garbled note | `lectionary_notes` | date (`clear` action only) |

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
