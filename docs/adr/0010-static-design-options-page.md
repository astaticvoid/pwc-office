# ADR 0010: Static design-options page for visual decision-making

## Status
Proposed

## Context

The visual design of the PWC Office app evolves through iteration. Changes to
typography, layout, and interactive controls need to be evaluated across
viewport widths before committing to code. Previously, design exploration
happened by editing `web/office.css` on a branch and loading the app — a
slow feedback loop that mixed design drafts with functional code.

We need a lightweight way to:

1. Prototype a visual change in isolation (one component, multiple variants)
2. View each variant at both desktop (58rem) and mobile (390px) widths
   side by side
3. Share the page via a static URL (no build, no JS, no server)
4. Make design decisions before touching the production CSS

## Decision

Create a **static design-options page** — a self-contained HTML file that
renders multiple design variants in a vertical stack, each with desktop and
mobile containers. The page uses the same CSS custom properties (colors,
fonts, tokens) as the production `web/office.css` via an inline `<style>`
block, but has zero dependencies on the application code.

### Format

- **File**: `design/OPTION-NAME.html` (e.g. `design/mp-ep-toggle.html`)
- **Layout**: Each variant gets a `<section class="option">` containing one
  "Desktop (58rem)" and one "Mobile (390px)" mockup, each wrapped in a
  dashed-border container matching the production content width.
- **No JavaScript**: All variants are static HTML. Interactive states
  (hover, active) are shown via CSS classes applied to the mockups.
- **Inline CSS**: All styles are in the `<style>` block — the page works
  offline and has no build step.

### When to use

- Proposing a visual change to any UI element (nav, header, toggle,
  reading blocks, section headings, collect cards)
- Comparing multiple design options before converging
- Getting design feedback from someone who can't run the dev server

### When NOT to use

- Changes that affect data rendering logic (use the real app)
- Changes that require dynamic state (e.g. date navigation, lectionary
  lookup)
- Trivial one-property tweaks (just edit `office.css`)

### Workflow

1. Branch from `main` (or `design-exploration`)
2. Create `design/FEATURE.html` with the variants under consideration
3. Open in a browser to review; iterate
4. Once a direction is chosen, implement the real CSS change on the branch
5. Delete the design page before merging (it served its purpose)

## Consequences

### Positive
- Design iteration is decoupled from application code
- Desktop and mobile variants are visible in a single glance
- The page can be opened directly from the file system (`open design/foo.html`)
- No risk of design-draft CSS leaking into production stylesheets

### Negative
- Requires maintaining CSS tokens in the design page (copy of `:root` from
  `office.css`). If tokens change, the design page can drift — but since
  it's a temporary artifact, this is acceptable.
- Cannot test interactive behavior (JS-based state changes). For that,
  the `_design-toggle.js` pattern (live DOM manipulation via URL params)
  remains available as a secondary tool.

### Neutral / Notes
- The existing `_design-toggle.js` script (live A/B on the real app) is a
  complementary tool for testing interactive behavior. The static page is
  for visual comparison only.
- Design pages are throwaway by design — they document the decision
  process during review and are deleted once the direction is settled.
