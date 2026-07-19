# PWC — Tracker

_Last updated: 2026-07-18_

## Active plan

The near-term goal is liturgical quality — ensuring every rendered office is coherent
and correct for a worshipper. We fixed extraction quality (PyMuPDF replacing pdfplumber).
Now we need to guarantee the rendered output is liturgically right.

### Done (this session)

- PyMuPDF replaces pdfplumber — single PDF dependency, 85 lines of heuristic code deleted
- Content-based page detection — no hardcoded page numbers
- Unified renderer — `render.js` has HTML + text + JSON output modes
- Correction consolidation — single `corrections.json` (1 active entry)
- Versioned deploy pipeline — `deploy-staging` → `test-staging` → `promote` → `rollback`
- Staging on `office-staging.k-sprawl.net`, production on `office.k-sprawl.net`
- Basic auth with persistent cookie (no per-refresh login)
- QA tools: `validate_office.cjs` (6 rules), `audit_office.cjs` (14 metrics, 4 peer groups)
- Compare tool: `compare_staging.cjs` — A/B diff before promotion
- Review tool: `review_form.cjs` — line-numbered text renderer
- Systemic fixes: "Amen ." (28/30 forms), Friday EP Phos Hilaron, rubric leakage in office mode
- NRSVUE fetcher (private repo)
- Stale docs cleaned: API.Bible, Go, SW caching references removed

### Done (2026-07-18 QA sprint)

- `renderOfficeJSON` — full-office structured output shared by validators and browser
- `assembleSections` — single source of truth for section ordering and visibility
- Expanded rule suite — 19 rules across 3 tiers (was 6)
- `coherence_score.cjs` — composite 0-100 score with promote gate
- CI gate — `make qa` wired into `make test`, GitHub Actions workflow
- PDF column-break artifacts fixed — systemic `_normalize_whitespace` regex
- CLI rendering fixes — canticle verse breaks, N placeholder text mode
- `collectSecondaryPage` moved to shared module
- CLI Lord's Prayer harmonized with web app section structure
- Sync test — Vitest verifies HTML and JSON paths produce matching output
- 8 expected audit outliers documented in `audit_expected.json`

### Next

- Paragraph-break aware scripture rendering — extract boundaries from ESV XML / Bible Gateway, apply to KJV + NRSVUE (needs Apocrypha source)
- Promote staging to production (user testing in progress)

### Parked

- Mobile Capacitor build

---

## Open issues

### Rendering

- ~~Mid-line breaks in prose collects from PDF column layout (affects ~14 dismissal blessings)~~ — Fixed 2026-07-18: `_normalize_whitespace` regex joins mid-sentence `\n` in leader/response segments. Validator confirms zero remaining.
- ~~"N" placeholder renders as bare text in CLI text mode~~ — Fixed 2026-07-18: `renderSegmentsText` wraps `N` as `(N)` in text mode.
- ~~Canticle verses join with spaces instead of line breaks in text mode~~ — Fixed 2026-07-18: CLI canticle rendering passes `verse: true`.

### Extraction

- BAS collect page 281: Ash Wednesday overlaps with Epiphany content (pre-existing)
- BAS collect page 407: Saint Matthias date parsing (pre-existing)

### Infrastructure

- ~~Staging cache headers need `make build` integration~~ — Done: `deploy-staging` already sets per-type cache headers.
- Production still on pre-rubric-fix release (user testing staging)
- ~~No CI — tests are local only~~ — Done 2026-07-18: GitHub Actions runs `make test` (Vitest + QA gate + integrity check) on push/PR.

---

## Deploy workflow

```bash
make deploy-staging          # upload to releases/vTIMESTAMP/ + staging/
make test-staging             # Playwright smoke
node tools/compare_staging.cjs [date] [mp|ep]  # eyeball diff
make promote                  # CloudFront origin-path swap
make rollback                 # revert to previous release
```

---

## QA gates

```bash
node tools/validate_office.cjs   # 6 liturgical rules (0 failures expected)
node tools/audit_office.cjs      # cross-form outlier detection (8 legit outliers)
make test                         # Vitest (117 tests)
make test-full                    # 794 structural checks
make check-integrity              # SHA-256 data integrity
```
