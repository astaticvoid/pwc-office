# PWC — UX Audit

_Last updated: 2026-06-06 (5 more fixed in session 2)_

---

## Nav crush on alternate-observance days (fixed)

**What happened.** The nav-bottom row was a two-column flex layout: `#nav-office` (flex: 1) containing Morning + Evening + the `#nav-observance` div, and `.nav-controls` (flex: 1) containing the translation picker and icon buttons. On days with an alternate observance, `#nav-observance` added two more buttons into the already-full `#nav-office` half. On today (6 June 2026, "Eve of Corpus Christi"), the four items — Morning, Evening, Primary, Eve of Corpus Christi — exceeded the ~168px half-width on mobile. `overflow: hidden` on `.nav-bottom` (required for the compact-scroll animation) silently clipped the overflow rather than wrapping.

**Fix applied (2026-06-06).** Moved `#nav-observance` out of `#nav-office` into a separate `.nav-observance-row` — a new third row in the nav, shown only on days with an alternate (class `nav-obs-active`). The row has the same collapse transition as `.nav-bottom` and is hidden on compact-scroll. On desktop (≥820px) it appears as a full-width centered row below the main nav bar, which the box-shadow accent line frames cleanly.

**Files changed:** `web/index.html`, `web/app.js`, `web/office.css`

---

## Open UX gaps

### Nav & chrome

**UX-01: No semantic separation between time-of-day and observance selection**  
Morning/Evening (time of day) and Primary/Alternate (which observance's readings to show) are different categories of choice but look visually identical in the nav. A user might not understand why there are four buttons, or which pair controls what.  
_Suggested fix:_ Add a thin vertical rule between the time buttons and observance buttons on desktop. On mobile (new third row), the separate row already provides visual separation — add a subtle label like "Observance:" in muted text before the buttons.

**UX-02: Compact nav hides the observance row when scrolling**  
When the user scrolls down and the nav collapses, the observance toggle disappears. On a long office with two observances (e.g., a saint's day), the user has no way to switch observance without scrolling back up.  
_Suggested fix:_ Keep the observance row visible in compact mode (don't collapse it), OR make it sticky at the very bottom of the compact nav. Since the compact nav is `overflow: hidden` only on `.nav-bottom`, the observance row (now separate) could stay visible with a simpler rule.

**UX-03: Translation selector has no label**  
The `<select>` shows "NRSVUE" or "KJV" with no surrounding label. First-time users may not know it's a Bible translation picker.  
_Suggested fix:_ Add a short label "Bible:" before the select on desktop. On mobile, the aria-label is sufficient for screen readers but a tooltip title would help sighted users.

**UX-04: Date picker interaction is invisible**  
The date is shown with a dotted underline (subtle) and tapping it opens the native date picker via a zero-opacity overlay. No visual affordance suggests it's interactive — a user following the arrows might never discover they can jump directly to a date.  
_Suggested fix:_ Add a small calendar icon (✦ or 📅) beside the date, or change the cursor to `pointer` on hover.

**UX-05: "Today" link only accessible via the brand logo or 't' keyboard shortcut**  
When navigated away from today, the only way back is clicking the brand logo (not obviously a link to today) or pressing 't' (undiscoverable). The nav arrows have no "jump to today" action.  
_Suggested fix:_ Add a "Today" button that appears when `state.date !== todayStr()`. Could replace one of the nav arrows on mobile when active, or appear as a small link between the arrows.

**UX-06: No keyboard shortcut hints visible anywhere**  
Arrow keys navigate days, m/e switch office, t goes to today. None of these are discoverable without reading source code or documentation.  
_Suggested fix:_ Add a `?` keyboard shortcut that shows a brief shortcuts panel (modal or inline). Or add `title` attributes to the nav arrows ("← Previous day [←]").

### Content & rendering

**UX-07: Evaluation banner dismisses per-session, not permanently**  
The banner uses `sessionStorage`, so it reappears every browser session. For trusted evaluators this is friction; for a production app it needs to be removed entirely.  
_Suggested fix:_ Either remove the banner (production), or switch to `localStorage` with a long TTL so it only shows once.

**UX-08: Silent fallback from NRSVUE to KJV**  
If the NRSVUE API fails or the book is unavailable, `fillScripture` silently falls back to KJV. The translation attribution at the bottom of the page still shows the originally selected translation. The user may read KJV text thinking it's NRSVUE.  
_Suggested fix:_ When the fallback is used, update the attribution per-reading (inline, e.g., "[KJV — NRSVUE unavailable]") rather than only at page bottom.

**UX-09: O Antiphons and liturgical notes look like editorial asides**  
The O Antiphons (Advent, Dec 17–23) are significant liturgical forms, but they render as plain small italic text — the same style as a pastoral note. They deserve prominent display.  
_Suggested fix:_ Render `o_antiphon` notes in a distinct block: display the antiphon text in the liturgy font at reading size, with a label "O Antiphon for [date]".

**UX-10: Day with no lectionary data shows raw error message**  
If `fetchDay()` throws (404 for a date not in the data), the user sees `<p class="error-msg">Failed to load: …</p>`. For dates at the boundary of coverage (late Dec 2026), this looks like a broken app.  
_Suggested fix:_ Detect the out-of-range case before fetching and show a friendly message: "Daily Office readings for [date] are not yet available. Coverage extends through [boundsMax]."

**UX-11: Long canticle tab labels overflow their containers**  
Canticle tabs show the full canticle name as a tab button — names like "Song of Jerusalem Our Mother" or "Song of the Heavenly City" are long. With multiple tabs side by side, they overflow or force the `.alt-tabs` container to wrap awkwardly.  
_Suggested fix:_ Truncate canticle labels to ~20 characters in the tab with the full name as `title` attribute. Or display only the key word (e.g., "Zechariah" instead of "Song of Zechariah").

**UX-12: Collapsible day notes have no visual affordance**  
Notes longer than 100 characters are truncated with "…" and a `▸` chevron suffix. The chevron is rendered via CSS `::after` content, very small and low-contrast. Users who don't notice it miss the full note.  
_Suggested fix:_ Make the "Read more" affordance explicit: replace the `▸` with a styled `[more]` link, or add a distinct "expand" button below the note.

**UX-13: Colour chip cycle has no instruction**  
On multi-colour days ("White or Red"), the liturgical colour chip is a button that cycles through options on click. The only hint is `title="Tap to cycle colour options"` — invisible on mobile (no hover). No visual treatment distinguishes a clickable chip from a static one.  
_Suggested fix:_ Add a small `↺` icon or dashed border to the cyclic chip, distinct from the static chip style.

**UX-14: Form title and subtitle are redundant with the day header**  
The content area opens with `<p class="form-title">Ordinary Saturday Morning Prayer</p>` immediately below the `<h1>` day title. On most days, this is obvious from context. The form title's main value is showing which seasonal form is in use (e.g., "Advent Morning Prayer").  
_Suggested fix:_ Suppress the form title on ordinary-time forms (it adds no information). Show it only for seasonal forms where the name is liturgically significant. Or relocate it into the day-meta row as a small label.

### Accessibility

**UX-15: Alt-tab keyboard navigation not fully implemented**  
The alternatives tabs (canticles, doxology, affirmation) are `<button>` elements in a tab list, but they don't have `role="tab"`, `aria-selected`, or `aria-controls`. Keyboard users navigating with Tab will land on each button individually rather than using arrow keys to move between tabs in a group.  
_Suggested fix:_ Add `role="tablist"` to `.alt-tabs`, `role="tab"` + `aria-selected` + `aria-controls` to each `.alt-tab`, and `role="tabpanel"` to each `.alt-panel`. Implement arrow-key navigation within the tablist.

**UX-16: Psalm verse numbers are not `aria-hidden`**  
Verse numbers in `.verse-num` are decorative from a reading perspective — a screen reader would say "3 Then God said…" when "Then God said…" is correct. The number is already visually presented.  
_Suggested fix:_ Add `aria-hidden="true"` to `.verse-num` elements.

**UX-17: No `lang` attribute differentiation for liturgical Latin or French content**  
The app currently serves only English, but some titles include Latin (psalm Latin titles) and any future French BAS support would need this.  
_Note:_ Low priority for now; tag when French support is planned.

---

## Summary table

| ID | Category | Severity | Status |
|----|----------|----------|--------|
| Nav crush | Nav | P0 | **Fixed 2026-06-06** |
| UX-01 | Nav | P2 | Open |
| UX-02 | Nav | P2 | **Fixed 2026-06-06** |
| UX-03 | Nav | P3 | Open |
| UX-04 | Nav | P2 | **Partial** (title attr added) |
| UX-05 | Nav | P2 | **Fixed 2026-06-06** |
| UX-06 | Nav | P3 | Open |
| UX-07 | Chrome | P2 | Open |
| UX-08 | Content | P1 | **Fixed 2026-06-06** |
| UX-09 | Content | P2 | Open |
| UX-10 | Content | P1 | **Fixed 2026-06-06** |
| UX-11 | Content | P3 | Open |
| UX-12 | Content | P3 | Open |
| UX-13 | Content | P3 | Open |
| UX-14 | Content | P3 | **Fixed 2026-06-06** |
| UX-15 | A11y | P2 | Open |
| UX-16 | A11y | P2 | Open |
| UX-17 | A11y | P3 | Open |
