# Runbook: taking a new lectionary year into the pipeline

When ACC publishes the next year's calendar, the work is not "re-run the
extractor". Most of the converter derives itself from the CSV (ADR 0017), but
a handful of things are keyed by date or by vocabulary, and **none of them
carry from one year to the next**. This runbook is the sequence; the tooling
carries the enumeration.

## Why a runbook at all

Because the failure is silent by nature. `NOTE_TYPES` is keyed by date, so
2027's notes are new keys with no entries — and the lookup used to default to
`pastoral`. That is how the Daily Office Lectionary sourcing notes spent a
year presented to readers as customs to observe, telling them in the voice of
a rubric which of two lectionary options a compiler had taken (#127).

So the intake is gated rather than documented-and-hoped-for. `make extract`
refuses a CSV whose decisions have not been made, and prints the worklist as
the error. This document exists to say what the worklist means.

## Sequence

```bash
make fetch-sources                  # if ACC republished the PDFs too
cp ~/Downloads/bas_short_2027.csv sources/
make intake-year                    # the worklist — report-only
#   … work the findings (below) …
make intake-year                    # until it reports nothing blocking
make extract                        # gated; refuses if anything is unresolved
make validate                       # citations vs lectionary.anglican.ca (network)
make test                           # lint, integrity, units, qa, mutations
make test-full                      # every date × MP+EP resolves
python3 tools/audit_observances.py  # line-level accounting of the name column
```

`make intake-year` reads the CSV and touches nothing. `make extract` is what
gates. The two report the same findings, so you can work the list without
repeatedly failing a build.

## What the findings mean

### Note types — blocking

Every date whose extra column carries text needs an entry in `NOTE_TYPES`
(`tools/convert_lectionary.py`). There is no default: the type is a judgment
about who a note is addressed to, and no heuristic makes it reliably.

The two that matter most are easy to confuse:

- **`source_note`** — the compiler's apparatus. Where a day's propers came
  from, which of two lectionary options was taken, how two sources package
  the same commemoration. It explains a decision *already applied to the
  data*. The reader is not being asked to do anything. Renders behind a
  closed "About these readings" disclosure.
- **`pastoral`** — a custom addressed to whoever is praying. Rose vestments
  on Gaudete, pancakes on Shrove Tuesday, blessing the animals. Renders in
  the open.

Others in the vocabulary: `o_antiphon`, `office_note` (an actionable
alternative for the office itself), `civil_day`, `week_of_prayer`,
`precedence_rule`, `ember_crossref`, `rogation_crossref`,
`reconciliation_propers`. The last four are suppressed — they are rules
already applied, not advice.

A cell may hold more than one note. Give it a **list** and each `<br>`-
separated segment is typed in order; a mismatch between the list length and
the segment count is a hard error, because a silent off-by-one would retype
every note after it. 2026-06-28 is the case that motivated this: a precedence
rule and its sourcing shared one cell, and typing the cell as a whole
suppressed both.

The intake tool prints each untyped date in paste-ready form with its
segments numbered.

### Eve vocabulary — advisory

An `Eve of X` name-column line whose `X` is outside `KNOWN_EVE_TARGETS` is
dropped with a warning, not guessed at — it does **not** block extraction. Add
the target, and add it to `EVE_THE_ARTICLE` if liturgical usage prefixes the
definite article — "Eve of the Epiphany", never "Eve of Epiphany". The CSV's
own capitalisation is not a reliable signal, which is why the convention is
encoded rather than parsed.

A **new** conditional eve — one carrying an `[if …]` bracket — also needs an
`EVE_COMPANION_TAGS` decision: whether it also emits a same-date bare tag.
The wording cannot decide it (Eve of Corpus Christi carries no companion, Eve
of Ascension Sunday does), so it is a judgment call, recorded with a comment.
Absence from the table means "decided: no companion", so only targets new to
the vocabulary are reported.

### Unmatched eves — blocking

An eve in an office column whose label matches no name-column line. Failing
open would put the day's colour on an office praying the eve's propers —
green on the Eve of Saint Mary — so extraction stops instead (#128). Either
the two columns have drifted apart, in which case extend `eve_identity`'s
matching, or ACC omitted the eve from the name column, in which case it is a
correction.

### Observance phrases — advisory

A name-column line matching no phrase but close to one. ACC may have
reworded a marker; the guard exists because a rewording would otherwise fail
silently. Each is either a rewording to add to `OBSERVANCE_PHRASES` or a
coincidence to ignore.

### Season bounds — blocking when required ones are missing

`detect_bounds` reads `CANONICAL_BOUNDS_PHRASES` against the name column. A
missing required bound means the phrase moved, and every form-season lookup
downstream depends on it.

### Corrections — found, not derived

`data/corrections.json`'s `lectionary_*` categories are per-date and do not
carry. A new year's errors surface through `make validate`, `make check-text`
and `make test-full`, not through the intake tool. Each fix goes in the
manifest with its `old` value (ADR 0005) — never as a direct edit to
`data/`, which is gitignored and regenerated.

## After extraction

`make extract` rewrites `tools/extract_manifest.json`, so `check-integrity`
will fail until the new hashes are committed. That is the intended prompt to
look at the diff before accepting it.

`--window 12` in the Makefile's extract step prunes months outside a rolling
window and deletes monthly files the current source no longer accounts for.
A year rollover is exactly when that matters: the previous year's months fall
out of the window and are removed.

## Related

- ADR 0005 — corrections live in one versioned manifest
- ADR 0017 — secondary observances are extracted, not transcribed
- ADR 0018 — the alternate-observance toggle presents the day's identity
- `tools/audit_observances.py` — line-level accounting, report-only
