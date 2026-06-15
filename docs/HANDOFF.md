# PWC — Handoff

_Updated: 2026-06-14_

Active handoff between Cowork (planning) and Claude Code (implementation). Cowork writes specs here; Code implements in order.

---

## Ready for Cowork review — Batch 11 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-c46c42f1`).

### What to spot-check

**BUG-23 — Seasonal EP opening responses restored**

- `http://localhost:8081/#/2025-12-03/ep` (Advent EP) — "Introductory Responses" subsection must appear under "The Gathering of the Community"
- `http://localhost:8081/#/2026-02-25/ep` (Lent EP) — same, Introductory Responses visible
- `http://localhost:8081/#/2026-05-20/ep` (Pentecost EP) — same
- `node cli/office.js ep 2025-12-03` — "## Opening Responses" section present in CLI output

**BUG-24 — CLI feast-day morning psalms**

- `node cli/office.js mp 2026-06-11` (Saint Barnabas — a feast with `psalm_sets`) — "## Psalm" line shows psalm citations, not "[object Object]" or empty

**Tests**

- `make test` — should pass: 108 Vitest + 143 pytest + Go
- New Vitest describe `all forms: shared-ref fields render non-empty HTML` — 62 tests covering `opening_responses` and `reading_response` for all 31 forms
- New pytest `test_opening_responses_resolves` — 31 parametrized cases, all passing

---

## Batch 11 — BUG-23 + BUG-24 hot-fix — Done

**BUG-23 (P0):** All 7 seasonal EP forms (`advent-ep` through `pentecost-ep`) silently drop Opening Responses. BUG-14 moved `opening_responses` to a shared ref dict; `app.js` line ~919 checks `.length` on it → undefined → section skipped. Same failure mode as BUG-19.

### Commit 1: Fix shared-ref resolution for `opening_responses` — `web/app.js` + `cli/office.js`

**`web/app.js`** — find the opening_responses block (~line 919):

```js
// Before:
if (form.opening_responses && form.opening_responses.length)
  html += renderSubsection('Introductory Responses', form.opening_responses, shared);

// After:
let openingResponses = form.opening_responses;
if (openingResponses?.type === 'shared' && shared)
  openingResponses = shared[openingResponses.key];
if (openingResponses && openingResponses.length)
  html += renderSubsection('Introductory Responses', openingResponses, shared);
```

**`cli/office.js`** — update the `section()` helper to resolve shared refs:

```js
// Before:
function section(title, segs) {
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}

// After:
function section(title, segs) {
  if (segs?.type === 'shared' && shared) segs = shared[segs.key];
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}
```

**Commit message:** `fix(ui): resolve shared ref for opening_responses in seasonal EP — BUG-23`

---

### Commit 2: Fix CLI psalm_sets fallback — `cli/office.js` (BUG-24)

Feast days store morning psalms as `psalm_sets` (array of arrays) not `psalms`. Update the psalm rendering line:

```js
// Before:
if (officeData?.psalms) out += `\n## Psalm\n${officeData.psalms.join(', ')}\n`;

// After:
const psalms = officeData?.psalms ?? officeData?.psalm_sets?.[0];
if (psalms) out += `\n## Psalm\n${(Array.isArray(psalms[0]) ? psalms[0] : psalms).map(p => typeof p === 'object' ? p.citation : p).join(', ')}\n`;
```

**Commit message:** `fix(cli): fall back to psalm_sets[0] for feast-day morning psalms — BUG-24`

---

### Commit 3: Add render-level Vitest test — `tests/unit/render.test.js`

The existing form-completeness test accepted shared refs as valid data without verifying the rendering code handles them. Add a render-level test for every field that can be a shared ref:

```js
describe('all forms: shared-ref fields render non-empty HTML', () => {
  test.each(forms)('%s opening_responses', (name, form) => {
    let or = form.opening_responses;
    if (or?.type === 'shared') or = shared[or.key];
    const html = renderSubsection('Introductory Responses', or, shared);
    expect(html, `${name} opening_responses rendered empty`).toBeTruthy();
  });

  test.each(forms)('%s reading_response', (name, form) => {
    // lessonHtml already tested elsewhere but confirm shared ref resolves
    let rr = form.reading_response;
    if (rr?.type === 'shared') rr = shared[rr.key];
    expect(Array.isArray(rr) ? rr.length : rr?.groups?.length,
      `${name} reading_response resolves to empty`).toBeGreaterThan(0);
  });
});
```

**Rule going forward:** any field that can hold a shared ref needs a render-level test, not just a data-structure check.

**Commit message:** `test(unit): render-level tests for shared-ref fields — catches BUG-23 class`

---

### Commit 4: Add regression test to `tools/tests/test_form_completeness.py`

Add a test that catches shared refs that fail to resolve:

```python
@pytest.mark.parametrize('name,form', forms)
def test_opening_responses_resolves(name, form):
    or_val = form.get('opening_responses')
    if isinstance(or_val, dict):
        assert or_val.get('type') == 'shared', f'{name}.opening_responses has unexpected dict type'
        key = or_val.get('key')
        assert key in shared, f'{name}.opening_responses refs missing shared key: {key}'
        assert isinstance(shared[key], list) and len(shared[key]) > 0, \
            f'{name}.opening_responses shared[{key!r}] is empty or not a list'
    else:
        assert isinstance(or_val, list) and len(or_val) > 0, \
            f'{name}.opening_responses must be non-empty list, got {type(or_val).__name__}'
```

Also add `shared` to the module-level setup:
```python
shared = offices.get('_shared', {})
```

**Commit message:** `test(tools): assert opening_responses resolves — catches BUG-23 class`

---

## Ready for Cowork review — Batch 10 + BUG-21 + BUG-14 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-4d284323`).

### What to spot-check

**Batch 10 — SW hot-fix**

- `http://localhost:8081/sw.js` — confirm `skipWaiting` is gone and `'/'` is not in the SHELL array
- `http://localhost:8081/` — app loads normally; no JS errors in console
- Check that the SW registers (DevTools → Application → Service Workers): status should be "activated and running" after page load
- On a second visit (no `?reset`), confirm the app still loads (not a blank page)

**BUG-21 — CLI field names fixed**

- `node cli/office.js mp 2026-06-17` — should show `## Psalm` and `## Lesson 1` / `## Lesson 2` sections with reading heading ("The Reading: …") and reading response (I / II / III tabs)
- `node cli/office.js ep 2026-06-17` — same structure for EP

**BUG-14 — EP opening_responses deduplicated**

- `make check-integrity` passes (already confirmed)
- `node cli/office.js ep 2025-12-03` (Advent EP) — confirm office renders; opening responses shown
- In offices.json `_shared`, confirm key `opening_responses_ep_seasonal` now exists with the 7 identical EP forms sharing it; advent-ep through pentecost-ep all reference it; allsaints-ep still has its own inline array

---

## Batch 10 — SW hot-fix (P0, deploy broken) — Done

**Deploy is currently broken.** Users who had the site open before the June 14 deploy see a blank "Loading…" page. Only `?reset` recovers them. Future deploys will reproduce this unless fixed.

### Root cause

`self.skipWaiting()` in `sw.js` causes the new SW to activate immediately, bypassing the normal wait-for-tabs-close lifecycle. During its `install` event, the new SW runs `addAll([..., '/', ...])` — fetching and caching `index.html` from the CloudFront edge. CloudFront invalidation takes 30–60+ seconds to propagate; during that window, the edge may still serve the **old** `index.html` (without `type="module"`). The new SW caches this stale HTML.

Once cached:
1. `clients.claim()` fires → `controllerchange` → `location.reload()`
2. Reload: new SW serves `'/'` from its cache → **old index.html** (no `type="module"`)
3. Old index.html loads `app.js` as a classic script
4. New `app.js` has `import { … } from './render.js'` at line 3 → `SyntaxError` in classic-script context
5. JS execution halts before the `controllerchange` listener is registered
6. Page stays in the initial "Loading…" DOM state forever
7. Refreshing makes it worse: SW keeps serving the stale cached `index.html`

### Fix (2 commits)

#### Commit 1: Remove `skipWaiting`, remove `'/'` from precache — `web/sw.js`

Replace entire `sw.js` with:

```js
'use strict';

const CACHE = 'pwc-v1'; // make build stamps this with a content hash

// Shell files cached on install. index.html ('/')  is intentionally excluded —
// it must always be fetched from the network so a stale CF edge never poisons
// the SW cache with an old HTML structure (e.g. missing type="module").
const SHELL = [
  '/app.js',
  '/render.js',
  '/office.css',
  '/manifest.json',
  '/data/offices.json',
  '/data/collects.json',
  '/data/season_bounds.json',
  '/data/psalter.json',
  '/data/fats/saints.json',
];

self.addEventListener('install', evt => {
  evt.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(SHELL))
  );
  // No self.skipWaiting() — new SW waits until all tabs running the old SW
  // are closed. This prevents the stale-HTML / module-import race on deploy.
});

self.addEventListener('activate', evt => {
  evt.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', evt => {
  if (evt.request.method !== 'GET') return;
  const url = new URL(evt.request.url);
  if (url.origin !== location.origin) return;

  // Never intercept index.html — let the browser fetch it fresh every time.
  if (url.pathname === '/' || url.pathname === '/index.html') return;

  // Everything else: network-first with cache fallback (offline support).
  evt.respondWith(networkFirst(evt.request));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached ?? new Response('Offline', { status: 503 });
  }
}
```

**Commit message:** `fix(sw): remove skipWaiting and '/' from precache — prevents blank page on deploy`

---

#### Commit 2: Remove `controllerchange` → reload hack from `app.js`

In `web/app.js`, find the SW registration block (around line 1349):

```js
// Before:
if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  navigator.serviceWorker.addEventListener('controllerchange', () => location.reload());
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// After:
if ('serviceWorker' in navigator && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}
```

The `controllerchange` reload was compensating for `skipWaiting`. Without `skipWaiting`, the new SW never takes over a live page mid-session, so the reload is both unnecessary and harmful (could cause reload loops if `controllerchange` fires at other times).

**Commit message:** `fix(ui): remove controllerchange reload — was compensating for skipWaiting`

---

### How to reproduce the old bug (for verification)

Before fixing, to confirm the bug:
1. Temporarily add `// location.hostname !== 'localhost' &&` to disable the localhost SW guard
2. `make build && make serve-dist` → visit `localhost:8081`, confirm SW registers
3. Make any trivial change (e.g. add a comment to `app.js`), rebuild → new cache hash
4. Refresh `localhost:8081` without doing `?reset` → blank "Loading…" page
5. Revert the localhost guard change

After fixing, steps 3–4 should show the old (working) version rather than blank page. Users see last-known-good content until they close all tabs and reopen.

### Post-deploy recovery for stuck users

Stuck users need `?reset`. The escape hatch (`/?reset`) already exists and works. No changes needed. Update help text or add a visible link in the error state if desired.

---

## Code work queue

Do in this order. Do not skip ahead.

| Batch | What | Status |
|-------|------|--------|
| **11** | BUG-23 + BUG-24 — seasonal EP opening responses + CLI psalm_sets | **Ready for Code** |
| **10** | SW hot-fix — blank page on deploy | Done |
| **7** | BUG-19 critical fix — reading response + Lord's Prayer + Go CLI | Done |
| **8** | JS render module + Node CLI + Vitest | Done |
| **9** | Rubrics redesign | Done |

---

## Ready for Cowork review — Batches 7 + 8 + 9 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-7740deb7`).

### What to spot-check

**Batch 7 — BUG-19 reading response + Lord's Prayer fix**

- `http://localhost:8081/#/2026-06-17/mp` (ordinary-time, Wednesday)
  - ✓ Reading response tab strip (I / II / III) appears after each lesson
  - ✓ "The Lord's Prayer" subsection visible in the Prayers section
- `http://localhost:8081/#/2026-02-25/mp` (Lent, seasonal)
  - ✓ Reading response tabs present after lesson
- Go CLI no longer crashes: `node cli/office.js mp 2026-06-17`

**Batch 8 — render.js module + Node CLI + Vitest**

- `http://localhost:8081/render.js` — served (should not 404)
- `http://localhost:8081/#/2026-05-17/mp` (Seventh Sunday of Easter)
  - ✓ App loads normally — no JS errors in console
  - ✓ All tabs, alternatives, readings render as before
- `http://localhost:8081/#/2026-06-17/ep` (ordinary-time EP)
  - ✓ Phos hilaron, canticle, readings all render
- Node CLI: `node cli/office.js ep 2026-02-25` should print Lent EP in plain text
- `make test` passes (vitest 48 + pytest 113 + Go)

**Batch 9 — Rubrics redesign**

- `http://localhost:8081/#/2026-06-17/mp` (ordinary-time, Wednesday)
  - ✓ "The Responsory is said or sung." rubric is suppressed
  - ✓ "The Litany is said or sung." rubric is suppressed
  - ✓ Intercessions block replaced with single italic line: "Offer intercessions, petitions, and thanksgivings, silently or aloud."
- `http://localhost:8081/#/2026-06-17/ep` (ordinary-time, Wednesday EP)
  - ✓ Same intercessions condensing visible
- `http://localhost:8081/#/2025-12-03/mp` (Advent MP)
  - ✓ "Morning Prayer may conclude with the following Sentence." suppressed
  - ✓ "The Responsory is said or sung." suppressed

---

## Code work queue

Do in this order. Do not skip ahead.

| Batch | What | Status |
|-------|------|--------|
| **7** | BUG-19 critical fix — reading response + Lord's Prayer + Go CLI | Done |
| **8** | JS render module + Node CLI + Vitest | Done |
| **9** | Rubrics redesign | Done |

---

## Batch 7 — BUG-19 critical fix

**All three issues are caused by `normalize_offices.py` converting inline segment arrays to shared ref dicts without corresponding support in the rendering layer. Fix all three before any other work.**

Confirmed broken on `localhost:8080/#/2026-06-17/mp` (2026-06-14): reading response absent after lesson, Lord's Prayer absent before Collect.

### Commit 1: Remove lords_prayer normalization

**File:** `tools/normalize_offices.py`

Delete the entire lords_prayer block (currently lines ~67–82):

```python
# ── lords_prayer_ordinary ─────────────────────────────────────────────────
ordinary_forms = {k: v for k, v in forms.items() if 'ordinary' in k and 'lords_prayer_intro' in v}
if ordinary_forms:
    vals = list(ordinary_forms.values())
    canonical = vals[0]['lords_prayer_intro']
    if all(blocks_equal(f['lords_prayer_intro'], canonical) for f in vals):
        key = 'lords_prayer_ordinary'
        if key not in shared:
            shared[key] = canonical
            print(f'  + shared.{key} ({len(ordinary_forms)} forms)')
        for k in ordinary_forms:
            if not isinstance(data[k].get('lords_prayer_intro'), dict) or data[k]['lords_prayer_intro'].get('type') != 'shared':
                data[k]['lords_prayer_intro'] = {'type': 'shared', 'key': key}
                changed += 1
    else:
        print('  WARNING: lords_prayer_intro not identical across ordinary forms — skipping')
```

After deletion: `lords_prayer_ordinary` disappears from `_shared`; `lords_prayer_intro` stays as an inline segment array in all ordinary-time forms.

**Why this fixes things:**
- Removes the raw JSON array from `_shared` → Go's `sharedBlock` can now parse `_shared` → CLI works
- Restores `lords_prayer_intro` to an array in all forms → `.length` check passes → Lord's Prayer renders

**Commit message:** `fix(tools): remove lords_prayer_ordinary normalization — breaks Go CLI and web rendering`

---

### Commit 2: Resolve shared ref in `lessonHtml()`

**File:** `web/app.js`, in `lessonHtml()` (around line 844)

```js
// Before:
const readingResponse = (form && form.reading_response) || READING_RESPONSE;

// After:
let readingResponse = (form && form.reading_response) || READING_RESPONSE;
if (readingResponse?.type === 'shared' && shared) {
  readingResponse = shared[readingResponse.key] || READING_RESPONSE;
}
```

**Why:** `form.reading_response` is always `{type:'shared', key:'...'}` (set by normalize). `renderAlternatives()` checks `seg.groups` — a shared ref has no `groups` → returns `''`. Adding resolution here passes the actual `{type:'alternatives', groups:[...]}` block to `renderAlternatives()`.

**Commit message:** `fix(ui): resolve shared ref in lessonHtml so reading response renders`

---

### Commit 3: Re-extract data

```bash
make extract
```

Verify before committing:
- `data/offices.json` `_shared` no longer has `lords_prayer_ordinary`
- All ordinary-time forms have `lords_prayer_intro` as an inline array (not dict)
- `make check-integrity` passes
- `make check-text` zero findings

**Commit messages:**
1. `chore(data): re-extract after removing lords_prayer normalization`
2. `chore(tools): update extract manifest`

---

### Commit 4: Data-layer form completeness test

**New file:** `tools/tests/test_form_completeness.py`

```python
"""Verify every office form in offices.json has all required sections.

BUG-19 was caused by normalize_offices.py converting lords_prayer_intro
from an array to a shared ref dict, silently breaking .length checks.
This test catches that class of regression immediately.
"""
import json, pytest
from pathlib import Path

DATA = Path(__file__).parent.parent.parent / 'data' / 'offices.json'

with open(DATA) as f:
    offices = json.load(f)

forms = [(k, v) for k, v in offices.items() if not k.startswith('_')]

@pytest.mark.parametrize('name,form', forms)
def test_required_sections_are_arrays(name, form):
    for field in ('opening_responses', 'lords_prayer_intro', 'dismissal'):
        assert isinstance(form.get(field), list), \
            f'{name}.{field} must be a list, got {type(form.get(field)).__name__}'
        assert len(form[field]) > 0, f'{name}.{field} is empty'

@pytest.mark.parametrize('name,form', forms)
def test_reading_response_present(name, form):
    rr = form.get('reading_response')
    assert rr is not None, f'{name} missing reading_response'
    # After BUG-19 fix, may be a shared ref dict OR inline alternatives — both ok
    # What's NOT ok is None
```

Wire into `make test-tools`:
```makefile
test-tools:
	python3 -m pytest tools/tests/ -v
```

(Already wired — just drop the new file in `tools/tests/`.)

**Commit message:** `test(tools): form completeness test — catches BUG-19 class of regression`

---

### Commit 5: Playwright regression test

**File:** `tests/e2e/office.spec.js`

Add a test block:

```js
test.describe('Reading response renders after lesson', () => {
  for (const [label, date, office] of [
    ['seasonal (Lent)', '2026-02-25', 'mp'],
    ['ordinary-time', '2026-06-17', 'mp'],
  ]) {
    test(label, async ({ page }) => {
      await page.goto(`/#/${date}/${office}`);
      // Wait for scripture to load (replaces placeholder)
      await page.waitForSelector('.scripture-placeholder:not(:has(.loading))', { timeout: 10000 });
      // Reading response tab strip must exist after the lesson
      const tabs = page.locator('.alt-tabs').first();
      await expect(tabs).toBeVisible();
      // Must have 3 options (I / II / III)
      await expect(page.locator('.alt-tab')).toHaveCount(3);
    });
  }
});

test('Lord\'s Prayer present in ordinary-time office', async ({ page }) => {
  await page.goto('/#/2026-06-17/mp');
  await expect(page.locator('.office-subsection-title', { hasText: "The Lord's Prayer" })).toBeVisible();
});
```

**Commit message:** `test(e2e): verify reading response and Lord's Prayer render`

---

## Batch 8 — JS render module + Node CLI + Vitest

**Goal:** shared rendering code between browser and Node; unit-testable rendering without Playwright; enables systematic correctness audit via CLI in the sandbox.

The rendering functions in `app.js` are already pure (data in → HTML string out, no browser APIs). This batch extracts them into a module so the Node CLI and Vitest tests can import them.

### Commit 1: Extract `web/render.js`

Create `web/render.js` as an ES module. Move these functions out of `app.js` and into it as named exports:

- `esc(s)` — HTML escape
- `parseDate(s)` — string to Date
- `seasonOf(dateStr, bounds)`
- `officeFormSeason(dateStr, bounds)`
- `seasonWeekIndex(dateStr, season, bounds)`
- `formKey(season, officeType, weekday)`
- `filterSeasonalCollects(segs, weekIdx)`
- `renderSegments(segs, shared)`
- `renderAlternatives(seg, shared, contextKey)`
- `renderSubsection(label, segs, shared)`
- `lessonHtml(lesson, shared, form)` — with the BUG-19 shared-ref fix already applied
- `READING_RESPONSE` — the hardcoded fallback constant
- `CANTICLE_SOURCE` — the canticle citation map
- `SKIP_RUBRICS` — the rubric suppression regex

In `app.js`, replace each definition with `import { ... } from './render.js'`. No behavior change to the browser — the module is a peer script, not a separate bundle.

**Commit message:** `refactor(web): extract rendering functions to web/render.js`

---

### Commit 2: Node CLI `cli/office.js`

```js
#!/usr/bin/env node
/**
 * Usage: node cli/office.js [mp|ep] [YYYY-MM-DD]
 * Renders a Daily Office to stdout using the same render.js as the browser.
 */
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import {
  seasonOf, officeFormSeason, seasonWeekIndex, formKey,
  filterSeasonalCollects, renderSegments, renderSubsection, lessonHtml
} from '../web/render.js';

const __dir = dirname(fileURLToPath(import.meta.url));
const load = (p) => JSON.parse(readFileSync(join(__dir, '..', p), 'utf8'));

const offices = load('data/offices.json');
const bounds  = load('data/season_bounds.json');

const officeType = process.argv[2] || 'mp';
const dateStr    = process.argv[3] || new Date().toISOString().slice(0, 10);

// Load lectionary for the month
const [year, month] = dateStr.split('-');
let lectionaryDay = null;
try {
  const lect = load(`data/lectionary/${year}-${month}.json`);
  lectionaryDay = lect.find(d => d.date === dateStr) || null;
} catch {}

const fSeason = officeFormSeason(dateStr, bounds);
const weekday = new Date(dateStr + 'T12:00:00Z').getUTCDay();
const weekIdx = seasonWeekIndex(dateStr, fSeason, bounds);
const key     = formKey(fSeason, officeType, weekday);
const form    = offices[key];
const shared  = offices._shared || {};

if (!form) {
  console.error(`No form found for key: ${key}`);
  process.exit(1);
}

const officeData = lectionaryDay ? lectionaryDay[officeType === 'mp' ? 'morning' : 'evening'] : null;

// Minimal text render (HTML tags stripped for readability)
function strip(html) { return html.replace(/<[^>]+>/g, '').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>'); }
function section(title, segs) {
  if (!segs || !segs.length) return '';
  return `\n## ${title}\n\n${strip(renderSegments(segs, shared))}\n`;
}

let out = `# ${officeType.toUpperCase()} — ${dateStr}\n`;
out += `Season: ${fSeason} | Form: ${key}\n`;
if (lectionaryDay) out += `Day: ${lectionaryDay.name}\n`;

out += section('Opening Responses', form.opening_responses);
if (officeData?.psalm) out += `\n## Psalm\n${JSON.stringify(officeData.psalm)}\n`;
if (officeData?.lesson1) out += `\n## Lesson 1\n${officeData.lesson1}\n`;
out += section('Responsory', form.responsory);
if (officeData?.lesson2) out += `\n## Lesson 2\n${officeData.lesson2}\n`;
out += section('Canticle', form.canticle);
out += section('Intercessions', form.intercessions);
out += section('Litany', form.litany);
out += section("Lord's Prayer", form.lords_prayer_intro);
out += section('Dismissal', form.dismissal);

console.log(out);
```

**Commit message:** `feat(cli): Node CLI renders any office using same render.js as browser`

---

### Commit 3: Vitest unit tests

**New file:** `tests/unit/render.test.js`

```js
import { describe, test, expect } from 'vitest';
import { readFileSync } from 'fs';
import { join } from 'path';
import {
  formKey, officeFormSeason, renderSegments, lessonHtml, filterSeasonalCollects
} from '../../web/render.js';

const offices = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/offices.json'), 'utf8'));
const bounds  = JSON.parse(readFileSync(join(import.meta.dirname, '../../data/season_bounds.json'), 'utf8'));
const shared  = offices._shared || {};
const forms   = Object.entries(offices).filter(([k]) => !k.startsWith('_'));

// ── Form selection ───────────────────────────────────────────────────────────

describe('formKey', () => {
  test.each([
    ['OrdinaryTime', 'mp', 0, 'ordinary-sunday-mp'],
    ['OrdinaryTime', 'mp', 3, 'ordinary-wednesday-mp'],
    ['OrdinaryTime', 'ep', 5, 'ordinary-friday-ep'],
    ['Advent',       'mp', 3, 'advent-mp'],
    ['Easter',       'ep', 6, 'easter-ep'],
  ])('%s %s weekday=%i → %s', (season, type, day, expected) => {
    expect(formKey(season, type, day)).toBe(expected);
  });
});

describe('officeFormSeason', () => {
  test.each([
    ['2026-06-17', 'OrdinaryTime'],
    ['2025-12-03', 'Advent'],
    ['2025-12-25', 'Christmas'],
    ['2026-04-08', 'Easter'],
    ['2026-02-25', 'Lent'],
    ['2026-03-25', 'Passiontide'],
    ['2026-05-20', 'Pentecost'],
    ['2026-11-04', 'AllSaints'],
  ])('%s → %s', (date, expected) => {
    expect(officeFormSeason(date, bounds)).toBe(expected);
  });
});

// ── Form completeness (data-layer, duplicates pytest but faster) ─────────────

describe('all forms have required sections as arrays', () => {
  test.each(forms)('%s', (name, form) => {
    for (const field of ['opening_responses', 'lords_prayer_intro', 'dismissal']) {
      expect(Array.isArray(form[field]), `${name}.${field} must be array`).toBe(true);
      expect(form[field].length, `${name}.${field} must be non-empty`).toBeGreaterThan(0);
    }
    expect(form.reading_response, `${name} missing reading_response`).toBeTruthy();
  });
});

// ── Rendering ────────────────────────────────────────────────────────────────

describe('renderSegments', () => {
  test('renders leader and response', () => {
    const segs = [
      { type: 'leader',   text: 'Lord, open our lips,' },
      { type: 'response', text: 'and our mouth shall proclaim your praise.' },
    ];
    const html = renderSegments(segs, shared);
    expect(html).toContain('Lord, open our lips');
    expect(html).toContain('and our mouth shall proclaim');
  });

  test('resolves shared ref', () => {
    const segs = [{ type: 'shared', key: 'doxology' }];
    const html = renderSegments(segs, shared);
    expect(html).toContain('alt-tabs'); // doxology is an alternatives block
  });
});

describe('lessonHtml', () => {
  test('reading response renders for ordinary-time form', () => {
    const form = offices['ordinary-wednesday-mp'];
    const html = lessonHtml('Genesis 1:1-5', shared, form);
    expect(html).toContain('alt-tabs'); // response tabs present
    expect(html).toContain('The word of the Lord');
  });

  test('reading response renders for seasonal form', () => {
    const form = offices['lent-mp'];
    const html = lessonHtml('Isaiah 55:1-9', shared, form);
    expect(html).toContain('alt-tabs');
  });

  test("Lord's Prayer present in ordinary-time form", () => {
    const form = offices['ordinary-wednesday-mp'];
    const lpHtml = renderSegments(form.lords_prayer_intro, shared);
    expect(lpHtml).toContain('Our Father in heaven');
  });
});
```

**`package.json` addition** (if not already present — add vitest):
```json
{
  "type": "module",
  "devDependencies": {
    "vitest": "^1.0.0"
  },
  "scripts": {
    "test": "vitest run"
  }
}
```

**Makefile addition:**
```makefile
test-unit:
	npm test
```

**Commit message:** `test(unit): Vitest suite for rendering functions and form completeness`

---

### Commit 4: Wire into CI / Makefile

Add `test-unit` to the default `make test` chain so it runs with `make test`:

```makefile
test: test-go test-unit test-tools
```

Also run vitest in `make check-dist` before deploy.

**Commit message:** `chore: wire test-unit into make test and check-dist`

---

## Batch 9 — Rubrics redesign

**Goal:** Reduce the wall of red rubric text in Office mode. Three targeted changes to `app.js` — no data changes.

**Confirmed rubrics in the app (from offices.json audit, 2026-06-14):**

| Rubric text (truncated) | Current | Target |
|-------------------------|---------|--------|
| "Morning Prayer continues with…" | Shown | Suppress |
| "Evening Prayer continues with…" | Shown | Suppress |
| "Morning Prayer may conclude with the following Sentence." | Shown | Suppress |
| "Evening Prayer may conclude with the following Sentence." | Shown | Suppress |
| "The Responsory is said or sung." | Shown | Suppress |
| "The Litany is said or sung." | Shown | Suppress |
| "The community may offer its intercessions…" + 5 bullets | Shown in full | Condense |
| "Additional intercessions…" + 5 bullets (seasonal) | Shown in full | Condense |
| "After the Canticle one of the following may be said or sung." | Shown | Keep |
| "Either the Collect of the Day or…" | Shown | Keep |
| "The following verses may be added." | Shown | Keep |
| Period labels: "Advent 1", "Week of Easter", etc. | Shown | Keep |

Note: "continues with" variants are already partially suppressed by existing `SKIP_RUBRICS`. The gaps are "may conclude with", the two instrument rubrics, and the intercessions block.

### Commit 1: Expand `SKIP_RUBRICS`

**File:** `web/app.js`

```js
// Before:
const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$|continues with/i;

// After:
const SKIP_RUBRICS = /^(Affirmation of Faith|[Tt]he Lord'?s Prayer)\.?\s*$|continues with|may conclude with|^The (Responsory|Litany) is said or sung\./i;
```

This suppresses:
- "Morning Prayer may conclude with the following Sentence."
- "Evening Prayer may conclude with the following Sentence."
- "The Responsory is said or sung."
- "The Litany is said or sung."

**Commit message:** `fix(ui): suppress navigation rubrics — conclude/responsory/litany`

---

### Commit 2: Condense intercessions rubric

**File:** `web/app.js`

Add a constant and update `renderSegments` to detect and condense the intercessions rubric. The intercessions rubric text always starts with "The community may offer" (ordinary-time) or "Additional intercessions" (seasonal).

Add near the top of the Office rendering section:

```js
const INTERCESSIONS_RE = /^(The community may offer|Additional intercessions)/;
const INTERCESSIONS_CONDENSED = '<p class="seg-rubric"><em>Offer intercessions, petitions, and thanksgivings, silently or aloud.</em></p>';
```

In `renderSegments`, in the segment map function, add before the existing type checks:

```js
if (seg.type === 'rubric' && INTERCESSIONS_RE.test(seg.text || '')) {
  return INTERCESSIONS_CONDENSED;
}
```

This replaces the full multi-line intercessions block (preamble + 5 weekly prayer bullets + nav text) with a single condensed italic line. Works for both ordinary-time and seasonal forms.

**Commit message:** `fix(ui): condense intercessions rubric to one line in Office mode`

---

## Completed — Batch 6 + mobile fix (deployed 2026-06-14)

Five items delivered and deployed to S3:
1. ✅ Removed "Today" text from nav (kept calendar icon)
2. ✅ Fixed stale-date banner not dismissing on navigate-to-today
3. ✅ Fixed "OrdinaryTime" → "Ordinary Time" display label
4. ✅ Added pdftotext version check to `check_data_integrity.py`
5. ✅ Fixed 5 FATS extraction artifacts (Chad, Maurice, Visitation, Boniface, Reformation Era)
6. ✅ Suppressed `#day-brand` duplicate header in mobile view

Spot-checked 2026-06-14 via computer-use screenshot on localhost:8080:
- ✓ "Ordinary Time" displays with space
- ✓ Reading section loads
- ✓ BUG-19 confirmed visually (batch 7 fixes this)

---

## Completed — Batch 5 (deployed 2026-06-07)

1. ✅ Fixed garbled collects (BAS pages 356, 358, 392, 396) — txt-fallback in `extract_collects.py`
2. ✅ Extraction manifest + data integrity guard (`tools/update_extract_manifest.py`, `tools/check_data_integrity.py`, `make check-integrity`)
3. ✅ Text quality checker (`tools/check_text_quality.py`, `make check-text`)
4. ✅ pdftotext version pinning in integrity guard

---

## Design: Notes on remaining open items

### Correctness audit (Milestone 2)

Defer until after Batch 8. The Node CLI (`cli/office.js`) makes this tractable — run it for all 30 form types and review Markdown output. Without the CLI it requires browser screenshots for each form.

### FATS minor feast readings

Design decision pending: do FATS readings show as an alternative to the BAS lectionary reading, or replace it? Check a specific minor feast live first to see what BAS prescribes (if anything) vs what FATS provides.

### RCL Daily extractor

Spec complete (see ROADMAP.md Phase 3). Unblocked but low priority until milestone 2 is done.
