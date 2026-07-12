# AGENTS.md

Instructions for automated tooling working in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and stored as JSON.

## One-time setup

```bash
npm install
npx playwright install   # Chromium browser for Playwright E2E tests

pip install pdfplumber
brew install poppler     # pdftotext — required by extraction pipeline
```

Required environment variables in `.env` (gitignored):
- `BIBLE_API_KEY` — API.Bible key for NRSVUE Scripture fetching
- `ANTHROPIC_API_KEY` — needed for test-smoke and test-seasonal (citation LLM checks)

Always use `python3` from Homebrew, not macOS system python (3.9, too old). The Makefile uses `python3` and `pytest` (not `python3 -m pytest`).

## Commands

```bash
# Development
make serve                        # http://localhost:8080 (no build, data symlink followed live)

# Data pipeline
make fetch-sources                # download ACC PDFs + CSVs → sources/
make extract                      # full pipeline → data/*.json + data/lectionary/

# Testing
make test                         # Vitest + pytest (fast, no network) — go-to test command
make test-full                    # structural check: every day × MP+EP in lectionary
make test-smoke                   # 4 cases: citation check vs lectionary.anglican.ca
make test-seasonal                # 26 cases: one MP+EP per liturgical form
make test-web                     # Playwright E2E — requires `make serve-dist` in another terminal
make test-tools                   # Python pytest for tools/
make validate                     # Validate lectionary JSON against ACC HTML (network)

# CLI book-mode checks
make check-book FORM=... DATE=... # Diff CLI output against PDF golden files
make generate-golden              # Regenerate golden files for all 31 forms (gitignored)

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

# RCL Daily
make extract-rcl                  # extract RCL Daily from RTF → data/rcl-daily/
make validate-rcl                 # validate RCL Daily output

# Deploy (needs AWS creds + BUCKET + CF_DISTRIBUTION_ID)
make deploy BUCKET=... CF_DISTRIBUTION_ID=...
```

### Focused test commands

```bash
npx vitest run -t "pattern"       # run a single Vitest test
pytest tools/tests/ -k "pattern"   # run a single pytest
make check-book FORM=allsaints-mp  # diff one form against golden file
```

## Architecture

### Data flow

```
PDFs / HTML  →  Python tools/  →  data/*.json + data/lectionary/YYYY-MM.json
                                        ↓
                          web/app.js (SPA) + cli/book.js + cli/office.js (Node CLI)
```

Copyrighted content in `data/` is permanently gitignored. Only `data/translations/kjv/` and `data/patches.json` are committed. `web/data` is a symlink to `../data` — `make build` dereferences it via `cp -rL` into `dist/`; `make serve` follows the symlink live.

### Web SPA (`web/`)

Two-file core: `web/render.js` contains all office rendering functions and is imported by the browser SPA (`web/app.js`), the Node CLI (`cli/book.js`, `cli/office.js`), and Vitest tests. A change to `render.js` affects all three. Vitest covers rendering; Playwright covers E2E; `make check-book` covers CLI.

`web/app.js` (~1300 lines) handles routing, lectionary lookup, form selection (season + weekday → one of 31 office forms), and Scripture fetching (NRSVUE from API.Bible, lazy cached). No framework, no build step. Sections are separated by `// ── Name ───` banners.

**Leaders & responses are rendered by `web/render.js`.** There is no separate Go or Node renderer — the shared module is the single source of truth.

**No service worker.** `sw.js` is a kill-switch only — it unregisters itself and clears all caches to clean up old installs. `app.js` no longer registers a SW. Do not add SW caching back.

**Feature gate:** `FEATURE_RCL_DAILY = false` in `web/app.js:14`. RCL Daily lectionary UI is scaffolded but disabled — data only exists from Nov 2026 forward.

### Node CLI (`cli/`)

| File | Role |
|------|------|
| `cli/book.js` | Book-mode plain-text renderer. `node cli/book.js FORM [DATE]`. Used by `make check-book` and Node test harnesses. |
| `cli/office.js` | Debug renderer. `node cli/office.js [mp\|ep] [DATE]`. Strips HTML from `render.js` output. |

### Python tools (`tools/`)

Extraction pipeline (run via `make extract`):

1. `extract_offices.py` → `data/offices.json` (31 forms)
2. `normalize_offices.py` → deduplicates shared blocks into `_shared`
3. `extract_psalter.py` → `data/psalter.json`
4. `extract_collects.py` → `data/collects.json`
5. `validate_patches.py` + `apply_patches.py` → applies `data/patches.json`
6. `convert_lectionary.py` → `data/lectionary/` (from `sources/bas_short_*.csv`)
7. `validate_lectionary.py` → quality check
8. `update_extract_manifest.py` → `tools/extract_manifest.json` (SHA-256 + counts, committed)

**Data integrity guard:** `check_data_integrity.py` compares current `data/*.json` hashes against `tools/extract_manifest.json`. Exits 1 if any file was edited outside the pipeline. Wired into `make deploy` as a gate.

**Local extraction versioning:** `data/` has its own local git repo (gitignored from main). `make extract` auto-commits there. Use `git -C data/ log` / `git -C data/ diff HEAD~1` to inspect extraction history.

### Mobile shell (`ios/`, `android/`)

Capacitor wraps `dist/` as a native app (`capacitor.config.json`, `webDir: dist`). `make mobile-sync` rebuilds dist + runs `npx cap sync`. Native builds happen in Xcode / Android Studio. The web build is the source of truth — no native-only code paths.

### Design docs (`docs/`)

- `docs/DESIGN.md` — canonical design reference
- `docs/HANDOFF.md` — cross-session handoff notes and delivery records
- `docs/ROADMAP.md` — milestones, priorities, blocked items
- `docs/CORRECTNESS.md`, `docs/UX_AUDIT.md` — audit findings

---

## Hard constraints

- **Never edit `data/*.json` directly.** All corrections go through extractor fixes (`_TEXT_PATCHES` in `tools/extract_offices.py`, dicts in `tools/convert_lectionary.py`) or `data/patches.json`. `make check-integrity` validates this — it fails if any data file was touched outside the pipeline.
- **One logical change per commit.** Push after each commit — don't batch.
- **Deploy requires user go-ahead.** Never run `make deploy` unprompted.
- **Keep `docs/HANDOFF.md` and `docs/ROADMAP.md` current.** After every batch/stage is delivered, add a "Verified" section to HANDOFF.md with gates + change summary table, and update ROADMAP.md to move the relevant milestone from "In progress" to "Completed." These two docs are the single source of truth for what's done, what's next, and what's blocked. A stale roadmap is worse than no roadmap.

## Data correction locations

| Correction type | File | Mechanism |
|----------------|------|-----------|
| Office text (casing, wording) | `tools/extract_offices.py` | `_TEXT_PATCHES` list |
| Lectionary: wrong citations | `tools/convert_lectionary.py` | `LESSON_FIXES` dict |
| Lectionary: wrong day names | `tools/convert_lectionary.py` | `NAME_FIXES` dict |
| Lectionary: wrong ranks | `tools/convert_lectionary.py` | `RANK_FIXES` dict |
| Lectionary: wrong colours | `tools/convert_lectionary.py` | `COLOUR_FIXES` dict |
| Lectionary: garbled notes | `tools/convert_lectionary.py` | `CLEAR_NOTES` dict |
| Lectionary: note types | `tools/convert_lectionary.py` | `NOTE_TYPES` dict |
| Editorial corrections | `data/patches.json` | `apply_patches.py` applies after extraction |

## Delivery workflow

After any data pipeline change:
```bash
make extract && make check-integrity && make test && make check-text
```

After all commits in a batch/stage are pushed:
1. `make check-integrity` — must pass
2. `make test` — all tests must pass
3. `make build && make serve-dist &` — serves dist/ on :8081
4. Self-review with browser at `http://localhost:8081`; record findings in `docs/HANDOFF.md`
5. **Update `docs/HANDOFF.md`** — add a "Verified" section at the top with gates, a change summary table, and a next-priority line
6. **Update `docs/ROADMAP.md`** — move completed milestones to §1, update test counts, refresh blocked/planned items
7. Stop — do not deploy

## Key constraints

- Lectionary coverage: rolling 12-month window, currently 2025–2026 (Year B)
- Office forms: 31 in `data/offices.json`; form selection is season- and weekday-aware
- `FEATURE_RCL_DAILY = false` until Nov 2026 data window

## Next priorities (2026-07)

- **Mobile Stage 2**: Store submission (Stage 1 delivered — blocked on Apple/Google Developer accounts + ACC rights)
- **RCL Daily**: Extraction pipeline complete, data extracted Nov 2026 forward. UI integration deferred until the data window opens.
