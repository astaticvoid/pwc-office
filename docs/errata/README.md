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

## Declarations

Every place the errata's text and ours diverge, and every erratum that asks for
something we do not represent. `tools/audit_errata.py` reads this table: a
divergence it finds must appear here, and a row matching no finding is reported
as stale. `Ruling` is `ours` (the errata was retyped wrong and our reading
stands), `errata` (ours is wrong and a correction is owed), or `n/a` (nothing
in the erratum applies to our data — clears the whole block, so `Errata reads`
is `—`).

| Document | Page | Errata reads | We read | Ruling | Why |
|---|---|---|---|---|---|
| Ordinary | p. 165 | who | whose | ours | "those who names are known to you alone" is a retyping slip. |
| Seasonal | p. 23 | our | your | ours | "in our word is my hope" in the final repeat only; the two earlier repeats read "your". |
| Seasonal | p. 26 | — | all | ours | The errata drops "all" from "with all the saints in light" while asking only for line breaks. |
| Seasonal | p. 30 | form | from | ours | "which was form the beginning" is a retyping slip. |
| Seasonal | p. 37 | us | up | ours | "Truth shall spring us from the earth" is a retyping slip. |
| Seasonal | p. 43 | voice | voices | ours | "With all the voice of heaven and earth"; the erratum asks only for line breaks. |
| Seasonal | p. 72 | faulty | fault | ours | The erratum's own note spells it "fault" and asks only for the missing period. |
| Seasonal | p. 80 | we | I | ours | "God forbid that we should glory" for Galatians 6:14's "I"; the erratum asks only for line breaks. |
| Seasonal | p. 100 | — | been | ours | The errata drops "been" from "has been poured into our hearts" (Romans 5:5). |
| Seasonal | p. 13 | — | — | n/a | A Penitential Office is not one of the 30 forms `extract_offices.py` covers, and the complaint is that a portion of the confession is not in bold — pure typography, carrying no meaning our renderer represents. |
| Seasonal | p. 66 | — | — | n/a | "The rubric should not be indented and should be printed in italics." Rubrics are a segment type styled by `office.css`; the printed book's indentation is not something we reproduce. |

One divergence is not in the table because the audit cannot see it: at Ordinary
p. 208 the errata prints "persecuted or ignored" where we have "persecuted, or
ignored". Alignment compares words with punctuation stripped, so a
punctuation-only difference never surfaces as a `WORDING` finding and a row for
it would always read as stale. The erratum claims only a formatting defect and
says nothing about the comma, so the serial comma stands.

## What has been applied

All of it, as 45 `office_text` entries in `data/corrections.json`. Three kinds:

1. **Wording, punctuation and casing** — 13 substantive defects. One corrects
   `_shared.reading_response_ordinary`, fixing all 14 Ordinary forms at once.
2. **Line breaks and reflow** — 31 segments, newline-only, no wording altered.
   Far fewer than the errata's 46 reflow items suggest: most ask for a break
   between versicle and response, and our extraction already splits those into
   separate `leader` and `response` segments.
3. **Structural** — two whole-field replaces: Seasonal p. 52, deleting the
   Epiphany EP doxologies; and Seasonal p. 66, splitting "The Responsory is said
   or sung." out of the Lent EP first leader segment so it stands as its own
   rubric. The second is not what that erratum asks for — its complaint about
   indentation and italics is still not applicable — but it is a defect found
   while checking it, one case against 59 where the same rubric is already its
   own segment.

**The trap that caught the first pass.** Aligning an errata block against our
segments as a whole fails silently wherever the block contains a wording
divergence, and drops every break inside it. Four went that way — three beside
a divergence tabulated above. Align per line *pair*, and run
`python3 tools/audit_errata.py`, which exists because nothing else could see it:
`make test`, `make qa` and a 100/100 coherence score were all green over them.

The errata author types two spaces after a sentence. No office text contains a
double space; lift the line structure without the spacing.

## Breaks the QA rules are told about

`collect-and-dismissal-no-orphan-breaks` (`validate_office.cjs`) and the litany
column-wrap scan (`check_text_quality.py`) both read a line ending mid-clause as
a suspected PDF column wrap. Several errata breaks land mid-clause by design —

    May God, who has called us out of darkness
    into the marvellous light of Christ,

Both read the sanctioned lines out of `data/corrections.json`, matched against
the exact line at the exact `{office, field}` the correction targets, so every
break nobody has vouched for is still reported and the exemption disappears with
the correction. Do not widen either rule to make a correction fit; add the
correction and let it vouch. See ADR 0012.
