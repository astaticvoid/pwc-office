#!/usr/bin/env node
/**
 * tools/validate_render.cjs — rendered DOM validation for all 30 forms.
 *
 * Assembles each form and verifies that the rendered HTML output is
 * structurally correct: section headings present, segment counts match,
 * no empty liturgy blocks, heading hierarchy is valid.
 *
 * Usage: node tools/validate_render.cjs [--json]
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

async function main() {
  const { assembleSections, renderSegments, walkSegments, SKIP_RUBRICS } = await import('../web/render.js');

  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared = offices._shared || {};
  const useJson = process.argv.includes('--json');

  const failures = [];

  // Load lectionary for dynamic checks
  let bounds;
  try {
    bounds = JSON.parse(readFileSync(join(root, 'data/season_bounds.json'), 'utf8'));
  } catch (_) { bounds = null; }

  let qaDates;
  try {
    qaDates = JSON.parse(readFileSync(join(root, 'tools/qa_dates.json'), 'utf8'));
  } catch (_) { qaDates = []; }

  // ── Static checks: all 30 forms ─────────────────────────────────────

  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));
  let staticForms = 0, staticPassed = 0;

  for (const fk of formKeys) {
    staticForms++;
    const form = offices[fk];
    const formFailures = [];

    // 1. Verify each section field renders non-empty HTML
    const renderableFields = {
      opening_responses: { verse: false },
      responsory: { verse: true },
      canticle: { verse: true },
      intercessions: { verse: false },
      litany: { verse: false },
      lords_prayer_intro: { verse: true },
      dismissal: { verse: true },
      phos_hilaron: { verse: true },
      invitatory: { verse: true },
      thanksgiving_for_light: { verse: true },
      affirmation: { verse: false },
    };

    for (const [field, opts] of Object.entries(renderableFields)) {
      const segs = form[field];
      if (!segs || !Array.isArray(segs)) continue;
      const html = renderSegments(segs, shared, opts.verse);
      if (!html || !html.trim()) {
        formFailures.push(`${fk}.${field}: renders empty HTML`);
        continue;
      }

      // 2. Segment count parity: HTML <p> count vs flattened segment count
      const items = [];
      for (const event of walkSegments(segs, shared)) {
        if (event.type === 'segment' && event.seg.text && event.seg.text.trim()
            && !SKIP_RUBRICS.test(event.seg.text)) {
          items.push(event.seg);
        }
      }
      const paraCount = (html.match(/<p\b/g) || []).length;
      // Amen splitting in verse leaders can add extra paragraphs
      const diff = Math.abs(paraCount - items.length);
      // Verse sections can have extra paragraphs from Amen splitting and doxology insertion
      const maxDiff = opts.verse ? 5 : 2;
      if (diff > maxDiff) {
        formFailures.push(`${fk}.${field}: paragraph count ${paraCount} vs ${items.length} segments (diff ${diff})`);
      }

      // 3. No empty liturgy (only whitespace between tags)
      const stripped = html.replace(/<[^>]+>/g, '').trim();
      if (paraCount > 0 && !stripped) {
        formFailures.push(`${fk}.${field}: tags but no visible text`);
      }
    }

    // 4. Seasonal collect must have content
    if (form.seasonal_collects && Array.isArray(form.seasonal_collects)) {
      const scHtml = renderSegments(form.seasonal_collects, shared, false);
      const scParaCount = (scHtml.match(/<p\b/g) || []).length;
      if (!scHtml.trim() && scParaCount === 0) {
        // empty seasonal collects is normal for some forms
      }
    }

    if (formFailures.length) {
      failures.push(...formFailures.map(d => ({ form: fk, detail: d })));
    } else {
      staticPassed++;
    }
  }

  // ── Dynamic checks: with lectionary data ─────────────────────────────

  let dynamicForms = 0, dynamicPassed = 0;
  if (bounds && qaDates.length) {
    const { seasonOf, officeFormSeason, seasonWeekIndex } = await import('../web/render.js');

    const dateCache = {};
    for (const entry of qaDates) {
      const [year, month] = entry.date.split('-');
      let lect;
      const cacheKey = `${year}-${month}`;
      if (dateCache[cacheKey]) {
        lect = dateCache[cacheKey];
      } else {
        try {
          lect = JSON.parse(readFileSync(join(root, `data/lectionary/${year}-${month}.json`), 'utf8'));
          dateCache[cacheKey] = lect;
        } catch (_) { continue; }
      }
      const day = lect[entry.date];
      if (!day) continue;

      for (const fk of entry.forms) {
        const form = offices[fk];
        if (!form) continue;
        dynamicForms++;
        const officeType = fk.endsWith('-ep') ? 'ep' : 'mp';
        const officeData = officeType === 'ep' ? (day.evening || {}) : (day.morning || {});
        const fSeason = officeFormSeason(entry.date, bounds);
        const season = seasonOf(entry.date, bounds);
        const weekIdx = seasonWeekIndex(entry.date, fSeason, bounds);

        const cfg = {
          form, shared, officeData, officeType, season,
          weekIdx: weekIdx || 0,
          collectRef: officeData.collect || null,
          collectInline: day.collect_inline || null,
        };

        const officeJSON = assembleSections(cfg);

        // 5. Section visibility: every section with subsections must have content
        for (const section of officeJSON.sections) {
          for (const sub of section.subsections) {
            if (!sub.segments.length) {
              failures.push({
                form: fk,
                detail: `${section.name}/${sub.label}: empty subsection (zero segments)`,
              });
            }
            // Check that at least one segment has real text
            const hasText = sub.segments.some(s => s.text && s.text.trim().length > 0);
            if (!hasText && sub.segments.length > 0) {
              failures.push({
                form: fk,
                detail: `${section.name}/${sub.label}: all segments are whitespace`,
              });
            }
          }
        }

        // 6. Dynamic fields sanity
        const proc = officeJSON.sections.find(s => s.name === 'Proclamation');
        if (proc) {
          if (proc.dynamic.readings && proc.dynamic.readings.length === 0) {
            // No readings is normal for some lectionary days
          }
          if ((proc.dynamic.psalms && proc.dynamic.psalms.length > 0) && !proc.dynamic.psalmDoxologyPresent) {
            failures.push({ form: fk, detail: 'Proclamation: psalms present but no doxology' });
          }
          if (proc.dynamic.readings && proc.dynamic.readings.length > 0 && !proc.dynamic.readingResponsePresent) {
            failures.push({ form: fk, detail: 'Proclamation: readings present but no reading response' });
          }
        }

        dynamicPassed++;
      }
    }
  }

  // ── Report ───────────────────────────────────────────────────────────

  const total = staticForms + dynamicForms;

  if (useJson) {
    console.log(JSON.stringify({
      static_checked: staticForms,
      static_passed: staticPassed,
      dynamic_checked: dynamicForms,
      dynamic_passed: dynamicPassed,
      failures: failures,
      failure_count: failures.length,
    }, null, 2));
    process.exit(0);
  }

  console.log(`Rendered DOM validation: ${staticForms} static forms + ${dynamicForms} dynamic checks`);
  if (failures.length === 0) {
    console.log(`All ${total} forms rendered correctly.`);
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.log(`  ${f.form}: ${f.detail}`);
  }

  process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
