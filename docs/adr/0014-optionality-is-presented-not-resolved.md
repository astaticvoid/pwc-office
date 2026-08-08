# ADR 0014: Optionality is presented, not resolved

## Status
Proposed — one open question, below, is pending upstream review before this can
be Accepted.

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
| Multiple psalms | all rendered, no selector — the selector was built, then removed | *"you should just read all the Psalms"* |
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
- **Alternatives tabs** — retained, subject to the open question.

### Open question

Does a tab satisfy obligation 3? What upstream review approved was a *toggle*
for psalms and readings, which suggests a control showing one option at a time
is fine when the other options are named on screen. The canticle and affirmation
tabs weren't part of that, and they hide authorized text behind a click in a way
the printed book doesn't. Extending the approval to cover them is an inference,
not something anyone approved.

This ADR states the rule as written above — tabs qualify — because that is the
most probable reading and it keeps the existing widget. It stays Proposed until
confirmed. If the answer is that all alternatives must be visible at once,
obligation 3 tightens and the tab widget becomes book-mode-only behaviour
throughout, which is a larger change than anything else here.

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
