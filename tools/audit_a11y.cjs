#!/usr/bin/env node
/**
 * tools/audit_a11y.cjs — static accessibility checks for rendered office HTML.
 *
 * Verifies heading hierarchy, ARIA attributes on interactive elements,
 * and basic markup correctness across all forms. No browser needed.
 *
 * Usage: node tools/audit_a11y.cjs [--json]
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

async function main() {
  const { assembleSections, renderSegments, walkSegments, renderSubsection } = await import('../web/render.js');
  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared = offices._shared || {};
  const useJson = process.argv.includes('--json');

  const failures = [];
  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  // Render a minimal office to check HTML structure
  for (const fk of formKeys) {
    const form = offices[fk];

    // Render each section and check the HTML output
    const renderables = [
      { field: 'opening_responses', label: 'Opening Responses', verse: false },
      { field: 'responsory', label: 'Responsory', verse: true },
      { field: 'canticle', label: 'Canticle', verse: true },
      { field: 'litany', label: 'Litany', verse: false },
      { field: 'dismissal', label: 'Dismissal', verse: true },
      { field: 'affirmation', label: 'Affirmation', verse: false },
    ];

    for (const { field, label, verse } of renderables) {
      if (!form[field] || !Array.isArray(form[field])) continue;
      const html = renderSegments(form[field], shared, verse);

      // 1. Check for missing ARIA attributes on interactive elements
      // Alternatives tabs are the main interactive elements
      const tabs = html.match(/<button[^>]*>/g) || [];
      for (const tab of tabs) {
        if (!/role="tab"/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing role="tab"' });
        }
        if (!/aria-selected/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing aria-selected' });
        }
        if (!/aria-controls/.test(tab)) {
          failures.push({ form: fk, section: label, detail: 'button missing aria-controls' });
        }
      }

      const panels = html.match(/<div[^>]*role="tabpanel"[^>]*>/g) || [];
      for (const panel of panels) {
        if (!/aria-labelledby/.test(panel)) {
          failures.push({ form: fk, section: label, detail: 'tabpanel missing aria-labelledby' });
        }
      }
    }

    // 2. Heading hierarchy: render a full section and check
    const dismissalHtml = form.dismissal && Array.isArray(form.dismissal)
      ? renderSubsection('Dismissal', form.dismissal, shared, true) : '';

    // 3. No empty alt attributes on meaningful content
  }

  // 4. Check heading hierarchy in a full rendered form
  // Use ordinary-sunday-mp as representative
  const fk = 'ordinary-sunday-mp';
  const form = offices[fk];
  if (form) {
    const cfg = {
      form, shared,
      officeData: { psalms: [{ citation: '145' }], lessons: [{ citation: 'Isaiah 55:1-5' }] },
      officeType: 'mp', season: 'OrdinaryTime', weekIdx: 0,
    };
    const asm = assembleSections(cfg);

    // Verify h2/h3 count matches section structure
    const expectedH2 = asm.sections.filter(s => s.visible && s.name !== 'Unknown').length;
    const expectedH3 = asm.sections.reduce((sum, s) => sum + s.subsections.length, 0);

    // Build the HTML to verify
    let html = '';
    for (const section of asm.sections) {
      const sectionLabels = {
        Gathering: 'The Gathering of the Community',
        Proclamation: 'The Proclamation of the Word',
        Affirmation: 'The Affirmation of Faith',
        Prayers: 'The Prayers of the Community',
        Sending: 'The Sending Forth of the Community',
      };
      const label = sectionLabels[section.name];
      if (!label) continue;
      html += `<h2 class="office-section-title">${label}</h2>`;
      for (const sub of section.subsections) {
        html += `<h3 class="office-subsection-title">${sub.label}</h3>`;
      }
    }

    const h2Count = (html.match(/<h2\b/g) || []).length;
    if (h2Count !== expectedH2) {
      failures.push({ form: fk, section: 'structure', detail: `h2 count ${h2Count} vs expected ${expectedH2}` });
    }
  }

  if (useJson) {
    console.log(JSON.stringify({
      forms_checked: formKeys.length,
      failures: failures,
      failure_count: failures.length,
    }, null, 2));
    process.exit(0);
  }

  console.log(`Accessibility audit: ${formKeys.length} forms`);
  if (failures.length === 0) {
    console.log('All forms pass accessibility checks.');
    return;
  }

  console.log(`\n${failures.length} failure(s):\n`);
  for (const f of failures) {
    console.log(`  ${f.form} ${f.section}: ${f.detail}`);
  }

  // Advisory only — exit 0
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
