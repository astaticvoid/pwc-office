# PWC errata

Editorial errata for *Pray Without Ceasing*, received for this project and
imported verbatim into two local documents:

| Document | Items |
|---|---|
| ordinary-time.md | 33 |
| seasonal.md | 41 |

**Gitignored, not in this repository (ADR 0021).** They reproduce the
corrected liturgical text in full, the same class of copyrighted artifact as
`sources/pray-without-ceasing.pdf` — held locally, reproducible by anyone with
their own copy of the errata, never committed. This file is the durable
record of what they said and decided: everything below quotes only the word
or two actually in dispute, never a reproduced block. `make audit-errata`
reports `SKIPPED` by name when a checkout does not have them.

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

All of it, as 45 of the 49 `office_text` entries in `data/corrections.json` —
every entry whose `source` is `pwc-errata-ordinary` or `pwc-errata-seasonal`.
The other four are not errata at all: they are the authorized divergences under
"Upstream review" below, carrying `source: upstream-review` and naming the ADR
item that settled each. Reading the manifest by `source` is what separates
"the book is wrong here" from "we deliberately say something else here".

The 45 errata entries are three kinds:

1. **Wording, punctuation and casing** — 12 substantive defects, plus the
   reading-response correction below moving into the extractor (see
   "Upstream review" below).
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

## Upstream review

Decisions from review of the app recorded under ADR 0015. Each row states its
provenance; a row backed by an errata document is also aligned by
`audit_errata.py`, which exists to check the errata documents.

| What | Was | Now | Decided |
|---|---|---|---|
| Reading-response third alternative | "Holy wisdom, holy word." in the 14 Ordinary forms | "Holy Word, Holy Wisdom." in all 30 forms | The reading response is synthesized rather than extracted, and the Ordinary form reproduced the printed book's error, which the errata corrects (Ordinary p. 132, "PWC has the wrong order"). The corrected form applies to every season. Fixed in `_add_reading_responses` (extractor) rather than the manifest, per AGENTS.md's systemic-fix rule; the errata correction that used to patch `_shared.reading_response_ordinary` was retired. |
| Psalm introduction | "A Psalm from the Daily Office Lectionary, the Weekday Eucharistic Lectionary, or the Revised Common Lectionary Daily Readings is said or sung." (as printed) | "A Psalm is said or sung." | Review: drop the named lectionaries. Was three app-authored variants chosen by psalm count; #84 recovered the printed sentence, so the settled wording is now a correction on the extracted rubric — `adr0019-item3-psalm-introduction` and `-or-psalms` in `data/corrections.json`, `source: upstream-review`. ADR 0019 items 3 and 6; one sentence, once, in all 30 forms. |
| Reading introduction | "A Reading from the Daily Office Lectionary, the Weekday Eucharistic Lectionary, or the Revised Common Lectionary Daily Readings is read." (as printed) | "A Reading is read." | Review: drop the named lectionaries. Applied as `adr0019-item3-reading-introduction` in `data/corrections.json`, `source: upstream-review`. A substring correction, so the reflection prompt sharing the printed paragraph stays attached. ADR 0019 item 3. |
| Morning/Evening Prayer affirmation transition | "{Morning,Evening} Prayer continues with an Affirmation of Faith or the Litany." (as printed, 16 seasonal forms) | "{Morning,Evening} Prayer continues with an Affirmation of Faith or the Prayers." | Review: "or the Litany" → "or the Prayers", both offices. The 14 ordinary forms already print "or the Prayers". Applied as `adr0019-item4-affirmation-transition` in `data/corrections.json`, `source: upstream-review`. ADR 0019 item 4. |
| Reading-pick rubric | "{cap} of the following {total} readings are read." (app-computed per date's pick/total) | "One or two readings are read." (fixed) | App-authored rubric; review: replace the computed per-count sentence with the approved fixed form. Both readings stay in the office in book order — no selector; the choice is carried by this rubric and the book's own transition rubric after the first reading. Rendered from `LITURGICAL_TEXT_REGISTER` in `web/render.js` (ADR 0019 item 7, issue #77). |
| Penitential Office absolution | "forgive you/us and free you/us from your/our sins," … (as printed; the slash doubles every pronoun) | "forgive you and free you from your sins," … (you-form throughout) | Review: drop the "you/our" slash distinction and keep the officiant-addressed "you" form — the deacon rubric printed below ("A deacon or lay person using the preceding form substitutes us for you and our for your.") covers the deacon/lay officiant. Applied as `adr0019-item10-absolution-you` and `-absolution-your` in `data/corrections.json`, `source: upstream-review`. ADR 0019 item 10. |

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
