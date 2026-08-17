#!/usr/bin/env node
/**
 * tools/audit_rubric_repeats.cjs — rubric self-consistency audit.
 *
 * Compares the corpus against itself, the same idea as check_conservation.py
 * (#94) applied to rubrics instead of extracted text:
 *
 * 1. Within one form, does any rubric print more than once? A form that
 *    prints the same cue twice is printing a copy-paste leftover, since
 *    nothing in the book repeats a rubric verbatim within one office.
 * 2. Across the 30 forms, does one form's doxology cue disagree with every
 *    other form's? Real phrasing variation (seasonal "At the end of the
 *    Canticle" vs. ordinary "After the Canticle", Pentecost's "either
 *    Canticle") always spans at least an MP/EP pair; a phrasing that no
 *    other form shares is a typo, not a variant.
 *
 * Found #97 (Ordinary Tuesday/Wednesday EP) with zero false positives across
 * the rest of the corpus. Advisory only — exit 0.
 *
 * Usage: node tools/audit_rubric_repeats.cjs [--json]
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

// The rubric immediately before each shared doxology is its cue ("At the end
// of the Canticle...", "After the Psalm..."). Mirrors the shape splitPsalmRubrics
// (web/render.js) already relies on, but the canticle field has no such export.
// Collects every occurrence, not just the first — a form with two canticles
// would otherwise have its second cue go unchecked.
function doxologyCuesOf(segs) {
  if (!Array.isArray(segs)) return [];
  const cues = [];
  segs.forEach((s, idx) => {
    if (s.type === 'shared' && s.key === 'doxology' && idx > 0 && segs[idx - 1].type === 'rubric') {
      cues.push(segs[idx - 1].text);
    }
  });
  return cues;
}

async function main() {
  const { segmentsToJSON, splitPsalmRubrics } = await import('../web/render.js');
  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared = offices._shared || {};
  const useJson = process.argv.includes('--json');

  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  // ── 1. Rubric text repeated within one form ──────────────────────────────
  const repeats = [];
  for (const key of formKeys) {
    const items = segmentsToJSON(offices[key], shared);
    const counts = {};
    for (const item of items) {
      if (item.type !== 'rubric') continue;
      counts[item.text] = (counts[item.text] || 0) + 1;
    }
    for (const [text, count] of Object.entries(counts)) {
      if (count > 1) repeats.push({ form: key, text, count });
    }
  }

  // ── 2. Doxology cue phrasing that no other form shares ───────────────────
  // Clusters by distinct form, not by occurrence: a form repeating its own
  // cue twice must not look like corroboration from a second form.
  function outliers(label, textsOf) {
    const clusters = {};
    for (const key of formKeys) {
      for (const text of textsOf(offices[key])) {
        (clusters[text] ||= new Set()).add(key);
      }
    }
    const findings = [];
    for (const [text, forms] of Object.entries(clusters)) {
      if (forms.size === 1) findings.push({ cue: label, form: [...forms][0], text });
    }
    return findings;
  }

  const cueOutliers = [
    ...outliers('canticle-doxology', f => doxologyCuesOf(f.canticle)),
    ...outliers('psalm-doxology', f => {
      const { doxologyCue } = splitPsalmRubrics(f.psalm_rubrics || []);
      const text = doxologyCue.map(s => s.text).join(' ');
      return text ? [text] : [];
    }),
  ];

  const findings = [
    ...repeats.map(r => ({ kind: 'repeated-within-form', ...r })),
    ...cueOutliers.map(o => ({ kind: 'cue-disagrees-with-corpus', ...o })),
  ];

  if (useJson) {
    console.log(JSON.stringify({ forms_checked: formKeys.length, findings }, null, 2));
    process.exit(0);
  }

  console.log(`Rubric repeat/consistency audit: ${formKeys.length} forms`);
  if (findings.length === 0) {
    console.log('No repeated or anomalous rubrics found.');
    return;
  }

  console.log(`\n${findings.length} finding(s):\n`);
  for (const f of findings) {
    if (f.kind === 'repeated-within-form') {
      console.log(`  [repeat] ${f.form}: "${f.text}" prints ${f.count} times`);
    } else {
      console.log(`  [outlier] ${f.form} (${f.cue}): "${f.text}" — no other form matches`);
    }
  }

  // Advisory only — exit 0
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
