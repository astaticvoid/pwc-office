# ADR 0021: Errata source documents are a gitignored input, not repository content

## Status
Accepted (2026-08-17)

## Context

`docs/errata/ordinary-time.md` (363 lines) and `docs/errata/seasonal.md` (681
lines) reproduce the ACC errata documents for *Pray Without Ceasing* verbatim.
Because of the form the errata takes — each entry prints the whole corrected
block rather than expressing it as a rubric — reproducing the errata means
reproducing the corrected liturgical text in full. Their headers also carry
the source `.docx` filenames and the date received.

AGENTS.md's "Distribution posture" states plainly: *the open-source repo must
not contain or ship copyrighted ACC/BAS text.* `sources/*` and `data/*` are
gitignored for exactly this reason — `sources/pray-without-ceasing.pdf` is
held locally, reproducible by anyone with their own copy, never committed.
These two files under `docs/` are the same class of artifact and are not
currently held to the same rule (#86).

**This conflicts with ADR 0015.** Its Notes section states: *"The errata
documents are published here with their letter headers pruned, as
docs/errata/README.md already records. Keep it that way — review is a
working conversation, and this repo is public."* That was the considered
position at the time — pruning the personal letter header was treated as
sufficient to make publication safe. AGENTS.md's distribution posture, as it
now reads, does not carve out an exception for review material: it draws the
line at copyrighted text, not at whether personal correspondence has been
removed from around it. Accepting this ADR supersedes that one line of ADR
0015's Notes; its own Status section carries a note on acceptance recording
exactly what still stands and what doesn't, rather than repeating the account
here.

Nothing about the *record* of what the errata said and decided needs to move.
`docs/errata/README.md` — the declarations table, the "Upstream review" table,
the applied-corrections accounting — is our own writing: rulings, a word or
two quoted at most (`who`/`whose`, `form`/`from`), never a reproduced block.
The durable evidence trail already lives outside the two documents in
`data/corrections.json` (45 `office_text` entries carrying `source:
pwc-errata-ordinary` / `pwc-errata-seasonal`, load-bearing per ADR 0012 for the
line-break exemptions).

The precedent for how a gitignored copyrighted input is tracked already exists
and is inconsistent within itself: `tools/extract_manifest.json`'s
`source_hashes` records `sources/bas_short_2026.csv` (public) but not
`sources/pray-without-ceasing.pdf` (copyrighted). This ADR follows the
PDF's precedent — untracked — rather than invent a third treatment.

`tools/audit_errata.py` globs `docs/errata/*.md` and, before this ADR's
prerequisite fix (#86, landed ahead of acceptance since it is a pure
hardening with no distribution-posture judgment in it), a missing document
read as zero findings — `"Errata fully applied"` — indistinguishable from a
real pass. It now checks for the two files by name and reports `SKIPPED`
instead, so removing them from the repository does not silently defang the
audit.

## Decision

**Reclassify the two errata source documents as a gitignored local input, the
same treatment already given `sources/pray-without-ceasing.pdf`.**

1. Add `docs/errata/ordinary-time.md` and `docs/errata/seasonal.md` to
   `.gitignore`, and remove them from tracking (`git rm --cached`) without
   deleting the working-tree copies — a contributor who already has them
   locally keeps using them; a fresh checkout does not receive them.
2. `docs/errata/README.md` stays, and gains a short note at the top stating
   the two source documents are a local, gitignored input (mirroring how
   `sources/*.pdf` is described in AGENTS.md), not something a fresh checkout
   will find.
3. `tools/audit_errata.py`'s missing-file handling (above) ships as a
   prerequisite, not a consequence — it is correct regardless of this ADR's
   outcome, and is why it landed already.
4. No change to `tools/extract_manifest.json`'s `source_hashes` — consistent
   with `sources/pray-without-ceasing.pdf` staying untracked there today.
5. `tools/validate_corrections.py`'s `PERMITTED_SOURCES` descriptions
   (`"the errata for Ordinary Time (docs/errata/ordinary-time.md)"` etc.) are
   strings only, never read from disk — no change needed, checked as part of
   this ADR's review rather than left as a follow-up.
6. The Makefile's `audit-errata` target and its comment name no files
   directly and need no change; `make audit-errata` against a fresh checkout
   now prints the `SKIPPED` report from (3) rather than a false pass.

## Consequences

### Positive
- Closes the distribution-posture gap #86 identified: the repository stops
  shipping the one place copyrighted corrected text sat outside `sources/`
  and `data/`.
- The precedent this sets — an input document can move from "published for
  review" to "gitignored, review already had" once its working conversation
  is over — is reusable for future review artifacts, not just these two.
- `audit_errata.py` becomes honest about a missing input at the same time,
  closing the vacuous-pass gap independent of whether this ADR is accepted.

### Negative
- A reviewer without their own copy of the `.docx` originals can no longer
  read the errata's own wording from the repository — only `README.md`'s
  summary of what it said and decided. `README.md`'s declarations table
  already quotes the specific words in dispute, which is the part a future
  auditor actually needs; the full corrected blocks are not.
- Reverses an explicit, considered ADR 0015 position rather than extending
  it. Recorded above rather than silently changed; ADR 0015 itself is left
  as written, per this project's convention of appending corrections to a
  Status block rather than editing a decision's history away — its Status
  gets a note pointing here once this ADR is accepted.

### Neutral / Notes
- The two documents stay in git history, unchanged from the precedent already
  set for the copyrighted golden fixtures: this stops forward distribution,
  it does not rewrite the past.
- `git rm --cached` (not deletion) is required specifically so this lands
  without disrupting any contributor's working tree that already holds the
  files — the same reasoning `sources/*` gitignoring already relies on.
