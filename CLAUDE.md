# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Go CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and committed as JSON.

## Commands

```bash
# Development — serve web/ directly (no build step, data symlink followed live)
make serve                        # http://localhost:8080

# Testing
make test                         # Go unit tests (fast, no API key)
make test-full                    # Structural check every day in lectionary
make test-smoke                   # 4 days + LLM evaluation (needs ANTHROPIC_API_KEY)
make test-seasonal                # One MP+EP per season + LLM evaluation
make test-web                     # Playwright E2E suite (tests/e2e/office.spec.js)
make test-tools                   # Python pytest for tools/ (needs pytest: brew install pytest)
make validate                     # Validate lectionary JSON against ACC HTML (network)

# Single Go test
go test -run TestName ./...

# Build & verify before deploy
make build                        # Assembles dist/, stamps service worker cache hash
make check-dist                   # Runs build + tools/check_dist.py validation
make serve-dist                   # Serves dist/ on :8081 (required for E2E pre-deploy)

# Deploy (needs AWS creds + BUCKET + CF_DISTRIBUTION_ID)
make deploy BUCKET=... CF_DISTRIBUTION_ID=...
```

Always use `python3` from Homebrew, not macOS system python (3.9, too old).

### Required environment variables (`.env`, gitignored)

```
ANTHROPIC_API_KEY=   # needed for test-smoke and test-seasonal
BIBLE_API_KEY=       # API.Bible key for NRSVUE Scripture fetching
```

## Architecture

### Data flow

```
PDFs / HTML  →  Python tools/  →  data/*.json + data/lectionary/YYYY-MM.json
                                        ↓
                          web/app.js  (SPA)   +   cmd/dailyoffice/main.go  (CLI)
                          (fetches JSON at runtime)    (loads JSON from disk)
```

Copyrighted ACC/BAS content in `data/` is gitignored; only KJV (public domain) is committed. The `web/data` entry is a symlink to `../data` — `make build` dereferences it via `cp -rL`.

### Go packages

| Path | Role |
|------|------|
| `*.go` (root) | Core types: `Day`, `Season`, `Form`, `Psalter`, `Collects`, `Bible` interface. Loaded by both CLI and e2e tests. |
| `internal/office/` | `office.Render()` — assembles a complete office as Markdown from a Day + data sources |
| `cmd/dailyoffice/` | CLI entry point: flag parsing, date resolution, calls `office.Render()` |
| `e2e/` | LLM-evaluated tests (build tags: `e2e_smoke`, `e2e_seasonal`, `e2e_full`) |
| `tests/e2e/` | Playwright browser tests (`office.spec.js`) — run via `make test-web` |

No external Go dependencies — stdlib only.

### Web SPA (`web/`)

Single-file architecture: `web/app.js` (~1400 lines) handles routing, lectionary lookup, form selection, rendering, and Scripture fetching. No framework, no build step. Sections are separated by `// ── Name ───` banners for navigation.

- **Form selection**: Season + weekday → one of 31 office forms from `data/offices.json`
- **Psalms**: Loaded from `data/psalter.json` with verse numbers and midpoint markers
- **Scripture**: KJV embedded in Go binary (`kjv_embed.go`); NRSVUE fetched from API.Bible (lazy, cached)
- **Lectionary**: Monthly JSON files (`data/lectionary/YYYY-MM.json`) fetched lazily and cached by service worker
- **Offline**: Service worker (`sw.js`) caches shell + all data files; cache key is SHA256-stamped at build time
- **Stuck SW escape hatch**: visit `/?reset` to unregister the service worker and clear caches

### Python tools (`tools/`)

One-time data pipeline scripts. Run in order:
1. `extract_offices.py` → `data/offices.json`
2. `extract_psalter.py` → `data/psalter.json`
3. `extract_collects.py` → `data/collects.json`
4. `scrape_lectionary.py` + `convert_lectionary.py` → `data/lectionary/`
5. `validate_lectionary.py` — quality check

### Redesign work (`redesign/`)

Active design exploration lives in `redesign/` (untracked). `DESIGN.md` is the canonical reference; `HANDOVER.md` summarises decisions for cross-session continuity. Do not delete this directory.

## Key constraints

- **Lectionary coverage**: rolling 12-month window (Year B complete; Year A coverage begins Advent 2026)
- **Service worker cache**: The string `pwc-v1` in `sw.js` is a placeholder — `make build` replaces it with a content hash. Never hardcode a real hash there.
- **Office forms**: 31 forms in `data/offices.json`; form selection logic in `app.js` is season- and weekday-aware
- **No Co-Authored-By** trailers in commits
- **One logical change per commit** — don't batch unrelated changes across sessions
