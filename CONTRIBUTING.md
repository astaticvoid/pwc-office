# Contributing to Pray Without Ceasing

## Dev environment setup

**Prerequisites:** Go 1.21+, Python 3.11+ (Homebrew — not macOS system python), Node.js 20+ (for Playwright).

```bash
git clone <repo>
cd pwc_office

# Install Playwright browsers (one-time)
npm install
npx playwright install

# Create .env with your API keys
cp .env.example .env   # edit as needed
# ANTHROPIC_API_KEY=  (needed for test-smoke and test-seasonal)
# BIBLE_API_KEY=       (API.Bible key for NRSVUE Scripture fetching)
```

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

Downloads ACC liturgical PDFs to `sources/` and BAS lectionary CSVs from the ACC website. Skip files that already exist.

**Step 2 — extract and transform** (~2 min):

```bash
make extract
```

Runs in order:
1. `tools/extract_offices.py` → `data/offices.json` — PDF character extraction (font/colour classification)
2. `tools/normalize_offices.py` — deduplicates shared blocks into `data/offices.json#_shared`
3. `tools/extract_psalter.py` → `data/psalter.json`
4. `tools/extract_collects.py` → `data/collects.json`
5. `tools/validate_patches.py` — verify patch `old` values match current data
6. `tools/apply_patches.py` — apply corrections from `data/patches.json`
7. `tools/convert_lectionary.py --accept --window 12` → `data/lectionary/YYYY-MM.json` (rolling 12-month window)
8. `tools/validate_lectionary.py` — cross-check against ACC HTML

Re-run the pipeline after updating any source PDF or CSV.

**Adding corrections:** text corrections belong in `data/patches.json` (committed), not as direct edits to `data/offices.json` (which is gitignored and regenerated on each extraction). See `tools/apply_patches.py` for the patch format.

---

## Test tiers

| Command | What it runs | When to use |
|---------|-------------|-------------|
| `make test` | Go unit tests — fast, no API key | Always, before committing |
| `make test-full` | Structural check of every day in the lectionary window | Before a data re-extraction |
| `make test-smoke` | 4 key dates: structure + reading cross-check | After office rendering changes |
| `make test-seasonal` | One MP+EP per liturgical season: structure + readings | After seasonal collect / form changes |
| `make test-web` | Playwright E2E suite (70+ browser tests) | After any `web/app.js` or CSS change |
| `make test-tools` | Python pytest for `tools/` (requires: `brew install pytest`) | After changing any extraction tool |
| `make validate` | Validate extracted lectionary against ACC HTML (network) | Before a data re-extraction |
| `make update-golden` | Regenerate golden snapshot files after intentional rendering change | After a rendering change |

**Typical pre-commit workflow:**

```bash
make test          # Go unit tests
make test-web      # Playwright suite (requires: make serve-dist in another terminal)
```

---

## Build and deploy

```bash
make build         # Assembles dist/ (dereferences data/ symlink, stamps sw.js cache key)
make check-dist    # Runs build + tools/check_dist.py validation
make serve-dist    # Serves dist/ on :8081 — required for Playwright pre-deploy check
make deploy BUCKET=<s3-bucket> CF_DISTRIBUTION_ID=<cf-id>
```

Deploy requires AWS credentials with S3 + CloudFront permissions. See `project_aws.md` in the memory directory for the bucket and distribution details.

---

## Copyright constraints

`sources/` and `data/` (except `data/translations/kjv/` and `data/patches.json`) are gitignored because they contain or derive from copyrighted ACC/BAS liturgical text. Never commit these files. The KJV is public domain and committed. `data/patches.json` contains only short text snippets used to verify corrections.

An ACC licence inquiry is pending to eventually allow committing `data/` publicly.
