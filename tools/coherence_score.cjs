#!/usr/bin/env node
/**
 * tools/coherence_score.cjs — composite liturgical quality score.
 *
 * Reads JSON output from validate_office.cjs --json and audit_office.cjs --json,
 * computes a 0-100 score from rule failures and audit outliers.
 *
 * Usage:
 *   node tools/coherence_score.cjs <validate.json> <audit.json>
 *   Exit 0 if score >= 85, exit 1 if below threshold.
 *   Use --check-promote flag for promote-gate use (no output, just exit code).
 */

const { readFileSync } = require('fs');
const { join, dirname } = require('path');

const THRESHOLD = parseInt(process.env.COHERENCE_THRESHOLD || '85');

// Load expected outlier exemptions
let expectedOutliers = [];
try {
  const expPath = join(dirname(__filename), 'audit_expected.json');
  expectedOutliers = JSON.parse(readFileSync(expPath, 'utf8')).expected_outliers || [];
} catch (_) { /* file missing — treat as empty */ }

// Tier penalties
const PENALTY = {
  tier1: 10,
  tier2: 3,
  tier3: 5,
  audit_z25: 5,
  audit_z30: 15,
  audit_bool: 5,
};

function main() {
  const args = process.argv.slice(2);
  const checkPromote = args.includes('--check-promote');
  const files = args.filter(a => !a.startsWith('--'));

  if (files.length < 2) {
    console.error('Usage: node tools/coherence_score.cjs <validate.json> <audit.json>');
    process.exit(2);
  }

  const [valFile, audFile] = files;

  let validate, audit;
  try {
    validate = JSON.parse(readFileSync(valFile, 'utf8'));
  } catch (e) {
    console.error(`Failed to read ${valFile}: ${e.message}`);
    process.exit(2);
  }
  try {
    audit = JSON.parse(readFileSync(audFile, 'utf8'));
  } catch (e) {
    console.error(`Failed to read ${audFile}: ${e.message}`);
    process.exit(2);
  }

  // ── Compute per-form penalties ──────────────────────────────────────
  const penalties = {};

  // From validator — tiered failures per form
  for (const f of (validate.failures || [])) {
    const key = f.form || '__global__';
    if (!penalties[key]) penalties[key] = 0;
    const tierKey = `tier${f.tier}`;
    penalties[key] += PENALTY[tierKey] || 0;
  }

  // From audit — z-score outliers and boolean minority flags
  // Filter out expected outliers (documented structural variance)
  for (const o of (audit.outliers || [])) {
    const key = o.form || '__global__';
    if (!penalties[key]) penalties[key] = 0;

    // Check if this outlier is expected
    const isExpected = expectedOutliers.some(
      e => e.form === o.form && e.metric === o.metric
    );
    if (isExpected) continue;

    if (o.zScore) {
      const z = parseFloat(o.zScore);
      if (z >= 3.0) penalties[key] += PENALTY.audit_z30;
      else penalties[key] += PENALTY.audit_z25;
    } else if (o.detail) {
      penalties[key] += PENALTY.audit_bool;
    }
  }

  // ── Compute scores ──────────────────────────────────────────────────
  let minScore = 100;
  const perForm = {};

  for (const [form, penalty] of Object.entries(penalties)) {
    const score = Math.max(0, 100 - penalty);
    perForm[form] = { penalty, score };
    if (score < minScore) minScore = score;
  }

  if (Object.keys(penalties).length === 0) {
    minScore = 100;
  }

  // ── Output ───────────────────────────────────────────────────────────
  if (checkPromote) {
    if (minScore >= THRESHOLD) {
      process.exit(0);
    } else {
      console.error(`Coherence score ${minScore} is below threshold (${THRESHOLD}).`);
      for (const [form, info] of Object.entries(perForm)) {
        if (info.score < THRESHOLD) {
          console.error(`  ${form}: ${info.score} (penalty: -${info.penalty})`);
        }
      }
      process.exit(1);
    }
  }

  console.log(`Coherence score: ${minScore}/100 (threshold: ${THRESHOLD})`);
  if (Object.keys(perForm).length) {
    for (const [form, info] of Object.entries(perForm)) {
      if (info.penalty > 0) {
        console.log(`  ${form}: ${info.score} (-${info.penalty})`);
      }
    }
  }
  console.log(`  Status: ${minScore >= THRESHOLD ? 'PASS' : 'FAIL'}`);
  process.exit(minScore >= THRESHOLD ? 0 : 1);
}

main();
