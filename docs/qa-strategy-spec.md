# QA Strategy — Implementation Specification

_Reference for implementing ADR 0008 and ADR 0009._

## OfficeJSON schema

`renderOfficeJSON(cfg)` produces:

```typescript
interface OfficeJSON {
  meta: {
    officeType: 'mp' | 'ep';
    season: string;
    formKey: string;
    weekIdx: number;
    hasAlternateObservance: boolean;
  };
  sections: OfficeSection[];
}

interface OfficeSection {
  name: 'Gathering' | 'Proclamation' | 'Affirmation' | 'Prayers' | 'Sending';
  visible: boolean;        // false if parent section heading is suppressed

  subsections: Subsection[];
  dynamic: DynamicBlock;
}

interface Subsection {
  label: string;
  hidden?: boolean;        // alternate observance subsections (hidden in UI)
  segments: SegItem[];
}

interface SegItem {
  section: string;
  type: 'leader' | 'response' | 'rubric' | 'label';
  text: string;
}

interface DynamicBlock {
  // Gathering
  invitatory?: { citation: string };
  phosHilaronPresent?: boolean;
  thanksgivingForLightPresent?: boolean;

  // Proclamation
  psalms?: PsalmRef[];
  psalmSets?: PsalmRef[][];
  psalmDoxologyPresent?: boolean;
  readings: ReadingRef[];
  readingResponsePresent?: boolean;
  canticleLabel?: string;
  lessonsPick?: { pick: number; total: number };

  // Affirmation
  hasAffirmation: boolean;

  // Prayers
  intercessionsCount?: number;
  litanyLeaderCount?: number;
  litanyResponseCount?: number;
  collectRef?: string;
  collectInline?: { name: string; text: string };
  collectOccasional?: { page: number; name: string; text: string };
  collectFatsFallback?: boolean;
  collectSeasonalItems: SegItem[];
  lordsPrayerPresent?: boolean;

  // Sending
  dismissalContainsAmen: boolean;
}
```

## Rule suite — 16 rules

### Tier 1 — Structural (penalty: -10)

| # | Rule name | Scope | Check |
|---|-----------|-------|-------|
| 1 | `dismissal-has-amen` | Sending | At least one segment in `dismissal` subsections contains "Amen" in its text |
| 2 | `no-stray-space-before-period` | All | No `SegItem.text` matches `Amen \.` or `\w \.$` |
| 3 | `non-empty-responses` | All | Every `type: 'response'` item has `text.length >= 3` |
| 4 | `opening-has-leader-and-response` | Gathering | `opening_responses` subsection has ≥1 leader AND ≥1 response |
| 5 | `no-empty-segments` | All | No `SegItem.text` is exactly `"N"` (unsubstituted `italicisePlaceholderN`) |
| 6 | `canticle-has-verse-content` | Proclamation | Canticle subsection has ≥1 `type: 'leader'` item beyond the label |
| 7 | `evening-has-light` | Gathering | If `officeType === 'ep'`: `phosHilaronPresent || thanksgivingForLightPresent` |
| 8 | `leader-response-alternation` | Gathering, Affirmation, Prayers, Sending | In dialogic subsections (opening_responses, affirmation, litany, dismissal): no two consecutive non-rubric segments of the same type. Rubrics are transparent — they're skipped when checking adjacency. Alternation is checked **per alternatives group** independently. Restart adjacency tracking on each `enter_group` event. |
| 9 | `psalter-gloria-present` | Proclamation | If `psalms` or `psalmSets` is non-empty: `psalmDoxologyPresent === true` |
| 10 | `reading-response-present` | Proclamation | If `readings` is non-empty: `readingResponsePresent === true` |
| 11 | `collect-resolvable` | Prayers | At least one of `collectRef`, `collectInline`, or `collectFatsFallback` is non-null |

### Tier 2 — Format (penalty: -3)

| # | Rule name | Scope | Check |
|---|-----------|-------|-------|
| 12 | `no-prose-line-breaks` | All (narrow scope) | In prose-only subsection labels (not: opening_responses, responsory, canticle, invitatory, phos_hilaron, thanksgiving_for_light, lords_prayer_intro, lords_prayer, intercessions, affirmation, litany, dismissal): leader/response items must not contain `\n` |
| 13 | `canticle-has-verse-breaks` | Proclamation | Canticle subsection: leader items should contain `\n` between verses. Flag if canticle text has zero `\n` characters (space-joined). No conflict with rule 12 — canticle is excluded from its scope. |
| 14 | `collect-and-dismissal-no-orphan-breaks` | Prayers, Sending | Collect text and dismissal text items: `\n` should only appear after sentence-ending punctuation (`[.?!:]`) or at text end. A `\n` preceded by a non-sentence-ending character is flagged. |
| 15 | `seasonal-title-coherence` | All | If `season !== 'OrdinaryTime'` and `form.title` exists: form title visible (check via `offices.json`, not `OfficeJSON`). If `season === 'OrdinaryTime'`: this rule is a **no-op** — ordinary forms have titles in data, correctly suppressed by `app.js:1065`. |
| 16 | `no-orphan-rubrics` | All | A subsection's last `SegItem` should not be `type: 'rubric'`. Exempt: rubrics matching `SKIP_RUBRICS` or `BOOK_ONLY_RUBRICS` patterns (these are navigation cues, not liturgical content). Apply exemption before flagging. |
| 17 | `intercessions-nonempty` | Prayers | Intercessions subsection: `intercessionsCount > 0` or subsection contains non-placeholder text |

### Tier 3 — Seasonal (penalty: -5)

| # | Rule name | Scope | Check |
|---|-----------|-------|-------|
| 18 | `advent-epiphany-canticles` | Proclamation | If season is Advent or Epiphany: `canticleLabel` should be in the Advent/Epiphany canticle set (`CANTICLE_SOURCE` map). Missing or unknown label: flag. |
| 19 | `lent-easter-canticles` | Proclamation | If season is Lent, Easter: `canticleLabel` in Lent/Easter set. |
| 20 | `ordinary-time-canticles` | Proclamation | If season is Ordinary Time: `canticleLabel` in Ordinary Time set. |
| 21 | `collect-week-in-range` | Prayers | Seasonal forms only: the resolved `weekIdx` is within the bounds of the form's `seasonal_collects` alternatives array. Does not apply to Ordinary Time (single alternatives block, not multi-week). |

### Interaction notes

**Rule 8 (`leader-response-alternation`)**: Walk segments depth-first using `walkSegments` events. Track adjacent segment types, skipping `rubric` items. On `enter_group`, reset adjacency. On `exit_group`, reset adjacency. This ensures alternation is checked within each alternatives group independently.

**Rule 14 (`collect-and-dismissal-no-orphan-breaks`)**: Sentence-end pattern is `[.?!:]\s*$` before `\n`. Use `/\n/g` to find all line breaks, check preceding character against `[.?!:]\s*`. Dismissal text comes from `dismissal` subsections in Sending. Collect text comes from `collectSeasonalItems` and any collect text embedded in the seasonal collect subsections.

**Rule 16 (`no-orphan-rubrics`)**: Exemption patterns: `SKIP_RUBRICS` (regex: rubric text matching patterns suppressed entirely by `renderSegments`) and `BOOK_ONLY_RUBRICS` (navigation cues like "Morning Prayer continues with..."). A rubric that ends a subsection but matches these patterns is not an orphan — it's programmatically hidden.

## Scoring formula

```
S = max(0, 100 − Σ(per-form penalties) − global penalties)
```

Per-form penalties:
```
P_form = (T1_count × 10) + (T2_count × 3) + (T3_count × 5)
       + (z25_count × 5) + (z30_count × 15) + (bool_minority_count × 5)
```

Global penalties:
```
P_global = text_quality_findings × 2
```

Aggregate score:
```
S_aggregate = max(0, 100 − max(P_form for all forms) − P_global)
```

Or, using weakest-link: `S_aggregate = min(S_form for all forms) − P_global` where `S_form = max(0, 100 − P_form)`.

Both formulations produce the same result. Use whichever is clearer in code.

## Promoted gate

```makefile
promote:
	@test -f .deploy-latest || (echo "Run deploy-staging first"; exit 1)
	@if [ -z "$$PROMOTE_FORCE" ]; then \
	  node tools/coherence_score.cjs /tmp/pwc-qa.json --check-promote \
	    || (echo "Promotion blocked — score below 85. Fix issues or use PROMOTE_FORCE=1 to bypass."; exit 1); \
	fi
	@RELEASE=$$(cat .deploy-latest); \
	aws cloudfront get-distribution-config --id $(CF_DISTRIBUTION_ID) \
	  > /tmp/cf-config.json; \
	...
```

## CI integration

```makefile
QA_TMP = /tmp/pwc-qa.json

qa:
	@echo "=== Liturgical validation ==="
	@node tools/validate_office.cjs --json | tee $(QA_TMP).validate
	@node tools/audit_office.cjs --json | tee $(QA_TMP).audit
	@node tools/coherence_score.cjs $(QA_TMP).validate $(QA_TMP).audit
	@rm -f $(QA_TMP).validate $(QA_TMP).audit

test: test-unit test-tools qa
```

`coherence_score.cjs` prints the score and exits 0 or 1 based on threshold.

Delete the temp files after scoring. In concurrent CI, each job uses its own `/tmp` namespace.

## Validation date list

File: `tools/qa_dates.json` (committed, maintained annually):

```json
[
  { "date": "2025-12-07", "forms": ["advent-mp", "advent-ep"] },
  { "date": "2025-12-25", "forms": ["christmas-mp", "christmas-ep"] },
  { "date": "2026-01-11", "forms": ["epiphany-mp", "epiphany-ep"] },
  { "date": "2026-03-08", "forms": ["lent-mp", "lent-ep"] },
  { "date": "2026-03-22", "forms": ["passiontide-mp", "passiontide-ep"] },
  { "date": "2026-04-12", "forms": ["easter-mp", "easter-ep"] },
  { "date": "2026-05-31", "forms": ["pentecost-mp", "pentecost-ep"] },
  { "date": "2025-11-01", "forms": ["allsaints-mp", "allsaints-ep"] },
  { "date": "2026-07-12", "forms": ["ordinary-sunday-mp", "ordinary-sunday-ep"] },
  { "date": "2026-07-13", "forms": ["ordinary-monday-mp", "ordinary-monday-ep"] },
  { "date": "2026-07-14", "forms": ["ordinary-tuesday-mp", "ordinary-tuesday-ep"] },
  { "date": "2026-07-15", "forms": ["ordinary-wednesday-mp", "ordinary-wednesday-ep"] },
  { "date": "2026-07-16", "forms": ["ordinary-thursday-mp", "ordinary-thursday-ep"] },
  { "date": "2026-07-17", "forms": ["ordinary-friday-mp", "ordinary-friday-ep"] },
  { "date": "2026-07-18", "forms": ["ordinary-saturday-mp", "ordinary-saturday-ep"] }
]
```

Each entry specifies the exact form keys to test. Ordinary Time needs 7 dates
(one per weekday) to cover all 14 weekday variants (7 MP + 7 EP). The date is
used for lectionary data loading only; the form key is used directly to look up
the form in `offices.json`.

## `renderOfficeJSON` implementation outline

```js
export function renderOfficeJSON(cfg) {
  const { form, shared, officeData, officeType, season, weekIdx,
          fatsEntry, collects, collectRef, collectInline } = cfg;

  const sections = [];

  // ── Meta ──
  const meta = {
    officeType,
    season,
    formKey: form._key,  // or derived from cfg
    weekIdx: weekIdx ?? 0,
    hasAlternateObservance: !!officeData.alternate,
  };

  // ── Gathering ──
  const gathering = { name: 'Gathering', visible: true, subsections: [], dynamic: {} };
  if (form.opening_responses) {
    const resolved = resolveShared(form.opening_responses, shared);
    gathering.subsections.push({
      label: 'Introductory Responses',
      segments: segmentsFrom(flattenSegments(resolved, shared)),
    });
    gathering.dynamic.invitatory = form.invitatory
      ? { citation: form.invitatory[0]?.text }
      : undefined;
    gathering.dynamic.phosHilaronPresent = !!(form.phos_hilaron?.length);
    gathering.dynamic.thanksgivingForLightPresent = !!(form.thanksgiving_for_light?.length);
  }
  sections.push(gathering);

  // ── Proclamation ──
  const proclamation = { name: 'Proclamation', visible: true, subsections: [], dynamic: {} };
  const lessons = officeData.lessons || [];
  proclamation.dynamic.psalms = officeData.psalms;
  proclamation.dynamic.psalmSets = officeData.psalm_sets;
  proclamation.dynamic.psalmDoxologyPresent = !!(shared.doxology);
  proclamation.dynamic.readings = lessons.map(l => l);
  proclamation.dynamic.readingResponsePresent = !!(form.reading_response);
  proclamation.dynamic.lessonsPick = officeData.lessons_pick
    ? { pick: officeData.lessons_pick, total: lessons.length }
    : undefined;
  // Responsory
  if (form.responsory) {
    proclamation.subsections.push({
      label: 'The Responsory',
      segments: flattenSegments(form.responsory, shared),
    });
  }
  // Canticle
  if (form.canticle) {
    proclamation.subsections.push({
      label: 'The Canticle',
      segments: flattenSegments(form.canticle, shared),
    });
    proclamation.dynamic.canticleLabel = form.canticle[0]?.label;
  }
  sections.push(proclamation);

  // ── Affirmation ──
  const affirmation = { name: 'Affirmation', visible: true, subsections: [], dynamic: {} };
  if (form.affirmation?.length) {
    affirmation.subsections.push({
      label: 'Affirmation of Faith',
      segments: flattenSegments(form.affirmation, shared),
    });
    affirmation.dynamic.hasAffirmation = true;
  }
  sections.push(affirmation);

  // ── Prayers ──
  const prayers = { name: 'Prayers', visible: true, subsections: [], dynamic: {} };
  // Intercessions
  if (form.intercessions) {
    const items = flattenSegments(form.intercessions, shared);
    prayers.subsections.push({ label: 'Intercessions and Thanksgivings', segments: items });
    prayers.dynamic.intercessionsCount = items.length;
  }
  // Litany
  if (form.litany?.length) {
    const items = flattenSegments(form.litany, shared);
    prayers.subsections.push({ label: 'The Litany', segments: items });
    prayers.dynamic.litanyLeaderCount = items.filter(i => i.type === 'leader').length;
    prayers.dynamic.litanyResponseCount = items.filter(i => i.type === 'response').length;
  }
  // Collect
  const seasonalSegs = filterSeasonalCollects(form.seasonal_collects || [], weekIdx);
  const seasonalItems = flattenSegments(seasonalSegs, shared);
  prayers.dynamic.collectRef = collectRef;
  prayers.dynamic.collectInline = collectInline;
  prayers.dynamic.collectFatsFallback = !!fatsEntry?.collect;
  prayers.dynamic.collectSeasonalItems = seasonalItems;
  if (collectRef && collectSecondaryPage(collectRef)) {
    const occPage = collectSecondaryPage(collectRef);
    const occCollect = collects[occPage];
    if (occCollect) {
      prayers.dynamic.collectOccasional = { page: occPage, name: occCollect.name, text: occCollect.text };
    }
  }
  // Lord's Prayer
  if (form.lords_prayer_intro?.length) {
    prayers.subsections.push({
      label: "The Lord's Prayer",
      segments: flattenSegments(form.lords_prayer_intro, shared),
    });
    prayers.dynamic.lordsPrayerPresent = true;
  }
  sections.push(prayers);

  // ── Sending ──
  const sending = { name: 'Sending', visible: true, subsections: [], dynamic: {} };
  if (form.dismissal?.length) {
    const items = flattenSegments(form.dismissal, shared);
    sending.subsections.push({ label: 'The Dismissal', segments: items });
    sending.dynamic.dismissalContainsAmen = items.some(i => i.text.includes('Amen'));
  }
  sections.push(sending);

  return { meta, sections };
}

// ── Helpers ──

function resolveShared(field, shared) {
  if (field?.type === 'shared' && shared) return shared[field.key] || field;
  return Array.isArray(field) ? field : [];
}

function flattenSegments(segs, shared) {
  const items = [];
  for (const event of walkSegments(segs, shared)) {
    if (event.type === 'segment') {
      const seg = event.seg;
      if (seg.text?.trim()) {
        items.push({ 
          section: '', // filled by caller by subsection label
          type: seg.type, 
          text: seg.text.trim() 
        });
      }
    }
  }
  return items;
}
```

The `section` field on `SegItem` is populated from the parent subsection label
for backward compatibility with existing validator rules that filter by
`item.section`.

## Testing strategy

1. **Unit: `renderOfficeJSON` structure** — Vitest test with known form +
   officeData. Assert section names, subsection labels, segment counts, dynamic
   boolean fields.
2. **Unit: Rule functions** — Each rule tested with contrived pass/fail
   `OfficeJSON` fixtures. Test both positive and negative cases.
3. **Integration: Sync test** — Render same office via `renderOfficeJSON` and
   via `renderSegments` HTML path. Collect `innerText` of HTML sections and
   compare structural elements (subsection count, approximate length).
4. **CI: `make qa`** — Runs on every `make test`. Gate: exit code 0 means score
   ≥ 85. This is the authoritative quality signal.

## Performance estimate

- 15 dates in `qa_dates.json`
- Each date loads one `data/lectionary/YYYY-MM.json` (~50-200KB)
- 30 forms total, each traversed via `walkSegments`
- Cold CI: ~5 seconds (disk I/O for lectionary files)
- Warm (local): ~1–2 seconds

Lectionary files are cached by date — forms sharing the same date reuse the
loaded data. This avoids 30 separate file reads.

## Implementation plan

### Phase 1 — Parallel path (now)

Implement validators as a separate consumer of the assembly logic.
`renderOfficeJSON` duplicates the section orchestration from `app.js:render()`.
All work is additive — the browser rendering path is untouched.

1. Move `collectSecondaryPage` from `app.js` → `render.js` (shared utility)
2. Fix `cli/book.js` Lord's Prayer placement (match web app)
3. Implement `renderOfficeJSON(cfg)` in `render.js`
4. Create `tools/qa_dates.json` (15-date validation fixture)
5. Add `--json` flag to `validate_office.cjs`
6. Add `--json` flag to `audit_office.cjs`
7. Expand rule suite in `validate_office.cjs` (10 new rules, rework existing 6 to consume `OfficeJSON`)
8. Create `tools/coherence_score.cjs`
9. Write sync test in Vitest
10. Update Makefile: `qa` target, promote gate, `make test` includes QA

### Phase 2 — Unification (after sync test passes)

Extract `assembleSections()` from the proven `renderOfficeJSON`. Refactor
`render()` to call it. Delete the duplicated assembly logic.

1. Extract `assembleSections()` — pure function returning `SectionDescriptor[]`
2. Refactor `app.js:render()` to call `assembleSections()`, looping over sections
3. Refactor `renderOfficeJSON()` to call the same `assembleSections()`
4. Delete the ~200-line duplication in `renderOfficeJSON`
5. Keep the sync test — it still passes after refactor
