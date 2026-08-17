#!/usr/bin/env node
/**
 * tools/test_rule_mutations.cjs — permanent mutation tests for validate_office.cjs rules.
 *
 * For each case below, apply one targeted violation to a temp copy of the
 * data (or, for the render-error case, a patched copy of web/render.js),
 * run the real validator against it in an isolated harness, and assert the
 * rule actually fires. Grew out of the manual, throwaway mutation harness
 * used to investigate #70, which found two rules that could not fail on the
 * exact input their name describes — intercessions-nonempty and
 * non-empty-responses (both fixed; see git history for non-empty-responses,
 * fixed as #72) — and #71, where a thrown dynamic render was swallowed with
 * no failure and no exit code (fixed).
 *
 * Coverage: all 10 static (qa_dates-independent) rules assert a rule fires,
 * plus 3 of the 10 dynamic rules (intercessions-nonempty,
 * canticle-has-verse-content, evening-has-light). The other 7 dynamic rules
 * have no entry here at all — not asserted and not documented as a gap,
 * same as any rule added after this file. main() prints which rules that is
 * on every run rather than hand-counting it in this comment, so the number
 * can't quietly drift out of date. KNOWN_GAPS documents rules found to be
 * unfalsifiable by construction — empty today, but kept as a mechanism.
 *
 * Usage: node tools/test_rule_mutations.cjs
 */

const { execFileSync } = require('child_process');
const { mkdtempSync, rmSync, symlinkSync, mkdirSync, writeFileSync, readFileSync, copyFileSync, readdirSync } = require('fs');
const { join } = require('path');
const os = require('os');

const root = join(__dirname, '..');

// ── Harness ──────────────────────────────────────────────────────────────

function freshOffices() {
  return JSON.parse(readFileSync(join(root, 'data/offices.json'), 'utf8'));
}

// Recurses into 'alternatives' groups (offices.json's only nesting below a
// field) so a mutation lands regardless of which alternative gets rendered.
// Skips 'shared' siblings (e.g. a trailing doxology ref) rather than
// mutating them — every case below targets content the form owns outright,
// not shared content other forms would be silently mutated through too.
// Deliberately not web/render.js's walkSegments: that resolves 'shared' by
// inlining and recursing into it, which is right for rendering but wrong
// here — it would make every mutation silently touch _shared, affecting
// every other form that references it, not just the one under test. The
// two cases that do need to mutate through the shared doxology
// (mutateFieldAndDoxology below) do so explicitly, on purpose, one field
// at a time.
function walkMutable(segs, fn) {
  for (const seg of segs) {
    if (seg.type === 'shared') continue;
    if (seg.type === 'alternatives') {
      for (const g of seg.groups) walkMutable(g.segments, fn);
      continue;
    }
    fn(seg);
  }
}

function mutateAll(segs, predicate, mutate) {
  let count = 0;
  walkMutable(segs, seg => { if (predicate(seg)) { mutate(seg); count++; } });
  return count;
}

function mutateFirst(segs, predicate, mutate) {
  let done = false;
  walkMutable(segs, seg => { if (!done && predicate(seg)) { mutate(seg); done = true; } });
  return done;
}

// Flips the type of the first segment that breaks leader/response
// alternation, structurally rather than by matching specific wording, so it
// survives future text edits to the liturgical content. Goes through
// walkMutable (rather than reading `list` directly) so it gets the same
// alternatives-recursion and shared-skip behaviour as every other mutator
// here, in case the target field ever grows either.
function breakAlternation(list) {
  const flat = [];
  walkMutable(list, seg => flat.push(seg));
  const nonRubric = flat.filter(s => s.type !== 'rubric');
  for (let i = 0; i + 1 < nonRubric.length; i++) {
    if (nonRubric[i].type !== nonRubric[i + 1].type) {
      nonRubric[i + 1].type = nonRubric[i].type;
      return true;
    }
  }
  return false;
}

// opening_responses and canticle both trail the shared doxology (a leader+
// response pair) as a sibling of their own content, so mutating only the
// form's own segments leaves the rule passing via the doxology's copy. This
// mutates both — in this run's temp copy only — to actually falsify the
// subsection.
function mutateFieldAndDoxology(offices, form, fieldName, predicate, mutate) {
  const n1 = mutateAll(form[fieldName], predicate, mutate);
  const n2 = mutateAll(offices._shared.doxology.groups.flatMap(g => g.segments), predicate, mutate);
  if (n1 === 0 || n2 === 0) throw new Error('mutation found nothing to change');
}

// Empties every response segment in the corpus, including through _shared —
// the exact reproduction from #70's investigation of non-empty-responses.
function emptyAllResponsesInCorpus(offices) {
  function walk(segs) {
    if (!segs) return;
    if (!Array.isArray(segs)) {
      if (segs.type === 'shared') return; // covered separately via offices._shared
      segs = [segs];
    }
    for (const seg of segs) {
      if (seg.type === 'alternatives') { for (const g of seg.groups) walk(g.segments); continue; }
      if (seg.type === 'response') seg.text = '';
    }
  }
  for (const [fk, form] of Object.entries(offices)) {
    if (fk === '_shared') continue;
    for (const v of Object.values(form)) walk(v);
  }
  for (const v of Object.values(offices._shared || {})) walk(v);
}

function runValidator({ officesMutator = null, renderPatch = null } = {}) {
  const dir = mkdtempSync(join(os.tmpdir(), 'pwc-mutation-'));
  try {
    mkdirSync(join(dir, 'tools'));
    copyFileSync(join(root, 'tools/validate_office.cjs'), join(dir, 'tools/validate_office.cjs'));
    copyFileSync(join(root, 'tools/qa_dates.json'), join(dir, 'tools/qa_dates.json'));

    mkdirSync(join(dir, 'data'));
    for (const entry of readdirSync(join(root, 'data'))) {
      if (entry === 'offices.json') continue;
      symlinkSync(join(root, 'data', entry), join(dir, 'data', entry));
    }
    const offices = freshOffices();
    if (officesMutator) officesMutator(offices);
    writeFileSync(join(dir, 'data/offices.json'), JSON.stringify(offices));

    if (renderPatch) {
      mkdirSync(join(dir, 'web'));
      for (const entry of readdirSync(join(root, 'web'))) {
        if (entry === 'render.js') continue;
        symlinkSync(join(root, 'web', entry), join(dir, 'web', entry));
      }
      writeFileSync(join(dir, 'web/render.js'), renderPatch(readFileSync(join(root, 'web/render.js'), 'utf8')));
    } else {
      symlinkSync(join(root, 'web'), join(dir, 'web'));
    }

    // Always --json: rule failures and render errors exit 0 (documented
    // contract). That does NOT cover a rule.check() itself throwing —
    // static-pass rules run with no try/catch (unlike the dynamic pass), so
    // a mutation that breaks a rule's own assumptions propagates through
    // main()'s top-level catch and exits 1 regardless of --json. Each CASE
    // below is written to avoid that; if one starts throwing here instead of
    // failing its check(), the mutation shape is the bug, not this harness.
    const out = execFileSync('node', ['tools/validate_office.cjs', '--json'], { cwd: dir, encoding: 'utf8' });
    return JSON.parse(out);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

function hasFailure(result, rule, form) {
  return result.failures.some(f => f.rule === rule && f.form === form);
}

// ── Cases: each must make its named rule fire on its named form ───────────

const CASES = [
  {
    name: '#71 regression: thrown dynamic render is reported, not swallowed',
    rule: null, // not one of validate_office.cjs's 20 rules — excluded from the coverage report below
    run: () => runValidator({
      renderPatch: src => src.replace(
        'export function assembleSections(cfg) {',
        'export function assembleSections(cfg) {\n  throw new Error("mutation: forced render failure");'
      ),
    }),
    check: result => result.render_errors.length > 0,
  },
  {
    name: 'intercessions-nonempty fires when intercessions is emptied (not just absent)',
    rule: 'intercessions-nonempty',
    run: () => runValidator({
      officesMutator: offices => { offices['ordinary-sunday-mp'].intercessions = []; },
    }),
    check: result => hasFailure(result, 'intercessions-nonempty', 'ordinary-sunday-mp'),
  },
  {
    name: 'dismissal-has-amen',
    rule: 'dismissal-has-amen',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        const n = mutateAll(form.dismissal, seg => seg.type !== 'rubric' && /Amen/.test(seg.text),
          seg => { seg.text = seg.text.replace(/\s*Amen\.?/g, ''); });
        if (n === 0) throw new Error('mutation found nothing to change');
      },
    }),
    check: result => hasFailure(result, 'dismissal-has-amen', 'ordinary-sunday-mp'),
  },
  {
    name: 'no-stray-space-before-period',
    rule: 'no-stray-space-before-period',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        if (!mutateFirst(form.dismissal, seg => seg.type === 'leader', seg => { seg.text = 'Let us bless the Lord .'; })) {
          throw new Error('mutation found nothing to change');
        }
      },
    }),
    check: result => hasFailure(result, 'no-stray-space-before-period', 'ordinary-sunday-mp'),
  },
  {
    name: 'opening-has-leader-and-response',
    rule: 'opening-has-leader-and-response',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        mutateFieldAndDoxology(offices, form, 'opening_responses', seg => seg.type === 'response', seg => { seg.type = 'rubric'; });
      },
    }),
    check: result => hasFailure(result, 'opening-has-leader-and-response', 'ordinary-sunday-mp'),
  },
  {
    name: 'no-empty-segments',
    rule: 'no-empty-segments',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        if (!mutateFirst(form.litany, seg => seg.type !== 'rubric', seg => { seg.text = 'N'; })) {
          throw new Error('mutation found nothing to change');
        }
      },
    }),
    check: result => hasFailure(result, 'no-empty-segments', 'ordinary-sunday-mp'),
  },
  {
    name: 'leader-response-alternation',
    rule: 'leader-response-alternation',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        if (!breakAlternation(form.litany)) throw new Error('mutation found nothing to change');
      },
    }),
    check: result => hasFailure(result, 'leader-response-alternation', 'ordinary-sunday-mp'),
  },
  {
    name: 'no-prose-line-breaks',
    rule: 'no-prose-line-breaks',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        const ok = mutateFirst(form.seasonal_collects, seg => seg.type === 'leader',
          seg => { seg.text = 'A line that keeps going\nwithout closing punctuation before the break'; });
        if (!ok) throw new Error('mutation found nothing to change');
      },
    }),
    check: result => hasFailure(result, 'no-prose-line-breaks', 'ordinary-sunday-mp'),
  },
  {
    name: 'phos-hilaron-line-count',
    rule: 'phos-hilaron-line-count',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-ep'];
        const ok = mutateFirst(form.phos_hilaron, seg => seg.type === 'leader',
          seg => { seg.text = 'A single test line with no stanza breaks.'; });
        if (!ok) throw new Error('mutation found nothing to change');
      },
    }),
    check: result => hasFailure(result, 'phos-hilaron-line-count', 'ordinary-sunday-ep'),
  },
  {
    name: 'seasonal-title-coherence',
    rule: 'seasonal-title-coherence',
    run: () => runValidator({
      officesMutator: offices => { offices['advent-mp'].title = ''; },
    }),
    check: result => hasFailure(result, 'seasonal-title-coherence', 'advent-mp'),
  },
  {
    name: 'no-orphan-rubrics',
    rule: 'no-orphan-rubrics',
    run: () => runValidator({
      officesMutator: offices => {
        offices['ordinary-sunday-mp'].litany.push({ type: 'rubric', text: 'This is an orphan rubric injected for a mutation test.' });
      },
    }),
    check: result => hasFailure(result, 'no-orphan-rubrics', 'ordinary-sunday-mp'),
  },
  {
    name: 'canticle-has-verse-content',
    rule: 'canticle-has-verse-content',
    run: () => runValidator({
      officesMutator: offices => {
        const form = offices['ordinary-sunday-mp'];
        mutateFieldAndDoxology(offices, form, 'canticle', seg => seg.type === 'leader', seg => { seg.type = 'response'; });
      },
    }),
    check: result => hasFailure(result, 'canticle-has-verse-content', 'ordinary-sunday-mp'),
  },
  {
    name: 'evening-has-light',
    rule: 'evening-has-light',
    run: () => runValidator({
      officesMutator: offices => { offices['ordinary-sunday-ep'].phos_hilaron = []; },
    }),
    check: result => hasFailure(result, 'evening-has-light', 'ordinary-sunday-ep'),
  },
  {
    name: 'non-empty-responses fires when every response in the corpus is emptied (regression for #72)',
    rule: 'non-empty-responses',
    // The rule reads raw form segments, ahead of web/render.js's
    // empty-segment filter, so emptying every response in the corpus —
    // including through _shared — must make it fire (#70, #72).
    run: () => runValidator({ officesMutator: emptyAllResponsesInCorpus }),
    check: result => result.failures.some(f => f.rule === 'non-empty-responses'),
  },
];

// ── Known gaps: documented, not asserted ───────────────────────────────────
// Currently empty. Kept as a mechanism (rather than removed) for the next
// rule that turns out to be unfalsifiable by construction — non-empty-
// responses lived here until the fix in this commit; see git history for
// the write-up if a case needs the same treatment again.
const KNOWN_GAPS = [];

// ── Coverage check ──────────────────────────────────────────────────────────
// Reads rule names directly out of validate_office.cjs rather than
// hand-maintaining a count in a comment (which is exactly how #70 happened:
// a rule silently lost the ability to fail and nothing said so). A rule
// present here with neither a CASE nor a KNOWN_GAPS entry is a rule this
// file makes no claim about at all — printed, not failed, since adding a
// rule shouldn't be blocked on writing a mutation for it in the same PR.
function allRuleNamesIn(validateSrc) {
  const names = [];
  const re = /rules\.push\(\{\s*name:\s*'([^']+)'/g;
  let m;
  while ((m = re.exec(validateSrc))) names.push(m[1]);
  return names;
}

// ── Run ──────────────────────────────────────────────────────────────────

function main() {
  let failed = 0;
  for (const c of CASES) {
    process.stdout.write(`  ${c.name} ... `);
    try {
      const result = c.run();
      if (c.check(result)) {
        console.log('ok');
      } else {
        console.log('FAILED (rule did not fire on its targeted mutation)');
        failed++;
      }
    } catch (e) {
      console.log(`FAILED (${e.message})`);
      failed++;
    }
  }

  if (KNOWN_GAPS.length) {
    console.log('\nKnown gaps (informational, not scored):');
    for (const g of KNOWN_GAPS) {
      process.stdout.write(`  ${g.name} ... `);
      try {
        const result = g.run();
        console.log(g.stillGap(result) ? 'still a gap' : 'NOTE: this now fires — consider promoting it to CASES and updating the comment above');
      } catch (e) {
        console.log(`could not evaluate (${e.message})`);
      }
    }
  }

  console.log(`\n${CASES.length - failed}/${CASES.length} mutation cases passed.`);

  const covered = new Set([...CASES, ...KNOWN_GAPS].map(c => c.rule).filter(Boolean));
  const validateSrc = readFileSync(join(root, 'tools/validate_office.cjs'), 'utf8');
  const uncovered = allRuleNamesIn(validateSrc).filter(n => !covered.has(n));
  if (uncovered.length) {
    console.log(`\n${uncovered.length} rule(s) in validate_office.cjs have no CASE or KNOWN_GAPS entry here: ${uncovered.join(', ')}`);
  }

  if (failed) process.exit(1);
}

main();
