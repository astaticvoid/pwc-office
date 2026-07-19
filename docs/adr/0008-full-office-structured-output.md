# ADR 0008: Full-office structured output for validators

## Status
Proposed

## Context

Liturgical validators (`validate_office.cjs`, `audit_office.cjs`) currently
consume `segmentsToJSON(form, shared)` — a function that walks the static
office form data from `offices.json` and produces a flat array of `{section,
type, text}` tuples. This gives validators the form template but **not the
assembled office** that a worshipper sees.

The full office is dynamically assembled in `web/app.js:render()` (lines
1050–1147). It combines the static form with:
- Psalms from the lectionary (`officeData.psalms`)
- Readings from the lectionary (`officeData.lessons`)
- The psalm doxology/Gloria (`shared.doxology`)
- Collect resolution (BAS ref, inline day propers, Occasional Prayer alternates,
  FATS fallback)
- Seasonal collect week-index filtering
- Observance toggling (primary vs. alternate)
- Section visibility decisions (Ordinary Time title suppression, EP light section)

Validators that only see `segmentsToJSON` output cannot detect errors in any of
these dynamic layers. A form that passes all 6 current rules can still render
incorrectly because the lectionary data is wrong.

### Alternatives considered

**A. Collector pattern on `renderSegments`.** Pass an optional accumulator array
to `renderSegments` that collects structured data alongside HTML generation.

*Rejected:* Couples the HTML rendering path to the JSON validation path.
Refactoring the HTML renderer could break validation output. The HTML renderer
is browser code; the collector would complicate its API for a Node-only concern.

**B. Parse the rendered HTML with a DOM parser.** Extract structured data from
the assembled HTML output using something like jsdom or cheerio.

*Rejected:* Fragile — depends on CSS class names, DOM structure. Changes to
layout (adding a `<div>` wrapper, reordering elements) would break validators
without affecting liturgical correctness. Also adds a heavy dependency.

**C. Separate assembly path producing JSON.** Implement a function that
independently assembles the same office sections as `app.js:render()` but
produces structured JSON instead of HTML. Shares `walkSegments` for static
segment traversal but independently handles dynamic data assembly.

*Selected.*

## Decision

Add `renderOfficeJSON(cfg)` to `web/render.js`. This function is a **parallel
assembly path** — it mirrors the section orchestration in `web/app.js:render()`
but produces a typed JSON object (`OfficeJSON`) instead of an HTML string.

### Why a parallel path?

The assembly logic in `render()` totals approximately 320 lines spread across
the top-level render function and its helpers (`proclamationHtml`, `psalmHtml`,
`collectToggleHtml`, `gloriaHtml`, `renderObservanceCard`). This logic is
orthogonal to HTML generation — it decides *what* to render, not *how*. The
JSON path makes the same decisions but emits data instead of markup.

The static segment traversal uses the existing `walkSegments` generator, so
the only duplicated logic is the section-ordering and dynamic-data-resolution
code (~200 lines for JSON output).

### What `renderOfficeJSON` does

- Receives a config object: `{ form, shared, officeData, officeType, season, weekIdx, fatsEntry, collects, collectRef, collectInline }`
- Resolves all the same decisions as `app.js:render()`:
  - Observance selection (primary data)
  - Seasonal collect filtering by week-index
  - Psalm set resolution (psalms vs. psalm_sets)
  - Collect resolution chain (BAS ref → inline → Occasional Prayer → FATS fallback)
  - Form title visibility (seasonal vs. Ordinary Time)
  - Doxology insertion after psalms
  - Reading response presence after each lesson
  - Section ordering: Gathering → Proclamation → Affirmation → Prayers → Sending
- Produces `OfficeJSON` — a typed object with sections, subsections, segment
  arrays, and dynamic metadata (see `docs/qa-strategy-spec.md` for full schema).
- Does **not** load psalter text or scripture text. Psalm
  citations and reading citations are captured as references.

### What `renderOfficeJSON` does NOT change

- `web/app.js` — untouched, continues rendering HTML as before.
- `web/render.js` existing exports (`renderSegments`, `walkSegments`,
  `segmentsToJSON`, `renderSegmentsText`, `blocksToString`) — untouched.
- `cli/book.js`, `cli/office.js` — untouched.
- Browser bundle — `renderOfficeJSON` compiles fine in browser context (no DOM
  deps) but is not called there. Modern bundlers tree-shake unused exports.
function.

## Consequences

### Positive

- Validators see the same assembled office that the browser renders. Dynamic
  errors (wrong psalm, missing doxology, unresolvable collect, incorrect
  week-index) become detectable.
- Existing code paths are entirely unchanged. The JSON path is additive.
- `walkSegments` is shared; static form traversal has no duplication.
- Typed JSON output enables rule authoring with autocomplete-aware tools.

### Negative

- ~200 lines of section assembly logic are duplicated between `app.js:render()`
  and `renderOfficeJSON`. If the assembly order changes in app.js, the JSON
  path must be updated in lockstep.
- `renderOfficeJSON` lives in `render.js` (shared browser+Node module) but is
  Node-only in practice. If tree-shaking fails, unused code ships in the SPA
  bundle. Acceptable risk: no DOM or network dependencies.
- Validators must load `offices.json` in addition to receiving `OfficeJSON` for
  form-level metadata (e.g., `form.title`, `form.seasonal_collects.length`) not
  captured in the output.

### Synchronization test

A Vitest test renders the same office via both paths and asserts:

1. Section labels in `OfficeJSON` match `<h2>`/`<h3>` headings in HTML output.
2. Segment counts per section match between paths.
3. Dynamic fields (`psalmDoxology`, `readingResponse`, `collect.ref`) are
   populated when the HTML path would include them.

This catches drift between app.js rendering and `renderOfficeJSON` assembly.

### Duplication and future deduplication

The parallel path creates ~200 lines of duplicated assembly logic. This is the
primary negative consequence of this decision. A future refactor could extract
a shared `assembleSections()` function from `renderOfficeJSON` and have both
`render()` and `renderOfficeJSON` call it, eliminating the duplication. The
sync test makes this refactor safe — it passes before and after, guaranteeing
no behavioral change. See `docs/qa-strategy-spec.md` for the full implementation
plan.
