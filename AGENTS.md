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
node tools/validate_office.cjs    # 6 liturgical rules against all 30 forms
node tools/audit_office.cjs       # cross-form statistical outlier detection (z-score)
node tools/compare_staging.cjs    # A/B diff staging vs production rendered DOM
node tools/review_form.cjs FORM   # line-numbered text renderer for manual review

# CLI book-mode checks
make check-book FORM=... DATE=... # Diff CLI output against PDF golden files
make generate-golden              # Regenerate golden files for all 30 forms (gitignored)

# Quality gates
make check-text                   # scan for PDF extraction artifacts
make check-text --strict          # same but exits non-zero on findings
make check-casing                 # casing oracle against pdftotext ground truth
make check-integrity              # verify data/ hashes match extract manifest — fails if any

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
make check-book FORM=allsaints-mp  # diff one form against golden file
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

Copyrighted content in `data/` is permanently gitignored. Only `data/translations/kjv/`, `data/patches.json`, and `data/corrections.json` are committed. `web/data` is a symlink to `../data` — `make build` dereferences it via `cp -rL` into `dist/`; `make serve` follows the symlink live.

### Web SPA (`web/`)

`web/render.js` contains all office rendering functions and is imported by the browser SPA (`web/app.js`), the Node CLI (`cli/book.js`, `cli/office.js`), QA tools, and Vitest tests. A change to `render.js` affects all consumers.

`web/app.js` handles routing, lectionary lookup, form selection (season + weekday → one of 30 office forms), and Scripture fetching (NRSVUE from local `data/translations/`, KJV bundled). No framework, no build step.

**Leaders & responses are rendered by `web/render.js`.** The shared module provides:
- `renderSegments` — HTML output (browser SPA)
- `renderSegmentsText` — structured text blocks (CLI, QA tools)
- `segmentsToJSON` — structured JSON output (validators, cross-form audit)

**No service worker.** `sw.js` is a kill-switch only — it unregisters itself and clears all caches to clean up old installs. Do not add SW caching back.

**Feature gate:** `FEATURE_RCL_DAILY = false` in `web/app.js:14`. RCL Daily lectionary UI is scaffolded but disabled — data only exists from Nov 2026 forward.

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

**Page bounds:** `detect_office_bounds.py` detects office form page ranges from PDF content (title patterns). Output is committed as `tools/office_bounds.json`. No hardcoded page numbers.

### QA tools (`tools/`)

| File | Role |
|------|------|
| `validate_office.cjs` | 6 liturgical rules checked against all 30 forms (Amen presence, line breaks, stray spaces, section completeness) |
| `audit_office.cjs` | Cross-form statistical audit — 14 metrics, 4 peer groups, 2σ z-score outlier detection |
| `compare_staging.cjs` | A/B rendered DOM diff between staging and production (use before `make promote`) |
| `review_form.cjs` | Line-numbered text renderer for manual review (`node tools/review_form.cjs advent-mp`) |

### Mobile shell (`ios/`, `android/`)

Capacitor wraps `dist/` as a native app (`capacitor.config.json`, `webDir: dist`). `make mobile-sync` rebuilds dist + runs `npx cap sync`. The web build is the source of truth — no native-only code paths.

---

## Hard constraints

- **Never edit `data/*.json` directly.** All corrections go through `data/corrections.json` (committed single manifest) or the extraction pipeline. `make check-integrity` validates this — it fails if any data file was touched outside the pipeline.
- **One logical change per commit.** Push after each commit — don't batch.
- **Subagent code review before commit.** Every change must be reviewed by a hostile subagent before committing. The subagent checks for bugs, edge cases, silent failures, performance issues, and integration problems. Fix all high-severity findings before committing.
- **Deploy requires user go-ahead.** Never run `make promote` unprompted. Staging deploys are always safe.
- **Systemic fixes over patches.** When a bug is found, categorize it: systemic (fix in extractor/renderer), pattern (multiple forms), or data (single form). Fix the root cause so all instances are resolved, not just the one found.

## Data correction locations

| Correction type | File | Mechanism |
|----------------|------|-----------|
| Office text (casing, wording, whitespace) | `tools/extract_offices.py` | `_normalize_whitespace()` pass (systemic) or `_TEXT_PATCHES` list (targeted) |
| Editorial corrections (all data types) | `data/corrections.json` | `validate_corrections.py` + `apply_corrections.py` |
| Lectionary: wrong citations | `tools/convert_lectionary.py` | Fix dicts (LESSON_FIXES, NAME_FIXES, etc.) |
| Psalter: missing/incorrect text | `tools/extract_psalter.py` | Inline fix with `source_corrections` metadata |

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
- PyMuPDF (fitz) is the sole PDF extraction dependency. pdftotext is optional (only for `check_casing.py` oracle)
- `FEATURE_RCL_DAILY = false` until Nov 2026 data window
