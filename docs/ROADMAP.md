# PWC — Roadmap

_Last updated: 2026-07-11_

---

## 1. Completed

### §1.1 — Core data pipeline (done)
- PDF extraction → `offices.json`, `psalter.json`, `collects.json`
- CSV conversion → `data/lectionary/YYYY-MM.json`
- Integrity manifest + `make check-integrity` gate
- `make check-text`, `make check-casing` quality oracles
- RCL Daily extraction pipeline (Nov 2026 forward)

### §1.2 — Web SPA (done)
- Vanilla JS SPA with routing, season-aware form selection
- NRSVUE Scripture fetching (API.Bible, lazy cached)
- Alternatives tabs, dark mode, print mode, book mode
- Responsive CSS with mobile breakpoints

### §1.3 — Node CLI (done)
- `cli/book.js` — book-mode plain-text renderer (31/31 forms passing `make check-book`)
- `cli/office.js` — debug renderer

### §1.4 — Testing (done)
- Vitest (117) + pytest (173) = 290 unit tests
- Playwright E2E (104 passed, 0 failed)
- `make test-full`, `make test-smoke`, `make test-seasonal`

### §1.5 — Correctness (done)
- 36 bugs closed; 0 open (BUGS.md)
- Casing oracle, column-wrap detector, line-break oracle
- 9 Batch-18 field-trial fixes deployed

---

## 2. In progress

### §2.1 — Mobile: Capacitor native shell → store submission
The Capacitor shell is committed (`ios/`, `android/`) and syncing (`make mobile-sync`). It is a pure webview wrapper with zero native integrations. The ACC's stated prime desire is a mobile app. See `docs/HANDOFF.md` — Batch 21 for the full two-stage spec.

**Stage 1 — Platform readiness** (est. 1 session)
Fix build issues, wire up Capacitor native plugins, add safe-area CSS and mobile-responsive refinements, integrate offline detection.

**Stage 2 — Store submission** (est. 1 session, blocked on ACC rights + Apple/Google accounts)
Branded app icons and splash screens, store metadata, signing, TestFlight/Play Internal Track beta distribution.

---

## 3. Planned

### §3.1 — RCL Daily UI integration (Nov 2026)
Extraction pipeline is complete (13 months, Nov 2026 forward). UI scaffolding exists behind `FEATURE_RCL_DAILY = false`. Flip to `true` when the data window opens and wire up the preference picker.

### §3.2 — Bishop name substitution
The `N` placeholder (italicised by Batch 18 Fix H) should accept a user-entered diocesan bishop name via settings. Parked in ASSESSMENT §6.

### §3.3 — 2027 lectionary data
Routine data update when ACC publishes 2027 lectionary CSVs. Not a bug (BUG-06 cleaned). `make fetch-sources && make extract`.

### §3.4 — Service worker PWA caching (post-store)
After the kill-switch SW is retired, evaluate SW caching for offline Scripture support. Not now — SW caching caused deploy issues (BUG-22) and the kill-switch is a cleanup tool, not an app feature.

---

## 4. Parked (owner decision needed)

### §4.1 — FATS minor-feast readings
Phase 1 (bio + collect fallback) is complete. FATS readings are Eucharistic propers — not suitable for Daily Office. Parked per ASSESSMENT §6.

### §4.2 — General propers surface
Should days with full Eucharistic propers show more than the collect? Parked per ASSESSMENT §6.

### §4.3 — BAS extension
Additional office forms, collects, canticles from the BAS. Requires re-running extraction against the BAS PDF. Parked per DESIGN §9.

### §4.4 — ACC copyright licence
ACC is obtaining rights to distribute copyrighted texts in the app. Until granted, `data/` stays gitignored and beta distribution stays within the Synod evaluation group.

---

## 5. Mobile milestones

### §5.1 — Shell committed (done, 2026-06)
Capacitor iOS + Android projects exist and sync. `make mobile-sync` works. Icons and splash are Capacitor defaults. Package ID: `ca.pwcoffice.dailyoffice`.

### §5.2 — Build fixes + plugin baseline (Stage 1)
Fix Android `colors.xml` build-blocker. Install and wire core Capacitor plugins: status-bar, splash-screen, keyboard, app (back-button), preferences (storage), browser (external links), network (offline detection). Add safe-area CSS.

### §5.3 — Branding + store prep (Stage 2)
Generate branded app icons (all sizes for both platforms). Branded splash screens. App Store Connect / Google Play Console setup. Store metadata. Signing. Beta distribution via TestFlight / Play Internal Track.

### §5.4 — Post-store polish (future)
Push notifications (daily office reminder — needs Firebase setup). Widget (today's office at a glance). Watch companion. `@capacitor/haptics` for tab/response feedback.
