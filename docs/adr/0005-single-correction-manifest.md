# ADR 0005: Single versioned manifest for all data corrections

## Status
Accepted (implemented 2026-07-27)

Corrected (2026-08-10): ADR 0017 replaced `convert_lectionary.py`'s
hand-transcribed `OBSERVANCES` dict with real extraction from the CSV name
column. The decision recorded here is unchanged — observances still get no
`corrections.json` category, because they remain classification output rather
than a correction of a wrong value.

## Context
The extraction pipeline must correct errors in upstream data sources. Corrected
data spans multiple types: office text (PDF extraction artifacts, editorial
fixes), lectionary data (CSV formatting errors from the ACC source, missing
semicolons, truncated names, misclassified ranks and colours), psalter text
(missing verses from page-break artifacts), and saint biographies (truncated
names).

Each correction must record the value it expects to find (`old`) and the value
to apply (`new`). When an upstream source fixes its own error, the stale
correction must be detected — silently skipping a correction that is no longer
needed can leave incorrect data in place if the upstream fix differs from the
correction target.

Currently, corrections are distributed across multiple files and data structures:
Python dicts in extraction scripts, a separate `patches.json` mechanism, and
embedded fixup lists. This distribution creates ambiguity about where a given
correction belongs.

## Decision
All data corrections live in a **single versioned JSON manifest**:
`data/corrections.json`. This file is the authoritative place for all
corrections applied to extracted data. It supersedes all previously distributed
correction mechanisms, which are removed as part of the implementation.

### Manifest structure
Corrections are organized by data type as top-level keys. Each entry carries:
- `id` — unique identifier; maps to a GitHub issue
- `source` — provenance; see "The `source` enum" below for the current values
- Target locator — varies by category. Office text uses `{office, field}`.
  Lectionary uses `{date, office, index}`. Psalter uses `{psalm, …}`.
  FATS uses `{saint, field}`.
- `old` — the value currently present in the data (validated before application)
- `new` — the value to apply

The full schema is defined in a JSON Schema file checked into the repository
alongside the manifest, not specified inline in this ADR.

**Correction (2026-08-07): that file was never written.** See the note on
`source` at the end of this ADR — the enum is now enforced in code rather than
in a schema, and this paragraph describes an artifact that does not exist.

### Tooling
Two tools operate on this manifest:

- **`validate_corrections.py`** — dry-run: for every entry, navigates to the
  target location and compares the `old` value. Reports mismatches. Exits 1 if
  any correction is stale (upstream fixed the error, making `old` no longer
  present).
- **`apply_corrections.py`** — applies all validated corrections to the target
  data files in-place.

### Pipeline order
```
extraction → normalization → validate_corrections → apply_corrections
→ update_extract_manifest
```

The validation step before application catches stale corrections before they
are applied to (or silently skipped against) new data.

### Relationship to integrity checks and version control
`data/corrections.json` lives in `data/` because it is part of the data
pipeline's configuration, not the extraction tools' source code. The integrity
check (`make check-integrity`) records its hash in the extraction manifest
alongside the data files, so any manual edit to corrections is detected.

`data/corrections.json` must be committed to version control. It is added to
the `.gitignore` exceptions alongside `data/patches.json` (which it supersedes)
and `data/translations/kjv/`. Without version control, the correction manifest
cannot be audited, rolled back, or reviewed alongside extraction changes.

### Transition from existing mechanisms
This manifest supersedes all previously distributed correction mechanisms:
`_TEXT_PATCHES` in `extract_offices.py`, fix dicts in `convert_lectionary.py`
(`LESSON_FIXES`, `NAME_FIXES`, `RANK_FIXES`, `COLOUR_FIXES`, `CLEAR_NOTES`,
`NOTE_TYPES`), `data/patches.json`, `psalter_corrections.py`, and FATS
`NAME_FIXES`. These are removed as part of the implementation. The AGENTS.md
correction table is updated to point to the single manifest.

## Consequences

### Positive
- **One file to consult** when investigating a data issue. No ambiguity about
  which mechanism to use.
- **Provenance tracking** — the `source` field distinguishes upstream errors
  from editorial corrections, enabling automated stale-correction detection.
- **`id` field** enables bidirectional traceability between corrections and the
  bug tracker.
- The manifest is a single validation target; no duplicated validation logic.

### Negative
- A single larger JSON file rather than corrections co-located with each
  extractor. The tradeoff is discoverability (one file to search) vs locality
  (corrections near the code that processes them). We choose discoverability
  because corrections are investigated by data content, not by extractor.
- Migrating existing corrections from their current distributed locations is a
  one-time step.

## Implementation notes (2026-07-27)

This ADR sat as Proposed for a long time: `data/corrections.json` and its
validators existed, and `office_text`/`lectionary_citations` were wired into
`apply_corrections.py`, but `psalter`/`fats`/`lectionary_names`/
`lectionary_ranks`/`lectionary_colours`/`lectionary_notes` were declared in
the schema and checked by `validate_corrections.py` yet never actually
*applied* by anything — the corresponding hardcoded dicts in
`extract_psalter.py`, `extract_fats.py`, and `convert_lectionary.py` kept
doing the real work independently, silently drifting from the manifest.
This was found and finished during a follow-up audit (the same one that
produced the canticle/litany/collects fixes in #11, #9, and #10),
prompted by the user asking to push data-correction cleanup as far as it
would go.

One concrete bug this closed: `extract_psalter.py`'s hardcoded Ps 35 v25 fix
matched a prefix (`\xa0`/`\n` immediately before "Do") that never actually
occurred in the real text (the verse starts with a verse number, "25 Do let
them say..."), so despite `source_corrections` claiming it was fixed, the
verse was shipping with "not" still missing — reversing the petition's
meaning — because nothing in the pipeline ever exercised the corresponding
(correct, already-declared) `corrections.json` entry either. Wiring up
`apply_corrections.py`'s psalter handler fixed it as a direct side effect.

What was actually migrated: `NAME_FIXES`/`_TEXT_FIXES` in `extract_fats.py`
(found to have zero live effect — removed rather than migrated),
`_fix_casing`'s two remaining rules and `extract_collects.py`'s redundant
`_clean()` regex (same: zero live effect, removed), and all of
`convert_lectionary.py`'s `LESSON_FIXES`/`NAME_FIXES`/`RANK_FIXES`/
`COLOUR_FIXES`/`CLEAR_NOTES` (all live — migrated to `lectionary_lessons`/
`lectionary_names`/`lectionary_ranks`/`lectionary_colours`/`lectionary_notes`,
verified byte-identical output against baseline aside from the Ps 35 fix
above). `data/patches.json` (referenced nowhere except a stale error-message
string) was deleted outright — its 7 entries all targeted a `subtitle` field
no current office even populates anymore, so there was nothing left to
migrate.

`psalter_corrections.py`, named in the original decision above, never
existed as a separate file — the psalter one-offs were always inline in
`extract_psalter.py`; that's what got migrated.

`convert_lectionary.py`'s `NOTE_TYPES` (72 entries) and `OBSERVANCES` (175
entries) were deliberately **not** migrated despite being named in the
original decision (`NOTE_TYPES`) or living in the same file (`OBSERVANCES`).
Both are substantive project-authored classification/annotation data with no
"old" value the CSV got wrong — there's nothing to record `source`/`old`/`new`
provenance against, and `corrections.json`'s schema doesn't fit data that
isn't a correction of something. `_fix_shared_affirmation` in
`extract_offices.py` (one office_text-shaped fix, but nested inside a shared
block the `office_text` category's `{office, field}` locator can't reach)
was evaluated and deliberately left as code for the same reason: not enough
of a pattern yet to justify a new correction category for one instance.

## The `source` enum (2026-08-07)

The decision above names three values — `editorial`, `acc-csv-error`,
`pwc-pdf-error` — and defers the rest to a JSON Schema that was never written.
The field grew to six without amendment, and nothing checked it.

That stopped being cosmetic when ADR 0012 made `source` load-bearing: the QA
rules decide which corrections may vouch for a deliberate line break by testing
for a `pwc-errata-` prefix. A typo that keeps the prefix vouches for a break
nobody sanctioned; one that loses it silently withdraws an exemption, and the
break it covered is reported as a column wrap by a rule that feeds the deploy
gate. An unchecked string cannot decide what a validator enforces.

The permitted values now live in `PERMITTED_SOURCES` in
`validate_corrections.py`, each with a sentence saying when to reach for it, and
are enforced there for every category — along with `id` being present and unique,
which this ADR requires but nothing verified either:

| value | meaning |
|---|---|
| `editorial` | a project editorial decision, no upstream error behind it |
| `acc-csv-error` | an error in the ACC lectionary CSV |
| `pwc-pdf-error` | an error in the printed *Pray Without Ceasing* PDF |
| `pdf-extraction-artifact` | an artifact of extraction, not a defect in the source |
| `pwc-errata-ordinary` | the errata for Ordinary Time |
| `pwc-errata-seasonal` | the errata for the seasonal offices |

Code rather than a JSON Schema file because the constraint that matters is a
coupling between two other tools, and it belongs where the reason for it can be
written down. Adding a value is a reviewable edit next to that explanation;
adding one beginning `pwc-errata-` grants the power to exempt a line break.
