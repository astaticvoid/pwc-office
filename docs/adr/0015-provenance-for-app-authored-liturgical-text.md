# ADR 0015: Provenance for app-authored liturgical text

## Status
Accepted (2026-08-07)

Corrected (2026-08-08): the Context's claim that the Holy Word erratum "is in
neither errata document" was wrong — it is documented at Ordinary p. 132
("PWC has the wrong order"). The decision is unchanged: the reading response
is synthesized rather than extracted, so the fix belongs in the extractor.
`upstream-review` remains the source for the four app-rubric wording
corrections, which genuinely have no errata document behind them.

Superseded in part (#84, #88): the Context below states that
`data/offices.json` "contains exactly one `continues with` rubric" and that the
psalm and reading introductions "are ours". Both were true of the data as it
stood. Neither is true now — the running-header fix recovered the printed
rubrics the old filter had been swallowing, so the book's own wording for the
Psalm and Reading introductions, and for the canticle and affirmation
hand-offs, is extracted into `form.psalm_rubrics` / `form.reading_rubrics` and
the section trailers.

The register therefore holds one entry, not ten. Nine were retired: the app was
not authoring those sentences, it was reproducing book text it had no way to
see it had. Where upstream review had settled a wording (ADR 0019 items 3, 4
and 6), the settled text now reaches the page as a correction on the extracted
rubric — the `adr0019-*` entries in `data/corrections.json`, `source:
upstream-review` — rather than as a second string rendered beside the book's.

That is a change of mechanism, not of decision. Every reading review settled
still ships, in the wording it settled. What moved is where the divergence is
recorded: in the manifest, next to the text it diverges from, where
`validate_corrections.py` checks it still applies and a stale one fails the
build. The register was the right home for text with no source behind it; it
was never able to record a divergence *from* a source, because the whole
premise was that no source existed.

`intercessionsPrompt` had already gone under ADR 0013 (#60). What is left is
`readingsPick`, the one string with no printed sentence behind it at all.

The Context and Decision below are left as written — they record what was known
and decided at the time.

Corrected (#91): the Status note above records that "the reading response is
synthesized rather than extracted, so the fix belongs in the extractor." The
reading responses are printed on the page and extraction now recovers them into
a real `reading_response` section (retiring `_add_reading_responses`), so that
premise no longer holds. The ordinary-time inverted wording ("Holy wisdom, holy
word.") is now corrected by a `pwc-errata-ordinary` manifest entry against
`_shared.reading_response_ordinary` — the same change of mechanism this Status
block already records for the psalm/reading rubrics. The decision is unchanged:
the Holy Word text ships as "Holy Word, Holy Wisdom." in every season, and ADR
0019 item 1's no-seasonal-branch rule is now enforced by the source (the 30
forms print the same three alternatives) rather than by a code comment.

## Context

ADR 0005 established one manifest for every correction to *extracted* data, and
ADR 0012 made its `source` field load-bearing. Both govern text that came out of
the PDF. Neither governs text the app makes up.

The app makes up a lot. Ten rubric strings are authored in JavaScript, with no
source, no manifest entry, no validator, and no audit:

| Location | Text |
|---|---|
| `render.js:95` | Offer intercessions, petitions, and thanksgivings, silently or aloud. |
| `render.js:509` | A Reading from the appointed lectionary is read. |
| `render.js:510` | After a period of silent reflection one of the following is said. |
| `render.js:534` | *One of the following N readings are read.* (generated) |
| `app.js:479` | At the end of the Psalm one of the following may be said or sung. |
| `app.js:497` | A Psalm from the appointed lectionary is said or sung. |
| `app.js:502` | The following Psalms from the appointed lectionary are said or sung. |
| `app.js:504` | The following Psalm from the appointed lectionary is said or sung. |
| `app.js:998` | *{Morning,Evening}* Prayer continues with an Affirmation of Faith or the Litany. |
| `app.js:1014` | *{Morning,Evening}* Prayer continues with the Litany. |

The first is authored twice — `render.js:95` and again, verbatim, in
`cli/book.js:51`. ADR 0013 removes both, but the duplication is the symptom:
invented liturgical text propagates by copy because nothing owns it.

`data/offices.json` contains exactly one `continues with` rubric — *"Evening
Prayer continues with [the Second Reading or] the Canticle or an Affirmation of
Faith."* The two in the table above are not it. They read as book text, are
styled as book text, and are ours.

Upstream review found four of the ten wrong: "or the Litany" should be "or the
Prayers" in both offices, and "from the appointed lectionary" should be dropped
from the psalm and reading introductions. A 40% error rate, in text the reader
will take as authorized, caught only by someone reading the running app. Nothing
in `make test` or `make qa` could have found it, because there is nothing to
check against.

The same review produced a correction with no home in the existing scheme: the
Ordinary Time reading conclusion *"Holy wisdom, holy word."* should read *"Holy
Word, Holy Wisdom."* everywhere, in all seasons. It is in neither errata
document, so none of the six `PERMITTED_SOURCES` in `validate_corrections.py`
describes it.

It is also not an `office_text` correction, because the text is not extracted.
`_add_reading_responses` (`extract_offices.py:882-917`) *synthesizes* the whole
response — its docstring says so — and branches on
`office_key.startswith('ordinary-')` to emit the lowercase inverted form for the
14 Ordinary offices. Neither string appears anywhere in `data/paragraphs.json`:

    'Holy Word'   in extracted paragraphs: 0
    'Holy wisdom' in extracted paragraphs: 0

So this is not a book typo we faithfully reproduced. We invented both strings
and hardcoded a seasonal/ordinary distinction with nothing behind it. That is
the clearest possible statement of the problem this ADR addresses: text with no
provenance drifts, and nothing in the pipeline can tell.

## Decision

**Liturgical text the app authors is held to the same provenance standard as
text it extracts.**

1. **A register of app-authored liturgical text.** The ten strings above move to
   one exported table in `render.js`, each with a `source` drawn from the same
   vocabulary the manifest uses, and a note recording what authorizes it.
   Scattered template literals cannot be reviewed as a set; a table can, and the
   next liturgist to read the app can be handed it directly.
2. **A new `source` value, `upstream-review`** — *a correction from upstream
   review of the app, with no errata document behind it.* Added to
   `PERMITTED_SOURCES` (`validate_corrections.py:33`) and usable in the
   register. It deliberately does **not** begin with `pwc-errata-`: ADR 0012
   keys break-vouching on that prefix, and a source with no document behind it
   must not quietly acquire the power to exempt a line break from the
   orphan-break rule.
3. **Each `upstream-review` item gets a row in `docs/errata/README.md`**, next
   to the existing account of which errata became corrections — what changed and
   what was decided. Enough for the next reader to know why the text says what
   it says.
4. **The Holy Word fix is a code fix, not a manifest entry.** AGENTS.md: systemic
   problems are fixed in the extractor, not corrected downstream. Our code
   invents the wrong string, so the branch at `extract_offices.py:914` is deleted
   and the docstring at `:882-888` corrected — it currently documents the error
   as intended behaviour. Provenance goes in the `docs/errata/README.md` table
   under (3). Adding a manifest entry to patch a string we ourselves generate
   would be the fix-dict pattern issue #13 removed.
5. **The four wrong rubrics are corrected in the register**: "or the Litany" →
   "or the Prayers" at `app.js:998`, and "from the appointed lectionary" dropped
   at `app.js:497`, `502`, `504` and `render.js:509`.

`app.js:1014` — *"Morning Prayer continues with the Litany."* — is **left
alone**. What was approved was the change at `app.js:998` for both Morning and
Evening (that string is already parameterized over both, so one edit covers it).
This is a different rubric, emitted before the Litany subsection, and was not
part of it. Flagged for confirmation rather than guessed at.

## Consequences

### Positive
- The category of defect that produced four wrong rubrics becomes visible: the
  register is a list a liturgist can review in one sitting, which is the only
  control that would actually have caught them.
- `upstream-review` closes a real gap. A review finding had no way to be
  recorded, so it would have landed as `editorial` — "a project editorial
  decision, with no upstream error behind it" — which is precisely wrong about
  what kind of decision it was.
- Keeping the new source outside the `pwc-errata-` prefix keeps ADR 0012's
  exemption tied to the errata documents, which are in the repo and reviewable
  as diffs.

### Negative
- A seventh `source` value, on an enum ADR 0012 already flagged as having drifted
  from ADR 0005's documented three to six with no schema written. This ADR adds
  to the drift rather than fixing it; the JSON Schema ADR 0005 promised is still
  unwritten and this is one more reason it should be.
- The register is a convention, not an enforced constraint. Nothing stops the
  next rubric being written inline as a template literal. A lint rule could
  catch `class="seg-rubric"` outside the register, and probably should, but that
  is a bigger commitment than this ADR needs to make now — the register's value
  is reviewability, and it delivers that on day one.
- Deleting the `ordinary-` branch changes `_shared.reading_response_ordinary`
  for all 14 Ordinary forms at once. Expect movement in the cross-form text
  audit and possibly in coherence scores; ADR 0012's notes record that a
  correction to one form can move its peers' statistics.

### Neutral / Notes
- The Holy Word correction is errata-documented (Ordinary p. 132), not
  `upstream-review` — the Context said otherwise and the Status note above
  corrects it. It still cannot be an `office_text` correction: the text is
  synthesized rather than extracted, so the fix lives in the extractor and the
  provenance in the `docs/errata/README.md` table.
- ADR 0016 states the general constraint this applies, and defers to this ADR
  for text the app authors rather than extracts.
- The errata documents are published here with their letter headers pruned, as
  `docs/errata/README.md` already records. Keep it that way — review is a
  working conversation, and this repo is public.
