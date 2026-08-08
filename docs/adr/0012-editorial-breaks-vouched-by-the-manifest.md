# ADR 0012: Editorial line breaks are vouched for by the correction manifest

## Status
Accepted (implemented 2026-08-07)

## Context

The ACC errata asks for line breaks the printed book does not have:

    May God, who has called us out of darkness
    into the marvellous light of Christ,
    bless us and fill us with peace. Amen.

These arrive as `office_text` corrections under ADR 0005, applied after
extraction. The extractor is untouched — it still decides every break from page
geometry, and AGENTS.md's "measure the page, never a proxy" is unaffected. The
errata is not a proxy for the geometry; it is a different authority applied
downstream, at the layer ADR 0005 already established for editorial corrections.

Two QA rules read a line ending without terminal punctuation as a suspected PDF
column wrap: `collect-and-dismissal-no-orphan-breaks` in `validate_office.cjs`
(tier 2, feeds the coherence score that gates `qa` and `promote`), and the
litany scan in `check_text_quality.py` (which hangs off `validate` and gates
nothing today). That inference is right for a wrap and wrong for a deliberate
break, so both rules report the lines above.

AGENTS.md forbids the obvious fix — "Do not widen either rule to make a
correction fit" — and section-level exemption is what `_VERSE_SECTIONS` did
before it was retired for being unfalsifiable.

## Decision

**A correction vouches for the breaks it introduces, at its own location.**
Both rules build their sanctioned set from `data/corrections.json`:

- Keyed on `source` (`pwc-errata-*`), not an `id` prefix — an id is a label,
  and renaming one must not change what is enforced.
- Scoped to the correction's `{office, field}`. Global matching would let one
  correction vouch for an identical line elsewhere; six dismissal lines repeat
  verbatim across two to four forms, so global scope makes "the exemption
  disappears with the correction" false.
- A correction on `_shared.K` vouches at every form whose field is
  `{"type": "shared", "key": K}`. Note this is the opposite of
  `corrections_lib.iter_text_segments`, which refuses to follow shared
  references: *applying* through one would rewrite siblings silently, but
  *vouching* through one is right, because the text really is at every form.
- Per line, not per section. Non-empty lines only: an errata stanza gap yields
  an empty string from the split, which is dropped rather than added. The first
  implementation added it, inert only because both call sites happened to test
  truthiness first.
- `collects.json` gets no sanctioned set, passed explicitly. No correction
  category reaches it.
- No manifest, or an unparseable one: empty set, every break checked.

Deriving the exemption from a file that feeds the pipeline deserves suspicion.
The mitigating facts are that `data/corrections.json` is committed (the data it
corrects is not), hash-guarded by `check_data_integrity.py`, and reviewed as a
diff. But that is only half an answer: "this break is intentional" cannot
distinguish a correctly applied errata block from one that dropped a break, and
the first reflow pass dropped four while `make test`, `make qa` and a 100/100
coherence score stayed green. So the exemption ships with its counterweight.

**`tools/audit_errata.py` checks the data against the errata.** It aligns every
```text block in `docs/errata/*.md` against `data/offices.json` and reports
`MISSING-BREAK`, `EXTRA-BREAK`, `WORDING` (texts diverge, no break adjudicable)
and `UNALIGNED`.

The office comes from the `##` heading, which is mechanical and total across
both documents. **The field is never parsed** — the block aligns against the
whole office, all sections concatenated with `{"type": "shared"}` resolved, and
the field is read off where the alignment lands. AGENTS.md warns that assigning
sections by heading "has produced confidently wrong measurements more than
once"; this makes that mistake unavailable, and is why the audit sees `canticle`
and `responsory` errata a field-guessing version would skip.

Matching is over the block's whole word stream in contiguous order
(`difflib.SequenceMatcher`); line pairs are the unit of *reporting* only.
Per-line matching would be ambiguous — `worthy to be praised and exalted for
ever.` occurs 7 times within `ordinary-sunday-mp` alone. Fields are separated
by a boundary marker so no match straddles two, and segment boundaries carry an
implicit break, since a break there is structural rather than a wrap.

`WORDING` is the load-bearing class, because a divergence is where breaks get
dropped: the first pass lost three of its four breaks next to one. Each is
cleared by a row in `docs/errata/README.md` recording whether the errata's
reading or ours is correct, and why.

**The audit reports; it does not gate.** It is a `make` target and a review
step, run when the errata or the corrections change. Gating `qa` on fuzzy
alignment over prose documents is a bet this ADR does not need to take — the
audit's value is that the dropped breaks become visible at all, and a
report nobody can ignore during a reflow change achieves that. Revisit once it
has a track record.

## Consequences

### Positive
- Both rules keep their full reach — no section exempted, no threshold loosened.
- An exemption cannot outlive its reason: it exists only while the correction
  does, only where the correction points.
- Dropped errata breaks become visible. The four lost in the first pass would
  have been caught.

### Negative
- The validators gain a dependency on `data/corrections.json`.
- The same schema is read by two hand-written implementations, in two
  languages, with no shared library possible across the boundary. A conformance
  test — one fixture, both readers, identical sets asserted — is the substitute
  for what `corrections_lib.py` does within Python. It is not theatre: the two
  sides had already drifted on whether a line is trimmed at one end or both,
  and it also caught a NUL byte standing where a space belonged in the JS key
  template, which would have meant no exemption ever matching anything.
- `source` is made load-bearing while ADR 0005's `source` enum has drifted from
  3 documented values to 6, and the JSON Schema that ADR promises was never
  written.
- Fuzzy alignment can misreport. Tolerable because the audit reports rather
  than gates; it would not be if it blocked `qa`.

### Neutral / Notes
- **Written after the fact.** `docs/adr/README.md`'s gate is that a Proposed ADR
  becomes Accepted before implementation begins. This one records a mechanism
  that had already shipped once with no ADR at all; the design here is what it
  should have been, and the implementation was corrected to match. Recorded so
  the next reader knows the order things happened in.
- What the audit found on first run, all since cleared: four `MISSING-BREAK`s;
  three undeclared `WORDING` divergences (Seasonal p. 43 `voices`, p. 80 `I`,
  p. 100 `been`); Ordinary p. 156, where our `“Abba,` / `Father.”` break is
  genuinely wrong; and Seasonal p. 52, deleting the Epiphany EP doxologies as a
  whole-field correction. `make audit-errata` now reports the errata fully
  applied — that is the baseline a future regression is measured against.
- Applying p. 52 shortened `epiphany-ep` from 51 segments to 45, which lowered
  the seasonal-EP peer mean and tightened its spread enough to push `easter-ep`
  past 2σ on two metrics without `easter-ep` changing at all. Both are recorded
  in `audit_expected.json` naming that cause. A correction to one form can move
  the statistics of its peers; the cross-form audit reports the form that moved
  least as readily as the one that changed.
- Hard breaks are not a new rendering category: `render.js` maps `\n` to `<br>`,
  and 3,205 such lines already ship with a length distribution the errata's 65
  are indistinguishable from. An earlier draft treated this as a blocking
  question about fluid versus fixed measure; the data says it is not one.
