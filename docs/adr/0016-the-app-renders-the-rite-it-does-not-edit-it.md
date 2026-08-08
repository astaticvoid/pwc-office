# ADR 0016: The app renders the authorized rite; it does not edit it

## Status
Proposed

## Context

Three ADRs each fix a different way the app had taken editorial liberties with
authorized liturgical text:

- **0013** — 59 of 86 distinct rubric texts withheld or rewritten in Office mode.
- **0014** — choices the rite leaves open, resolved by the app instead of offered.
- **0015** — ten rubric strings invented in JavaScript, four of them wrong.

Each is written as a scoped mechanism, and each Decision binds only its own
area. Nothing states the constraint all three share. So condensing a canticle,
auto-selecting a collect, reordering a section, or abbreviating a dismissal is
covered by none of them, and each would be the same mistake in a new place.

The pattern is worth naming, because it is not carelessness. Every one of these
changes was locally reasonable. Hiding the branching rubrics did make Office
mode cleaner. Rendering all psalms *is* simpler than a selector. One sentence of
intercession bidding reads better than seven bullets. The defect is not bad
design judgement — it is design judgement applied to something that was never
ours to design.

Note also what the warrants were. The psalm selector was removed because "you
should just read all the Psalms," a devotional opinion. `BOOK_ONLY_RUBRICS` is
commented "noisy in the interactive app," an aesthetic one. Both are perfectly
reasonable opinions to hold. Neither is authority over authorized text, and in
the absence of a stated rule, the maintainer's preferences became the de facto
authority by default.

## Decision

**The app renders the authorized rite. It does not edit it.**

For any text originating in PWC, the BAS, or the lectionary:

1. **It renders.** Whether authorized text appears is not a design decision.
2. **It renders as written.** Paraphrase, condensation, and summary are edits.
3. **Choices stay choices.** Where the rite offers alternatives, the app presents
   them. It does not choose, and it does not remove a branch.
4. **Presentation is ours.** Typography, spacing, ordering on screen,
   interaction, mode — all free, so long as 1–3 hold.
5. **Any exception is named, justified where it lives, and testable.** Not a
   regex, not a section allowlist. ADR 0012's vouching and ADR 0013's
   duplicate-suppression rule are the shape to copy.

Where a rule and a nicer design conflict, the rule wins, and the cost is
recorded in the ADR that accepts it rather than quietly designed around.

**Text the app authors itself** — transitions, generated rubrics, anything with
no source in the book — is held to ADR 0015's provenance standard. Inventing
text is sometimes necessary. Doing it unaccountably is not.

**Scope.** This governs authorized liturgical content only. It says nothing
about the app's own chrome — settings, navigation, the date picker, error
states, the evaluation banner. Those are ordinary product design and should be
designed well.

## Consequences

### Positive
- One constraint to apply in a new area, rather than re-deriving it or missing
  it. ADRs 0013–0015 stop reading as three separate opinions and become three
  applications of one rule.
- It is answerable in review. "Does this change what the reader sees of
  authorized text?" has a yes or no; "is this too much streamlining?" does not.
- It names the failure mode that produced all three: a locally good design
  decision taken in a place where design decisions were not available.

### Negative
- **It rules out real improvements.** Rendering every psalm is cleaner than any
  selector. The condensed intercession rubric genuinely reads better than the
  bidding list. Accepting this means accepting a less elegant app in exchange
  for a correct one, permanently and by policy.
- The Office view gets longer and denser. ADR 0013 already books that cost; this
  ADR makes it structural rather than a one-time concession.
- **Risk of over-application.** Rule 2 could be misread as forbidding the
  errata line breaks of ADR 0012, or the extractor's whitespace normalisation.
  It does not: those move the rendered text *toward* what is authorized. The
  test is direction, not whether text changed.

### Neutral / Notes
- Not a supersession. ADRs 0013–0015 keep their numbers and their Decisions.
  This is the principle they share, numbered later because it was derived from
  them rather than the other way round.
- AGENTS.md carries the operative rule and points here for the reasoning. That
  split is deliberate: AGENTS.md is loaded as standing instruction, which is
  where a constraint has to live to actually bind future work. An ADR alone
  would be read once, at most.
- The warrant for all four ADRs is upstream review rather than a document in
  this repository. That is deliberate; see ADR 0015's notes.
