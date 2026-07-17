# ADR 0004: Single rendering engine with HTML and text output modes

## Status
Proposed

## Context
The project has three consumers that render office form data:
- The browser SPA (`web/app.js`) — needs HTML with interactive alternatives tabs
- The CLI plain-text renderer (`cli/book.js`) — needs plain text for diffing,
  golden-file comparison, and structural test verification
- The test harness (`tools/test_full.js`, `tools/test_eval.js`) — needs
  structural verification of rendered output

These three consumers currently use two separate rendering implementations:
`web/render.js` produces HTML; `cli/book.js` implements text rendering from
scratch, duplicating the segment traversal, shared-block resolution,
alternatives grouping, rubric filtering, and response formatting. The test
harness tests the CLI's duplicated renderer — a different code path than
production users see. A rendering bug in one path passes the other path's tests.

## Decision
Extend `web/render.js` with a **text output mode** that shares the same segment
traversal logic as the HTML mode. All three consumers use the same module.

### API

The shared `walkSegments(segs, shared)` generator traverses segment trees
depth-first, resolving `_shared` references and recursing into `alternatives`
groups. Both the HTML renderer and the new text renderer consume this generator.

The text renderer adds three exports: `renderSegmentsText` (segments to
structured text blocks), `renderAlternativesText` (alternatives block as text),
and `blocksToString` (blocks joined with appropriate spacing). Format options
(`verse`, `showLabel`, `skipRubrics`, `skipShortLabels`, `condenseRubrics`,
`alleluia`) control book-mode vs app-mode presentation without duplicating
rendering code.

### Consumer changes
- **`cli/book.js`** — calls `renderSegmentsText` for each office section with
  book-mode options. Becomes thin orchestration (~80 lines).
- **`cli/office.js`** — calls `blocksToString(renderSegmentsText(...))` instead
  of stripping HTML from `renderSegments` output with a regex.
- **Tests** — `test_full.js` and `test_eval.js` call `renderSegmentsText`
  directly as an imported module, running in-process instead of spawning child
  processes.

### Testing strategy
The text renderer is tested by:
1. **Vitest unit tests** — call `renderSegmentsText` for each section type
   (opening responses, canticle, litany, dismissal) with known segment data
   and assert the text output matches expectations.
2. **Golden-file comparison** — `make check-book` diffs `cli/book.js` output
   (which uses `renderSegmentsText`) against PDF-derived golden files for all
   31 forms. This exercises the full rendering path with all options active.
3. **Structural smoke tests** — `make test-full` verifies that all 38 forms
   (31 seasonal + 7 Ordinary Time weekday variants) produce text containing the
   six canonical section headings.

Option combinations are covered by the golden-file tests: each of the 31 forms
exercises a realistic combination of `verse`, `showLabel`, `skipRubrics`, and
`skipShortLabels` as appropriate for its season and office type.

## Consequences

### Positive
- Single source of truth for all segment traversal and rendering logic.
- A rendering change applies to all three consumers.
- `cli/book.js` rendering is covered by Vitest unit tests via the shared module.
- `test_full.js` runs in-process, eliminating the memory cost of spawning child
  processes.

### Negative
- `render.js` grows to accommodate the text mode. The shared `walkSegments`
  generator and text renderer add approximately 150–200 lines.
- The text mode must agree with the HTML mode on structural decisions (which
  rubrics to suppress, how to label alternatives groups). These decisions are
  encoded in the options object rather than duplicated in code.
