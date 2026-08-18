# ADR 0020: The product renders the office and the saints; FATS propers are extraction-only

## Status
Accepted (2026-08-14)

Amended (2026-08-17): the product scope widens from "MP/EP office rendering"
to "the Daily Office — Morning and Evening Prayer, with the Penitential Office
as an optional opening and Prayers at Mid-day as a third office" (#146, split
into #165 and #166). The FATS-propers decision below is unchanged; only the
scope sentence in the Decision is broadened.

## Context

For All The Saints (FATS) is the book of commemorations whose data `web/app.js`
draws on for a saint's day. Extraction reached a high standard: biographies
render, and the prose fields — `bio`, `sentence`, `collect` and `refrain` —
are correct and conserved by the fats chain (#102). The citation fields
`sentence_ref`, `psalm` and `readings` are extracted but are references, not
prose, so that chain does not cover them.

Only `bio` and `collect` are rendered; the other five fields have no consumer.
The open issues #114–#118 concerned the readings (#114, #115), the refrain
(#116) and the collect (#117, #118). The project's exit is a Morning and
Evening Prayer app with saint biographies whose extraction is verifiably
correct; rendering the remaining propers is beyond that scope and has no
reader-facing demand.

## Decision

**The product is the Daily Office — Morning and Evening Prayer, the Penitential
Office as an optional opening to them, and Prayers at Mid-day as a third
office — plus saint biographies. The remaining FATS fields stay
extraction-only.**

The two new offices are not the same shape: the Penitential Office is an
optional prefix to an existing MP/EP office (page 13: *"When this Penitential
Office is used, Morning Prayer or Evening Prayer continues with the
Introductory Responses."*), while Prayers at Mid-day is a standalone office
reached the way MP and EP are. This ADR records the scope; the extraction and
selector design for each office live in #165 and #166.

1. `sentence`, `sentence_ref`, `psalm`, `refrain` and `readings` remain
   data-only: extracted, unrendered.
2. The FATS collect renders only through the existing fallback in
   `collectToggleHtml`; it is not offered as a peer alternative to a BAS
   collect, and a `FAS nnn` page in a collect citation is not resolved into a
   presented choice. ADR 0014 is unaffected in practice: no choice is surfaced,
   so none is made.
3. #114, #115, #116, #117, #118 are closed as not planned; #112's bare-chapter
   remainder is out of scope. Reopening any of them requires superseding this
   ADR.

## Consequences

### Positive
- A stable definition of done: the office and the saints are the surface, and
  the backlog no longer carries a feature that was never going to be built.
- The extraction work is not wasted: the prose fields are correct and
  conserved, and the citation fields are extracted, so a future consumer, if
  one is ever wanted, starts from a trustworthy source.

### Negative
- A saint's commemoration shows the biography; the appointed readings, refrain
  and sentence stay invisible to the reader despite being extracted, and the
  collect renders only as a fallback. This is a product limit, recorded here
  rather than left as an open question.

### Neutral / Notes
- Nothing is deleted: the fields stay in the data. This ADR governs the render
  surface, not the extraction.
