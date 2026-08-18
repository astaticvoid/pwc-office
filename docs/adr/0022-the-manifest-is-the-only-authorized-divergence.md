# ADR 0022: The manifest is the only authorized divergence from the source text

## Status
Proposed (2026-08-17)

## Context

Every ADR that governs divergence from the printed source governs the **render**
layer: ADR 0013 (rubrics are rendered, not curated), ADR 0014 (optionality is
presented, not resolved), ADR 0015 (app-authored text carries provenance), ADR
0016 (the app renders the rite, it does not edit it), ADR 0019 (the settled
readings). Nothing governs what the **pipeline** may change about the text on
its way through (#92).

The pipeline has five stages where shipped text can differ from the page, and
only one of them records why:

| stage | can change the text? | records why? |
|---|---|---|
| `extract_office_styles.py` — noise filtering, line typing | yes | no |
| `extract_offices.py` — sectioning, merging, alternatives, reflow, shared dedup | yes | no |
| `normalize_offices.py` — hoists shared blocks into `_shared` | yes | no |
| `apply_corrections.py` | yes | **`data/corrections.json`, audited** (ADR 0005, ADR 0012) |
| render — `SKIP_RUBRICS`, `LITURGICAL_TEXT_REGISTER` | yes | ADR 0013 (falsifiable), ADR 0015 (register entries carry `source`) |

Two of the last three serious defects were unrecorded divergences at an
unaudited stage: #84 (a stage-1 noise filter ate every rubric opening "Morning
/Evening Prayer …" for the life of the project) and #87 (a stage-2 dedup keyed
shared blocks by *shape* rather than equality, so all 30 forms inherited one
office's transition rubrics). Both were invisible because nothing compared
extracted text against the page.

The distinction this ADR draws is **structural change vs wording change**:

- The pipeline's legitimate transformations are structural: dropping running
  headers and page furniture (non-content), normalizing whitespace, deciding
  line breaks from geometry (#38, #39), merging segments, grouping
  alternatives, hoisting shared blocks. They change how the page's text is
  broken up, not what it says. Recovery is the same direction: a parse fix
  that moves output *toward* the page (the dehyphenation of PDF line-wrap
  artifacts in saint bios, the #84 header-filter fix) restores the author's
  text instead of departing from it.
- A **wording** divergence — any letter, word, or punctuation that differs
  from the page — is authorized in exactly one place: `data/corrections.json`,
  where `validate_corrections.py` checks the `source` is permitted and the
  `old` value still matches the pre-correction artifact, and where ADR 0012's
  line-break exemptions are keyed on the source.

Since #92 was filed, the manifest-side mechanism has largely caught up with the
intent, in ADR 0015's status notes:

- Four `upstream-review` entries (`adr0019-item3-*`, `adr0019-item4-*`) now
  record the settled readings as corrections on the extracted rubrics, each
  carrying the ADR item that settled it.
- The register holds one entry, `readingsPick` — the only text with no page
  behind it, which is what ADR 0015 says the register is for.
- The reading responses are extracted, not synthesized (#91).
- `SKIP_RUBRICS` is down to one entry under ADR 0013's amendment.

What is still missing is the governing statement itself and the warrant
requirement for non-error divergences. Every manifest entry today carries a
`reason` (77/77) and the upstream-review entries carry `adr` (4/4), but
`validate_provenance` enforces neither — a future entry could drop its warrant
and nothing would fail. The issue also floated splitting `editorial` into
"ruled on by the project" vs "extraction cosmetics"; the data answers that
before it is asked: all 11 `editorial` entries are rulings (orthography,
observance rank, the #101 creed comma) each with a `reason`, and extraction
cosmetics already have their own source, `pdf-extraction-artifact`.

One pre-existing wobble is recorded here so it is visible, not fixed: ADR 0019
is still marked **Proposed** in `docs/adr/README.md` while its items are cited
as warrants by the `adr0019-*` corrections. The manifest cites the ADR file as
the settled reading regardless of its status marker, and this ADR follows that
usage; the status marker itself is a separate matter.

## Decision

**The pipeline reproduces the page. It may restructure; it may recover. It may
not reword. A wording divergence from the page is authorized only as an entry
in `data/corrections.json` — anywhere else it is a defect, not a design
choice.**

1. **What each stage may change:**

   | stage | may change | authority |
   |---|---|---|
   | `extract_office_styles.py` | drop running headers and page furniture; normalize whitespace; type lines | geometric — measure the page (#38, #39); a real header ends in a page number (#84) |
   | `extract_offices.py` | section, merge, group alternatives, reflow (litany adjudicated per break), dedup shared blocks | structural; shared dedup compares content equality, not shape (#87, #101); reflow from geometry with ambiguous breaks adjudicated (#39) |
   | `normalize_offices.py` | hoist shared blocks into `_shared`; unwrap single-element alternatives | structural only — no wording |
   | `apply_corrections.py` | any wording or structure change | only via `data/corrections.json`; `source` permitted (ADR 0005), vouching per ADR 0012 |
   | render | suppress (`SKIP_RUBRICS`, falsifiable per ADR 0013); author app text (register, sourced per ADR 0015) | ADR 0013, ADR 0015, ADR 0016, ADR 0019 |

2. **Every manifest entry names its warrant.** `validate_provenance` requires
   a `reason` on every entry, and an `adr` citing the ADR that settled it on
   every `upstream-review` entry — the source whose whole point is a review
   ruling. An `adr` value must resolve to a real ADR number in `docs/adr/`.
   The current manifest already satisfies all of this; the requirement guards
   drift, not today's data. `editorial` entries keep their `reason` as the
   warrant — no ADR is invented for orthography rulings that have none.

3. **The register stays at its endpoint.** `LITURGICAL_TEXT_REGISTER` holds
   only text with no page behind it, each entry carrying its source and
   warrant — the state ADR 0015's status records. App-authored text that
   merely restates a printed sentence is a wording divergence and belongs in
   the manifest as a correction on the extracted text, not in the register.

4. **`editorial` is not split.** All 11 entries are rulings with reasons;
   extraction cosmetics already route to `pdf-extraction-artifact`. The
   conflation #92 worried about is already prevented by the source enum.

5. **The operative consequence.** A divergence with no manifest entry is a
   defect, not a design choice — which is what `check_conservation.py` already
   enforces: a shipped line the page never printed, or a printed line that
   never ships, is UNACCOUNTED unless a manifest entry or a named rule covers
   it. This ADR makes the rule the conservation check implements into the
   governing statement, so a new divergence is classified by one question —
   *is it structural/recovery (pipeline's own business) or wording (must be in
   the manifest)?*

## Consequences

### Positive
- The question #92 asks has a direction test: restructuring and recovery are
  the pipeline's; rewording is the manifest's. A reviewer can classify any
  change immediately, which is what the extraction-diff workflow
  (`make extract-baseline` / `make extract-diff`) needs to mean anything.
- The warrant requirement closes the last unaudited gap: source + manifest =
  shipped, and every delta names its warrant. Enforcement is fail-closed and
  passes the committed manifest unchanged — no backfill, no invented ADR
  citations.
- The `adr`-resolution check makes a citation that cannot be followed fail
  loudly, the same way a `source` typo that drops the `pwc-errata-` prefix
  fails today (ADR 0012): an unchecked string cannot decide what a validator
  enforces.

### Negative
- The structural/wording line needs judgment at the margin — a hyphen at a PDF
  line wrap is recovery (the page's own artifact, not its text), while a
  hyphen the page deliberately prints is wording. The direction test handles
  both, but the classification is a human call per change, which is exactly
  the work a code review is for.
- `reason` is enforced for presence, not content — "fix", "tidy" passes.
  `PERMITTED_SOURCES` has the same shape (checked for presence and membership,
  not semantics), and the JSON Schema ADR 0005 promised is still unwritten;
  this ADR does not write it either.
- The `adr`-resolution check couples `validate_corrections.py` to
  `docs/adr/`. A renamed ADR file keeps its number, so the coupling survives
  renames; a renumbered one fails the run until the citing entry is updated,
  which is the point — a citation should break loudly, not silently dangle.

### Neutral / Notes
- Mechanism Q1 (the manifest carries all authorized divergences) is recorded
  as already achieved, not proposed: the four `upstream-review` entries and
  the single-entry register are the endpoint, and this ADR ratifies the state
  ADR 0015's status notes produced rather than re-deciding it.
- ADR 0019's Proposed status marker in the README is noted above, not changed.
- The `docs/errata/README.md` "Upstream review" table remains the human-facing
  account of what the upstream-review entries decided; this ADR governs the
  mechanism, not the record.
