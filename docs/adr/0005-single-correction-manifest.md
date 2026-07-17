# ADR 0005: Single versioned manifest for all data corrections

## Status
Proposed

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
- `id` — unique identifier; maps to a BUGS.md entry or GitHub issue
- `source` — provenance: `"editorial"`, `"acc-csv-error"`, or `"pwc-pdf-error"`
- Target locator — varies by category. Office text uses `{office, field}`.
  Lectionary uses `{date, office, index}`. Psalter uses `{psalm, …}`.
  FATS uses `{saint, field}`.
- `old` — the value currently present in the data (validated before application)
- `new` — the value to apply

The full schema is defined in a JSON Schema file checked into the repository
alongside the manifest, not specified inline in this ADR.

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
