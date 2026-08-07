# PWC errata

Editorial errata for *Pray Without Ceasing*, received from the Anglican
Church of Canada and imported verbatim:

| Document | Items |
|---|---|
| [ordinary-time.md](ordinary-time.md) | 33 |
| [seasonal.md](seasonal.md) | 41 |

The personal letter header of each document has been pruned to the context
that matters — scope and form. Everything from the first form heading onward
is reproduced as received.

## How these become corrections

An erratum is not itself a rule. Each one is checked against the text
`extract_offices.py` actually produces, and only the ones that describe a real
difference become entries in `data/corrections.json` under `office_text`. Many
do not: the errata complains at length that the printed book runs versicle and
response together without line breaks, but our extraction already splits those
into separate `leader`/`response` segments, so the rendered office is correct
and there is nothing to correct.

The errata is a correction to *the printed book*, not to our extractor. That
is why these are corrections rather than extractor fixes — the geometry we read
off the page is faithful, and the page is what is wrong. See
`docs/adr/0005-single-correction-manifest.md`.

## The errata's own transcription slips

The corrected text in these documents was retyped by hand, and some of it was
retyped wrong. In each case below our extraction already has the right reading,
so applying the errata verbatim would *introduce* an error. These are recorded
here rather than silently fixed in the imported files, which are verbatim.

| Document | Erratum | Errata reads | Correct (and what we already have) |
|---|---|---|---|
| Ordinary | p. 165, Tuesday MP litany | "those who names are known to you alone" | "those **whose** names are known to you alone" |
| Seasonal | p. 23, Advent EP responsory | "in **our** word is my hope" (final repeat only) | "in **your** word is my hope" |
| Seasonal | p. 30, Christmas MP responsory | "which was **form** the beginning" | "which was **from** the beginning" |
| Seasonal | p. 37, Christmas EP responsory | "Truth shall spring **us** from the earth" | "Truth shall spring **up** from the earth" |
| Seasonal | p. 72, Passiontide MP responses | "bruised for no **faulty** but ours" | "bruised for no **fault** but ours" — the erratum's own note spells it correctly, and asks only for the missing period |

One more difference is *not* treated as a slip in either direction: at
Ordinary p. 208 the errata prints "lonely, sick, hungry, persecuted or
ignored" where we have "persecuted, or ignored". The erratum claims only a
formatting defect and says nothing about the comma, so the serial comma
stands.

## Not applicable

- **Seasonal p. 13, A Penitential Office** — "a portion of the confession is
  not in bold print". The Penitential Office is not one of the 30 forms
  `extract_offices.py` covers, so there is nothing to correct. It is also a
  pure typographic complaint about the printed page, which carries no meaning
  our renderer represents.
- **Seasonal p. 66, Lent EP** — "the rubric should not be indented and should
  be printed in italics". Rubrics are a segment type in our data and are
  styled by `office.css`; the printed book's indentation is not something we
  reproduce.

## Staging

Substantive wording, punctuation and casing errors were applied first as one
reviewable change. The much larger set of line-break and reflow requests
("awkwardly formatted", "should have line breaks") is a separate pass — it
touches the rendered text of nearly every office and wants its own diff
review via `make extract-diff`.
