# PWC — Handoff

_Updated: 2026-06-14_

Active handoff between Cowork (planning) and Claude Code (implementation). Cowork writes specs here; Code implements in order.

---

## Ready for Cowork review — Batches 7 + 8 (2026-06-14)

Serving at **http://localhost:8081** (cache: `pwc-bacd9557`).

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

---

## Code work queue

Do in this order. Do not skip ahead.

| Batch | What | Status |
|-------|------|--------|
| **7** | BUG-19 critical fix — reading response + Lord's Prayer + Go CLI | Done |
| **8** | JS render module + Node CLI + Vitest | Done |
| **9** | Rubrics redesign | Ready for Code |

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
