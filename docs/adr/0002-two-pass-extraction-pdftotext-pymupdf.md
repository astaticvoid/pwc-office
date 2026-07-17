# ADR 0002: Use pdftotext for text content; separate text from style

## Status
Proposed

## Context
A PDF extraction pipeline must produce two things from each source page: the
**text** (what the words say, including correct casing and paragraph breaks)
and the **style** (which words are bold, italic, red, rubric, etc.).

These two outputs have different correctness requirements:
- **Text** requires accurate Unicode mapping, correct casing of small-caps fonts
  (which encode capitals as lowercase glyphs — the extractor must recover the
  intended case), and preservation of intentional line and paragraph breaks as
  laid out by the typesetter.
- **Style** requires reliable access to the PDF's font descriptors: bold/italic
  flags, color values, and font size.

No single extractor is best at both. The project's `check_casing.py` script
already uses pdftotext as a ground-truth oracle for casing because the current
extractor mis-decodes small-caps. Conversely, pdftotext provides no style
information. A single-tool approach forces compromises: the extractor either
gets correct text with no style data, or correct style data with incorrect text
that must be post-corrected.

## Decision
Separate text extraction from style extraction in a **two-pass architecture**:

1. **Text pass** — `pdftotext -layout` produces canonical prose with correct
   casing, paragraph boundaries, and line breaks. This is the text-of-record for
   the extraction pipeline.

2. **Style pass** — PyMuPDF (ADR 0001) produces typed text runs with position
   and bounding box: `[(type, text, bbox), ...]`.

3. **Alignment pass** (`align_extraction.py`) — assigns the correct type to each
   pdftotext paragraph by matching it against the PyMuPDF typed runs.

### Alignment strategy

The alignment uses two signals, both required for a match:

- **Text similarity**: the pdftotext paragraph and the PyMuPDF text runs
  covering the same content must match via `difflib.SequenceMatcher` on
  Unicode-normalized (NFC), whitespace-collapsed text with a minimum similarity
  ratio. The starting threshold is 0.85, tuned during implementation by running
  the alignment against all 38 form variants (31 seasonal + 7 Ordinary Time
  weekday variants) and measuring the distribution of observed ratios on
  correctly-matched paragraphs. The threshold should be set to reject known
  false positives (liturgically distinct but lexically similar phrases, e.g.
  differing versicles-and-responses) while accepting the normal range of
  character-level variance from the two extraction tools.
- **Positional proximity**: the PyMuPDF runs must fall within the same vertical
  band as the pdftotext paragraph (their bounding boxes must overlap in y).

When SequenceMatcher produces multiple candidate matches for a paragraph (as
can happen with repetitive liturgical text — repeated responses, refrains), the
positional constraint breaks the tie: only runs whose bounding boxes overlap the
paragraph's y-range are considered.

Paragagraphs that fail to achieve the similarity threshold, or whose matched
runs fall outside the positional band, generate a warning and are emitted as
untyped (`type: "unknown"`) for human review. This is a **fail-visible**
strategy: the pipeline does not silently assign a wrong type to liturgical text.

### Casing

pdftotext provides the canonical casing. The editorial choice to capitalize the
first word of response segments (where the printed book keeps grammatical
continuations lowercase after a colon) is made in the renderer (ADR 0004), not
in the extraction pipeline. The data stores the text as it appears in the PDF;
the renderer applies display conventions.

## Consequences

### Positive
- Casing errors from small-caps decoding are eliminated at the text source.
  pdftotext has the best-tested Unicode mapping pipeline in open source.
- `check_casing.py` now agrees with the text source by construction (both use
  pdftotext). It is retained as a regression guard.
- Paragraph and line breaks are the typesetter's breaks, not a heuristic
  reconstruction.
- The text source and the style classifier are independently swappable.

### Negative
- The alignment step is the novel part of this architecture. The dual-signal
  strategy (text + position) is designed to handle repetitive liturgical text,
  but it requires testing against all 31 forms and all 7 Ordinary Time weekday
  variants (38 forms total) to validate the similarity threshold and
  positional-banding logic.
- Unicode normalization (NFC) and whitespace collapsing must be applied
  consistently in both the alignment pass and the text source to prevent false
  mismatches from invisible character differences (ligatures, non-breaking
  spaces, soft hyphens).
- pdftotext has its own artifacts (ligature decomposition, page-break hyphenation,
  running-header text). These artifacts are different from the previous tool's
  artifacts; they are handled in the alignment pass rather than in post-hoc
  text patches.

### Notes
- The two passes operate on the same page range, identified by the content-based
  page detection (ADR 0003).
- The alignment pass replaces the text-reconstruction code in the old single-pass
  extractor. Structural post-processing (`_group_alternatives`,
  `_fold_berakah_blessings`, `_split_lords_prayer`, etc.) is unchanged — it
  operates on the already-typed segments regardless of how they were produced.
