# PWC — UX Audit

_Last updated: 2026-06-13. Redesign complete as of 2026-06-10._

---

## Status summary

All P0–P1 UX issues resolved. The nav redesign (settings bottom sheet, MP/EP row, observance card) and book mode were fully implemented before the Synod review on 10 June 2026.

| ID | Category | Severity | Status |
|----|----------|----------|--------|
| Nav crush | Nav | P0 | ✅ Fixed 2026-06-06 — observance row separated |
| UX-01 | Nav | P2 | ✅ Moot — observance is now a content card, not a nav element |
| UX-02 | Nav | P2 | ✅ Fixed 2026-06-06 — separate observance row with independent collapse |
| UX-03 | Nav | P3 | ✅ Fixed — settings sheet has labelled "Translation" row |
| UX-04 | Nav | P2 | ✅ Partial — title attr added; calendar icon in nav |
| UX-05 | Nav | P2 | ✅ Fixed then revised — Today button added, then replaced by calendar icon jump-to-today |
| UX-06 | Nav | P3 | 🔲 Open — keyboard shortcuts undiscoverable; no `?` panel |
| UX-07 | Chrome | P2 | ✅ Fixed — evaluation banner uses localStorage (one-time dismiss) |
| UX-08 | Content | P1 | ✅ Fixed 2026-06-06 — inline "[KJV — NRSVUE unavailable]" fallback note |
| UX-09 | Content | P2 | ✅ Fixed 2026-06-07 — O Antiphons render as liturgical block with accent border |
| UX-10 | Content | P1 | ✅ Fixed 2026-06-06 — friendly out-of-range message |
| UX-11 | Content | P3 | ✅ Fixed — canticle tab labels truncated at 22 chars with full name in title |
| UX-12 | Content | P3 | ✅ Fixed — day notes have "Read more" expand button |
| UX-13 | Content | P3 | ✅ Fixed — colour chip shows ↺ indicator on cyclic days |
| UX-14 | Content | P3 | ✅ Fixed 2026-06-06 — form title suppressed on ordinary-time forms |
| UX-15 | A11y | P2 | 🔲 Open — alt-tabs lack role="tab", aria-selected, arrow-key navigation |
| UX-16 | A11y | P2 | ✅ Fixed — psalm verse numbers have aria-hidden="true" |
| UX-17 | A11y | P3 | 🔲 Future — lang attribute for Latin psalm titles; defer to French BAS work |

---

## Open items detail

### UX-06: Keyboard shortcut hints (P3)

Keyboard shortcuts (← → days, m/e office, b book mode, t today) are undiscoverable. No help panel, no title attributes on nav arrows beyond what's already there.

**Suggested fix:** `?` key opens a small modal or inline panel listing shortcuts. Or add `title` attr to MP/EP buttons and nav arrows with key hint.

### UX-15: ARIA tab roles (P2)

The alternatives tabs (canticles, doxology, affirmation) are `<button>` elements in a `.alt-tabs` container. They lack `role="tab"`, `aria-selected`, `aria-controls`. Keyboard users Tab to each button individually instead of using arrow keys within the group.

**Fix spec:** Add `role="tablist"` to `.alt-tabs`; `role="tab"` + `aria-selected` + `aria-controls="alt-panel-{n}"` to each `.alt-tab`; `role="tabpanel"` + `id="alt-panel-{n}"` to each `.alt-panel`. Implement left/right arrow key navigation within the tablist (focus moves, does not activate). This is a pure JS/HTML change — no data or CSS changes needed.

_File:_ `web/app.js` (`renderAlternatives` function)
