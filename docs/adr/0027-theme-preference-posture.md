# ADR 0027: Theme Preference Posture — Auto by Default with Explicit Overrides

## Status
Accepted

## Context
Liturgical prayer takes place across widely varied physical and environmental contexts:
- Morning Prayer typically in daylight, office, or church environments.
- Evening Prayer and Compline often at dusk, in dimly lit rooms, or at bedside before sleep.

Previously, the app used an implicit binary toggle button in the Settings sheet:
- Unconfigured installations fell back to `window.matchMedia('(prefers-color-scheme: dark)')`.
- However, as soon as a reader toggled the theme once, an absolute `'light'` or `'dark'` key was written to `localStorage['pwc-theme']`.
- There was no mechanism for the user to return to automatic, system-directed scheduling once an override had been touched.

## Decision
1. **Default Posture:** The app defaults to **Auto (System)**. When no manual override is selected, the application listens dynamically to OS color scheme transitions (`matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)`), immediately matching the device's daylight/evening schedules.
2. **Tri-State Control:** The Settings sheet exposes an explicit 3-way segmented control: `Auto | Light | Dark`.
3. **Persistence Semantics:**
   - `Auto`: `localStorage.removeItem('pwc-theme')`. The DOM attribute `data-theme` mirrors the live OS query.
   - `Light`: `localStorage.setItem('pwc-theme', 'light')`. The DOM attribute `data-theme` is set to `"light"`.
   - `Dark`: `localStorage.setItem('pwc-theme', 'dark')`. The DOM attribute `data-theme` is set to `"dark"`.
4. **Native Shell Coordination:** When running within native Capacitor shells (iOS/Android), the system status bar background color updates synchronously with the resolved theme state (`#15382A` for light mode, `#1C1A17` for dark mode). Because both themes employ dark navigation headers, the status bar content style is set to light icons (`Style.Dark` in Capacitor's inverted nomenclature) to preserve WCAG AA contrast.

## Consequences
- Readers who prefer printed paper appearance (cream/warm-white) at all hours can lock `Light`.
- Readers who pray in dark environments can lock `Dark`.
- All other readers naturally receive day-to-night transitions matching their operating system without friction.
