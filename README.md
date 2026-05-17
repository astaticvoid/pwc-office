# Pray Without Ceasing — Daily Office

A Go CLI that renders the Anglican Daily Office (Morning and Evening Prayer)
for any date in the liturgical year, following the Book of Alternative Services
(BAS) and the *Pray Without Ceasing* (PWC) office book of the Anglican Church
of Canada.

## What it does

Given a date and office type, it produces a complete, ready-to-read office in
Markdown:

- Liturgical form for the season (opening responses, invitatory, canticles,
  litany, seasonal collects, Lord's Prayer, dismissal)
- Appointed psalm(s) with full text
- Scripture lessons with full text
- Collect reference
- Feast day and alternate readings where applicable

```
$ dailyoffice --translation kjv mp 2026-04-05
# Morning Prayer — Easter Day
Sunday, 5 April 2026
Season: Easter | Rank: PF | Colour: White or Gold
...
```

## Building

Requires Go 1.23+.

```sh
go build ./cmd/dailyoffice
```

## Running

```sh
# Today's Morning Prayer (KJV, embedded — no setup required)
./dailyoffice --translation kjv mp

# A specific date, Evening Prayer
./dailyoffice --translation kjv ep 2026-12-25

# API.Bible (requires BIBLE_API_KEY in environment or .env)
./dailyoffice --translation api mp
```

## Testing

```sh
# Unit tests (no network, no API key)
make test

# Smoke suite — 4 LLM-evaluated days, requires claude CLI
make test-smoke

# Seasonal suite — one MP+EP per liturgical season, requires claude CLI
make test-seasonal

# Full structural check — every day in 2026 × MP+EP
make test-full
```

The smoke and seasonal suites use the `claude` CLI
(`npm install -g @anthropic-ai/claude-code`) to evaluate rendered output
against liturgical criteria and cross-check readings against
[lectionary.anglican.ca](https://lectionary.anglican.ca).

## Data files

### Liturgical text

The psalter, office forms, and collects are extracted from *Pray Without
Ceasing* and the Book of Alternative Services, both copyright the Anglican
Church of Canada. These files are **not included** in the repository and must
be obtained separately. The extraction tools in `tools/` can regenerate
`data/` from the source PDFs. They require `pdfplumber`
(`pip install pdfplumber`) and, for best results, `pdftotext` from
[poppler](https://poppler.freedesktop.org/) (`brew install poppler` on macOS).
Plain-text versions of the PDFs are generated automatically on first run.

### Scripture

**KJV** (King James Version 1769, with Apocrypha) is embedded in the binary
and requires no setup. Use `--translation kjv`.

**API.Bible** is also supported. Set `BIBLE_API_KEY` in the environment or a
`.env` file and use `--translation api`.

## Web interface

A pure client-side SPA is included in `web/`. It reads the same `data/` files
as the CLI and requires no build step or server.

```sh
# Serve source tree for local development (http://localhost:8080/web/)
make serve

# Build deployable snapshot in dist/
make build

# Verify dist/ completeness before deploying
make check-dist

# Build and serve dist/ exactly as deployed (http://localhost:8081/)
make serve-dist
```

The web app includes: liturgical forms, psalm and scripture text, observance
toggle for days with alternate readings, seasonal colour theming, translation
switch (NRSVUE / KJV), and dark mode.

## Status

All 730 day/office combinations in the 2026 liturgical year render correctly
and pass structural validation (`make test-full`). Prayers, psalms, and
readings are reproduced word-for-word from the BAS and PWC — no liturgical
content was generated or altered by AI. Developed with Claude Code (Anthropic).

Open-sourcing is pending a licence discussion with the Anglican Church of
Canada.

## Licence

Source code: MIT.  
Liturgical text and scripture: copyright their respective holders — see above.
