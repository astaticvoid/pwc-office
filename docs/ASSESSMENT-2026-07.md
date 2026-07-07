# PWC — Project Assessment & Strategy Validation

_Written 2026-07-05 during a full audit. Audience: the project owner and future implementing sessions (including smaller models). This document holds the **reasoning**; the executable work lives in `docs/HANDOFF.md` (Batch 18/19), `BUGS.md`, and `ROADMAP.md`. When this document and a spec disagree, the spec wins — but update whichever is wrong._

---

## 1. Executive summary

The project is **healthy and close to trial-ready**. All automated gates pass (147 pytest, Vitest, integrity manifest, text-quality scan, zero unresolvable collect refs across 19 lectionary months). The architecture — extract-from-source, never-edit-data, integrity-hash gate, correction layers inside the extractors — is sound and is the right shape for the copyright constraints. The June field observations exposed one class of real error (small-caps casing) and three gaps where **data exists but nothing renders it** (`eucharist` propers, `observances`, `lessons_pick`). None are architectural; all nine fixes are specced in Batch 18.

The single most important process finding: **BUG-18 was "fixed" in the wrong direction and shipped** (litany responses lowercased when the PDF has "Holy One"). The lesson is not that a mistake happened — it's that casing corrections were made without a ground-truth oracle. Batch 19 adds that oracle (`pdftotext` decodes the small-caps font correctly; pdfplumber doesn't). **Rule going forward: no casing/text patch lands without citing the oracle or PDF line numbers as evidence.**

Strategic context (stated by the owner, 2026-07-05):
- The app is **under trial by the Anglican Church of Canada** to determine feasibility as the official prayer app.
- ACC is **obtaining the rights to distribute the copyrighted texts in the app** (distribution builds may contain texts; the open-source repo must not).
- ACC's **prime desire is mobile apps** — the Capacitor shell (committed 2026-06) is the vehicle.
- Correctness errors erode trust with this audience more than missing features do. The existing "cleanup before features" priority principle is correct; keep it.

## 2. Health snapshot (2026-07-05)

| Check | Result |
|---|---|
| `make check-integrity` | ✅ all data files match extraction manifest (no monkey-patching) |
| `make test` (Vitest + 147 pytest) | ✅ all pass |
| `make check-text` | ✅ no PDF-artifact patterns |
| Collect ref resolution (all 19 months, MP+EP) | ✅ 0 unresolvable |
| Psalter | ✅ 150/150 psalms |
| Lectionary window | 2025-06 → 2026-12 (19 months, contiguous); 2027 pending ACC data (BUG-06) |
| Office forms | 31 forms; 30/30 audited forms pass CLI correctness audit |
| Open bugs | 9 (2×P1, 4×P2, 3×P3) — all specced in Batch 18; none architectural |
| Stale docs | ROADMAP §4.4 "Go CLI parity" — the Go CLI no longer exists (Node CLI replaced it); §5 still describes Capacitor as a future decision (it shipped) |

## 3. Strategy validation: extraction-embedded fixes vs `patches.json`

The project has **four** correction mechanisms. Assessment: this is the right design, but the boundaries need to be stated once, plainly, because choosing the wrong layer is how BUG-18-class errors happen.

| Layer | Lives in | Right for | Wrong for |
|---|---|---|---|
| Parsing logic + `_DIVINE_FIXES` / `_fix_casing` | `extract_offices.py` | **Systematic** artifacts of the PDF encoding (small-caps → lowercase, spacing). Fixes whole classes. | One-off wording. |
| `_TEXT_PATCHES` | `extract_offices.py` | Individual strings where the *extraction* is wrong and no rule generalises. | Anything a `_DIVINE_FIXES` rule could cover (prefer the rule — it protects future extractions of other texts). |
| Correction dicts (`LESSON_FIXES`, `NAME_FIXES`, …) | `convert_lectionary.py` | Individual CSV cells that are wrong/garbled at source. Keyed by date+office; self-documenting. | Patterns appearing >3 times (fix the parser instead — see Batch 18 Fix B/F which turn recurring artifacts into parser rules). |
| `data/patches.json` | data repo + `apply_patches.py` | **Editorial judgment** that isn't a parsing fix (wording the source itself gets wrong, page mislabels). Versioned, validated, visible. | Anything expressible as extraction logic. |

Why this layering beats alternatives that were implicitly on the table:

- **Post-extraction sed-style patching of `data/*.json`** would be simpler per-fix but destroys the property that `make extract` from clean sources reproduces the shipped data — which is the entire copyright/open-source story (§5) *and* the integrity guard's premise. Rejected, and the `check-integrity` gate enforces the rejection.
- **All fixes in `patches.json`** would make the extractors "pure" but scatter parsing knowledge into data; a re-extraction against a new PDF edition would silently re-break everything the parser could have handled. `patches.json` staying small (6 entries) is a health indicator — watch it: if it grows past ~15, parsing rules are being dodged.
- **Tradeoff accepted:** embedding fixes in extractors means corrections only take effect after `make extract`, and contributors must run the pipeline to see them. That cost is already paid by the copyright design (contributors must extract locally anyway).

**Verdict: keep the design.** The one weakness is evidential, not structural — corrections were applied on visual inspection ("looks lowercase in the PDF") rather than verified decoding. Batch 19's casing oracle closes that.

## 4. Data quality: how to raise confidence (the program)

Current quality is high (see §2) but confidence was, until now, anecdotal — trust in past audits plus field reports. The June observations show field reports work but arrive one at a time. The program below converts the biggest error classes into machine checks. Priority order:

1. **Casing oracle** (`check_casing.py`, Batch 19.1) — pdftotext as ground truth for every leader/response/label segment. Would have caught all 22 BUG-25 errors and prevented BUG-18. *This is the highest-leverage quality tool available to this project.*
2. **Column-wrap detector** (Batch 19.2) — prose lines ending without punctuation. Prevents BUG-29 regressing at next extraction.
3. **Structural lectionary invariants** — extend `validate_lectionary.py`: every `lessons` citation must match a citation grammar (`^[1-4]? ?[A-Z][a-z]+`… plus known abbreviations); would have caught "Coll above", "O Antiphon", and the 2026-09-27 merge mechanically. Cheap; a Sonnet-sized task; do it when touching that file.
4. **Category audit completion** — `NOTE_TYPES` is complete for 2026 only; the rolling window includes 2025-06 onward. Audit 2025 H2 notes (small: one pass over ~180 days' `notes` fields, classify, extend the dict).
5. **Spelling** — lowest priority: liturgical vocabulary defeats stock dictionaries. If wanted: `aspell list` over extracted text with a committed allowlist (`tools/spell_allowlist.txt`), advisory only. Do not gate on it.

What NOT to build: LLM-based text comparison as a gate (already exists as `test-smoke`/`test-seasonal` for citations, appropriately non-blocking); pixel-level PDF diffing (the golden-file `check-book` already covers layout-faithfulness where it matters).

## 5. Copyright & distribution posture (validated)

Constraint set: open-source repo **must not** contain or derive-and-ship copyrighted ACC/BAS text; the ACC-distributed **app builds may** (rights being obtained by ACC); contributors need a streamlined path from clean checkout to working app.

Audit result — the posture is **correct and complete**:
- `sources/*` gitignored (except the public bas_short CSVs — *verify these are ACC-published-as-public before any repo publicity*), `data/*` gitignored except KJV (public domain) + `patches.json` (short snippets).
- Golden fixtures, Capacitor-synced assets (`ios/App/App/public/`, `android/…/assets/public/`), and audit artifacts are all gitignored — checked each.
- `make fetch-sources && make extract` is the streamlined path; `extract_manifest.json` (hashes+counts only) gives extraction history without content. `data/`'s own local git gives content diff/rollback locally.
- The deploy gate (`check-integrity` inside `make deploy`) enforces that shipped data is pipeline-produced.

One residual risk to track: **the Capacitor store builds bundle the texts into the app binary.** That is exactly what the ACC rights negotiation covers — but until rights are granted, TestFlight/Play internal tracks count as distribution to testers. Keep beta distribution within the Synod evaluation group under ACC's direction; note this in any store-submission checklist.

## 6. Parked design decisions (need the owner, not code)

- **General propers surface**: should days with full Eucharistic propers (NIDP-class) show more than the collect (Prayer over the Gifts, etc.) in a Daily Office app? Batch 18 Fix C deliberately ships only the collect.
- **Name substitution**: settings for diocesan bishop / sovereign names replacing *N* (Batch 18 Fix H ships italics only). Nice for an official app; needs a UX decision.
- **`observances` field**: still has no consumer after Fix C (the collect comes via `collect_inline`). Either render eve-of/feast chips from it or document it as converter-internal.
- **FATS minor-feast readings** (Milestone 3) — design pending since June.

## 7. Efficiency of methods (observed)

- The pipeline is fast (extraction seconds, tests sub-second for unit tiers) and the Make-target taxonomy is well-factored: cheap gates (`test`, `check-integrity`, `check-text`) vs network/LLM tiers (`validate`, `test-smoke`, `test-seasonal`) vs E2E. No changes recommended.
- The HANDOFF batch workflow (spec → implement → :8081 review → deploy) has produced 17 clean batches; keep it, with Claude Code now performing the :8081 review itself (Cowork retired 2026-07-05; deploy still requires the owner's go-ahead). Its weakness is spec ambiguity when the spec author hasn't verified against data — the Batch 18 specs therefore embed exact expected outputs and grep counts.
- Field observations (June 21/23/24) took ~2 weeks to reach triage. Cheap improvement: a standing "Field observations" inbox section at the top of BUGS.md so notes land with a date and get triaged next session.

## 8. Guidance for implementing sessions (Opus/Sonnet/Haiku)

1. **Never edit `data/*.json`.** If output is wrong, the fix is in `tools/` (or `patches.json` for editorial judgment). `make check-integrity` will catch you; don't fight it.
2. **Evidence before patches.** Any text/casing correction must cite `pdftotext` output (line numbers) or the Batch 19 oracle. If the oracle and pdfplumber disagree, pdftotext wins for *casing*; pdfplumber wins for *layout/structure*.
3. **Follow Batch 18 in order, one commit per fix, push each.** Re-extract + full gates after every extractor change. Expected-output greps in the spec are acceptance criteria, not suggestions.
4. **When a fix touches ≥4 similar instances, stop and write a parser rule instead of enumerated patches** (the BUG-25/26/33 lesson). If unsure which layer a correction belongs in, consult the table in §3.
5. **Don't expand scope mid-batch.** Parked decisions (§6) need the owner; note new findings in BUGS.md "Field observations" and move on.
6. **The priority order is: Batch 18 → Batch 19 → mobile milestones (ROADMAP §5.4).** Mobile is the ACC's prime desire; correctness fixes come first only because they're small and trust-critical.

## 9. Model routing (added 2026-07-06)

Right-size the model to the cognitive load of the task, and right-size the *orchestrator* so cheap glue can stay inline instead of being delegated.

| Tier | Give it | Examples in this repo |
|---|---|---|
| **Haiku** | Rote, spec-complete work with no judgment | Test bodies transcribed from an exact spec; mechanical find/replace across enumerated sites |
| **Sonnet** (workhorse) | Single/few-file fixes with a clear spec; straightforward extractor or converter edits; wiring tests to a suite | Most individual Batch-18-style fixes; `LESSON_FIXES`/`NAME_FIXES` additions; render-path tweaks |
| **Fable / Opus** | Orchestration; cross-cutting reasoning; **correctness & liturgical audits**; ambiguous specs; golden-file "is this diff acceptable" judgment | Running a batch; auditing diffs against the PDF; deciding which correction layer (§3) a fix belongs in; anything where being wrong ships a text error to the ACC audience |

**Delegation economics — the load-bearing rule.** A subagent costs a spawn plus cold re-derivation of context (HANDOFF spec, target files, the pdftotext gotcha, the re-extract/verify loop). Only delegate when the task's value clears that fixed cost:

- **Do NOT delegate trivial glue.** `git commit`, a 5-line edit in a file the orchestrator already has loaded, a single grep — the orchestrator (kept on a strong model) does these inline. Serializing working-tree state into a subagent prompt costs more than the op.
- **Do NOT delegate work already in the orchestrator's context** mid-batch. If the files and mental model are loaded, finishing inline beats a cold agent re-reading everything to write 20 lines.
- **DO delegate the independent audit.** After a batch, a fresh Fable/Opus agent reads the diffs against the evidence with no confirmation bias — bounded context (diffs + BUGS.md + PDF), high value. This is the delegation that pays.
- **DO delegate genuinely parallel or cold-start work.** Future batches begun fresh; several independent fixes at once. For parallel *data-pipeline* fixes use `isolation: worktree` — `make extract` mutates shared `data/`, so concurrent extractor edits collide without it.
- When delegating, pass the model explicitly and hand the subagent the spec section + exact acceptance greps so it doesn't re-plan.
