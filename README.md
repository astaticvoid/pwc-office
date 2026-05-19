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
variables). `CF_DISTRIBUTION_ID` can be omitted if not using CloudFront.

## Testing

```sh
make test         # Go unit tests (data parsing, season logic)
make test-web     # Playwright E2E suite against web/
make test-full    # structural check of every day × MP+EP in the lectionary year
```

The smoke and seasonal suites use the `claude` CLI to evaluate rendered output
against liturgical criteria:

```sh
make test-smoke    # 4 representative days, LLM-evaluated
make test-seasonal # one MP+EP per liturgical season, LLM-evaluated
```

## Data pipeline

All data files are gitignored — they contain copyrighted ACC/BAS content
and are generated locally from source PDFs and the ACC lectionary.

### Liturgical text (one-time setup)

Requires `pdfplumber` and `pdftotext` (poppler):

```sh
pip install pdfplumber
brew install poppler   # macOS

python3 tools/extract_offices.py    # → data/offices.json
python3 tools/extract_psalter.py    # → data/psalter.json
python3 tools/extract_collects.py   # → data/collects.json
```

Source PDFs go in `sources/` (gitignored).

### Lectionary (annual update)

The ACC publishes an annual CSV covering the current liturgical year
(`bas_short_YYYY.csv`). Historical years are scraped from the ACC daily
lectionary portal.

```sh
# Download current year's CSV from lectionary.anglican.ca and convert
python3 tools/scrape_lectionary.py
python3 tools/convert_lectionary.py   # → data/lectionary/YYYY-MM.json

# Scrape historical HTML (slow — ~1 req/sec)
python3 tools/scrape_daily.py --start 2016-11-27 --end 2025-11-29
python3 tools/scrape_daily.py --re-parse  # reparse cache after parser changes
python3 tools/scrape_daily.py --audit     # quality check

# Validate HTML-scraped data against CSV
python3 tools/validate_lectionary.py
```

### Scripture

KJV is embedded in the Go binary (public domain, committed to the repo).
NRSVUE requires a Bible API key:

```sh
# Set in .env (gitignored)
BIBLE_API_KEY=your_key_here
```

## Architecture

```
web/          Pure client-side SPA — HTML/CSS/vanilla JS, no build step
  app.js      Routing, lectionary, office rendering, psalm/scripture fetching
  office.css  Styling and seasonal theming
  sw.js       Service worker — cache-first, offline support

tools/        Python data pipeline (extraction, scraping, validation)
data/         Generated JSON — gitignored (copyrighted content)
  offices.json        All 31 office forms
  psalter.json        Full psalter with verse numbers and midpoint markers
  collects.json       Collects indexed by date
  season_bounds.json  Liturgical season boundaries for current year
  lectionary/         Monthly JSON — YYYY-MM.json

*.go          Go CLI (dev tool) and data-integrity test suite
cmd/          CLI entrypoint
e2e/          Playwright and LLM-evaluated test suites
```

## Status

- Lectionary data: 2016–2026 (Year B complete; Year A pending Advent 2026)
- All 31 office forms rendering correctly
- ACC licence inquiry pending (required before open-sourcing `data/`)

## Licence

Source code: MIT.
Liturgical text and scripture: copyright their respective holders — see above.
