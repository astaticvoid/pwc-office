# ADR 0019: Settled readings of the rubrics

## Status
Proposed (2026-08-12)

Amends ADR 0014 (the reading selector, and the wording of the reading rubric).
ADRs 0013, 0015 and 0016 are unchanged; this ADR records the settled
*interpretations* their rules are applied to.

## Context

The rules are written down. ADR 0013 says authorized rubrics render rather than
get curated; 0014 says a choice is presented rather than resolved; 0015 says text
the app authors carries provenance; 0016 states the constraint all three apply.
What is not written down is the set of **specific readings** upstream review has
settled — which sentence is right, where it belongs, and what it is that the app
must therefore stop doing.

That gap has cost us three times already:

- The reading conclusion was synthesized with a season branch, corrected under
  ADR 0015, and remains a two-line change away from coming back — nothing in the
  extractor says *why* the branch is wrong, only that it is gone.
- Rubric suppression was built twice under two names (`BOOK_ONLY_RUBRICS`, and
  `opts.condenseRubrics` in the text path) before 0013 removed both. Neither
  author thought they were re-adding a deleted mechanism.
- The reading selector shipped under 0014 and, in presenting the choice between
  readings, removed the Responsory and the Canticle — two subsections that are
  not part of that choice (#77).

A rule with no worked instances is easy to honour in the abstract and violate in
a diff. This ADR is the list of instances.

Two rounds of upstream review are folded in. Where they differ, the later
governs, and the difference is noted at the item.

**The governing principle, restated because it decides every tie below.** The
branching is not clutter to be tidied away. Following the rubrics as written is
what the authorizing body approves and what those praying the office are
expected to do, so the reader's choice *is* the authorized shape of the rite.
Streamlining is permitted only where it takes nothing away from that.

## Decision

Nine settled readings. Each records the interpretation, what it forbids, and
where it stands. **"Forbids" is the operative line** — it is what a future change
has to be checked against.

### 1. The reading conclusion is "Holy Word, Holy Wisdom.", everywhere

The lowercase inverted form ("Holy wisdom, holy word.") is an error in the
printed book, confirmed upstream and documented in the errata. It is the same
sentence in every office and every season.

*Forbids:* any seasonal or ordinary/seasonal branch on this string. The defect
was a `office_key.startswith('ordinary-')` test in `_add_reading_responses`
(ADR 0015); a re-introduction would most likely arrive as "restoring what the
book prints".

*Status:* shipped (#62).

### 2. The same rubrics appear in Office mode and in Book mode

Book mode is a typographic mode. It may change how a rubric looks, never whether
it appears.

*Forbids:* any mode-, setting-, or density-conditional rubric suppression. The
`SKIP_RUBRICS` duplicates are the only exemption, and each is pinned to the
heading it defers to (ADR 0013). Written when there were four; three remain
since #84 recovered the first line of the `Affirmation of Faith.` rubric, which
had been a bare heading-shaped fragment only because the running-header filter
was eating the rest of the sentence.

*Status:* shipped (#59).

### 3. The psalm and reading introductions drop "from the appointed lectionary"

*Forbids:* re-expanding them to name the lectionary. Note this is a divergence
from the printed page, which names three lectionaries in full (#84) —
authorized on review, so it stays, and it stays recorded as a divergence rather
than quietly becoming what we think the book says.

*Status:* shipped. Recorded as `adr0019-item3-psalm-introduction`,
`-or-psalms` and `-reading-introduction` in `data/corrections.json` (#88). It
was briefly violated in the other direction: #84 recovered the printed sentence
and rendered it, which is what "re-expanding" names, so the divergence now
lives in the manifest against the extracted text rather than as a shorter
string rendered beside it.

### 4. The affirmation transition reads "…or the Prayers", not "…or the Litany"

In both offices.

*Status:* shipped. Applied as `adr0019-item4-affirmation-transition` to the
canticle's closing rubric, which is where the book prints it (16 seasonal forms
read "…or the Litany"; the 14 ordinary forms already read "…or the Prayers").

### 5. The pre-Litany transition sentence is deleted

*"{Morning|Evening} Prayer continues with the Litany."*, printed under
Intercessions and Thanksgivings, goes. It is ours, not the book's — a registered
app-authored string (`litanyTransition`, `source: editorial`).

*Forbids:* authoring a replacement bridge sentence between the intercessions and
the Litany. The Litany's own heading is the transition.

*Status:* shipped (#80, #84). One correction to the premise: the sentence is
**not** ours. It only looked app-authored because the running-header filter was
eating it, so it never reached the data. The app-authored copy under
Intercessions and Thanksgivings is deleted as this item asks; the book's own,
which closes the Affirmation, is extracted and renders there.

### 6. The Psalms section says its rubric once, at the head

*"A Psalm is said or sung."* — one sentence, at the top of the section,
regardless of how many psalms the day appoints or how they are grouped.

*Forbids:* per-branch variants of the sentence (three existed —
`psalmIntro`, `psalmsIntro`, `singlePsalmIntro`), and repeating the
end-of-psalm rubric once per alternative panel.

*Status:* shipped (#79, #88), both halves.

All three variants and `psalmEnd` are gone from the register; the section's own
extracted rubric renders once at its head, and the two Pentecost forms' printed
"(or Psalms)" wording resolves to the same sentence as the other 28 under this
item.

The repetition half took a second pass. Retiring `psalmEnd` removed the fixed
string but the extracted cue replaced it inside `gloriaHtml`, which runs once
per selector panel — and book mode makes every panel visible, so the cue and
the doxology printed N+1 times. Both now sit outside the selector, once: the
selector chooses which psalms are said, and the doxology follows whichever they
were, so it was never part of that choice.

### 7. Both appointed readings stay in the office, and the rubric carries the choice

The Reading subcomponent keeps its readings in book order, with the Responsory
after the first and the Canticle after the second. The reader is told about the
choice in two rubrics rather than shown a control that resolves it:

- at the head of the section, *"One or two readings are read."*;
- after the first reading, the book's own transition —
  *"{Morning|Evening} Prayer continues with the Responsory or the Canticle or
  both. If two Readings are read, then the Responsory follows the first Reading
  and the Canticle the second."*

The second is book text on every Reading page and is missing from our data
because extraction discards the block it sits in (#84). It should be extracted,
not authored.

*Forbids:* a control whose per-reading view removes the Responsory or the
Canticle; and re-adopting the longer head-of-section wording, *"One or two of
the following readings are read."*, which the earlier round approved and the
later round shortened.

*Status:* open (#77). **Amends ADR 0014**, whose "Applied" list adopted both the
per-reading selector and the longer sentence.

### 8. Brackets mean optional

A parenthesised citation or verse span is an optional part of what is appointed
— not a separate alternative, and not evidence of a different lectionary year.
The Year 1 / Year 2 scheme belongs to a different book and is not what the
published lectionary follows; that query was withdrawn on review.

Applied to psalms, this reads on two levels: choose between the appointed
psalms, and then, within the chosen one, the bracketed verses may be omitted.
`Ps 101, 109:1-4, (5-19), 20-30` is one choice with an omission inside it, not
four peers (#78).

*Forbids:* flattening a bracketed span into a peer alternative; and per-date
special cases to paper over it — the shape belongs in `convert_lectionary.py`
(see #13).

*Status:* readings shipped (ADR 0014); psalms open (#78).

### 9. A control may filter only what a rubric makes optional

The general rule behind item 7, stated so it binds the next selector as well as
this one. A widget that presents a choice may show and hide exactly the text the
governing rubric marks as choosable. Anything else on the page stays on the
page, in every view of the control, because nothing authorized it to leave.

*Forbids:* "tab shows just this branch" as a default implementation shape. The
question a selector has to answer first is *what does the rubric say is
optional*, and the answer is frequently narrower than the block the widget is
convenient to wrap around.

*Status:* new here; #77 is its first application.

## Consequences

### Positive
- The interpretations become checkable. Each item names what a future diff must
  not do, so a reviewer has something to test a change against rather than a
  general principle to feel their way around.
- Three settled items (5, 6, 7) are open work; recording them before they ship
  keeps the reasoning from having to be rebuilt from an issue thread.
- Item 9 generalises the reading-selector defect, so the next control does not
  have to make the same mistake to discover the rule.
- The divergences we are authorized to keep (item 3) are recorded *as*
  divergences. That is the difference between an approved shortening and a
  drift.

### Negative
- Nine items is a list to maintain, and a list that goes stale is worse than no
  list. Each item carries an issue number or an ADR reference so its status can
  be checked rather than assumed.
- Items 5–8 are stated ahead of implementation, so the ADR describes an app that
  does not exist yet. Read the *Status* line before citing an item as current
  behaviour.
- Item 9 is a real constraint on interaction design. It rules out the simplest
  implementation of a selector — wrap the block, show one branch — and every
  future control pays that cost.

### Neutral / Notes
- ADR 0016 is the rule; 0013, 0014 and 0015 are its mechanisms; this is the
  casebook. It introduces no new mechanism and adds no code.
- ADR 0014's obligations 1–3 stand unamended. Item 7 changes *which control*
  satisfies them for the readings, not the obligations themselves — and the
  rubric-led answer satisfies obligation 3 more directly than a tab strip does,
  since nothing is hidden at all.
- Where an item's rubric is book text we do not currently hold (items 7 and,
  partly, 3), the fix is extraction (#84), not a new app-authored string. ADR
  0015's register is for text with no page behind it; it is not a shortcut past
  a gap in the extractor.
- Upstream asked for wider user testing of the psalm and reading toggles. That
  evidence can amend item 9's application, and 0014 already anticipates it. It
  cannot amend items 1–8, which are readings of the rite rather than judgements
  about the interface.
