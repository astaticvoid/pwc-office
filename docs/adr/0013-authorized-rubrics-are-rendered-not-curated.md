# ADR 0013: Authorized rubrics are rendered, not curated

## Status
Accepted (2026-08-07)

Amended (2026-08-17): two of the four `SKIP_RUBRICS` entries this ADR named —
"The Responsory is said or sung." and "The Litany is said or sung." — are
withdrawn. Checked against the actual upstream correspondence this ADR's
Context section paraphrases, neither was ever raised as a duplicate to
suppress; only the Lord's Prayer intro and the Affirmation-of-Faith heading
were. The "duplicate of the heading" reasoning below was this ADR's own
extension by analogy, not a reviewed decision, and it sat oddly next to ADR
0019 item 6 keeping the equivalent "A Psalm is said or sung." unsuppressed for
the identical reason. Both rubrics now render, under ADR 0016 rule 1's
default (authorized text renders absent a justified exception). The `SKIP_RUBRICS`
mechanism itself, and its remaining Lord's Prayer entry, are unaffected.

## Context

ACC rubrics are authorized text — the national church and the diocesan bishops
approve them, and the branching they describe (pick one of these, then either
that or the other) is part of what gets approved. The app can present the
office; it shouldn't edit it. Upstream review flagged our streamlining as having
gone past that line.

Measured against `data/offices.json` — 321 rubric segments, 86 distinct texts —
the app currently withholds or rewrites **59 of the 86 (69%)** in Office mode,
by three mechanisms in `web/render.js`, all reached from one dispatch in
`renderSegments` (`render.js:450-455`):

| Mechanism | Distinct texts | Effect | Applies in book mode |
|---|---|---|---|
| `INTERCESSIONS_CONDENSED` (`render.js:95`) | 16 | replaced with our own sentence | yes |
| `SKIP_RUBRICS` (`render.js:84`) | 4 | deleted | yes |
| `BOOK_ONLY_RUBRICS` (`render.js:88`) | 39 | hidden unless `body.book-mode` | no |
| — | 27 | rendered | — |

The stated reason is aesthetic. `BOOK_ONLY_RUBRICS` is commented "noisy in the
interactive app"; `SKIP_RUBRICS`, "section-navigation cues". Noise is a real
cost, but not one we get to charge against authorized text — and the regex is
not a neutral filter: it matches `continues with`, `one of the following may be said
or sung`, `one of the following affirmations`, `may be offered silently` —
precisely the branching instructions that carry the authorized structure. The
mechanism removes the choice by removing the sentences that announce it.

`INTERCESSIONS_CONDENSED` is the sharpest case and the only one that destroys
content rather than navigation. The rubric it replaces carries a season-specific
bidding list — for `advent-mp`:

    Additional intercessions, petitions, and thanksgivings may be offered
    silently or aloud. Among these concerns it is appropriate to remember:
    • the Church, that we may be ready for the coming of Christ
    • the leaders of the Church
    • the nations, that they may seek peace and reconciliation
    • those who are working for justice in the world
    • the broken, that they may find God's healing.

Thirty such texts, distinct per season and per office, are all rendered as the
same fifteen words of ours: *"Offer intercessions, petitions, and thanksgivings,
silently or aloud."* It reaches the reader through `collectToggleHtml`'s
`generalRubrics` path (`app.js:579`), which calls `renderSegments` and so hits
the substitution before anything else. There is no mode in which the biddings
appear. Nobody decided this in an ADR; it accreted.

In the web app, book mode is otherwise a *typographic* mode — verse numbers on,
alternative panels expanded (`office.css:376-398`). `.rubric-book-only` is the
single place where it becomes a *different text*. Closing that gap — the same
rubrics in both settings — is what upstream review asked for.

### The text renderer is worse, and it is why nobody caught this

ADR 0004 established `web/render.js` as the single engine behind three
consumers, and required that "the text mode must agree with the HTML mode on
structural decisions (which rubrics to suppress…)". It does not agree. The text
path takes suppression from caller options — `opts.skipRubrics` and
`opts.condenseRubrics` (`render.js:620-632`) — and `cli/book.js:46-53` passes a
*fourth* rule set, differently worded again, which deletes `continues with`
outright where the web hides it behind a recoverable class.

That divergence is the intended part. The unintended part is a control-flow bug:
when `condenseRubrics` is set, the `continue` at `render.js:631` fires for every
rubric, so any rubric that matches no condense pattern is dropped silently.
Across all 30 forms:

    rubric segments in data:        321
    rendered by cli/book.js:         14
    rendered if the bug is fixed:   290

**Fourteen of 321.** `cli/book.js` and `tools/review_form.cjs` are the two
callers that set `condenseRubrics`, and `review_form.cjs` is the tool whose
header says "suitable for marking issues" — the one a human reads to review a
form. The review instrument has been blind to 96% of the rubrics, which is a
sufficient explanation for four wrong rubrics surviving every review that used
it and being caught only by reading the running app.
(`compare_staging.cjs` is unaffected; it diffs rendered DOM.)

## Decision

**The renderer may change where a rubric appears and how it looks. It may not
change whether it appears, or what it says.**

Four permitted transformations, exhaustive:

1. **Render.** The default, and what 27 texts already get.
2. **Reposition or regenerate.** A rubric may be moved, or emitted
   programmatically at a point the data does not carry it, provided the words
   the reader sees are the book's words.
3. **Suppress as a duplicate.** Permitted only when the same text is already
   rendered elsewhere *in the same view and the same mode*, and only per-text
   with the duplicate named, **and only where that suppression was itself
   put to upstream review** — this ADR is not itself the authority to decide
   a rubric is "just a duplicate." Of the four `SKIP_RUBRICS` entries
   originally listed here, only `The Lord's Prayer` (each emitted as a
   heading by `renderSubsection`) and `Affirmation of Faith.` (recovered
   under #84, no longer suppressed) trace to an actual request; `The
   Responsory is said or sung.` and `The Litany is said or sung.` did not and
   are withdrawn as of the 2026-08-17 amendment above.
4. **Restyle.** Any typography, spacing, or emphasis.

Paraphrase and hide-by-mode are not on the list.

- **Delete `INTERCESSIONS_CONDENSED` and `INTERCESSIONS_RE`** (`render.js:94-95`,
  `450`). The biddings render.
- **Delete `BOOK_ONLY_RUBRICS`** (`render.js:88`, `454`), the `.rubric-book-only`
  class (`office.css:373-374`), and its eight call sites in `app.js` and
  `render.js`. Book mode keeps its typographic differences and loses its textual
  one.
- **`SKIP_RUBRICS` survives, made falsifiable.** Today it is an unfalsifiable
  section-shaped exemption of the kind AGENTS.md records as having failed before
  (`_VERSE_SECTIONS`, retired). Each of the four entries gains the heading it
  defers to, and a test asserts that heading is in the rendered DOM. If the
  heading stops being emitted, the suppression fails rather than silently
  swallowing the rubric.

- **Fix `render.js:631` and retire the caller-supplied rubric options.** The
  misplaced `continue` is a bug and is fixed regardless of the rest of this ADR.
  Beyond that, `opts.skipRubrics` and `opts.condenseRubrics` are how the text
  mode came to disagree with the HTML mode in violation of ADR 0004: suppression
  policy set per-caller cannot be one policy. Both options are removed, and the
  text mode takes the same `SKIP_RUBRICS` allowlist the HTML mode does.
  `cli/book.js:46-53` and `tools/review_form.cjs:35-38` lose their local rule
  sets.

**A validator holds the line, over the fields it can currently reach.**
`validate_render.cjs` gains a rule: every rubric segment in a checked field
appears in the rendered Office-mode DOM, except those on the `SKIP_RUBRICS`
allowlist, each of which must produce its named duplicate. This is the ADR 0012
shape — the exemption lives at the thing it exempts and dies with it — rather
than a regex nobody re-reads. The rule counts rubrics in the text mode against
the same expectation, so the two modes cannot drift apart again without failing.

**`seasonal_collects` is out of reach today, and it is 112 of the 321 rubric
segments (35%).** Rubrics by field: `seasonal_collects` 112, `responsory` 60,
`canticle` 60, `affirmation` 30, `litany` 30, `opening_responses` 14,
`intercessions` 14, `invitatory` 1. `validate_render.cjs`'s `renderableFields`
map (`:47-59`) covers eleven fields and excludes this one, and it cannot be
fixed by adding a twelfth entry:

- The field needs `filterSeasonalCollects(segs, weekIdx)` (`render.js:213-240`)
  to narrow to the right week first — per-date, not per-form, so the check must
  iterate weeks rather than render the field once.
- The narrowed result is rendered by `collectToggleHtml` (`app.js:554`), which
  is not exported.
- `app.js` calls `document.addEventListener` at module top level (`:1200`), so
  it cannot be imported under plain Node at all.

Extracting `collectToggleHtml` into `render.js` is therefore a **prerequisite**
for covering the largest single share of the rubrics, and it is a real refactor,
not a line in a config map. Until it happens the rule protects 209 of 321
segments and the ADR should not be read as claiming more. Do not widen the
`renderableFields` map to make the number look better — a rule that renders
`seasonal_collects` through the wrong path would pass while checking nothing.

## Consequences

### Positive
- The rendered office is the authorized office. The app stops editing text it
  has no business editing.
- Thirty seasonal bidding lists, currently extracted and then discarded at the
  last step, reach the reader for the first time.
- Suppression becomes falsifiable and enumerable — four named cases with tests,
  not two regexes with 43 incidental matches.
- Book mode and Office mode stop disagreeing about what the office says, which
  removes a whole class of "which mode is right?" bug report.
- `review_form.cjs` starts showing rubrics, so the human review step can see the
  text it is supposed to be reviewing. This is the finding with the widest
  reach: 276 rubric segments were being dropped by a stray `continue`, and no
  test, QA rule, or coherence score noticed.
- ADR 0004's requirement that the two modes agree on rubric suppression becomes
  enforced rather than merely stated.

### Negative
- **Office mode gets materially longer**, which is a real regression by the
  metric that motivated the hiding. Thirty-nine rubrics return, and the
  intercession biddings are five to seven bullets each. Typography now has to
  carry what deletion used to: `.seg-rubric` becomes load-bearing, and this
  likely needs a pass through ADR 0010's design-options process before it ships.
  We are accepting a worse-looking app for a correct one, with the design debt
  named rather than deferred silently.
- The validator lands with 35% of the rubrics uncovered until `collectToggleHtml`
  is extracted from `app.js`. That is a genuine hole in the guarantee, named
  here rather than discovered later: `seasonal_collects` is exactly where the
  intercession biddings live, so the field this ADR most wants to protect is the
  one the rule reaches last.
- The bidding lists arrive as one rubric segment containing bulleted lines. They
  will render as a `<br>`-separated block, not a list. Acceptable but ugly;
  turning them into real list markup is a data-shape change and is out of scope
  here.
- Eight call sites emit rubric strings the app invents rather than extracts, and
  removing the book-only class exposes all of them unconditionally. Four of the
  eight are known to be wrong. ADR 0015 covers that; this ADR must not ship
  ahead of those corrections or it promotes known-wrong text from hidden to
  visible.

### Neutral / Notes
- This reverses a decision that was never recorded. There is no ADR to supersede
  — the hiding accreted through `render.js` constants across several changes.
- ADR 0016 states the general constraint this applies. This ADR is one of its
  three worked cases and does not restate it.
- **Relationship to ADR 0004.** This does not contradict it; it enforces a
  requirement 0004 stated and never implemented. 0004 stays Accepted. The
  removal of `opts.skipRubrics`/`opts.condenseRubrics` narrows the options
  surface 0004 describes, which is a simplification of its design, not a
  reversal.
- `cli/book.js` output will grow substantially — from 14 rubric segments to
  ~290 across the corpus. Any golden-file tests over that output need
  regenerating, and the diff will be large and almost entirely legitimate.
  Review it for what is *missing* rather than what is added.
- The 69% figure counts distinct texts, not segments, per AGENTS.md's "count only
  what can exhibit the defect": the same rubric repeated across 30 forms is one
  editorial decision, not thirty.
- The wording corrections under ADR 0015 (drop "from the appointed lectionary",
  "or the Litany" → "or the Prayers") touch some of the same lines. Keep them in
  separate commits: this ADR changes *whether* text shows, ADR 0015 changes
  *what it says*, and a combined diff would make neither reviewable.
