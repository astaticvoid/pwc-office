# AGENTS.md

Instructions for automated tooling working in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy (Morning and Evening Prayer). The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from ACC/BAS PDFs and CSVs via Python scripts and stored as JSON.

This file is the authoritative technical reference. `CLAUDE.md` is a pointer to it. `README.md` (user orientation) and `CONTRIBUTING.md` (contributor setup and test tiers) summarize the same ground for humans. When a change here invalidates documentation there, update them in the same commit.

## Governing Liturgical Principle

**Render the rite; do not edit it (ADR 0016).** Liturgical text from PWC, the BAS, or the lectionary renders as authorized and as written:
- No hiding text behind a mode, condensing it, paraphrasing it, or resolving choices on the reader's behalf (ADR 0013, 0014).
- App-authored liturgical text requires provenance (ADR 0015).
- **ADR 0019 is the casebook** of settled readings upstream review has approved, each defining what it forbids. Consult it before touching rubrics or selectors.

## Setup & Environment

```bash
npm install
npx playwright install              # Chromium browser for Playwright E2E tests
make venv                           # .venv with pymupdf + pytest + ruff
```

Every Python target runs through `$(PYTHON)`, resolving to `.venv/bin/python3` when the venv exists and falling back to ambient `python3` otherwise (CI). Do not install into Homebrew's python3 directly (PEP 668).

Environment variables in `.env` (gitignored, loaded automatically via `Makefile` `-include .env`):
- `BUCKET`, `CF_DISTRIBUTION_ID`: Required for `make deploy-staging`, `promote`, `rollback`.
- `STAGING_DOMAIN`: Required for `make test-staging`.
- `AWS_PROFILE`: Set so AWS CLI credentials resolve automatically.
- Scripture: Bundled KJV works offline in `data/translations/kjv/`. Local NRSVUE in `data/translations/nrsvue/` is used automatically when present.

**Always run build, test, and deploy operations through `make`.**

## Commands

```bash
# Development
make serve                        # http://localhost:8080 (live data symlink)

# Data pipeline
make fetch-sources                # download ACC PDFs + CSVs → sources/
make extract                      # full pipeline → data/*.json + data/lectionary/

# Testing
make test                         # primary local gate: lint → check-integrity → test-unit → test-tools → qa → test-mutations
make lint                         # eslint (JS) + tsc (web type-check) + ruff (Python) + stylelint (CSS)
make test-unit                    # Vitest suite (tests/unit/)
make test-tools                   # pytest suite for extraction tools (tools/tests/)
make test-web                     # Playwright E2E suite across desktop and mobile (tests/e2e/)
make test-smoke                   # representative days: structure + reading cross-check
make test-seasonal                # seasonal cases: one MP+EP per liturgical form
make test-full                    # structural check of every day in lectionary window
make validate                     # check-text + validate_lectionary.py vs ACC HTML (network)

# Quality assurance (all run by `make qa`, and gated by `make test`)
make check-conservation           # page ↔ data line accounting across all active chains
node tools/validate_office.cjs    # liturgical rules across structural, textual, and seasonal tiers
node tools/validate_render.cjs    # rendered-DOM structure for all office forms
node tools/validate_css.cjs       # structural CSS validity (web/*.css)
node tools/validate_lectionary.cjs # citation syntax and data resolution for every date × office
node tools/audit_office.cjs       # cross-form statistical outlier detection (z-score)
node tools/audit_text.cjs         # cross-form text-length outliers within peer groups
node tools/audit_rubric_repeats.cjs # duplicate rubrics or isolated doxology cue anomalies
node tools/audit_a11y.cjs         # HTML accessibility structure + WCAG AA palette contrast
node tools/coherence_score.cjs V.json A.json  # composite quality score (threshold: 100)

# Quality gates & reviews
make check-integrity              # verify data/ hashes match extract_manifest.json
make intake-year                  # report lectionary CSV decisions for an upcoming year
make audit-errata                 # check data/offices.json against docs/errata/
make check-text --strict          # scan for PDF extraction artifacts
node tools/compare_staging.cjs [date] [mp|ep]  # A/B diff staging vs production DOM
node tools/review_form.cjs FORM   # line-numbered text renderer for manual review

# Build & Mobile
make build                        # assemble dist/ (copies web/, dereferences data symlink)
make check-dist                   # build dist/ + run tools/check_dist.py validation
make serve-dist                   # serve dist/ on :8081 (for pre-deploy verification)
make mobile-sync                  # build dist/ + cap sync + verify native asset parity
make mobile-bump-version          # increment iOS CFBundleVersion in project.pbxproj
make mobile-ios                   # mobile-sync + open Xcode
make mobile-android               # mobile-sync + open Android Studio

# Deploy
make deploy-staging               # upload release to S3 staging/
make test-staging                 # Playwright tests against staging
make promote                      # swap CloudFront origin path to production
make rollback                     # revert to previous release
```

## Architecture

### Data Flow

```
PDFs / CSVs  →  PyMuPDF (fitz)  →  .build/ (Stage 1 & 2)
                                       ↓
                            apply_corrections.py (Stage 3)
                                       ↓
                 data/*.json  +  data/lectionary/YYYY-MM.json
                                       ↓
                   web/render.js (shared rendering engine)
                   ├── web/app.js (client SPA)
                   ├── cli/book.js (plain-text CLI)
                   └── cli/office.js (debug CLI)
```

- **Distribution posture:** Copyrighted liturgical text in `data/` and `sources/` is gitignored. Only public-domain KJV, `data/corrections.json`, and `data/paragraphs.json` are committed. `web/data` is a symlink to `../data` dereferenced into `dist/` on build.
- **Capacitor binary note:** Store builds bundle text into the app package; keep beta distribution inside authorized Synod evaluation groups.
- **Shared renderer (`web/render.js`):** Single source of truth for rendering segments to HTML (`renderSegments`), plain text (`renderSegmentsText`), and structured JSON (`segmentsToJSON`).
- **No service worker:** `sw.js` is a kill-switch only (unregisters old installs and clears caches).

## Data Pipeline & Integrity

The extraction pipeline runs via `make extract`:

| Stage | Script | Writes | Role |
|---|---|---|---|
| 1 | `tools/extract_offices.py` | `.build/offices.1-extract.json` | Span extraction with font flag & color classification |
| 2 | `tools/normalize_offices.py` | `.build/offices.2-normalized.json` | Hoists shared blocks into `_shared` |
| 3 | `tools/extract_psalter.py` | `.build/psalter.1-extract.json` | Psalter extraction with verse & midpoint markers |
| 4 | `tools/extract_collects.py` | `data/collects.json` | Direct extraction of seasonal and holy day collects |
| 5 | `tools/extract_fats.py` | `.build/fats-saints.1-extract.json` | For All the Saints saint biographies |
| 6 | `tools/convert_lectionary.py` | `.build/lectionary/`, `data/season_bounds.json` | Lectionary CSV conversion over a rolling 12-month window |
| 7 | `tools/validate_corrections.py` | *(read-only)* | Checks `data/corrections.json` against pre-correction `.build/` artifacts |
| 8 | `tools/apply_corrections.py` | `data/offices.json`, `psalter.json`, `fats/saints.json`, `lectionary/` | Derives all published data, applying audited corrections |
| 9 | `tools/update_extract_manifest.py` | `tools/extract_manifest.json` | Records published file and source hashes |

### Pipeline Invariants

- **Derivation is unconditional:** `apply_corrections.py` derives every published file on every run, even when correction lists are empty.
- **Intermediates are never final:** `.build/` holds stage artifacts; only `data/` ships.
- **Integrity guard:** `check_data_integrity.py` verifies published files against `tools/extract_manifest.json`. Retiring an input requires removing it from `EXTRACTION_SOURCES` in `update_extract_manifest.py`.
- **Changing an extractor:** Verify behavior preservation by running `make extract-baseline`, making the edit, and requiring `make extract-diff EXPECT=0` followed by `make check-conservation`. PyMuPDF version updates must be treated as extractor changes.
- **Line break geometry:** Line break decisions are physical measurements of page horizontal slack (`gap`) and vertical leading (`lead`), never trailing spaces or regex proxies.
- **Page bounds:** Office page ranges are detected from PDF content via `tools/detect_office_bounds.py` (committed to `tools/office_bounds.json`). No hardcoded page numbers.
- **New lectionary year:** Follow `docs/runbooks/lectionary-year-intake.md` using `make intake-year`.

## Quality Assurance & Source Conservation

- **`check_conservation.py`** is the primary truth check against the printed page. It walks source lines in both directions:
  1. *Page → Data:* Every printed line must ship or match a named rule (reflow, heading consumed as structure, label, audited correction).
  2. *Data → Page:* Every shipped line must appear on the page or match an authorized rule.
  - Active chains: `offices`, `psalter`, `fats`.
  - Open divergences are tracked in `tools/conservation_baseline.json` (`known: []`). A fix deletes its entry in the same commit; shrinking the list represents convergence.
- **Liturgical validators (`tools/validate_office.cjs`):** Evaluates forms against structural, textual, and seasonal rules, driving `tools/coherence_score.cjs` (threshold 100 required).
- **Accessibility contrast check (`tools/audit_a11y.cjs`):** Programmatically composites every text and graphic color pair across all seasons and themes in OKLab against WCAG AA standards.
- **Design reviews (ADR 0010):** Visual UI changes must be prototyped on a temporary `web/_design-*.html` page with stacked desktop (58rem) and mobile (390px) mockups before touching `office.css`. The prototype is deleted once implemented.

## Mobile Shell (Capacitor)

- **Staleness guard:** Synced directories (`ios/App/App/public/`, `android/.../assets/public/`) are gitignored. `tools/check_mobile_sync.py` (run by `make mobile-sync`) verifies bidirectional parity between `dist/` and native public directories to prevent archiving stale web assets.
- **Build numbers:** TestFlight requires increasing `CFBundleVersion` per upload. Run `make mobile-bump-version` to atomically update Debug and Release configurations in `project.pbxproj`.
- **App name propagation:** Display name changes must be made across `capacitor.config.json` (`appName`), `ios/App/App/Info.plist` (`CFBundleDisplayName`), `android/.../strings.xml` (`app_name`), and `web/manifest.json`.
- **Release runbook:** Follow `docs/runbooks/ios-testflight-ship.md`.

## Data Corrections Manifest

All corrections live in `data/corrections.json` (ADR 0005) and are categorized by target:
- `office_text`: `{office, field}` + substring replace (or whole-field list/dict for structural changes). Use `office: "*"` for identical shared rubrics.
- `psalter`: Psalm number + substring replace.
- `fats`: Saint + field + substring replace.
- `lectionary_citations`, `lectionary_psalms`, `lectionary_lessons`, `lectionary_names`, `lectionary_ranks`, `lectionary_colours`, `lectionary_notes`.
Systemic extraction errors must be resolved in extractors, not patched in `corrections.json`. Run `make audit-errata` after modifying `docs/errata/` or `office_text`.

## Commit, Review & Code Standards

- **Never edit `data/*.json` directly.** Edit extractors or `data/corrections.json` and re-run `make extract`.
- **One logical change per commit.** Keep changes atomic and independently testable.
- **No `Co-Authored-By` trailers.** Commits must be attributed solely to the human author (enforced by `githooks/commit-msg`).
- **Subagent code review:** Every substantial change must be reviewed by an adversarial subagent before commit to identify regressions or edge cases.
- **Production deploys require approval:** Never run `make promote` unprompted. Staging deploys are safe to run.
- **Comments describe what is, not what was.** Do not include bug histories or previous implementations in comments. Use bare issue references (`#110`) for historical context. All tasks and bugs are tracked in GitHub Issues.
