# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and committed as JSON.

## Delivery workflow

After each commit: `git push`. Do not batch pushes — GitHub is the running record of progress.

After all commits in a batch are pushed:
1. `make check-integrity` — must pass before build
2. `make build && make serve-dist` — serves dist/ on :8081 in the background (`make serve-dist &`)
3. Write a "Ready for Cowork review" section at the top of `docs/HANDOFF.md` listing what to spot-check and at which URLs
4. Stop. Do not run `make deploy`. Cowork reviews the running :8081 instance and approves deploy.

Cowork will browse to `http://localhost:8081` via browser tools, verify key dates, and trigger `make deploy` only after approving.

## Commands

```bash
# Development — serve web/ directly (no build step, data symlink followed live)
make serve                        # http://localhost:8080

# Testing
make test                         # Vitest unit tests + Python pytest (fast, no API key)
make test-full                    # Structural check every day in lectionary (node)
make test-smoke                   # 4 cases: structural + citation check vs lectionary.anglican.ca
make test-seasonal                # 26 cases: one MP+EP per liturgical form
make test-web                     # Playwright E2E suite (tests/e2e/office.spec.js)
make test-tools                   # Python pytest for tools/ (needs pytest: brew install pytest)
make validate                     # Validate lectionary JSON against ACC HTML (network)

# Build & verify before deploy
make build                        # Assembles dist/, stamps service worker cache hash
make check-dist                   # Runs build + tools/check_dist.py validation
make serve-dist                   # Serves dist/ on :8081 (required for E2E pre-deploy)

# Deploy (needs AWS creds + BUCKET + CF_DISTRIBUTION_ID) — Cowork approval required first
make deploy BUCKET=... CF_DISTRIBUTION_ID=...
```

Always use `python3` from Homebrew, not macOS system python (3.9, too old).

### Required environment variables (`.env`, gitignored)

```
BIBLE_API_KEY=       # API.Bible key for NRSVUE Scripture fetching
```

## Architecture

### Data flow

```
PDFs / HTML  →  Python tools/  →  data/*.json + data/lectionary/YYYY-MM.json
                                        ↓
                          web/app.js  (SPA)   +   cli/book.js + cli/office.js  (Node CLI)
                          (fetches JSON at runtime)    (loads JSON from disk)
```

Copyrighted ACC/BAS content in `data/` is gitignored. The `web/data` entry is a symlink to `../data` — `make build` dereferences it via `cp -rL`.

### Node CLI (`cli/`)

| File | Role |
|------|------|
| `cli/book.js` | Book-mode plain-text renderer. `node cli/book.js FORM [DATE]`. Output suitable for diffing against PDF golden files. Used by `make check-book` and all Node test harnesses. |
| `cli/office.js` | Debug renderer. `node cli/office.js [mp\|ep] [DATE]`. Strips HTML from `render.js` output; useful for quick inspection. |

### Web SPA (`web/`)

Single-file architecture: `web/app.js` (~1400 lines) handles routing, lectionary lookup, form selection, rendering, and Scripture fetching. No framework, no build step. Sections are separated by `// ── Name ───` banners for navigation.

- **Form selection**: Season + weekday → one of 31 office forms from `data/offices.json`
- **Psalms**: Loaded from `data/psalter.json` with verse numbers and midpoint markers
- **Scripture**: NRSVUE fetched from API.Bible (lazy, cached)
- **Lectionary**: Monthly JSON files (`data/lectionary/YYYY-MM.json`) fetched lazily and cached by service worker
- **Offline**: Service worker (`sw.js`) caches shell + all data files; cache key is SHA256-stamped at build time
- **Stuck SW escape hatch**: visit `/?reset` to unregister the service worker and clear caches

### Python tools (`tools/`)

One-time data pipeline scripts. Run via `make extract` (or in order):
1. `extract_offices.py` → `data/offices.json`
2. `normalize_offices.py` → deduplicates shared blocks into `_shared`
3. `extract_psalter.py` → `data/psalter.json`
4. `extract_collects.py` → `data/collects.json`
5. `validate_patches.py` + `apply_patches.py` → applies `data/patches.json` post-extraction corrections
6. `convert_lectionary.py` → `data/lectionary/` (reads `sources/bas_short_*.csv`)
7. `validate_lectionary.py` — quality check
8. `update_extract_manifest.py` → `tools/extract_manifest.json` (SHA-256 + entry counts; committed to git — tracks extraction history without committing copyrighted data)

**Data integrity guard** (`make check-integrity`): `check_data_integrity.py` — compares current `data/*.json` hashes against `tools/extract_manifest.json`. Exits 1 if any file was modified outside the pipeline (i.e. monkey-patched directly). Wired into `make deploy` as a gate — deploy fails if data drift is detected. This is the primary protection against agent sessions editing `data/` directly instead of going through extractors or `patches.json`.

**Local extraction versioning**: `data/` has its own local git repo (never pushed — `data/` is gitignored). `make extract` commits after each run. `git -C data/ diff HEAD~1` shows exact text diff between last two extractions; `git -C data/ log` gives full history. Complements the integrity guard: the guard catches monkey patches; the local git gives content diff and rollback.

**Text quality check** (`make check-text`): `check_text_quality.py` — rule-based scan for PDF extraction artifacts (missing spaces, duplicate words, merged tokens). Run after `make extract` to catch issues before deploy.

### Manual data corrections — where they live

**Never edit `data/*.json` files directly.** All corrections are baked into the extractors and survive re-extraction. Re-extraction will overwrite any direct edits.

| Correction type | File | Mechanism |
|----------------|------|-----------|
| Offices: mis-capitalised responses (BUG-18) | `tools/extract_offices.py` | `_TEXT_PATCHES` list → `_apply_text_patches()` runs at end of extraction |
| Lectionary: wrong lesson citations | `tools/convert_lectionary.py` | `LESSON_FIXES` dict (keyed by date + office) |
| Lectionary: wrong day names | `tools/convert_lectionary.py` | `NAME_FIXES` dict |
| Lectionary: wrong ranks | `tools/convert_lectionary.py` | `RANK_FIXES` dict |
| Lectionary: wrong colours | `tools/convert_lectionary.py` | `COLOUR_FIXES` dict |
| Lectionary: garbled notes | `tools/convert_lectionary.py` | `CLEAR_NOTES` dict |
| Lectionary: note type classification | `tools/convert_lectionary.py` | `NOTE_TYPES` dict |
| Future offices.json corrections | `data/patches.json` | Add patch entry; `apply_patches.py` applies after extraction |

`data/patches.json` currently has 6 active entries (sovereign collect text, Canada Day / Saint Peter / Saint Paul page mislabeling). Add entries there only for corrections that cannot be expressed in the extraction logic (e.g. wording changes that require editorial judgment rather than a parsing fix).

### Redesign work (`redesign/`)

Active design exploration lives in `redesign/` (untracked). `DESIGN.md` is the canonical reference; `HANDOVER.md` summarises decisions for cross-session continuity. Do not delete this directory.

## Key constraints

- **Lectionary coverage**: rolling 12-month window (Year B complete; Year A coverage begins Advent 2026)
- **Service worker cache**: The string `pwc-v1` in `sw.js` is a placeholder — `make build` replaces it with a content hash. Never hardcode a real hash there.
- **Office forms**: 31 forms in `data/offices.json`; form selection logic in `app.js` is season- and weekday-aware
- **No Co-Authored-By** trailers in commits
- **One logical change per commit** — don't batch unrelated changes across sessions
