# Remaining QA Gaps — Specifications

## 1. Rendered DOM Validation

### Gap
The sync test in `tests/unit/render.test.js` verifies one form (`ordinary-sunday-mp`).
No automated check that all 30 forms render correctly in the browser or that
the HTML output matches the structured JSON output across all forms.

The `compare_staging.cjs` tool diffs staging-vs-production DOM but is ad-hoc
and date-specific.

### Proposal: `tools/validate_render.cjs`

A new tool that loads each form, assembles it via `renderOfficeJSON`, renders
each section via `renderSegments`, and verifies:

1. **Section presence** — every section in `officeJSON` produces non-empty HTML
2. **Segment count parity** — HTML paragraph count matches JSON segment count
   (within tolerance for Amen splitting)
3. **Heading hierarchy** — `<h2>` count matches top-level section count,
   `<h3>` matches subsection count
4. **No empty liturgy divs** — `<div class="liturgy">` never contains only
   whitespace
5. **No broken alternatives** — every alternatives section has at least one
   group with non-empty segments

Runs on all 30 forms via `segmentsToJSON` (static, fast). Optionally uses
`renderOfficeJSON` with lectionary data for the same 15-date fixture.

**Cost:** ~80 lines. No new dependencies. `walkSegments` + `renderSegments`
already available.

**CI integration:** `make validate-render` added to `make qa`.

---

## 2. Accessibility Audit

### Gap
No automated checks for:
- Heading hierarchy (no skipped levels: `<h2>` must not appear before `<h1>`)
- Color contrast ratios (liturgical colors against background)
- ARIA labels on interactive elements (tabs, observance toggles)
- Keyboard navigation for tab controls
- Text size legibility at mobile breakpoints

### Proposal: `tools/audit_a11y.cjs`

A static analysis tool running without a browser:

1. **Heading hierarchy** — parse rendered HTML for each form, verify no skipped
   levels. Assert: every `<h3>` has a preceding `<h2>`, no `<h4>` without `<h3>`.
2. **Contrast check** — load `web/office.css`, parse `var(--color-*)` values
   from the computed `:root` theme, compute WCAG AA ratios for text-on-background.
   Check liturgical colors (--color-day) against both light and dark themes.
3. **Tab accessibility** — verify every `.alt-tab` button has `aria-selected`,
   `aria-controls`, `role="tab"`. Verify every `.alt-panel` has `role="tabpanel"`,
   `aria-labelledby`.
4. **Interactive element labeling** — all buttons have discernible text or
   `aria-label`. All `[data-key]` elements have corresponding `role` attributes.

**Cost:** ~60 lines. Parse CSS for color values, parse HTML strings for
attribute presence. No browser needed.

**CI integration:** `make audit-a11y` runs standalone (not gating `make test`).

---

## 3. Responsive Layout Checks

### Gap
No automated verification that the app renders legibly at mobile breakpoints.
Playwright E2E tests exist but are not run in CI (need browser).

### Proposal: `tests/e2e/responsive.spec.js`

New Playwright test that runs in existing `test-web` target:

1. **Viewport independence** — render 4 representative forms at 3 viewports
   (320px, 768px, 1280px), verify no horizontal overflow
2. **Font scaling** — verify `--font-size` CSS variable changes propagate
   to all text elements
3. **Tab wrapping** — verify alternatives tabs do not overflow on mobile;
   the slimmer `alt-tab--slim` variant activates correctly

**Cost:** ~40 lines. Reuses existing Playwright infrastructure.

**CI integration:** Not in CI (needs browser). `make test-web` runs locally.

---

## 4. Cross-Form Text Comparison

### Gap
The audit tool checks structural metrics (segment counts). It does not check
text content consistency — e.g., the dismissal blessing in two adjacent
ordinary-weekday forms should be identical text, but if one has an extraction
artifact the other doesn't, no tool catches it.

### Proposal: `tools/audit_text.cjs`

A new tool that compares text content across peer groups:

1. **Duplicate detection** — within each peer group, compare leader/response
   text for shared subsections (dismissal, litany, opening_responses).
   Text that appears identically in 80%+ of peers but differs in one form
   signals an extraction artifact.
2. **Length outlier** — same as above but for text length
   (z-score on character count per subsection)
3. **Missing sections** — detect if a section present in all peer forms is
   missing from one (more specific than the existing `required-sections` rule)

**Cost:** ~60 lines. Uses `segmentsToJSON` output, grouped by peer category.

**CI integration:** `make audit-text` runs standalone (advisory, not gating).

---

## Integration Plan

| Tool | CI Gate? | Phase |
|------|----------|-------|
| `tools/validate_render.cjs` | Yes — `make qa` | Phase 1 |
| `tools/audit_a11y.cjs` | No — advisory | Phase 2 |
| `tests/e2e/responsive.spec.js` | No — local only | Phase 3 |
| `tools/audit_text.cjs` | No — advisory | Phase 2 |

## Implementation Priority

1. **Rendered DOM validation** — highest value, catches real bugs before deploy
2. **Cross-form text comparison** — catches extraction artifacts the normalizer missed
3. **Accessibility audit** — correctness for screen readers, legally important
4. **Responsive layout** — nice to have, covered by manual testing
