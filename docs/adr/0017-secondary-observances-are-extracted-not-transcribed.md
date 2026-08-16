# ADR 0017: Secondary observances are extracted, not transcribed

## Status
Accepted

Corrected (2026-08-10): the phrase vocabulary was completed with the three
civil markers the hand-written dict had omitted (`remembrance_day`,
`new_year_day`, `accession_day`) — transcription gaps of the same class as
the 2026-10-31 eve gap this ADR's extraction fixed. The decision — per-date
observances are extracted from the CSV, not transcribed — is unchanged.

Amended (2026-08-16, #129): point 3 kept commemoration lines out of the
`observances` vocabulary, which was right, and dropped them entirely, which
was not. They are observances of a different kind — a person the day
remembers, carrying their own rank and colour — so they now reach the data
as `commemorations` rather than as tags. Ten days in the window carry one
below the day's own line, and none of them reached a reader: their
biographies ship in `data/fats/saints.json` and could not be opened, because
the lookup keyed on the day's name alone. Point 3's own example is one of
them — Florence Nightingale sits under a Rogation Day, and the sentence
naming her as a line to ignore was the reason she was.

Point 3's separator text is untouched — "And / or" still becomes no
observance. It is now *read* rather than ignored, as the word that says two
commemorations stand equal; see point 6.

## Context

`tools/convert_lectionary.py` carries `OBSERVANCES: dict[str, list[str]]` — 175
date-keyed entries tagging secondary liturgical facts that don't fit the
primary name/rank/colour fields: `fast_day`, `eve_of:Advent II`,
`season_of_creation`, `octave_of_christmas`, and a handful of one-off
national/ecumenical days (`canada_day`, `remembrance_sunday`,
`national_indigenous_day_of_prayer`, and others). The header comment says
these are "Derived from the secondary markers in the CSV name column" — but
unlike every other field this extractor produces, nothing parses that claim
out of the source. The dict is typed in by hand.

The source CSV's name column (`sources/bas_short_YYYY.csv`, column 1) packs
everything into one `<br>`-separated field: primary name/rank/colour on line
1, then often one or more further lines. The existing parser,
`parse_name_meta`, only ever reads line 1 (`first_line(clean(raw))`) —
everything after the first `<br>` is discarded by the automated path and only
exists in the app's data because someone read those lines by eye and typed
`OBSERVANCES` out separately. Issue #56 is tracking both that this data has
no reader-facing consumer, and (per a comment there) a confirmed gap found
while investigating this ADR — a concrete instance of the risk hand
transcription of 175 individual facts carries.

A prototype dynamic extractor — reading the same lines that were manually
transcribed and classifying them against the known tag vocabulary — was built
to check whether this data can be produced the same way every other field in
this pipeline is: parsed from the source rather than retyped. It reproduces
`OBSERVANCES` using a small rule set (~24-entry phrase→tag table, one regex
for `"Eve of X"`, a 5-entry table for the handful of feasts that also get a
same-date bare tag alongside their eve) — the same order of magnitude as the
existing `NOTE_TYPES`-style tables already in this file.

## Decision

**Replace `OBSERVANCES` with a real extraction pass over the CSV's name
column.**

1. Take every line of the cleaned name field, not just line 1. Most
   secondary-observance markers are lines after the first `<br>`, but at
   least one (`National Indigenous Day of Prayer`) appears as the *entire*
   primary line on its date — the classifier has to see all lines to catch
   both shapes.
2. Classify each line against a small table: a `phrase → tag` substring map
   for the fixed-vocabulary markers (`fast_day`, `season_of_creation`, the
   octave and one-off national/ecumenical tags), plus one regex for `"Eve of
   X (...)"` that strips the trailing colour/bracket decoration and emits
   `eve_of:X`.
3. Lines that don't match anything in the table become no tag — the CSV's
   column 1 also carries commemoration lines ("Florence Nightingale... -
   Com") and separator text ("And / or") that are not observances of the
   fixed-vocabulary kind and must not become one just for appearing on line
   2+. A ranked line is still read, as a commemoration rather than a tag
   (amended, #129); only the separator text yields nothing on its own.
4. The `eve_of:X` target-name spelling (whether `X` keeps a leading "the",
   e.g. `eve_of:the Epiphany` vs `eve_of:Advent II`) is **not** derivable
   from the CSV's own capitalization — it needs its own small hardcoded list
   of which feast names conventionally take the article in English
   liturgical usage, kept independent of the outgoing `OBSERVANCES` dict so
   the replacement doesn't quietly depend on the thing it replaces.
5. The 5-entry "eve also gets a same-date bare tag" table (e.g. `eve_of:the
   Ascension` + a same-day companion, `eve_of:Harvest Thanksgiving` +
   `harvest_thanksgiving`) is a genuine per-feast judgment call that CSV
   wording alone doesn't resolve — two structurally identical `[if also
   celebrated on Sunday]` lines (Corpus Christi, Ascension) get different
   treatment in the current data. This table stays explicit, commented,
   hand-maintained data — the claim of this ADR is that the *165-and-counting
   per-date facts* move to extraction, not that every part of the
   classification becomes mechanical.

6. **A ranked line below the day's own is a commemoration** (#129), parsed
   for its own name, rank and colour into `commemorations`. Its standing is
   read from the day's — the day being line 1 whether or not it carries a
   rank suffix, since an Ember day carries none and still governs the lines
   under it. A line matching the day's rank *and* colour is the calendar
   offering either of two days of equal weight, and is marked `coequal` so
   the header can name both rather than choose one, which ADR 0016 forbids
   the app doing on the reader's behalf. Anything else is kept under the day
   and named as a marker. The word joining a co-equal pair comes from
   `CO_COMMEMORATION_JOINS`, a two-entry vocabulary: the calendar writes it
   after the pair ("Or Both Together") or between them ("And / or"), so
   position is not the signal and the wording is. A co-equal pair joined by a
   wording not in that table blocks extraction with the worklist, on the same
   terms as the eve gate — the alternative is a header that silently names
   one of two days.

**Out of scope for this ADR:** how (or whether) `observances` gets a
reader-facing consumer. That's issue #56's other half and a UI/product
decision independent of how the data gets produced. This ADR only settles
the production method.

## Consequences

### Positive
- Collapses 175 hand-typed per-date facts into ~30 general rules a reviewer
  can audit in one sitting, the same benefit ADR 0015's register gave
  app-authored rubric text — and the same category of transcription risk
  ADR 0015 already named for text, applied here to data.
- Self-updating: when ACC ships next year's CSV, secondary observances arrive
  automatically instead of requiring someone to re-read every date by eye and
  extend the dict.
- The extraction is testable in the way the hand-authored dict wasn't — it
  can be diffed against the CSV mechanically, the way this ADR's own
  prototype was.

### Negative
- This does not eliminate hand-authored data, it relocates it: the
  phrase→tag table, the eve-of regex's edge cases, the "the"-article list, and
  the 5-entry companion-tag table are all still human-encoded knowledge. The
  claim is narrower — that ~30 general, reviewable rules are a smaller and
  more auditable surface than 175 per-date facts, not that the risk is zero.
- If ACC changes the wording of a marker (e.g. rephrases "Day of discipline
  and self-denial"), the classifier silently stops matching that line rather
  than erroring — the same silent-drift risk `detect_bounds()` already
  guards against for season boundaries with a fuzzy-match warning. Worth the
  same treatment here rather than assuming this ADR's classifier is exempt.
- Adds a second read-all-lines pass alongside the existing first-line-only
  `parse_name_meta` path; the two must stay in sync if the CSV's line
  structure changes.

### Neutral / Notes
- Whether `observances` gets rendered (issue #56's "give it a consumer or
  document it as internal" choice) is still open. This ADR only says the
  data itself should stop being hand-transcribed.
- A concrete data gap found while investigating this ADR is tracked as a
  comment on issue #56, not here — this document is about the go-forward
  method, not a record of what the old method got wrong.
