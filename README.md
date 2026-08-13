# Pray Without Ceasing — Daily Office

A web app for Morning and Evening Prayer following the Book of Alternative
Services (BAS) and the *Pray Without Ceasing* (PWC) office book of the
Anglican Church of Canada.

## What it does

For any date in the liturgical year the app renders a complete, ready-to-pray
office:

- Full liturgical form for the season: opening responses, invitatory,
  responsory, canticle, affirmation, litany, seasonal collects, Lord's Prayer,
  dismissal
- Appointed psalm(s) with full verse text and midpoint markers
- Scripture lessons with full text (NRSVUE default, KJV available)
- Collect of the Day
- Observance toggle for feast days with alternate readings
- Seasonal colour theming, dark mode, font-size control
- PWA — installs on iOS/Android via Capacitor

## Running locally

```sh
make serve        # http://localhost:8080
```

Requires `data/` to be populated — see **Data pipeline** below.

## Deploying

Three-stage deploy pipeline with staging verification:

```sh
make deploy-staging    # upload to releases/vTIMESTAMP/ + staging/
make test-staging      # Playwright smoke tests against staging
make promote           # CloudFront origin-path swap to production
make rollback          # revert to previous release
```

Requires the AWS CLI plus `BUCKET` and `CF_DISTRIBUTION_ID` in `.env`, and
`STAGING_DOMAIN` for `make test-staging` (see `.env.example`).

Before promoting, review changes:

```sh
node tools/compare_staging.cjs [date] [mp|ep]   # A/B diff staging vs production
```

## Testing

```sh
make test             # the go-to check, no network — data integrity, Vitest,
                      # pytest, and the liturgical QA gate
make test-web         # Playwright E2E suite (142 tests: desktop + mobile)
make test-full        # structural check of every day × MP+EP in the lectionary year
make test-smoke       # 4 representative days: structure + reading cross-check
make test-seasonal    # 26 cases: one MP+EP per liturgical form
```

### Quality assurance

`make qa` runs the whole gate — liturgical rule validation, rendered-DOM and CSS
structure, lectionary resolution, cross-form statistical audits, accessibility,
and a composite coherence score that has to come back at 100. `make test` already
includes it, so running a single tool is a way to read one failure in full rather
than extra coverage:

```sh
node tools/validate_office.cjs   # 20 liturgical rules, 3 tiers, all 30 forms
node tools/audit_office.cjs      # cross-form statistical outlier detection
node tools/review_form.cjs FORM [date]  # line-numbered text renderer for review
```

## Data pipeline

All data files are gitignored — they contain copyrighted ACC/BAS content
and are generated locally from source PDFs and the ACC lectionary.

### One-time setup

Requires `PyMuPDF`. Create the project venv:

```sh
make venv
```

`make` picks up `.venv/` automatically — no `activate` needed before
`make extract`, `make test-tools`, or any other target.

Source PDFs go in `sources/` (gitignored). Run `make fetch-sources` to
download publicly available source files, then `make extract` to run the
full pipeline:

```sh
make fetch-sources   # download ACC source files
make extract         # → data/offices.json, psalter.json, collects.json,
                     #   fats/saints.json, season_bounds.json, data/lectionary/
```

Extractors write intermediates to `.build/`; `tools/apply_corrections.py` derives
every published file in `data/` from them, applying `data/corrections.json` as it
goes. Everything in `data/` other than the three committed files is generated
output, so never edit it by hand — put the change in `corrections.json` or the
extractor instead. `make check-integrity` compares it against the hashes in
`tools/extract_manifest.json` and fails if anything was touched outside the
pipeline or if an extractor changed without a re-run.

Office form page ranges are detected from PDF content (not hardcoded):

```sh
python3 tools/detect_office_bounds.py --strict  # verify committed bounds
python3 tools/detect_office_bounds.py --write   # regenerate after PDF change
```

Corrections to extracted text live in `data/corrections.json` (committed), one
manifest covering office text, psalter, saints, and lectionary entries.

### Scripture

KJV (with Apocrypha) is bundled in `data/translations/kjv/` and works offline.

NRSVUE is not distributable. If you have a local copy, place it at
`data/translations/nrsvue/` (one JSON file per book, same format as KJV)
and the app will use it automatically. Without it, all readings fall back
to KJV.

## Architecture

```
web/          Pure client-side SPA — HTML/CSS/vanilla JS, no build step
  app.js      Routing, lectionary, office rendering, psalm/scripture fetching
  render.js   Shared rendering functions (HTML + text modes, structured output)
  office.css  Styling and seasonal theming
  sw.js       Service worker — kill-switch only (unregisters old installs)
  assets/     bas-cross*.svg — logo variants; only bas-cross-simple-ring.svg is
              wired into index.html today, the rest are alternates kept as
              assets for use as needed

cli/          Node CLI tools (ES modules)
  book.js     Book-mode plain-text renderer — node cli/book.js FORM [DATE]
  office.js   Structured text renderer — node cli/office.js [mp|ep] [DATE]

tools/        Extraction, validation, QA, and testing
  extract_offices.py        Office form extraction (PyMuPDF)
  extract_office_styles.py  Span-level style classification
  extract_psalter.py        Psalter extraction
  extract_collects.py       BAS collects extraction
  extract_fats.py           For All The Saints — saint biographies
  extract_paragraphs.py     WEB USFX → data/paragraphs.json (not in `make extract`)
  convert_lectionary.py     CSV → monthly JSON lectionary
  detect_office_bounds.py   Content-based page detection
  normalize_offices.py      Shared-block deduplication
  validate_corrections.py   Checks corrections against pre-correction artifacts
  apply_corrections.py      Derives data/ from .build/ + corrections.json
  check_data_integrity.py   SHA-256 integrity guard
  update_extract_manifest.py  Extraction manifest writer
  validate_office.cjs       Liturgical rule validators (all 30 forms)
  validate_render.cjs       Rendered-DOM structure validation
  validate_lectionary.cjs   Citation syntax + resolution, every date × office
  audit_office.cjs          Cross-form statistical outlier detection
  audit_text.cjs            Cross-form text-length outliers
  audit_a11y.cjs            Static accessibility checks
  coherence_score.cjs       Composite 0–100 quality score (gate: 100)
  compare_staging.cjs       Staging vs production A/B diff
  review_form.cjs           Line-numbered text renderer for review

.build/       Extraction intermediates — never published, never diffed as final

data/         Generated JSON — gitignored (copyrighted content)
  offices.json         30 office forms + _shared blocks
  psalter.json         Full psalter with verse numbers and midpoint markers
  collects.json        Collects indexed by date
  fats/saints.json     Saint biographies
  season_bounds.json   Liturgical season boundaries for current year
  lectionary/          Monthly JSON — YYYY-MM.json
  corrections.json     Single versioned correction manifest (committed)
  paragraphs.json      Committed
  translations/kjv/    Committed — public domain
```

## Status

- Lectionary data: 2025–2026 (Year B)
- All 30 office forms rendering correctly
- PyMuPDF extraction pipeline — single PDF dependency
- Corrections consolidated to a single `corrections.json` — 64 entries across 9
  categories (41 of them office text)
- Liturgical QA tools: rule validators, cross-form audits, a11y, coherence score
- Liturgical data is permanently gitignored — each user runs the extraction pipeline locally from ACC source files

## Licence

Source code: MIT.
Liturgical text and scripture: copyright their respective holders — see above.
