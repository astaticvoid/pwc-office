# ADR 0011: Single-pass fitz extraction; no independent casing oracle

## Status
Accepted

## Context

The original extractor used pdfplumber, which decodes this PDF's small-caps
font as lowercase — a real decoding bug. That justified a layer of manual
casing correction carried in `extract_offices.py`: `_fix_casing` force-
capitalised the first letter of every `response` segment (except a short
allowlist of continuation words), `_DIVINE_FIXES` restored ~14 divine titles
regex-by-regex, and `_TEXT_PATCHES` patched specific known-bad segments by
exact text match. `check_casing.py` was added later (Batch 19, per
`docs/ASSESSMENT-2026-07.md`) as an independent pdftotext-based oracle to
catch regressions in these corrections — at the time called *"the highest-
leverage quality tool available to this project."*

ADR 0001 replaced pdfplumber with PyMuPDF (fitz) for style classification.
ADR 0002 proposed going further — a two-pass architecture using `pdftotext`
for text content and fitz only for style — on the premise that "the current
extractor mis-decodes small-caps." ADR 0002 was never implemented (it stayed
Proposed). In practice, the extractor moved to single-pass fitz for both text
and style, but the pdfplumber-era correction layer (`_fix_casing`'s force-
capitalise, `_DIVINE_FIXES`, `_TEXT_PATCHES`) and the pdftotext oracle
(`check_casing.py`) were carried forward unquestioned — nobody had re-checked
whether fitz's own text decoding still needed them.

On 2026-07-26, while fixing an unrelated bug (an Invitatory Psalm heading), a
user-reported casing issue ("As it was..." should read "as it was...") led to
tracing `_fix_casing`. Rather than patch the one instance, the question was
asked: does fitz still have the small-caps decoding bug pdfplumber had? This
was checked directly — comparing fitz's *raw* per-span output (before any
correction runs) against the actual printed PDF page, rendered as a pixmap
image, not against another text-extraction tool. Findings, in the order they
surfaced:

1. `_fix_casing`'s force-capitalise step was wrong in ~60 places across the
   dataset — fitz already decoded these correctly (including genuine
   lowercase grammatical continuations, e.g. "...Holy Spirit: / as it was...
   Amen."), and the force-capitalise step was overriding the correct decode.
2. `check_casing.py` itself had a matching bug: it always compared a repeated
   string against its *first* occurrence in the PDF, so a responsory refrain
   repeated 4–5 times (correctly cased differently on each repeat by design)
   produced false "casing difference" reports against itself.
3. `_DIVINE_FIXES` and the remaining `_TEXT_PATCHES` entries were tested
   empirically: each rule's effect was disabled, the full 30-form extraction
   was re-run, and the output was byte-diffed against the baseline.
   `_DIVINE_FIXES` had exactly **one** live effect on the entire dataset — and
   it was wrong (forced "Creator" where the printed page genuinely reads
   lowercase "creator", a grammatical continuation). `_TEXT_PATCHES` had
   **zero** live effect — every remaining entry was already redundant with
   what fitz decodes on its own.

No decoding bug remains to correct, and the oracle that existed to catch one
found none once its own bug was fixed.

## Decision

Remove all casing-correction machinery that existed to compensate for
pdfplumber's small-caps decoding, now that fitz is proven not to need it:

- `_fix_casing`'s force-capitalise-every-response step, and the
  `_CONTINUATION_STARTS` allowlist it depended on.
- `_DIVINE_FIXES` (divine-title regex list).
- `_TEXT_PATCHES`, `_patch_segments`, `_apply_text_patches`.
- `check_casing.py` (the independent pdftotext oracle) — the one artifact
  ADR 0002 actually shipped — along with its `make check-casing` target and
  its `validate` dependency.
- The `pdftotext` version-tracking in `check_data_integrity.py` and
  `update_extract_manifest.py` (the extraction manifest no longer records a
  `pdftotext` field).
- Stale "uses pdftotext" documentation in `extract_collects.py` and ADRs
  0001/0002/0003 that described a dependency no longer used anywhere.

`_fix_casing` is not deleted — it retains the two corrections independently
verified as still necessary: recapitalising the start of a new sentence
inside a segment after `_merge()` joins originally-separate PDF lines with
`"\n"`, and fixing standalone lowercase `"i"` → `"I"`.

This formally settles ADR 0002. It never reached Accepted and its two-pass
architecture was never built; this ADR closes it with direct evidence
(fitz's raw decode matches the printed page) rather than a competing
proposal.

## Consequences

### Positive
- ~230 lines of dead-or-wrong correction code removed from
  `extract_offices.py` and `check_casing.py` combined.
- One fewer external dependency: `poppler-utils`/`pdftotext` is not required
  anywhere in the project now — nothing to install, nothing to keep two
  decoders in sync against.
- Data is more faithful to the printed source, not less: the one correction
  still doing something (`creator` → `Creator`) was wrong, and removing it
  fixed a real (if minor) divergence from the book.
- Simpler mental model going forward: fitz's decoded text is the text of
  record. There is no post-hoc casing-correction layer to reason about when
  debugging a casing question — check the PDF page directly.

### Negative
- No independent cross-check remains for fitz's text decoding. If a future
  PyMuPDF version, or a re-typeset PDF edition, introduces a font/glyph
  decoding regression, nothing in this pipeline will catch it automatically.
  `check_casing.py` was the only thing that could, even though — per the
  Context above — it wasn't catching anything real by the time it was
  removed.
- This is a deliberate, accepted trade-off, not an oversight. The
  alternative (keep the oracle as a low-cost, non-CI-gated safety net) was
  raised explicitly and rejected: the tool's near-zero real hit rate, plus
  its own two confirmed matching bugs found during this cleanup, weighed
  against keeping it.
- If a decoding regression is later suspected, there is no standing oracle
  to reach for. The recovery path is the same empirical method used here:
  disable the suspect correction, re-run extraction across all forms, diff
  against baseline, and render the actual PDF page as a pixmap to check any
  remaining live effect against the true printed text — not another
  text-extraction tool.

### Neutral / Notes
- The empirical method used to reach this decision — disable a correction,
  re-run the full extraction, diff against baseline, and verify any surviving
  effect against a rendered pixmap of the actual page — is reusable for
  auditing whether any future extraction "fix" is still earning its keep.
  Full trail recorded in `BUGS.md`, dated 2026-07-26.
- `docs/ASSESSMENT-2026-07.md` and `docs/CORRECTNESS.md` are historical audit
  records from when `check_casing.py` was introduced and still describe it
  as load-bearing; they are left unedited as a record of what was true when
  written, not updated to reflect this ADR.
