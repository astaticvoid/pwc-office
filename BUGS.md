# PWC — Tracker

_Last updated: 2026-07-24_

## Field observations

_User reports that need triage — move to the appropriate section after investigation._

- Password re-prompts on every page refresh (2026-07-24). Root cause found: `pwc-basic-auth` CloudFront Function (viewer-request only) never sets a session cookie after a successful Basic Auth check — AWS's own stored comment on it says "Basic auth with cookie check," but the `viewer-response` half that would actually write `Set-Cookie` was never attached/implemented. Confirmed via curl against production: a 200 response to an authenticated request carries no `Set-Cookie` header. Blocked on IAM — the `pwc-deploy` user has no `cloudfront:GetFunction`/`UpdateFunction`/`PublishFunction` permissions, so the function source can't be read or fixed until those are granted (scoped to `function/pwc-*`).

---

## Active plan

The near-term goal is liturgical quality — ensuring every rendered office is coherent
and correct for a worshipper. We fixed extraction quality (PyMuPDF replacing pdfplumber).
Now we need to guarantee the rendered output is liturgically right.

### Done (this session)

- Paragraph-break aware scripture rendering — BibleGateway-style paragraph rendering, left-aligned section headings (2026-07-21, `7978854` + `b435069`)
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

- ~~Promote staging to production~~ — Promoted 2026-07-21.
- ~~`prefers-color-scheme` auto-detection~~ — System preference followed when no stored override 2026-07-21.
- ~~`#day-office-name` button semantics~~ — role="button", tabindex, Enter/Space key handler 2026-07-21.
- ~~Unify tab builders~~ — `collectToggleHtml` tabBlock now includes title + truncation matching `renderAlternatives` 2026-07-21.
- ~~Error-state consistency~~ — Missing form shows notice, unresolvable collect shows "not available" note 2026-07-21.
- ~~`CONTRIBUTING.md`~~ — Fixed stale references (patches→corrections, update-golden→generate-golden, deploy→deploy-staging/promote) 2026-07-21.
- ~~E2E staging test auth~~ — HTTP basic auth credentials added to playwright config 2026-07-21.
- Visual-regression testing: no screenshot/visual tests, dark mode untested in CI.

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
- ~~Production still on pre-rubric-fix release (user testing staging)~~ — Promoted to production 2026-07-21.
- ~~No CI — tests are local only~~ — Done 2026-07-18: GitHub Actions runs `make test` (Vitest + QA gate + integrity check) on push/PR.
- ~~P0 alternate-observance crash + 5 validity bugs~~ — Fixed 2026-07-21 (Commits 1–6): dead observance card, duplicate ARIA IDs, `--font-body` token, `--color-day` token, StatusBar ternary, `@smoke` test gate.
- ~~Dead CSS/JS cleanup (~80 lines CSS, #view-toggle/#nav-date wiring)~~ — Purged 2026-07-21.
- ~~Missing font weights (Garamond 700, Plex 600/700)~~ — Added 2026-07-21.
- ~~Mobile line-height override~~ — Removed hardcoded 1.7, token flows through 2026-07-21.
- ~~Settings-sheet a11y~~ — Visibility hidden removes from tab order, aria-modal, focus management 2026-07-21.
- ~~Dark-mode gaps~~ — color-scheme meta/root, brass ink typo, seasonal accent dark variants 2026-07-21.
- ~~Chapter drop-num on mid-chapter readings~~ — Skip when firstV ≠ 1 2026-07-21.
- ~~Attribution label inconsistency~~ — Unified as "Scripture:" 2026-07-21.
- ~~ADRs stuck at Proposed~~ — Marked Accepted (0002 Superseded) 2026-07-21.
- ~~Stale DESIGN.md~~ — Deleted (all info in AGENTS.md + ADRs) 2026-07-21.
- ~~Throwaway prototype files~~ — Deleted _design-options.html, _cross-test.html 2026-07-21.
- Missing visual-regression coverage: no screenshot/visual tests, dark mode untested in CI.
- ~~`make promote` silently failing~~ — Fixed 2026-07-24: the `jq` filter piped the whole `{ETag, DistributionConfig}` wrapper into `--distribution-config`, and `--if-match` was never passed. Every step was `;`-chained instead of `&&`, so the broken `aws cloudfront update-distribution` call failed silently and the recipe still printed a false "Promoted ... to production." Production had been stuck on the 2026-07-18 release for 3 days/5 releases with no visible error. Same bug (plus a trailing-slash `OriginPath` bug) fixed in `rollback`. Re-ran `make promote` after the fix — production confirmed serving the 2026-07-21 release (`index.html` hash matches S3 byte-for-byte).

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
