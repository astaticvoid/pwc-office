# AGENTS.md

Instructions for automated tooling working in this repository.

## Project Overview

**Pray Without Ceasing (PWC)** — a Daily Office web app and Node CLI for Anglican liturgy. The web SPA is the primary product; the CLI shares the same data layer. Data is extracted from PDFs (ACC/BAS) via Python scripts and stored as JSON.

This file is the authoritative one, and `CLAUDE.md` is a pointer to it.
`README.md` (what the app is, how to run it) and `CONTRIBUTING.md` (setup, test
tiers, deploy) cover the same ground for humans at less depth. They had drifted
badly enough to mislead — CONTRIBUTING described extractors writing straight into
`data/`, three releases after #48/#49 moved them to `.build/` — so when a change
here invalidates something there, fix it in the same commit. The Makefile and the
tools are the tiebreaker for all three.

## One-time setup

```bash
npm install
npx playwright install              # Chromium browser for Playwright E2E tests
make venv                           # .venv with pymupdf (PDF extraction) + pytest
```

Every Python target runs through `$(PYTHON)`, which resolves to `.venv/bin/python3`
when the venv exists and falls back to the ambient `python3` otherwise (CI). No
shell activation is needed. Installing directly into Homebrew's python3 is not
supported — it is an externally-managed environment (PEP 668).

Required environment variables in `.env` (gitignored):
- No keys required. KJV scripture is bundled in `data/translations/kjv/` and works offline.
- NRSVUE scripture is not distributable — if a local copy is placed at `data/translations/nrsvue/` the app will use it.
- `make deploy-staging` / `promote` / `rollback` need `BUCKET` and `CF_DISTRIBUTION_ID`.
- `make test-staging` needs `STAGING_DOMAIN`; it is only used to build `BASE_URL` for Playwright.
- `STAGING_CF_ID` is not read by anything today — staging freshness comes from the short cache-control headers `deploy-staging` sets, not from an invalidation.
- Also provide `AWS_PROFILE` in `.env` so AWS CLI credentials resolve automatically.

**All build, test, and deploy operations should be run through `make`.**
The Makefile includes `.env` at line 1 (`-include .env`), so environment
variables are loaded automatically. Running `aws` CLI commands directly will
fail with "Unable to locate credentials" because the shell environment does
not source `.env`. Use `make deploy-staging`, `make serve-dist`, etc.

## Commands

```bash
# Development
make serve                        # http://localhost:8080 (no build, data symlink followed live)

# Data pipeline
make fetch-sources                # download ACC PDFs + CSVs → sources/
make extract                      # full pipeline → data/*.json + data/lectionary/

# Testing
make test                         # go-to command, no network. Composite:
                                  #   lint → check-integrity → test-unit → test-tools → qa
make test-unit                    # Vitest only (tests/unit/) — `npm test`
make test-tools                   # pytest only (tools/tests/) — extraction-tool units
make test-full                    # structural check: every day × MP+EP in lectionary
make test-smoke                   # 4 cases: citation check vs lectionary.anglican.ca
make test-seasonal                # 26 cases: one MP+EP per liturgical form
make test-web                     # Playwright E2E (tests/e2e/) — starts web/ on :8080 itself
make validate                     # check-text + validate_lectionary.py vs ACC HTML (network)

# Quality assurance — `make qa` runs ALL of these, and `make test` runs `qa`.
# Reach for one directly to read a failure in full, not to add coverage after
# `make test`: that adds none.
make check-conservation           # every printed line accounted for, both directions, offices + psalter
python3 tools/check_conservation.py --show-text   # ...and read what is unaccounted (offices)
python3 tools/check_conservation.py --chain psalter --show-text   # ...and the psalter chain
node tools/validate_office.cjs    # 20 liturgical rules across 3 tiers, all 30 forms
node tools/validate_render.cjs    # rendered-DOM structure for all 30 forms
node tools/validate_css.cjs       # structural CSS validity (web/*.css)
node tools/validate_lectionary.cjs # every date × office: citation syntax + resolution
node tools/audit_office.cjs       # cross-form statistical outlier detection (z-score)
node tools/audit_text.cjs         # cross-form text-length outliers within peer groups
node tools/audit_a11y.cjs         # heading hierarchy + ARIA on rendered HTML, no browser,
                                  # plus WCAG AA contrast over the office.css palette
node tools/coherence_score.cjs V.json A.json  # composite 0–100 from the two --json outputs

# Human review steps — not run by `make qa`
node tools/compare_staging.cjs [date] [mp|ep]  # A/B diff staging vs production rendered DOM
node tools/review_form.cjs FORM   # line-numbered text renderer for manual review

# Quality gates
make audit-errata                 # data/offices.json vs docs/errata/ — reports, does not gate
make check-text                   # scan for PDF extraction artifacts
make check-text --strict          # same but exits non-zero on findings
make check-integrity              # verify data/ hashes match extract manifest — fails if any
# NOTE: after changing any extractor, re-run `make extract`. The manifest stores
# hashes of the committed data, so stale hashes after a code change fail this —
# which is the point, and why it also gates `make test`.

# Build & verify
make build                        # assemble dist/ (copies web/, dereferences data symlink)
make check-dist                   # build + tools/check_dist.py validation
make serve-dist                   # serve dist/ on :8081 (required for E2E pre-deploy)

# Mobile (Capacitor shell)
make mobile-sync                  # build + npx cap sync
make mobile-ios                   # mobile-sync + open Xcode
make mobile-android               # mobile-sync + open Android Studio

# Deploy (needs AWS creds + BUCKET + CF_DISTRIBUTION_ID + STAGING_DOMAIN in .env)
make deploy-staging               # upload to releases/vTIMESTAMP/ + staging/
make test-staging                 # Playwright smoke tests against staging
make promote                      # CloudFront origin-path swap to production
make rollback                     # revert to previous release

# Page bounds detection (content-based, not hardcoded)
python3 tools/detect_office_bounds.py --strict  # verify committed bounds
python3 tools/detect_office_bounds.py --write   # regenerate after PDF change
```

### Watching convergence

The one number that tracks whether extraction quality is *improving* is the
open-divergence count in `tools/conservation_baseline.json` — the list
`check_conservation.py` reports as unaccounted-but-licensed. A fix that closes
a divergence deletes its entry in the same commit, so the count drops only
when a defect is actually resolved; a stale entry a fix left behind is itself
a failure. See the trend:

```bash
git log --oneline -- tools/conservation_baseline.json

# or count the known[] entries per commit:
git log --format='%h %s' -- tools/conservation_baseline.json | while read sha msg; do
  n=$(git show $sha:tools/conservation_baseline.json 2>/dev/null |
      python3 -c "import sys,json;print(len(json.load(sys.stdin)['known']))" 2>/dev/null)
  echo "$n  $msg"
done
```

A shrinking count is convergence; a count that grows, or an entry that should
have been deleted in the fixing commit but was not, is a regression.

### Focused test commands

```bash
npx vitest run -t "pattern"                    # a single Vitest test
.venv/bin/python3 -m pytest tools/tests/test_x.py -k name   # a single pytest
COHERENCE_THRESHOLD=100 node tools/coherence_score.cjs …  # what qa uses; the
                                               # 85 default is an ad-hoc floor only
```

Test suites live in three places, and the three `make` tiers map onto them
one-to-one: `tests/unit/` (Vitest, imports `web/render.js` directly),
`tests/e2e/` (Playwright, both a `chromium` and a `mobile` project), and
`tools/tests/` (pytest over the extraction tools). `tools/test_rule_mutations.cjs`
is a fourth, narrower one — mutation tests for the qa rules themselves
(`make test-mutations`) — living directly in `tools/` rather than
`tools/tests/` because it drives `tools/validate_office.cjs` as a subprocess
instead of importing it.

## Architecture

### Data flow

```
PDFs  →  PyMuPDF (fitz)  →  data/*.json + data/lectionary/YYYY-MM.json
                                        ↓
              web/render.js (shared rendering: HTML + text + structured output)
              ├── web/app.js (SPA)
              ├── cli/book.js (plain-text CLI)
              └── cli/office.js (debug CLI)
```

Copyrighted content in `data/` is permanently gitignored. Only `data/translations/kjv/`, `data/corrections.json`, and `data/paragraphs.json` are committed. `web/data` is a symlink to `../data` — `make build` dereferences it via `cp -rL` into `dist/`; `make serve` follows the symlink live.

**Distribution posture.** The open-source repo must not contain or ship
copyrighted ACC/BAS text; the ACC-distributed app builds may, under rights ACC
is obtaining. `sources/*` is gitignored except the public `bas_short` CSVs,
along with golden fixtures, Capacitor-synced assets (`ios/App/App/public/`,
`android/…/assets/public/`), and audit artifacts. `make fetch-sources && make
extract` is the path from a clean checkout; `extract_manifest.json` carries
hashes and counts, never content.

The residual risk is that **Capacitor store builds bundle the texts into the app
binary**, and until rights are granted a TestFlight or Play internal track counts
as distribution to testers. Keep beta distribution inside the Synod evaluation
group under ACC's direction, and carry this into any store-submission checklist.

### Web SPA (`web/`)

`web/render.js` contains all office rendering functions and is imported by the browser SPA (`web/app.js`), the Node CLI (`cli/book.js`, `cli/office.js`), QA tools, and Vitest tests. A change to `render.js` affects all consumers.

`web/app.js` handles routing, lectionary lookup, form selection (season + weekday → one of 30 office forms), and Scripture fetching (NRSVUE from local `data/translations/`, KJV bundled). No framework, no build step.

**Leaders & responses are rendered by `web/render.js`.** The shared module provides:
- `renderSegments` — HTML output (browser SPA)
- `renderSegmentsText` — structured text blocks (CLI, QA tools)
- `segmentsToJSON` — structured JSON output (validators, cross-form audit)

**No service worker.** `sw.js` is a kill-switch only — it unregisters itself and clears all caches to clean up old installs. Do not add SW caching back.

### Node CLI (`cli/`)

| File | Role |
|------|------|
| `cli/book.js` | Book-mode plain-text renderer. Uses `renderSegmentsText` from render.js. `node cli/book.js FORM [DATE]`. |
| `cli/office.js` | Structured text renderer. Uses `renderSegmentsText`. `node cli/office.js [mp\|ep] [DATE]`. |

### Python tools (`tools/`)

Extraction pipeline (run via `make extract`):

Each stage reads a named input and writes its own output; nothing is mutated in
place. Intermediates live in `.build/` — outside `data/`, which is the tree that
ships via the `web/data` symlink. Only the right-hand column is published.

| Stage | Writes |
|---|---|
| `extract_offices.py` (30 forms, PyMuPDF span-level) | `.build/offices.1-extract.json` |
| `extract_office_styles.py` — span classification by font flags + sRGB colour | *(library)* |
| `normalize_offices.py` — hoists shared blocks into `_shared` | `.build/offices.2-normalized.json` |
| `extract_psalter.py` | `.build/psalter.1-extract.json` |
| `extract_fats.py` | `.build/fats-saints.1-extract.json` |
| `convert_lectionary.py` (from `sources/bas_short_*.csv`) | `.build/lectionary/YYYY-MM.json`, `data/season_bounds.json` |
| `extract_collects.py` | `data/collects.json` |
| `corrections_lib.py` — shared matching for `office_text`, used by both scripts below | *(library)* |
| `validate_corrections.py` — checks corrections against the pre-correction artifacts | *(read-only)* |
| `apply_corrections.py` — applies `data/corrections.json` | `data/offices.json`, `data/psalter.json`, `data/fats/saints.json`, `data/lectionary/` |
| `update_extract_manifest.py` | `tools/extract_manifest.json` (committed) |

Not part of this chain: `extract_paragraphs.py` generates `data/paragraphs.json`
from a hand-fetched WEB USFX XML (source URL in the script's docstring). It has
no Makefile target — `data/paragraphs.json` is a committed static asset, not
pipeline output (see `update_extract_manifest.py`'s `PUBLISHED_FILES` comment),
and the WEB changes approximately never. Run by hand only when it needs
regenerating: `python3 tools/extract_paragraphs.py [path-to-usfx-xml]`.

`apply_corrections.py` writes **every** file it publishes on every run —
`offices.json`, `psalter.json`, `fats/saints.json`, `lectionary/` — including
when the matching correction list is empty or `data/corrections.json` is absent
entirely. It is the stage that *derives* those files from their `.build/`
artifacts, not merely the stage that patches them. Never make a derivation
conditional on there being a correction to apply: that guard shipped on all four
chains, and on the offices chain it left the published file stale after an
extractor change through a `make extract` that reported success and a
`check-integrity` that passed, because the manifest was rehashed from the same
stale file. It also turned CI red for four days with `missing data files`, since
there the file is absent rather than stale.

Correction lists are *meant* to drain — "Data correction locations" below directs
systemic problems into the extractor — so an empty list is the expected steady
state, not a signal that there is no work to do.

Every stage input is checked before the first write, and a missing one exits 1
with the remediation. For `.build/lectionary/` "missing" includes *empty*:
`_seed_lectionary` mirrors it exactly, so an empty source deletes every published
month rather than copying none.

Because each stage names its input, the order is a data dependency rather than a
rule to remember: `convert_lectionary.py` cannot discard published corrections,
and `validate_corrections.py` cannot see corrected output, whenever they run
(#49, closing the #37 failure mode).

**Data integrity guard:** `check_data_integrity.py` compares current `data/*.json` hashes against `tools/extract_manifest.json`. Exits 1 if any file was edited outside the pipeline, or if an extractor changed without a re-run. Gates both `make test` and `make deploy-staging`.

`source_hashes` in that manifest has three states, and the third is load-bearing:

| value | meaning |
|---|---|
| a hash | the input must still hash to this |
| `null` | the input was **absent** when the manifest was written — drift, exits 1 |
| key absent | not tracked; either a pre-#51 manifest or a retired input |

An input that disappears is recorded rather than dropped. Omitting it let the
key vanish from the committed manifest on the next `make extract`, so nothing
recorded that the input had ever been expected: `rm data/corrections.json &&
make extract && make test` was green while every office was republished with all
corrections silently dropped, the Synod errata among them. A warning was not
enough — check-integrity is the deploy gate, so anything exiting 0 ships the
tree regardless.

**Retiring an input is removing it from `EXTRACTION_SOURCES`**, in the same
commit as whatever removed the file. That is a reviewable edit; a file missing
from a worktree is not. Glob entries (`sources/bas_short_*.csv`) name a set, so
they record only concrete matches and never a null — zero matches is
indistinguishable from a year not yet added, and `convert_lectionary.py` already
fails loudly on a missing CSV.

**Verse sections — one list, in the validator only.** `VERSE_SECTIONS` in `tools/validate_office.cjs` asks *"does this section contain any intentional line breaks?"*, so `no-prose-line-breaks` won't flag a `\n`. There is no longer a Python counterpart: extraction decides every break from the page (see below), so nothing needs a section-level exemption. `_VERSE_SECTIONS` and the `_LINE_JOIN` regex it gated were removed once the geometry reproduced the extraction exactly without them. When adding a verse-like section, update the JS list and the line-count assertions in `tests/unit/render.test.js`.

### Changing an extractor

Extraction output is copyrighted text nobody diffs by eye, and the test suite
cannot see most of what can go wrong with it — the coherence score sat at 100/100
through a change that collapsed every evening hymn into prose. So the diff is the
verification, and it is not optional.

```bash
make extract-baseline          # full pipeline, snapshot
# ...edit tools/extract_*.py...
make extract-diff EXPECT=0     # a refactor must change nothing
make extract-diff              # or read what actually moved
```

**Upgrading PyMuPDF is changing an extractor.** It supplies every coordinate the
line-break decision reads, against a window documented below as sitting 0.5pt
off a false positive, so treat a version bump exactly like an edit to
`extract_offices.py`: re-extract and `make extract-diff EXPECT=0`. The file
hashes will not tell you — `make extract` rewrites them and the recorded version
together, so they agree with whatever produced them. `make check-integrity`
prints a `VERSION WARN` when the installed PyMuPDF differs from the manifest,
and that warning is the only automatic signal for this (ADR 0011). It warns
rather than fails only because `make test` depends on check-integrity, and
failing would lock out any contributor whose PyMuPDF differs until they re-run a
network extraction.

State the expected node count before running it, and make the change explain the
number. "0 nodes" is the target for anything meant to be behaviour-preserving;
a real fix should change exactly the nodes it claims and no others.

`make check-conservation` is the other half of that verification and answers the
question the diff cannot: the diff says what moved between two runs of *this*
extractor, and the conservation check says whether the result still matches the
page. A change that drops a line consistently is invisible to `extract-diff`
after the first run and permanent; that is exactly how #84 survived for the life
of the project. Run both.

**Each stage writes its own artifact.** `.build/*.1-extract.json` and friends are
inputs to the next stage; only `data/` is published. Never treat an intermediate
as final, and never point a diff at one — that comparison is meaningless and
looks authoritative. Running a single extractor cannot corrupt `data/` any more
(#48, #49), but it also does not produce it.

One exception, and it is the only one: `convert_lectionary.py` writes
`data/season_bounds.json` straight into the published tree rather than through
`.build/`. So running that extractor standalone *does* rewrite a published,
manifest-tracked file. It is safe as it stands — the write is unconditional and
`detect_bounds()` runs before the `--window` pruning, so the content does not
depend on the day it ran — but it is a real carve-out from the paragraph above,
not an oversight to be tidied away without moving the file to `.build/` first.

**`_heading_to_key` is not a list of sections.** `seasonal_collects` and
`lords_prayer_intro` are carved out of the litany block afterwards, so anything
walking typed lines and assigning sections by heading reports zero for them
rather than failing. Walk `SECTION_ORDER` or `sections_of(form)` instead. This
has produced confidently wrong measurements more than once.

**Count only what can exhibit the defect.** A paragraph-break count went 47 → 30
→ 14 in one session because the first two included segment-type transitions that
`_merge` already separates. Narrow the population before reporting a number, and
say which population it is.

**Deciding a break: measure the page, never a proxy.** Whether a line break is deliberate or a PDF column wrap is a physical question — did the line run out of horizontal room? Answer it from geometry (`gap`, the unused space at the end of the line, and `lead`, the leading opened up below it), both carried out of `spans_to_typed_lines`. Two attempts to use a proxy instead have shipped broken text: a "terminal punctuation" rule produced 46 false breaks (#9), and classifying by the trailing space PyMuPDF leaves on a span collapsed every evening hymn stanza into prose (#38, reverted in 0ac1b86) — that space marks "this line does not end the block", not "this line was wrapped". `litany` is the only section mixed enough to need per-break judgement; `_reflow_litany` does it, with the handful of ambiguous breaks adjudicated explicitly and anything new warned about rather than guessed at. See #39.

**Page bounds:** `detect_office_bounds.py` detects office form page ranges from PDF content (title patterns). Output is committed as `tools/office_bounds.json`. No hardcoded page numbers.

**Design review process (ADR 0010):** Visual changes to UI elements (layout, typography, interactive controls) are prototyped on a static design-options page before touching production CSS. Usually no such page exists — step 4 below deletes it once it has served its purpose, so an empty tree is the expected steady state rather than a missing file. The workflow is:
1. Create a self-contained HTML file in `web/` (e.g. `_design-foo.html`) with inline CSS using the same custom properties as `office.css`.
2. For each variant, render a desktop (58rem) and mobile (390px) mockup stacked vertically.
3. Review, pick a direction, then implement the real CSS change.
4. Delete the design page after merging — it served its purpose.

### QA tools (`tools/`)

| File | Role |
|------|------|
| `validate_css.cjs` | Structural CSS validity for every file in `web/*.css`: no style rule nested inside another style rule's declaration block (only `@media`/`@supports`/etc. and `@keyframes` bodies may nest), and brace-balance at end of file. Catches an unclosed/stray rule silently swallowing the rest of the stylesheet — this happened for real (see issue #22) and nothing else in this project's test suite validates CSS syntax at all. |
| `check_conservation.py` | The only check that compares the data against the **page** rather than against itself or a hardcoded expectation, which is why nothing else in this list could see #84, #87, #91 or #93. Walks every source line as extraction does and accounts for it in both directions: every printed line either ships or matches a named rule (reflow, whitespace, heading consumed as structure, an audited correction…), and every shipped line either was printed or matches one. Residue is the defect list. Both directions are load-bearing — a shipped line the page prints as a *prefix* of it is absorbed by substring matching going one way and caught only coming back (#101). Needs `sources/` and `.build/` as well as `data/`. Reports an unaccounted line by form, section and content hash; `--show-text` prints the line and is deliberately not the default. **Conservation is a set property per form**: it sees a line leave the pipeline, not one occurrence of a repeated line going missing, and not surviving text moving to the wrong place. That is #99's subject, and the two are complements. **Multi-chain since #102**: `--chain psalter` walks the same PDF's psalter section and accounts every verse/continuation/section head against `data/psalter.json`, with its own `corrected` rule (the `data/corrections.json` "psalter" entries applied to `.build/psalter.1-extract.json`); `make check-conservation` and `qa` run both chains. |
| ↳ the `corrected` rule | The one rule worth understanding before trusting the others, because two weaker versions of it shipped and both were wrong. It reconstructs — applies `data/corrections.json` to the pre-correction block and asks whether the result is what ships — rather than looking for an entry that mentions the line. Keying on `{office, field}` let one three-word errata fix vouch for every line in its section, exempting 121 of the corpus's form-fields; comparing the line against `old`/`new` directly then failed wherever a printed line straddles the end of a substring correction and runs into the next sentence. Reconstruction is ADR 0005's own claim — source plus manifest equals shipped — made computable, which is why it is the version that holds. |
| `conservation_baseline.json` | The divergences `check_conservation.py` finds that are tracked as open issues, so it can gate on *new* ones. An entry is a licence to keep failing, not a claim that the divergence is legitimate — legitimate ones are named rules in the tool. Counts are exact in both directions: a defect that grew is a regression, and one that shrank is a fix that left its entry behind, so both fail and the entry is deleted in the commit that fixes it. Holds no book text, only sha256 prefixes. Entries may carry an optional `chain` field (default "offices"); a psalter-chain divergence is licensed with `"chain": "psalter"` so it never claims an offices finding, and vice-versa. |
| `validate_office.cjs` | 20 liturgical rules against all 30 forms, in 3 tiers — T1 structural (Amen presence, non-empty responses, leader/response alternation, collect resolvable), T2 textual (prose line breaks, orphan rubrics, Phos Hilaron line count), T3 seasonal coherence. The 10 rules in `DYNAMIC_RULES` need lectionary data, so they are skipped in the static pass and checked per date against fully assembled offices instead. Tier drives the `coherence_score.cjs` penalty. |
| `validate_render.cjs` | Rendered-DOM structure for all 30 forms: section headings present, segment counts match, no empty liturgy blocks, valid heading hierarchy. Complements `validate_office.cjs`, which checks the data rather than the HTML. |
| `audit_text.cjs` | Cross-form text-length outliers for shared subsections within a peer group — a section much shorter or longer than its peers signals an extraction artifact. |
| `audit_a11y.cjs` | Static a11y checks over the rendered HTML (heading hierarchy, ARIA on interactive elements). No browser, so it runs in `qa` rather than in Playwright. Those checks are **advisory** — they print and never set the exit code themselves; the contrast check below is what can make the tool exit 1. |
| ↳ the contrast check | The one part of that tool that **gates**, because its inputs are the stylesheet's own tokens rather than a heuristic: it reads the palette out of `web/office.css` — both themes, every seasonal override, the two `color-mix` grounds mixed in OKLab as the browser does, and text dimmed by `opacity` composited as the browser does — and measures every pair against WCAG AA. What it cannot infer is *which ground a foreground is painted on*: the cascade knows that, so `TEXT_PAIRS` / `GRAPHIC_PAIRS` / `OPACITY_RULES` declare the ink, the ground, and whether the element carries its own background. Everything a value can state is read from the sheet instead of declared — the alpha above all, since a remembered `0.78` would rebuild the #85 failure mode one layer up. **Two scans keep those tables from being a list of the pairs someone remembered**: every `color:` declaration must name a declared token or literal, and every `opacity:` under 1 must name a declared selector — anything else fails rather than going unmeasured. Which pairs vary by season is derived from the palette, not declared, so a seasonal override of a token nobody marked seasonal cannot go measured in one season and unmeasured in eight. `KNOWN_CONTRAST` licenses the failures tracked as open issues, on `conservation_baseline.json`'s terms: a licensed pair that starts passing — **or that nothing measures any more** — fails too, so the fixing commit deletes its entry. Added with #85, where `--color-muted` carried most of the app's small print at 4.02:1 for the life of the project and nothing could see it; the opacity half caught two more call sites of that same defect, one of them an interactive control at 2.57:1. |
| `coherence_score.cjs` | Composite 0–100 from `validate_office --json` + `audit_office --json`, with exemptions from `tools/audit_expected.json`. `make qa` and the promote gate both set `COHERENCE_THRESHOLD=100`; the promote gate was 85 and so would not have blocked c81b341, which scored 97 with every evening hymn stanza collapsed into prose. |
| `validate_lectionary.cjs` | Every date × office (397 × 2) in the lectionary: syntax checks (well-formed citations) **and** resolution checks (collect page/psalm number/lesson citation actually resolves to real data in collects.json/psalter.json/translations — not just a well-formed reference). Reuses the exact runtime resolution functions from `web/render.js`, not reimplementations. Run this after any re-extraction, especially a new lectionary year. |
| `audit_office.cjs` | Cross-form statistical audit — 14 metrics, 4 peer groups, 2σ z-score outlier detection |
| `compare_staging.cjs` | A/B rendered DOM diff between staging and production (use before `make promote`) |
| `review_form.cjs` | Line-numbered text renderer for manual review (`node tools/review_form.cjs advent-mp`) |

### Mobile shell (`ios/`, `android/`)

Capacitor wraps `dist/` as a native app (`capacitor.config.json`, `webDir: dist`). `make mobile-sync` rebuilds dist + runs `npx cap sync`. The web build is the source of truth — no native-only code paths.

---

## Bug tracking

All task tracking lives in [GitHub Issues](https://github.com/astaticvoid/pwc-office/issues) — there is no in-repo tracker. `BUGS.md` was retired 2026-07-30 and its full history migrated: every resolved entry is a closed issue, so a `see issue #N` comment in the source resolves to the original writeup.

- **Triaging a user report** — open an issue rather than noting it in a file. Label `bug`; leave it unlabelled for severity until investigated.
- **Findings during development** — a defect or warning surfaced during build, test, review, or deploy (including non-blocking ones) is triaged as *known* (an open issue already exists) or *captured* (open one) before continuing — never dismissed as "pre-existing".
- **Fixing a bug** — close its issue with the findings in the closing comment. That writeup is the durable record; keep it detailed enough that a future session can reconstruct *why*, not just *what*.
- **Citing rationale from code** — reference the issue number (`see issue #13`), not a date or a file. Issue numbers are stable; the tracker file was not.
- **Parked work** — an open issue with no milestone, not a "Parked" list.

## Source comments

A comment describes the code that is there. It does not narrate the code that
used to be there.

- **No history in comments.** Not "this used to be a private copy", not "the
  list used to hold six", not "before #84 this was hardcoded". Git log, the
  commit message, and the issue hold that; a comment repeating it goes stale
  the moment someone edits around it, and it makes the reader reconstruct a
  version of the file they cannot see.
- **A bare `#N` is the whole citation.** `(#110)` after a statement about the
  current behaviour points at the writeup — that is the supported way to reach
  the history, per the rule above. Do not inline a summary of the issue.
- **Say what and why, about what exists.** "Lookup needs a chapter; display
  must not print one the book omits" is about the code. "This is what
  rendering the block whole would have done" is about a version that is not
  there.
- **No musing.** No weighing of alternatives not taken, no notes on what a
  future pass might do, no commentary on other files' defects beyond a `#N`.

This applies to comments in tests too — a test's comment states the invariant
it pins, not the bug that prompted it.

## Hard constraints

- **Never edit `data/*.json` directly.** All corrections go through `data/corrections.json` (committed single manifest) or the extraction pipeline. `make check-integrity` validates this — it fails if any data file was touched outside the pipeline.
- **One logical change per commit.** Push after each commit — don't batch.
  Each commit should contain a single atomic change that can be understood,
  reverted, and tested independently. Group related files by concern:
  - Docs (ADRs, specs) in their own commit
  - Shared code changes (render.js) with their consumers
  - Tooling changes in their own commit
  - Configuration (Makefile) in its own commit
  - Data pipeline changes (extractor, manifest) in their own commit
  Never accumulate unrelated changes into a "ball of mud" commit. Each commit
  message should explain what changed at the concern level, not file-by-file.
- **No Co-Authored-By** trailers in commits — enforced by the `commit-msg`
  hook in `githooks/`, installed with `make hooks`. This is a hard rule, not a
  preference; the trailer is what makes an AI agent a visible co-author on
  GitHub, and this repo keeps its history attributed to the human author alone.
- **Subagent code review before commit.** Every change must be reviewed by a hostile subagent before committing. The subagent checks for bugs, edge cases, silent failures, performance issues, and integration problems. Fix all high-severity findings before committing.
- **Deploy requires user go-ahead.** Never run `make promote` unprompted. Staging deploys are always safe.
- **Systemic fixes over patches.** When a bug is found, categorize it: systemic (fix in extractor/renderer), pattern (multiple forms), or data (single form). Fix the root cause so all instances are resolved, not just the one found.
- **Render the rite; do not edit it** (ADR 0016). Text from PWC, the BAS, or the
  lectionary renders, renders as written, and keeps its choices: no hiding it
  behind a mode, no paraphrasing or condensing it, no picking a branch on the
  reader's behalf. Presentation — typography, spacing, ordering, interaction —
  is yours. Any exception must be named at its own location and testable, the
  way ADR 0012 vouches for a line break; a regex or a section allowlist is not
  an exception, it is an unfalsifiable one. This does not restrict the app's own
  chrome (settings, navigation, error states). It also does not forbid changes
  that move rendered text *toward* what is authorized, such as the errata
  breaks or whitespace normalisation — the test is direction, not whether text
  changed. Worked applications: ADR 0013 (rubrics), 0014 (choices), 0015
  (text the app authors itself). **ADR 0019 is the casebook** — the specific
  readings upstream review has settled, each with the thing it forbids. Read it
  before changing a rubric or a selector; it exists because three of those
  decisions have already been re-litigated or rebuilt under a new name.
  **The shipped code does not comply yet, and this rule is not a licence to make
  it comply.** `BOOK_ONLY_RUBRICS` is gone (deleted under ADR 0013, #59) and
  `SKIP_RUBRICS` survives only as three named duplicates, each pinned to the
  heading it defers to by `validate_render.cjs` and a corpus test. The psalm and
  reading selectors shipped (#63). What is outstanding is on the other side of
  that line: the reading selector removes the Responsory and the Canticle, which
  the choice does not cover, so ADR 0019 item 7 withdraws it in favour of the
  book's own rubric (#77). The Reading and Psalm block is extracted since #84,
  so the rubrics printed there render from `form.psalm_rubrics` /
  `form.reading_rubrics`, and the readings ADR 0019 settled reach the page as
  `adr0019-*` corrections on that extracted text (#88). The rule binds *new*
  work: don't add a mechanism of the same kind.

## Data correction locations

**There is one correction manifest: `data/corrections.json`** (ADR 0005). Extractors extract; they no longer patch their own output. Every editorial correction goes in the manifest under the category matching its data type, is checked for staleness by `validate_corrections.py`, and is applied by `apply_corrections.py` after extraction in `make extract`.

| Correction type | Manifest category | Target locator |
|----------------|-------------------|----------------|
| Office text (wording, casing, whitespace) | `office_text` | `{office, field}` + substring replace; `office: "*"` for text the book repeats in every form |
| Psalter: missing/incorrect verse text | `psalter` | psalm number + substring replace |
| Saint biographies | `fats` | saint + field + substring replace |
| Lectionary: wrong citation | `lectionary_citations` | date + office + lesson index |
| Lectionary: wrong lesson list | `lectionary_lessons` | date + office (whole-list replace) |
| Lectionary: name / rank / colour | `lectionary_names`, `lectionary_ranks`, `lectionary_colours` | date (whole-value replace) |
| Lectionary: garbled note | `lectionary_notes` | date (`clear` action only) |

`office_text` takes two shapes, chosen by the type of `old` (see
`tools/corrections_lib.py`, which both the validator and the applier call so
they cannot disagree):

- **Substring** — `old`/`new` are strings. Every occurrence in every
  text-bearing segment of the field is replaced. `count` states how many
  occurrences are expected and defaults to 1; a mismatch fails the run rather
  than applying partially. This is what almost everything wants — the
  alternative is restating an entire canticle to change one word.
- **Whole-field** — `old`/`new` are lists/dicts. The field must equal `old`.
  For structural edits only: deleting segments, reordering, retyping a segment.
  Names one office; a wildcard is refused, since it would write the same
  structure over each.

`office: "*"` addresses every form carrying the field, for the rubrics the book
prints identically in all 30 — the Psalm and Reading introductions, the section
hand-offs. `count` stays a corpus-wide **total**, so the staleness guarantee is
unchanged: one entry reading `"count": 28` fails exactly as loudly as 28 entries
reading `"count": 1`, and says in one line how far the text reaches. The
alternative is 30 near-identical entries differing only in a key, which is a
worse record, not a stricter one — nobody reads 30 copies to check they agree.

**Not every divergence is an error.** Read the manifest by `source`:
`pwc-errata-*` and `*-error` mean the source is wrong; `upstream-review` and
`editorial` mean the source is right and we deliberately say something else.
The second kind names the decision that authorized it in an `adr` field — the
`adr0019-*` entries are the worked examples. A divergence with no manifest entry
is a defect, not a design choice (#92).

The walk does **not** follow `{"type": "shared"}` references. A shared block is
reachable from many forms, so correcting it through one form would silently
rewrite the others; address `_shared` directly instead.

Editorial errata for the printed PWC live in `docs/errata/` — see the README there for
which items became corrections, which the extraction already handles, and which
of the errata's own transcription slips must not be propagated.

**Run `make audit-errata` after touching `docs/errata/` or any `office_text`
correction.** It aligns every errata block against `data/offices.json` and
reports breaks the errata asks for that are missing, breaks we have that it does
not, and wording divergences not declared in the errata README. Nothing else can
see this: the first reflow pass dropped four breaks — three of them beside a
divergence the README already tabulated, because aligning a block as a whole
drops every break inside it when any line fails to match — and `make test`,
`make qa` and a 100/100 coherence score were all green over them.

Errata line breaks land mid-clause by design, which the orphan-break rule in
`validate_office.cjs` and the litany scan in `check_text_quality.py` would
otherwise read as column wraps. Both take their exemptions from the corrections
that introduce the breaks, keyed on `{office, field}` and on the exact line, so
a correction vouches only where it points and the exemption disappears with it
(ADR 0012). Do not widen either rule to make a correction fit; add the
correction and let it vouch. The two readers are hand-rolled in different
languages and are held to one reading by a conformance test in
`tools/tests/test_errata_breaks.py` — extend it when either side changes.

Systemic parsing problems are **not** corrections — fix those in the extractor (`_normalize_whitespace()` and friends in `tools/extract_offices.py`) so every instance resolves at once. The hardcoded fix dicts that used to live in `extract_psalter.py`, `extract_fats.py`, and `convert_lectionary.py` were migrated into the manifest and deleted; don't reintroduce that pattern (see issue #13).

## Delivery workflow

Before merging to main:
```bash
make test          # already includes check-integrity and the full qa gate
make test-web      # after any web/app.js, render.js, or CSS change
```

Before promoting staging to production:
```bash
make deploy-staging && make test-staging
node tools/compare_staging.cjs [date] [mp]   # review diff
node tools/compare_staging.cjs [date] [ep]   # review diff
# → human review of diffs
make promote
```

## Key constraints

- Lectionary coverage: rolling 12-month window, currently 2025–2026 (Year B)
- Office forms: 30 in `data/offices.json`; form selection is season- and weekday-aware
- PyMuPDF (fitz) is the sole PDF extraction dependency.
