# ADR 0018: The alternate-observance toggle presents the day's identity

## Status
Accepted (2026-08-10)

Corrected (2026-08-15, #128): point 2's rank rule ranked eve lines `feria`
alongside actual ferias, for want of a token of their own; they now rank
`eve`. The same enrichment reaches an eve sitting in the *primary* slot,
which this ADR reached only through the alternate. The decision recorded here
— the toggle presents the selected observance's identity — is unchanged; an
eve that replaces the day's propers outright has no toggle to be presented
by, and that is the gap #128 closed.

Amended (2026-08-16, #133): point 3's fallback is withdrawn. Where the name
column states no identity for the alternate, the colour and rank chips are
omitted rather than filled from the day. The fallback was adopted as the
safe option because it was the behaviour already shipping, but what it
actually does is attribute the primary's colour and rank to the observance
the reader has just chosen instead of it — and it does so in the one place
the reader looks to see which day is being kept. Saying nothing is the only
option that neither misdescribes the alternate nor asserts a colour the
source withholds; the third, inferring the colour the label implies, would
have the app author an identity and belongs to the ADR 0015/0016 family if
it is ever wanted. The Negative bullet's request for an audit is met in the
same change: `validate_lectionary.cjs` licenses the slots this affects and
fails when the set moves in either direction.

## Context

The lectionary provides days with two possible observances. The office
columns carry both propers sets separated by an "Or" line (`Easter VII: Ps
66, 67; …` / `Ascension: Ps 8, 47; …`), which `parse_office_column` splits
into `officeData.alternate`. The name column's secondary lines carry the
alternate observance's own identity — `Corpus Christi (White) [if also
celebrated on Sunday]`, `Feria in Christmastide (White)`, `Ascension Sunday
(White or Gold) [if kept on Sunday]`. The full population is 15 dates in the
current lectionary window (transferable feasts — Saint Stephen OR Feria,
Ascension OR Easter VII, Corpus Christi OR Proper 10, Dedication OR Proper 30
— plus the eve-of alternations and saint's-day-or-feria days).

The app's Primary/Alternate toggle (ADR 0014: optionality is presented, not
resolved) switches the office propers — title, psalms, lessons, collect
reference — but leaves the day's **identity** pinned to the primary:
`day-title` and the document title switch to the alternate's label
(`app.js:816-821`), but the rank chip (`formatRank(day.rank)`, `app.js:844`)
and the colour chips (`colourHexes(day.colour)`, `app.js:824`) always render
the primary's. Toggling to Corpus Christi on 2026-06-07 (Proper 10, Green)
still shows green chips; toggling to Feria on 2026-12-26 (Saint Stephen,
Holy Day, Red) still announces Holy Day. The toggle is half-wired: it swaps
the readings but presents the wrong day's rank and colour.

ADR 0017 deliberately left the `observances` field's consumer open (issue
#56: "give it a consumer … or document it as converter-internal"). This ADR
settles it: the consumer is the toggle's missing identity half. The second
line of the name column — the same lines ADR 0017's classifier reads — is
where the alternate observance's name and colour live.

## Decision

**The alternate-observance toggle also switches the day's identity: the
colour chips and the rank chip follow the selected observance.**

1. **Data — the extractor enriches each office alternate with the alternate
   observance's identity.** `convert_lectionary.py` post-processes every
   entry that has a morning or evening `alternate`: it matches the
   alternate's label (e.g. "Feria", "Corpus Christi", "Eve of the
   Ascension") against the name column's secondary lines by case-insensitive
   containment in either direction, after stripping "the" from both sides
   (the label's article form need not match the CSV's bare form). On a match
   it sets `alternate.colour` from the line's colour decoration `(White)`,
   `(White or Gold)`) and `alternate.optional` from
   the presence of an `[if …]` bracket. Where no line matches — 2026-01-12's
   "Feria" alternate has no feria line in the name column — none of those
   fields is written, and `optional` is the one the match always sets, so its
   absence is what marks an alternate the name column never identified. What
   the UI does with that is point 3.
2. **Rank.** The alternate's rank is `feria` when its matched line is a
   feria line (contains "Feria" — "Easter Feria", "Feria in Christmastide")
   or begins with "Eve"; otherwise it keeps the day's rank (a feast kept on
   Sunday takes the Sunday's rank). This is the one judgment call in the
   ADR; it matches how the transferable-feast days actually parse.
3. **UI — `web/app.js`.** When the alternate is active and it matched a
   name-column line, the colour chips and rank chip render from the
   alternate's identity, falling back to the day's for a field that line does
   not carry — a feast kept on Sunday takes the Sunday's rank. When it
   matched no line at all, both chips are omitted (amended, #133). No new
   control: the existing toggle buttons are the whole surface.
4. **Tests.** Unit tests for the enrichment pass (matching, colour, rank,
   fallback) and an e2e assertion that toggling 2026-06-07 MP swaps the
   colour chip Green → White and toggling 2026-12-26 swaps the rank chip
   Holy Day → Feria.

**Out of scope:** rendering the remaining observance facts (fast days,
octaves, season of creation, plain eves) as chips or indicators. They are
informational rather than toggles, no reader has asked for them, and they
remain converter-internal data under ADR 0017. If a need appears, it is a
separate decision.

## Consequences

### Positive
- The toggle becomes fully correct: the reader who keeps Corpus Christi sees
  Corpus Christi's colour, not Proper 10's.
- The second line of the name column gains a reader-facing consumer, closing
  issue #56's question with an answer rather than a deferral.
- The `observances` vocabulary (ADR 0017) is justified end-to-end: the same
  lines it classifies carry the identity the toggle now presents.

### Negative
- A matching heuristic (containment after "the"-stripping) is a new
  hand-encoded rule; a date whose alternate matches no secondary line shows
  no colour or rank at all (amended, #133 — it showed the day's until then).
  Seven slots are in that state, licensed in `validate_lectionary.cjs`, and
  in every one of them the name column simply never states the alternate's
  identity, so there is nothing a better match would find.
- The rank rule is a judgment call, not derivable from the source alone.
- Adds a second post-pass over the name column alongside the observances
  classifier; the two must stay in sync if the CSV's line structure changes.

### Neutral / Notes
- The whole population is the 15 transferable-feast dates in the current
  window; the field is emitted only for entries that have an office
  alternate.
- ADR 0017's out-of-scope note ("how observances gets a consumer … is issue
  #56's other half") is satisfied by this decision; 0017 itself remains the
  record of the production method.
