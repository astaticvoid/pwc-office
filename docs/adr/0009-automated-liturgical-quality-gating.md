# ADR 0009: Automated liturgical quality gating

## Status
Proposed

## Context

Today, liturgical quality is assessed manually. A human runs three tools
independently and decides whether output is acceptable:

| Tool | Scope | Exit code |
|------|-------|-----------|
| `validate_office.cjs` | 6 rules across 30 static forms | 1 on any failure |
| `audit_office.cjs` | 14 metrics × 4 peer groups (z-score) | 0 still reports outliers |
| `check_text_quality.py` | PDF extraction artifacts | 0 unless `--strict` |

Problems:
- No CI integration — `make test` runs Vitest but not these tools. A PR can
  break liturgical rendering and pass CI.
- No aggregate signal — three tools produce three independent pass/fail
  judgments. There is no single "is this release safe to promote?" answer.
- Rule coverage is narrow — structural presence checks catch surface errors but
  miss formatting issues, seasonal coherence, and dynamic data integrity.
- No promotion gate — `make promote` deploys regardless of validation state.

### Alternatives considered

**A. Pass/fail gate only.** Wire `validate_office.cjs` into `make test` and
block promotion on any Tier 1 failure. No scoring, no tiers.

*Rejected:* Too coarse. One formatting warning shouldn't block a deploy.
Lossy — the signal from `audit_office.cjs` (statistical outliers) and
`check_text_quality.py` is discarded.

**B. Separate gates for each tool.** Each tool has its own threshold; promote
requires all gates pass. No composite score.

*Rejected:* Fragments the quality signal. A potential deployer must check 3+
separate conditions. No way to express "one Tier 3 warning is fine, but 5 plus
an audit outlier needs attention."

**C. Weighted composite score with promote gate.** Combine signals from all QA
tools into a single 0–100 score. Gate promotion on a threshold. Tier rules
by severity. Provide an override for false positives.

*Selected.*

## Decision

### Three-tier rule classification

Rules are classified by liturgical severity into three tiers:

| Tier | Label | Meaning | Score penalty |
|------|-------|---------|---------------|
| 1 | Structural | Liturgical error — blocks correct worship | −10 |
| 2 | Format | Rendering artifact — cosmetic but visible | −3 |
| 3 | Seasonal | Seasonal coherence — informational check | −5 |

A rule that fires incorrectly can be downgraded (Tier 1 → Tier 2) without
changing the scoring architecture.

### Composite coherence score

```
S = max(0, 100 − Σ penalties)
```

Penalties accumulate from four signal sources:

| Signal | Penalty | Source |
|--------|---------|--------|
| Tier 1 rule failure | −10 | `validate_office.cjs --json` |
| Tier 2 rule failure | −3 | `validate_office.cjs --json` |
| Tier 3 rule failure | −5 | `validate_office.cjs --json` |
| Audit z > 2.0 outlier | −5 | `audit_office.cjs --json` |
| Audit z > 3.0 outlier | −15 | `audit_office.cjs --json` |
| Audit boolean minority | −5 | `audit_office.cjs --json` |
| Text quality finding (strict) | −2 | `check_text_quality.py --strict` exit |

Penalties are computed per form. The aggregate score is the **minimum per-form
score** (weakest-link model: one broken form blocks promotion), minus any
global text-quality penalties.

### Promotion gate

`make promote` checks the coherence score. Score ≥ 85 required to proceed.
Blocked promotion prints the score and failing rules, and suggests `make
rollback` or fixing the data.

**Override:** `PROMOTE_FORCE=1 make promote` bypasses the gate. This handles
false-positive audit outliers (z-score blips from normal variation) that
shouldn't block an urgent deploy.

### CI integration

```makefile
qa:
	@node tools/validate_office.cjs --json > /tmp/pwc-validate.json
	@node tools/audit_office.cjs --json > /tmp/pwc-audit.json
	@node tools/coherence_score.cjs /tmp/pwc-validate.json /tmp/pwc-audit.json
	@rm -f /tmp/pwc-validate.json /tmp/pwc-audit.json

test: test-unit test-tools qa
```

**`--json` mode contract:**

- `validate_office.cjs --json` writes JSON to stdout: `{ forms_checked, rules_checked, failures: [...], perFormScores: {...} }`. Always exits 0. Without `--json`, retains current human-readable output and exit code (1 on failures).
- `audit_office.cjs --json` writes JSON to stdout: `{ forms_checked, groups: [...], outliers: [...] }`. Always exits 0. Without `--json`, retains current output.
- `coherence_score.cjs` reads the JSON files, computes S, prints `score: N`. Exits 0 if S ≥ 85, exits 1 if below.

**Validation date strategy:**

Validators test all 30 forms against one representative date per seasonal
period. A `tools/qa_dates.json` file maps season → date → form keys:

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

Each date loads one `data/lectionary/YYYY-MM.json` file. Forms sharing the same
date reuse the cached lectionary data. Ordinary Time forms need 7 distinct
dates (one per weekday) to cover all 14 weekday variants.

### Rule suite overview

16 rules across 3 tiers. Full details in `docs/qa-strategy-spec.md`.

**Tier 1 (structural, 10 rules):** `dismissal-has-amen`,
`no-stray-space-before-period`, `non-empty-responses`,
`opening-has-leader-and-response`, `no-empty-segments`,
`canticle-has-verse-content`, `evening-has-light`,
`leader-response-alternation`, `psalter-gloria-present`,
`reading-response-present`, `collect-resolvable`.

**Tier 2 (format, 6 rules):** `no-prose-line-breaks`, `canticle-has-verse-breaks`,
`collect-and-dismissal-no-orphan-breaks`, `seasonal-title-coherence`,
`no-orphan-rubrics`, `intercessions-nonempty`.

**Tier 3 (seasonal, 4 rules):** `advent-epiphany-canticles`,
`lent-easter-canticles`, `ordinary-time-defaults`, `collect-week-in-range`.

## Consequences

### Positive

- `make test` becomes a single quality gate — no separate manual validation.
  PRs that break liturgical rendering are caught before merge.
- The coherence score replaces human judgment for promotion decisions. The
  threshold is machine-enforceable.
- Three-tier classification provides flexible severity — a minor formatting
  issue doesn't block deployment, but a structural liturgical error does.
- `--json` mode enables future consumers (dashboards, alerts, pre-commit hooks).
- `PROMOTE_FORCE` provides an escape hatch for false positives.
- The rule suite is extensible — adding a liturgical check requires only adding
  a rule function to `validate_office.cjs` with a tier label.

### Negative

- `validate_office.cjs` and `audit_office.cjs` must be extended with `--json`
  mode (~20 lines each) and the validator must load lectionary data (~30 lines).
- False-positive risk from new rules. Downgrade path: Tier 1 → Tier 2.
- The 85-point threshold and penalty weights are initial values. Tuning
  requires empirical data from several releases. The values are hardcoded in
  v1; a `coherence_config.json` is deferred.
- The date list (`qa_dates.json`) must be maintained as the lectionary window
  rolls forward (~annual maintenance: pick new representative dates).
- `check_text_quality.py` lacks structured output — treated as binary
  pass/fail in the initial version. Per-finding penalties are deferred.

### Neutral / Notes

- `cli/book.js` previously placed Lord's Prayer under Sending; the web app
  places it under Prayers. Fixed: `cli/book.js` moved Lord's Prayer before
  Sending to match the web app structure.
- Performance: ~15 lectionary files + 30 form traversals + rule checks.
  Estimated at <2s warm, <5s cold (slower CI disk I/O). Fast enough for
  per-commit CI.
