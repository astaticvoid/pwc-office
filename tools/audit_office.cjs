#!/usr/bin/env node
/**
 * tools/audit_office.cjs — cross-form statistical audit.
 *
 * Renders all 30 forms to structured JSON, extracts structural metrics,
 * and flags outliers within peer groups (seasonal MP, seasonal EP,
 * ordinary MP, ordinary EP).
 *
 * Usage: node tools/audit_office.cjs
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');
const root = join(dirname(__filename), '..');

function mean(values) { return values.reduce((a, b) => a + b, 0) / values.length; }
function stddev(values, m) {
  if (values.length < 2) return 0;
  const sq = values.reduce((a, b) => a + (b - m) ** 2, 0) / values.length;
  return Math.sqrt(sq);
}

async function main() {
  const { segmentsToJSON } = await import('../web/render.js');
  const offices = JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
  const shared  = offices._shared || {};

  const formKeys = Object.keys(offices).filter(k => !k.startsWith('_'));

  // ── Extract metrics per form ─────────────────────────────────────────
  const metrics = {};
  for (const key of formKeys) {
    const form = offices[key];
    const items = segmentsToJSON(form, shared);

    const sections = new Set(items.map(i => i.section));
    const byType = {};
    const bySection = {};
    for (const i of items) {
      byType[i.type] = (byType[i.type] || 0) + 1;
      bySection[i.section] = (bySection[i.section] || 0) + 1;
    }

    metrics[key] = {
      key,
      isMP: key.endsWith('-mp'),
      isEP: key.endsWith('-ep'),
      isOrdinary: key.startsWith('ordinary-'),
      isSeasonal: !key.startsWith('ordinary-'),
      totalSegments: items.length,
      leaderCount: byType.leader || 0,
      responseCount: byType.response || 0,
      rubricCount: byType.rubric || 0,
      sectionCount: sections.size,
      hasAffirmation: sections.has('affirmation'),
      hasCollects: sections.has('seasonal_collects'),
      hasInvitation: sections.has('invitatory'),
      hasPhosHilaron: sections.has('phos_hilaron'),
      hasThanksgiving: sections.has('thanksgiving_for_light'),
      litanySegments: bySection.litany || 0,
      openingSegments: bySection.opening_responses || 0,
      dismissalSegments: bySection.dismissal || 0,
      collectSegments: bySection.seasonal_collects || 0,
    };
  }

  // ── Group forms into peer categories ─────────────────────────────────
  const groups = {
    'seasonal-mp': Object.values(metrics).filter(m => m.isSeasonal && m.isMP),
    'seasonal-ep': Object.values(metrics).filter(m => m.isSeasonal && m.isEP),
    'ordinary-mp': Object.values(metrics).filter(m => m.isOrdinary && m.isMP),
    'ordinary-ep': Object.values(metrics).filter(m => m.isOrdinary && m.isEP),
  };

  // ── Compute stats and flag outliers per metric ──────────────────────
  const metricNames = ['totalSegments', 'leaderCount', 'responseCount',
    'rubricCount', 'sectionCount', 'litanySegments', 'openingSegments',
    'dismissalSegments', 'collectSegments'];

  const outliers = [];

  for (const [groupName, groupForms] of Object.entries(groups)) {
    for (const metricName of metricNames) {
      const values = groupForms.map(f => f[metricName]).filter(v => v > 0);
      if (values.length < 2) continue;
      const m = mean(values);
      const s = stddev(values, m);
      if (s === 0) continue; // no variance

      for (const form of groupForms) {
        const v = form[metricName];
        if (v === 0 || v === undefined) continue;
        const z = Math.abs(v - m) / s;
        if (z > 2.0) {
          outliers.push({
            group: groupName,
            form: form.key,
            metric: metricName,
            value: v,
            peerMean: Math.round(m),
            peerStddev: Math.round(s),
            zScore: z.toFixed(1),
          });
        }
      }
    }
  }

  // ── Boolean metrics (presence/absence) ───────────────────────────────
  const boolMetrics = ['hasAffirmation', 'hasCollects', 'hasInvitation',
    'hasPhosHilaron', 'hasThanksgiving'];

  for (const [groupName, groupForms] of Object.entries(groups)) {
    for (const metricName of boolMetrics) {
      const trues = groupForms.filter(f => f[metricName]).length;
      const falses = groupForms.length - trues;
      // Flag if minority behavior exists (1-2 forms differ from majority)
      if (trues > 0 && falses > 0 && Math.min(trues, falses) <= 2) {
        const minority = groupForms.filter(f => f[metricName] !== (trues > falses));
        for (const form of minority) {
          outliers.push({
            group: groupName,
            form: form.key,
            metric: metricName,
            value: form[metricName],
            peerMajority: trues > falses,
            detail: `${groupForms.length - minority.length}/${groupForms.length} peers have it`,
          });
        }
      }
    }
  }

  // ── Report ───────────────────────────────────────────────────────────
  console.log(`Cross-form audit: ${formKeys.length} forms, ${Object.keys(groups).length} peer groups, ${metricNames.length + boolMetrics.length} metrics\n`);

  if (outliers.length === 0) {
    console.log('No outliers detected. All forms are within expected ranges.');
    return;
  }

  // Group by form
  const byForm = {};
  for (const o of outliers) {
    byForm[o.form] = (byForm[o.form] || []).push(o) && byForm[o.form] || [o];
  }

  console.log(`${outliers.length} outlier(s) across ${Object.keys(byForm).length} form(s):\n`);
  for (const [form, items] of Object.entries(byForm)) {
    console.log(`  ${form}:`);
    for (const item of items) {
      if (item.zScore) {
        console.log(`    ${item.metric}: ${item.value} (peer avg ${item.peerMean}±${item.peerStddev}, z=${item.zScore})`);
      } else {
        console.log(`    ${item.metric}: ${item.value} (${item.detail})`);
      }
    }
    console.log();
  }

  process.exit(1);
}

main().catch(e => { console.error(e.message); process.exit(1); });
