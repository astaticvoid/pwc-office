# ADR 0025: Backend-For-Frontend (BFF) Lectionary API and Licensing Constraints

## Status
Accepted

## Context
Historically, the client app shipped with the full year's lectionary calendar (`data/lectionary/*.json`) and a bundled public domain Bible (KJV). It resolved the liturgical day locally, then requested the appointed NRSVue scripture from the API (ADR 0023, ADR 0024).

Recent negotiations with NRSVue rights management yielded strict licensing constraints that require us to tightly control the distribution and retention of the text:
1. **Scope:** NRSVue text is strictly for appointed Daily Office lectionary readings. Psalms are excluded.
2. **Temporal Window:** Users may view readings within approximately **±30 days** of the current date.
3. **Storage & Caching:** Text may be stored on the server and locally cached on devices *only as reasonably necessary* for offline functionality, and must expire/purge outside the window.
4. **Feature Restrictions:** No search, copy, download, print, export, or share functionality.
5. **No AI:** No AI or AI-assisted use of the text.
6. **Distribution:** The app must remain free of charge.

Additionally, managing bundled lectionary updates requires mobile app store releases. By shifting to a "thin client" / Backend-For-Frontend (BFF) model, we can address both the licensing constraints and the update cycle simultaneously. 

## Decision
We will transition the architecture to a **Unified BFF API** that serves both the lectionary calendar and the appointed scripture in a single payload.

### 1. Unified Slicer (Build Time)
The build pipeline (`make extract`) will iterate over the calendar and slice a unified JSON object for each day, containing both the calendar variables (colors, proper collects, lesson citations) and the raw scripture verses. 
The mobile and web clients will **no longer bundle** the lectionary calendar or the KJV text. 

### 2. Batch Edge API (`/api/v2/calendar`)
The CloudFront edge function will expose a `v2` endpoint capable of resolving unified calendar days.
- It will support a `?start=YYYY-MM-DD&end=YYYY-MM-DD` query to allow the client to pre-fetch a batch.
- **Licensing Gate:** If a requested date falls inside the ±30 day window, the payload includes the **NRSVue** text.
- **Fallback:** If a requested date falls outside the window, the API still returns the calendar payload, but gracefully substitutes the **KJV** scripture.

### 3. Client Responsibilities & UX
The client remains responsible for assembling and rendering the Office structure (`offices.json` remains bundled).
- **Offline Cache:** The client will pre-fetch a rolling window (e.g., today + 14 days) and store it in IndexedDB/Local Storage.
- **Cache Purge:** The client must actively purge any cached NRSVue payloads older than 30 days to strictly comply with the license.
- **Error States:** 
  - If a user navigates to an un-cached date while offline, the UI will display a "Network connection required" error.
  - If a user navigates outside the ±30-day window, the UI will display an informational notice that KJV is being shown due to licensing limits.

## Consequences

### Positive
- Total bundle size shrinks significantly (lectionary and KJV removed).
- Calendar bugs or lectionary updates can be shipped immediately via the web/API without Apple/Google app store review.
- The KJV API fallback perfectly handles the ±30 day limit without outright breaking the app for distant dates.
- Strict and transparent compliance with NRSVue licensing rules.

### Negative
- **Airplane Mode Degradation:** An empty cache + no network connection renders the app completely unable to load the Office (previously, the bundled KJV would work).
- **API Complexity:** The CloudFront edge function must handle translation fallback and batch aggregation.

### Neutral / Notes
- The client retains `offices.json` (the templates) and `psalter.json`. The BFF supplies the "variables" (the propers, readings, and calendar).
