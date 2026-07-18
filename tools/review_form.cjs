#!/usr/bin/env node
/**
 * tools/review_form.cjs — render a single office form as numbered text for review.
 *
 * Usage: node tools/review_form.cjs FORM [YYYY-MM-DD]
 *   node tools/review_form.cjs advent-mp 2025-12-07
 *
 * Outputs the full office text with line numbers, suitable for marking issues.
 */
const { readFileSync } = require('fs');
const { join, dirname } = require('path');

const root = join(dirname(__filename), '..');
const load = p => JSON.parse(readFileSync(join(root, p), 'utf8'));

const offices = load('data/offices.json');
const shared  = offices._shared || {};

const formName = process.argv[2] || 'ordinary-sunday-ep';
const dateStr  = process.argv[3] || new Date().toISOString().slice(0, 10);

const form = offices[formName];
if (!form) {
  console.error(`Unknown form: ${formName}`);
  console.error('Available:', Object.keys(offices).filter(k => !k.startsWith('_')).sort().join(', '));
  process.exit(1);
}

// Dynamically import ESM render.js
(async () => {
  const { renderSegmentsText, blocksToString } = await import('../web/render.js');

  const BK = {
    verse: false,
    showLabel: true,
    skipRubrics: /continues with|may conclude with|^The Litany is said or sung\./i,
    skipShortLabels: true,
    condenseRubrics: {
      'The community may offer': 'Offer intercessions, petitions, and thanksgivings, silently or aloud.',
    },
  };

  function text(segs, opts = {}) {
    return blocksToString(renderSegmentsText(segs, shared, { ...BK, ...opts }));
  }

  function resolve(field) {
    if (field?.type === 'shared' && shared) return shared[field.key];
    return field || [];
  }

  console.log(`# ${formName} — ${dateStr}`);
  if (form.subtitle) console.log(form.subtitle);
  console.log();

  let lineNum = 0;
  function section(title, segs, opts) {
    console.log(`${title}`);
    const t = text(segs, opts);
    if (t) {
      for (const l of t.split('\n')) {
        lineNum++;
        const n = String(lineNum).padStart(4);
        console.log(`${n} │ ${l}`);
      }
    }
    console.log();
  }

  const opening = resolve(form.opening_responses);
  section('Opening Responses', opening.filter(s => !(s.type === 'shared' && s.key === 'doxology')));
  if (shared.doxology && opening.some(s => s.type === 'shared' && s.key === 'doxology')) {
    section('Doxology', [shared.doxology], { alleluia: true });
  }

  if (form.thanksgiving_for_light) section('Thanksgiving for Light', form.thanksgiving_for_light);
  if (form.phos_hilaron) section('Phos Hilaron', form.phos_hilaron);
  if (form.invitatory) section('Invitatory', form.invitatory);

  section('Responsory', form.responsory);
  section('Canticle', form.canticle, { showLabel: true });
  section('Affirmation', form.affirmation, { showLabel: true });

  if (form.intercessions) section('Intercessions', form.intercessions);

  section('Litany', form.litany);

  if (form.seasonal_collects) {
    section('Seasonal Collects', form.seasonal_collects, { joinLines: true });
  }

  section('Lord\'s Prayer Intro', form.lords_prayer_intro);
  section('Dismissal', form.dismissal);

})();
