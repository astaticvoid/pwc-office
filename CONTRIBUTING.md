# Contributing to Pray Without Ceasing

## Dev environment setup

**Prerequisites:** Python 3.11+, Node.js 20+ (for Playwright and Vitest).

```bash
git clone <repo>
cd pwc_office

# Node dependencies + Playwright browsers (one-time)
npm install
npx playwright install

# Python venv with PyMuPDF and pytest (one-time)
make venv

# .env — no API keys needed; deploy targets read BUCKET, CF_DISTRIBUTION_ID,
# STAGING_DOMAIN, AWS_PROFILE from it
cp .env.example .env   # edit as needed
```

`make` picks up `.venv/bin/python3` automatically when it exists and falls back
to the ambient `python3` otherwise, so nothing needs activating. Installing into
Homebrew's python3 instead is not supported — it is externally managed (PEP 668).

The Makefile does `-include .env` on its first line, so `make` targets get those
variables and bare `aws` commands in your shell do not. Run deploys through
`make`.

Start the dev server:

```bash
make serve              # http://localhost:8080
```

`web/data` is a symlink to `../data` — changes to data files are picked up live without rebuilding.

---

## Data pipeline

All liturgical data is copyrighted and gitignored. You must run the pipeline locally to populate `data/` and `sources/`.

**Step 1 — download sources** (~30s, rate-limited to 1 req/s):

```bash
make fetch-sources
```

Downloads ACC liturgical PDFs to `sources/` and BAS lectionary CSVs from the ACC website. Skips files that already exist.

**Step 2 — extract and transform** (~2 min):

```bash
make extract
```

Extractors write intermediates into `.build/`; only the corrections stage writes
into `data/`. Runs in order:

1. `tools/extract_offices.py` → `.build/offices.1-extract.json` — PDF span extraction (font/colour classification)
2. `tools/normalize_offices.py` → `.build/offices.2-normalized.json` — hoists shared blocks into `_shared`
3. `tools/extract_psalter.py` → `.build/psalter.1-extract.json`
4. `tools/extract_collects.py` → `data/collects.json`
5. `tools/extract_fats.py` → `.build/fats-saints.1-extract.json`
6. `tools/convert_lectionary.py --window 12` → `.build/lectionary/YYYY-MM.json` + `data/season_bounds.json` (rolling 12-month window)
7. `tools/validate_corrections.py` — verify correction `old` values against the pre-correction artifacts
8. `tools/apply_corrections.py` — derives `data/offices.json`, `psalter.json`, `fats/saints.json`, and `data/lectionary/` from the `.build/` artifacts, applying `data/corrections.json`
9. `tools/update_extract_manifest.py` → `tools/extract_manifest.json` (committed hashes)

Re-run the whole pipeline after updating any source PDF or CSV, and after
changing any extractor — `make check-integrity` (which `make test` runs after
lint) fails on data that no longer matches the manifest. Running a single extractor
produces an intermediate, not a publishable file.

`tools/validate_lectionary.py` cross-checks the result against the ACC HTML and
needs network, so it is a separate `make validate` rather than part of `make
extract`.

**Changing an extractor** is verified by diffing its output, not by the test
suite — most extraction regressions are invisible to the tests:

```bash
make extract-baseline
# ...edit tools/extract_*.py...
make extract-diff EXPECT=0   # a refactor must change nothing
```

**Adding corrections:** text corrections belong in `data/corrections.json`
(committed), never as direct edits to `data/*.json` (gitignored and regenerated
on every extraction). Each correction goes under the category matching its data
type:

| Correction | Category | Located by |
|---|---|---|
| Office wording, casing, whitespace | `office_text` | `{office, field}` + substring |
| Missing or wrong psalm verse text | `psalter` | psalm number + substring |
| Saint biography | `fats` | saint + field + substring |
| Wrong citation | `lectionary_citations` | date + office + lesson index |
| Wrong lesson list | `lectionary_lessons` | date + office (whole list) |
| Name / rank / colour | `lectionary_names`, `_ranks`, `_colours` | date (whole value) |
| Garbled note | `lectionary_notes` | date (`clear` only) |

`office_text` takes two shapes, chosen by the type of `old`. Strings mean
substring replacement across every text-bearing segment of the field, with
`count` stating how many occurrences to expect (default 1; a mismatch fails the
run rather than applying partially) — this is what almost everything wants, since
the alternative is restating an entire canticle to change one word. Lists or
dicts mean whole-field replacement, for structural edits only: deleting,
reordering, or retyping segments.

Corrections do not follow `{"type": "shared"}` references. A shared block is
reachable from many forms, so correct `_shared` directly rather than through one
form — one correction to `_shared.reading_response_ordinary` fixes all 14
Ordinary forms at once.

A systemic parsing problem is not a correction: fix it in the extractor
(`_normalize_whitespace()` and friends in `tools/extract_offices.py`) so every
instance resolves at once.

---

## Test tiers

| Command | What it runs | When to use |
|---------|-------------|-------------|
| `make test` | lint → check-integrity → Vitest → pytest → the `qa` gate → rule mutation tests. No network | Always, before committing |
| `make qa` | Liturgical validators, audits, a11y, coherence score (threshold 100) | Included in `make test`; run alone to read a failure in full |
| `make test-mutations` | Mutation tests for the qa rules themselves — asserts each rule still fires on a targeted violation | Included in `make test`; run alone after changing `tools/validate_office.cjs` |
| `make check-integrity` | `data/` hashes vs `tools/extract_manifest.json` | Included in `make test`; run alone after any pipeline work |
| `make test-full` | Structural check of every day in the lectionary window | Before a data re-extraction |
| `make test-smoke` | 4 key dates: structure + reading cross-check | After office rendering changes |
| `make test-seasonal` | One MP+EP per liturgical season: structure + readings | After seasonal collect / form changes |
| `make test-web` | Playwright E2E — 142 tests across desktop + mobile projects | After any `web/app.js`, `render.js`, or CSS change |
| `make test-tools` | pytest for `tools/` (pytest comes from `make venv`) | After changing any extraction tool |
| `make validate` | Validate extracted lectionary against ACC HTML (network) | Before a data re-extraction |

**Typical pre-commit workflow:**

```bash
make test          # integrity, unit, tools, QA gate, rule mutation tests
make test-web      # Playwright suite (starts web/ on :8080 itself)
```

---

## Build and deploy

```bash
make build         # Assembles dist/ (dereferences data/ symlink)
make check-dist    # Runs build + tools/check_dist.py validation
make serve-dist    # Serves dist/ on :8081 — required for Playwright pre-deploy check
make deploy-staging   # Upload to releases/vTIMESTAMP/ + staging/ on S3
make test-staging     # Playwright smoke tests against staging
make promote          # CloudFront origin-path swap to production
```

Deploy requires AWS credentials with S3 + CloudFront permissions. Bucket and
distribution come from `BUCKET` and `CF_DISTRIBUTION_ID` in `.env` (see
`.env.example`); add `AWS_PROFILE` there too so credentials resolve without
passing a profile flag. `make deploy-staging` gates on `check-integrity`
and `check-dist`; staging deploys are always safe, but `make promote` publishes
to production, so don't run it without a decision to ship.

---

## Copyright constraints

`sources/` and `data/` (except `data/translations/kjv/`, `data/corrections.json`, and `data/paragraphs.json`) are gitignored because they contain or derive from copyrighted ACC/BAS liturgical text. Never commit these files — each contributor must run the extraction pipeline locally from ACC source files. The KJV is public domain and committed. `data/corrections.json` contains only short text snippets used to verify corrections.
