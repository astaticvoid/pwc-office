#!/usr/bin/env node
/**
 * tools/validate_office.cjs — liturgical coherence validators for structured output.
 *
 * Consumes segmentsToJSON from render.js and checks rules against all 30 forms.
 * Each rule returns {pass, detail} — failures are reported, not exceptions.
 *
 * Usage: node tools/validate_office.cjs [--json]
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

async function main() {
  const { segmentsToJSON } = await import('../web/render.js');

  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared  = offices._shared || {};

  const rules = [];
  const failures = [];

  // ── Rule 1: Every dismissal must contain "Amen" ──────────────────────────
  rules.push({ name: 'dismissal-has-amen', check(form, formKey, items) {
    const dismissal = items.filter(i => i.section === 'dismissal');
    const amens = dismissal.filter(i => i.text.includes('Amen'));
    const amenTexts = amens.map(i => {
      const idx = i.text.indexOf('Amen');
      return idx >= 0 ? '...' + i.text.slice(Math.max(0, idx - 10), idx + 10) + '...' : i.text.slice(-30);
    });
    return {
      pass: amens.length > 0,
      detail: amens.length ? `"${amenTexts[0]}"` : 'no Amen found in dismissal',
    };
  }});

  // ── Rule 2: No orphan line breaks in PROSE leader/response segments ────
  rules.push({ name: 'no-prose-line-breaks', check(form, formKey, items) {
    // Sections where verse breaks are intentional liturgical structure
    const verseSections = ['opening_responses', 'responsory', 'canticle', 'invitatory',
      'phos_hilaron', 'thanksgiving_for_light', 'lords_prayer_intro',
      'lords_prayer', 'intercessions', 'affirmation', 'litany', 'dismissal'];
    const proseItems = items.filter(i =>
      (i.type === 'leader' || i.type === 'response')
      && !verseSections.includes(i.section)
      && i.text.includes('\n')
    );
    // Ignore single newline at end of segment (trailing)
    const orphans = proseItems.filter(i => i.text.includes('\n') && !i.text.endsWith('\n'));
    return {
      pass: orphans.length === 0,
      detail: orphans.length ? `${orphans.length} prose segments have line breaks (first: "${orphans[0].text.slice(0, 60)}...")` : '',
    };
  }});

  // ── Rule 3: No stray "Amen ." or "... ." — space before period ──────────
  rules.push({ name: 'no-stray-space-before-period', check(form, formKey, items) {
    // Match "Amen ." or any word ending with " ." (space before period)
    const stray = items.filter(i => /Amen \./.test(i.text) || /\w \.$/.test(i.text));
    return {
      pass: stray.length === 0,
      detail: stray.length ? `${stray.length} segments (first: "${stray[0].text.slice(-30)}")` : '',
    };
  }});

  // ── Rule 4: Every response segment has non-zero length ────────────────────
  rules.push({ name: 'non-empty-responses', check(form, formKey, items) {
    const empty = items.filter(i => i.type === 'response' && i.text.length < 2);
    return {
      pass: empty.length === 0,
      detail: empty.length ? `${empty.length} near-empty responses` : '',
    };
  }});

  // ── Rule 5: Required sections are present ─────────────────────────────────
  rules.push({ name: 'required-sections', check(form, formKey, items) {
    const sections = new Set(items.map(i => i.section));
    const required = ['opening_responses', 'responsory', 'canticle', 'dismissal'];
    const missing = required.filter(r => !sections.has(r));
    // EP forms may not have affermation, seasonal have seasonal_collects vs ordinary
    return {
      pass: missing.length === 0,
      detail: missing.length ? `missing: ${missing.join(', ')}` : '',
    };
  }});

  // ── Rule 6: Opening responses have at least one leader-response pair ──────
  rules.push({ name: 'opening-has-leader-and-response', check(form, formKey, items) {
    const opening = items.filter(i => i.section === 'opening_responses');
    const hasLeader = opening.some(i => i.type === 'leader');
    const hasResponse = opening.some(i => i.type === 'response');
    return {
      pass: hasLeader && hasResponse,
      detail: `leader=${hasLeader} response=${hasResponse}`,
    };
  }});

  // ── Run all rules against all forms ──────────────────────────────────────
  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  for (const formKey of formKeys) {
    const form = offices[formKey];
    const items = segmentsToJSON(form, shared);

    for (const rule of rules) {
      const { pass, detail } = rule.check(form, formKey, items);
      if (!pass) {
        failures.push({ rule: rule.name, form: formKey, detail });
      }
    }
  }

  // ── Report ───────────────────────────────────────────────────────────────
  console.log(`Checked ${formKeys.length} forms × ${rules.length} rules`);
  if (failures.length === 0) {
    console.log('All rules passed.');
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.log(`  [${f.rule}] ${f.form}: ${f.detail}`);
  }

  // Summary by rule
  const byRule = {};
  for (const f of failures) {
    byRule[f.rule] = (byRule[f.rule] || 0) + 1;
  }
  console.log('\nBy rule:');
  for (const [rule, count] of Object.entries(byRule)) {
    console.log(`  ${rule}: ${count}/${formKeys.length} forms`);
  }

  process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });
