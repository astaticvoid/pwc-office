#!/usr/bin/env node
/**
 * tools/audit_text.cjs — cross-form text length outlier detection.
 *
 * Within each peer group, compares text length of shared subsections.
 * A form whose section text is significantly shorter or longer than
 * peers signals a possible extraction artifact.
 *
 * Usage: node tools/audit_text.cjs [--json]
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

function mean(v) { return v.reduce((a, b) => a + b, 0) / v.length; }
function stddev(v, m) { return Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length); }

async function main() {
  const { segmentsToJSON } = await import('../web/render.js');
  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared = offices._shared || {};
  const useJson = process.argv.includes('--json');

  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  // Build per-form text lengths
  const lengths = {};
  for (const key of formKeys) {
    const form = offices[key];
    const items = segmentsToJSON(form, shared);
    const bySection = {};
    for (const item of items) {
      if (item.type === 'rubric' || item.type === 'label') continue;
      if (!bySection[item.section]) bySection[item.section] = 0;
      bySection[item.section] += item.text.length;
    }
    lengths[key] = {
      isMP: key.endsWith('-mp'),
      isEP: key.endsWith('-ep'),
      isOrdinary: key.startsWith('ordinary-'),
      total: Object.values(bySection).reduce((a, b) => a + b, 0),
      ...bySection,
    };
  }

  // Peer groups
  const groups = {
    'seasonal-mp': formKeys.filter(k => lengths[k].isMP && !lengths[k].isOrdinary),
    'seasonal-ep': formKeys.filter(k => lengths[k].isEP && !lengths[k].isOrdinary),
    'ordinary-mp': formKeys.filter(k => lengths[k].isMP && lengths[k].isOrdinary),
    'ordinary-ep': formKeys.filter(k => lengths[k].isEP && lengths[k].isOrdinary),
  };

  const findings = [];
  const sections = ['total', 'dismissal', 'litany', 'opening_responses', 'intercessions', 'seasonal_collects', 'responsory', 'canticle'];

  for (const [groupName, keys] of Object.entries(groups)) {
    if (keys.length < 2) continue;

    for (const section of sections) {
      const values = keys.map(k => lengths[k][section]).filter(v => v !== undefined && v !== null);
      if (values.length < 2) continue;
      const m = mean(values);
      const s = stddev(values, m);
      if (s === 0) continue;

      for (const key of keys) {
        const v = lengths[key][section];
        if (v === undefined || v === null || v === 0) continue;
        const z = Math.abs(v - m) / s;
        if (z > 2.0) {
          findings.push({
            group: groupName,
            form: key,
            metric: section,
            value: v,
            peerMean: Math.round(m),
            peerStddev: Math.round(s),
            zScore: z.toFixed(1),
          });
        }
      }
    }
  }

  if (useJson) {
    console.log(JSON.stringify({
      forms_checked: formKeys.length,
      peer_groups: Object.keys(groups).length,
      findings: findings,
      finding_count: findings.length,
    }, null, 2));
    process.exit(0);
  }

  console.log(`Cross-form text length audit: ${formKeys.length} forms, ${Object.keys(groups).length} peer groups`);
  if (findings.length === 0) {
    console.log('All text lengths within normal range across peer groups.');
    return;
  }

  console.log(`\n${findings.length} finding(s):\n`);
  for (const f of findings) {
    console.log(`  [${f.group}] ${f.form} ${f.metric}: ${f.value} chars (peer mean ${f.peerMean}±${f.peerStddev}, z=${f.zScore})`);
  }

  // Advisory only — exit 0
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
