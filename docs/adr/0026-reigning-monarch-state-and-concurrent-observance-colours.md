# ADR 0026: Reigning monarch state and concurrent observance colours

## Status
Proposed (2026-09-08)

Amends ADR 0017 (secondary observances extraction) and ADR 0018 (observance identity and marker presentation).

## Context

An audit of the Daily Office on 2026-09-08 (Tuesday in Ordinary Time, Proper 23) revealed two interrelated defects in liturgical fidelity (ADR 0016) and data synchronization:

1. **Cross-edition monarch drift:**
   - The 1985 Book of Alternative Services (`sources/BAS.pdf`, p. 677, Prayer 8) was compiled under Queen Elizabeth II:
     *"For the Queen: Almighty God, fountain of all goodness, bless our Sovereign Lady, Queen Elizabeth, and all who are in authority under her..."*
   - The 2024 Daily Office booklet (`sources/pray-without-ceasing.pdf`) was updated under King Charles III, printing *"May Charles our King..."* (Tuesday MP) and *"Strengthen Charles our King..."* (Saturday MP).
   - The 2026 Lectionary (`sources/bas_short_2026.csv`) explicitly directs:
     `Coll 378 or Coll 8, 677 (The King) (Mem: 403 or FAS 273)`
     and commemorates `Accession Day of HM King Charles III (Green)`.
   - In Canadian Anglican canon law, prayers for the Sovereign are adapted by ecclesiastical authority upon the demise of the Crown (substituting names, titles, styles, and pronouns) without reprinting the 1985 BAS.
   - However, our extraction pipeline extracted BAS p. 677 verbatim into `data/collects.json` without adaptation. Furthermore, `web/render.js:collectSecondaryPage()` stripped `(The King)` from the collect citation. As a result, on Accession Day 2026, the app presented a collect tab labelled **"For the Queen"** praying for Queen Elizabeth.

2. **Suppression of secondary observance titles and colours (ADR 0016 violation):**
   - In `sources/bas_short_2026.csv`, Column 1 names:
     `Nativity of the Blessed Virgin Mary - Mem (White)<br>Accession Day of HM King Charles III (Green)<br>Season of Creation`
   - `tools/convert_lectionary.py` parsed line 2 via a generic regex into the tag `accession_day`, and `web/render.js:dayMarkers()` mapped it to the static label `"Accession Day"`.
   - This dropped the authorized title `"of HM King Charles III"` and discarded the explicit colour `(Green)`.
   - A similar pattern affects other civil/national days with independent colours:
     - Victoria Day: `Victoria Day [Monarch’s Official Birthday] (White)` vs. `Feria (Green)`
     - Remembrance Day: `Remembrance Day (Violet or Black)` vs. `Martin, Bishop of Tours - Mem (White)`
     - Thanksgiving Day: `Thanksgiving Day (White)` vs. `Feria (Green)`
   - The primary day's colour chip (`White`) misrepresents the concurrent national observance (`Green`), while suppressing the observance's stated colour and full title leaves the reader uninformed.

## Decision

### 1. Centralized Reigning Monarch State (`data/monarch.json`)

A single, committed configuration file `data/monarch.json` defines the reigning sovereign:
```json
{
  "title": "King",
  "name": "Charles",
  "regnal_name": "HM King Charles III",
  "style": "our Sovereign Lord, King Charles",
  "pronouns": {
    "subject": "he",
    "object": "him",
    "possessive": "his"
  },
  "collect_title": "For the King"
}
```
- `data/monarch.json` is committed and tracked in `tools/update_extract_manifest.py` under `EXTRACTION_SOURCES`.
- **Collect 677 adaptation:** `tools/extract_collects.py` adapts Prayer 8 on BAS p. 677 using `monarch.json`. The name is set to `monarch.collect_title` (`"For the King"`), and the body text substitutes the monarch's style and pronouns. This aligns with the lectionary's explicit direction `Coll 8, 677 (The King)`.
- **Collect tab display:** When `web/app.js` renders the Occasional Prayer tab for Collect 677, it uses `occCollect.name` (now `"For the King"`).

### 2. Full Extraction of Secondary Observance Titles (No Suppression)

- `tools/convert_lectionary.py` preserves the specific authorized text of secondary observances rather than reducing them to generic tags.
- In `day.observances`, entries that carry specific designations (such as Accession Day or Victoria Day) are preserved with their full extracted title and declared colour:
  ```json
  "observances": [
    {
      "tag": "accession_day",
      "name": "Accession Day of HM King Charles III",
      "colour": "Green"
    },
    "season_of_creation"
  ]
  ```
  (Simple vocabulary tags without specialized text or colour remain strings for backwards compatibility).

### 3. Presentation of Concurrent Observance Colours

Where a calendar day carries concurrent observances with differing colours:
- **The primary colour chip and rank chip** in `#day-meta` represent the **primary office being kept** (e.g. `White` for *Nativity of the Blessed Virgin Mary*).
- **Secondary observance marker chips** (`.meta-item--marker`) carry their own colour identity directly on the chip:
  - If a secondary observance specifies a colour (e.g. `Green`), the marker chip renders with an inline mini colour swatch or parenthetical colour indicator:
    `Accession Day of HM King Charles III (Green)`
  - This prevents conflating distinct liturgical rites into the primary colour chip while fully rendering the authorized calendar data.

## Consequences

### Positive
- **Liturgical truthfulness:** Prayers for the Sovereign reflect the living Canadian rite as directed by Church authority and the 2026 lectionary.
- **Single point of change for adapted text:** When the Crown passes, updating `data/monarch.json` adapts Collect 677 in one place. Lectionary CSVs govern accession day calendar titles as published by the ACC, while Daily Office booklet text reflects print edition conservation.
- **Fidelity to the source (ADR 0016):** Full titles ("of HM King Charles III", "[Monarch's Official Birthday]") and explicit colours ("Green", "Violet or Black", "White or Gold") are no longer deleted during extraction.
- **Clarity on multiple colours:** The primary colour worn for the office is unambiguous, while secondary observances display their own distinct liturgical colour.

### Negative
- `day.observances` evolves from a purely flat `string[]` to supporting structured entries `(string | { tag, name, colour })[]`. Both `web/render.js` and TypeScript types must accommodate this union.
- `tools/extract_collects.py` diverges from verbatim 1985 text for Collect 677, requiring explicit documentation of canonical provenance.

### Neutral / Notes
- `pray-without-ceasing.pdf` (2024) already prints "Charles" and "King", so `offices.json` remains in complete conservation compliance with the 2024 Daily Office print edition.
- For Days where an alternate office reading track exists (transferable feasts), ADR 0018's interactive toggle continues to switch the entire day's primary identity.
