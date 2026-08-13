# ADR 0014: Optionality is presented, not resolved

## Status
Accepted (2026-08-07)

Amended (2026-08-12) by ADR 0019, items 7 and 9. Two lines of the "Applied"
list below are superseded: the readings do **not** get a per-reading selector —
the per-reading view removed the Responsory and the Canticle, which are not part
of that choice — and the head-of-section rubric is the shorter *"One or two
readings are read."* The three obligations in the Decision are unchanged, and
the psalm selector, the alternatives tabs, and the whole of the reasoning about
optional readings stand.

## Context

*Pray Without Ceasing* branches by design. A form offers alternative canticles,
alternative affirmations, either-or collects; the lectionary appoints psalms and
readings of which some are optional. The branching isn't incidental structure to
be tidied away — it's part of the authorized rite, and following it is expected.
ADR 0013 records the same constraint for the rubrics that announce these
choices; this ADR covers the choices themselves.

The app currently answers a branch three different ways, and the three disagree:

| Branch | Present behaviour | Chosen because |
|---|---|---|
| `alternatives` blocks (canticle, affirmation, collect) | tab widget, one panel visible, selection persisted in `localStorage` | interactive-app convention |
| Multiple psalms | all rendered, no selector — the selector was built, then removed | maintainer's devotional preference |
| Multiple readings | all rendered, no selector; optional ones parenthesized; an advisory rubric from `lessonsPickText` (`render.js:526-535`, BUG-28) | no interaction was built |

The psalm row is the problem in miniature: a control that presented an
authorized choice was deleted on the maintainer's own devotional preference. The
reading row is the same gap arrived at by omission rather than decision —
`lessonsPickText`'s comment concedes it, "the app renders all M (it has no
pick-interaction)." Upstream review approved restoring a selector for both.

One reported defect resolves without code. The Evening Prayer OT reading for
2026-08-07, `2 Sam 12:1-14`, was queried as a BAS Year 1 reading appearing in
Year 2. That reading of it was withdrawn: Year 1/Year 2 is a BAS scheme, the
revised online daily office lectionary is the format to follow, and the brackets
mean the reading is **optional**. `data/lectionary/2026-08.json` already models
it that way (`{"citation": "2 Sam 12:1-14", "optional": true}`) and `lessonHtml`
parenthesizes it (`render.js:508`). The data was right; only its presentation
failed to make the optionality actionable.

## Decision

**Where the rite offers a choice, the app offers the choice.** Three
obligations, all of which must hold:

1. **The governing rubric is visible.** The sentence that establishes the choice
   is authorized text and renders unconditionally (ADR 0013). A control without
   its rubric tells the reader they may choose but not what the choice is
   between, or how many they may take.
2. **Every branch is reachable** from the office view, without changing mode,
   date, or setting.
3. **The app never silently resolves a choice.** No default may conceal that a
   choice existed. Remembering a previous selection is permitted *only* while
   the alternatives stay visibly enumerable — tab labels on screen satisfy this;
   an alternative dropped from the render does not.

Applied:

- **Psalms** — restore the selector, in the three-way form it had: show A, show
  B, show all.
- **Readings** — the same control, over the appointed readings. Optional
  readings stay marked as the lectionary marks them; being optional is a fact
  about the reading, and the parentheses are how the reader is told.
- **The reading rubric** — adopt the approved short form at the head of The
  Reading, *"One or two of the following readings are read."* Reconcile it with
  `lessonsPickText`, which already generates "One of the following two readings
  are read." for the same purpose; one mechanism, not two adjacent ones. The
  longer Evening Prayer form ("Evening Prayer continues with the Responsory or
  the Canticle or both…") is book text and returns on its own under ADR 0013 —
  we do not need to author it.
- **Alternatives tabs** — retained; see below.

### Tabs satisfy obligation 3

Upstream review confirmed that a tab is an acceptable way to present an
authorized choice, for canticles and affirmations as well as for the psalm and
reading selectors. The reasoning holds together: the other options stay named on
screen, so the reader is never shown a resolved choice they cannot see was a
choice. Combined with ADR 0013 restoring the governing rubric above the tab
strip, the reader is told a choice exists and given the control that takes it —
where today the rubric is hidden and the tabs are the only hint.

This is revisitable. If wider user testing shows the tabs read as "this is the
canticle" rather than "here are three", obligation 3 tightens and the widget
changes. That is an amendment on evidence, not a defect in this decision.

## Consequences

### Positive
- One rule covers psalms, readings, canticles, affirmations, and collects, where
  three ad-hoc behaviours stood.
- The maintainer's devotional preferences stop being expressible as app
  behaviour. That is the actual defect behind the removed psalm selector, and it
  is not fixed by re-adding the selector alone.
- Optional readings become actionable rather than merely annotated — the
  2026-08-07 case reads correctly with no data change.

### Negative
- More interactive state. Psalm and reading selections need persistence, and
  each new persisted key is another entry in the `localStorage` list at
  `app.js:61` and another thing to reset.
- A selector is a claim about how many readings are appointed, so it depends on
  `lessons_pick` and `optional` being right in the lectionary data for every
  date. Today those fields are advisory; a control makes them load-bearing, and
  a wrong value becomes a wrong instruction rather than a wrong hint.
- The rule forbids a genuinely nice simplification. Rendering all psalms is
  cleaner than any selector, and for most users it is what they want.

### Neutral / Notes
- ADR 0016 states the general constraint this applies; the three obligations
  above are its rules 1–3 read against a branch.
- The selector's design is pending wider user testing. Treat the control's
  *form* as provisional; the obligations above are not.
- This ADR does not settle whether the date picker is discoverable enough. That
  is a UI defect — changing the date currently requires knowing that tapping it
  works — not a question about optionality. Tracked separately.
