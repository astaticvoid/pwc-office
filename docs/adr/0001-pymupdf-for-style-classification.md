# ADR 0001: Use PyMuPDF for PDF style classification

## Status
Proposed

## Context
The extraction pipeline must classify every text run in the source PDF as one
of: leader, response, rubric, heading, or footer. Classification depends on
five signals: font weight (bold vs roman), font style (italic), color (red for
rubrics), font size, and vertical position (headers and footers appear at
predictable y-coordinates).

Two tools provide access to this metadata:

- **pdfplumber** operates at the character level. Each glyph is a separate dict
  with `fontname`, `size`, color (RGB tuple), and position. Text runs must be
  reconstructed by grouping consecutive characters with matching (font, size,
  color) — requiring y-proximity bucketing, x-sorting within buckets, and space
  insertion between characters. Bold/italic detection parses the font name for
  substrings; rubric detection calibrates RGB ranges from observed values.

- **PyMuPDF (fitz)** provides pre-grouped span-level dicts via
  `get_text("dict")`. Each span represents adjacent characters with identical
  font properties: `{text, font, size, color (sRGB int), flags (bitmask), bbox}`.
  Bold is `flags & 16`, italic is `flags & 2`. Color is an exact sRGB integer.

A spike (2026-07-16) on advent-mp confirmed the span-level advantage: a single
8-page office form produces 11,070 individual glyph dicts from pdfplumber vs
360 pre-grouped spans from PyMuPDF — a 31× reduction in data units. The font
names from PyMuPDF are also cleaner: `Palatino-Bold` vs
`AJSWHC+Palatino-Bold` (no PDF subset prefix to strip).

On the PWC source PDF, the flags observed are `0x04` (serif, used for leader
text), `0x06` (italic + serif, used for rubric text), and `0x14` (bold + serif,
used for responses). The colors observed are `0x231F20` (near-black body text)
and `0xBC303A` (rubric red). All five classification signals are available as
direct property queries on the span dict — no grouping, substring matching, or
range calibration required.

## Decision
Use **PyMuPDF (fitz)** as the style classification tool in the extraction
pipeline. Text runs are obtained as pre-grouped spans with native bitmask flags
and exact sRGB color values.

The extraction tool pins PyMuPDF to a specific version in `requirements.txt`
to prevent silent breakage from API changes. The extraction manifest records
the PyMuPDF version alongside the pdftotext version.

## Consequences

### Positive
- No character-grouping logic — spans arrive pre-grouped by identical font
  properties, eliminating y-bucketing, x-sorting, and space-insertion code.
- Bold/italic classification is `flags & 16` / `flags & 2` — a bitmask check
  against the font descriptor, not a substring search of the font name.
- Rubric detection is an exact color comparison (`color == 0xBC303A`), not an
  RGB-range calibration that must be retuned per PDF edition.
- Font names omit the PDF subset prefix, simplifying downstream matching.

### Negative
- PyMuPDF is AGPL-licensed. The extraction scripts that `import fitz` carry an
  AGPL license. This is acceptable under the GPL FAQ's guidance that a program's
  output is not a derivative work of the program (the extraction scripts produce
  JSON; the JSON and all consuming code do not link to PyMuPDF). The extraction
  scripts live in a clearly-bounded directory with their own `LICENSE` file.

### Notes
- The extraction architecture separates style classification (this ADR) from
  text content (ADR 0002). PyMuPDF provides style; pdftotext provides text.
- If the AGPL license proves incompatible with a future deployment scenario,
  pdfplumber can be used as the style classifier. The two-pass architecture is
  tool-agnostic — only the style pass changes.
- A PyMuPDF API change could break the `get_text("dict")` output format.
  Pinning the version and recording it in the extraction manifest (alongside the
  pdftotext version) catches this at `make check-integrity` time.
