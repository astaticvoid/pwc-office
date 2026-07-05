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
- PWA — installs on iOS/Android, works fully offline

## Running locally

```sh
make serve        # http://localhost:8080
```

Requires `data/` to be populated — see **Data pipeline** below.

## Deploying

```sh
make build        # assemble dist/ (stamps service worker cache hash)
make check-dist   # verify completeness
make deploy BUCKET=my-bucket CF_DISTRIBUTION_ID=XXXXX  # sync to S3 + invalidate CloudFront
```

Requires the AWS CLI and ambient credentials (`AWS_PROFILE` or environment
variables).

## Testing

```sh
make test         # Vitest unit tests + Python pytest (fast, no network)
make test-web     # Playwright E2E suite against web/
make test-full    # structural check of every day × MP+EP in the lectionary year (~25s)
```

The smoke and seasonal suites check rendered output against citations fetched
from `lectionary.anglican.ca` (skipped, not failed, if the site is unreachable):

```sh
make test-smoke    # 4 representative days: Easter, Lent, a feast day
make test-seasonal # 26 cases: one MP+EP per liturgical form
```

## Data pipeline

All data files are gitignored — they contain copyrighted ACC/BAS content
and are generated locally from source PDFs and the ACC lectionary.

### One-time setup

Requires `pdfplumber` and `pdftotext` (poppler):

```sh
pip install pdfplumber
brew install poppler   # macOS
```

Source PDFs go in `sources/` (gitignored). Run `make fetch-sources` to
download publicly available source files, then `make extract` to run the
full pipeline:

```sh
make fetch-sources   # download ACC source files
make extract         # → data/offices.json, psalter.json, collects.json,
                     #   season_bounds.json, data/lectionary/
```

### Scripture

NRSVUE is fetched on demand from API.Bible (lazy, cached by the service worker).
KJV can be downloaded and converted for offline use:

```sh
BIBLE_API_KEY=your_key_here   # set in .env (gitignored)
```

## Architecture

```
web/          Pure client-side SPA — HTML/CSS/vanilla JS, no build step
  app.js      Routing, lectionary, office rendering, psalm/scripture fetching
  render.js   Shared rendering functions (imported by app.js and Node CLI)
  office.css  Styling and seasonal theming
  sw.js       Service worker — cache-first, offline support

cli/          Node CLI tools (ES modules, no build step)
  book.js     Book-mode plain-text renderer — node cli/book.js FORM [DATE]
  office.js   Debug HTML-strip renderer — node cli/office.js [mp|ep] [DATE]

tools/        Python data pipeline (extraction, validation, testing)
  test_full.js      Structural check: all dates × MP+EP
  test_eval.js      Citation check vs lectionary.anglican.ca (smoke + seasonal)

data/         Generated JSON — gitignored (copyrighted content)
  offices.json        All 31 office forms
  psalter.json        Full psalter with verse numbers and midpoint markers
  collects.json       Collects indexed by date
  season_bounds.json  Liturgical season boundaries for current year
  lectionary/         Monthly JSON — YYYY-MM.json
```

## Status

- Lectionary data: 2025–2026 (Year B)
- All 31 office forms rendering correctly
- Liturgical data is permanently gitignored — each user runs the extraction pipeline locally from ACC source files

## Licence

Source code: MIT.
Liturgical text and scripture: copyright their respective holders — see above.
