#!/usr/bin/env python3
"""check_conservation.py — compare the shipped extracted data against the page.

Every other check in this project compares the data against itself or against a
hardcoded expectation. `check_data_integrity.py` hashes `data/*.json`, which
proves the output did not change, not that it is right. So the whole defect
class this project keeps hitting — text silently left the pipeline, or was
silently invented — is invisible to `make qa` by construction (#94).

This walks the source lines for each form, exactly as extraction does, and
accounts for every one of them in both directions:

  PAGE → DATA   every printed line either ships, or matches a named rule saying
                why it does not.
  DATA → PAGE   every shipped line either was printed, or matches a named rule
                saying where else it came from.

The residue is the defect list. A line matching no rule is a bug, and the check
fails on it. Read the rule table as the answer to "what does this pipeline
change about the source, and why" — it is the same question #92 asks in prose,
made enforceable.

Nothing here hardcodes book text: the rules are predicates, and the report
identifies an unaccounted line by form, section and content hash. `--show-text`
prints the line itself for local diagnosis and is deliberately not the default,
so the check stays safe to run anywhere its output might be kept.

**What it cannot see.** Conservation is a set property, per form: it asks whether
a line is present, not how many times or where. So it does not catch a line that
still appears somewhere in the form but in the wrong place, and it does not catch
one occurrence of a repeated line going missing — deleting a single instance of a
litany's response refrain leaves the other instances satisfying the check.
Multiplicity and placement are #99's subject, and the two checks are complements
rather than overlapping: this one is the only thing that can see text leave the
pipeline, and that one is the only thing that can see surviving text move.

The two directions within this check are themselves complements, and neither
alone is a conservation proof: a printed line the shipped text begins with is
accounted for by substring going PAGE→DATA, so a suffix the page printed and the
data dropped is absorbed that way and surfaces only in the DATA→PAGE residue
(the #101 shape). Reading one direction as sufficient is how a dropped suffix
stops being a defect.

**Chains.** The methodology is offices-shaped (field segments), but the same
two-direction argument applies to the other published chains, which have had
their own silent-drop defects and nothing compared them to the page (#102). The
psalter is the first chain to share it: `--chain psalter` walks the same PDF's
psalter section line-by-line and accounts every verse, continuation, section
heading and psalm head against `data/psalter.json`, with its own `corrected`
rule (the `data/corrections.json` "psalter" entries applied to
`.build/psalter.1-extract.json`). Baseline entries carry an optional `chain`
field (default "offices") so a divergence in any chain can be licensed without
colliding with another's.

Usage:
    python3 tools/check_conservation.py [--show-text] [--json] [--form KEY]
                                        [--chain offices|psalter|fats|midday]
"""

import argparse
import contextlib
import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# PyMuPDF prints its `fitz` deprecation banner to stdout on import, which would
# land in the middle of `--json` output. Send anything the imports say to stderr;
# this file's stdout is the report and nothing else.
with contextlib.redirect_stdout(sys.stderr):
    import fitz  # PyMuPDF

    # The manifest's own segment walk, for the penitential `corrected` rule:
    # replaying the `_penitential` entries over the pre-correction artifact
    # must use the same walk the validator and applier use, or reconstruction
    # and application could disagree about what was authorised.
    from corrections_lib import iter_text_segments, replace_occurrences

    # The fats extractor's own page walk and body parsers, for the `--chain
    # fats` walk — same rationale as the psalter: classify with the code under
    # test, not with a copy of its predicates.
    from extract_fats import (
        _extract_bio_body,
        _fats_keys,
        _page_text_without_margin_artifacts,
        is_bio_page,
        is_propers_page,
        parse_bio,
        parse_propers,
        strip_garbage_header,
    )

    # The mid-day extractor's own page walk, span classification and line
    # merge, for the `--chain midday` walk — same rationale: classify with the
    # code under test, not with a copy of its predicates (#166).
    from extract_midday import (
        _COLLECT_RUBRIC_RE,
        _FIELD_BOUNDARY_PREFIXES,
        _LORDS_PRAYER,
        _OR_FOLLOWING_RE,
        _PSALMODY_RUBRIC_RE,
        _READING_RUBRIC_RE,
        _TITLE,
        _merge_lines,
        _page_lines,
        detect_pages,
    )
    from extract_office_styles import document_metrics, extract_office_typed_lines

    # The extractor's own predicates, imported rather than restated: every
    # decision that can drift is made by the code under test, not by a copy of
    # it here.
    from extract_offices import (
        _CONTINUE,
        _CONTROL_CHARS,
        _PEN_SUBHEAD_RE,
        _RESPONSE_HDRS,
        OFFICES,
        PENITENTIAL_BOUNDS,
        _alt_label,
        _heading_to_key,
        _is_noise,
        _normalize_whitespace,
        _pen_clean,
        _pen_span_lines,
    )

    # The psalter extractor's own line classification and source reader, for
    # the `--chain psalter` walk — same rationale: classify with the code under
    # test, not with a copy of its regexes.
    from extract_psalter import (
        RE_BOOK,
        RE_PSALM_HEAD,
        RE_SECTION,
        RE_VERSE,
        normalise_quotes,
        pdf_lines_with_x0,
        strip_page_header,
    )

ROOT = Path(__file__).parent.parent
PDF = ROOT / "sources" / "pray-without-ceasing.pdf"
SHIPPED = ROOT / "data" / "offices.json"
PRE_CORRECTION = ROOT / ".build" / "offices.2-normalized.json"
CORRECTIONS = ROOT / "data" / "corrections.json"
BASELINE = ROOT / "tools" / "conservation_baseline.json"

# Sections whose page content is a lectionary lookup rather than form text. The
# fixed rubrics printed around it are kept; everything else on those pages is
# supplied per day (#84).
LECTIONARY_SECTIONS = ("psalm_rubrics", "reading_rubrics")


# ── Text comparison ───────────────────────────────────────────────────────────

def squash(text: str) -> str:
    """Normalise a line to what a reader would call the same text.

    Composition, non-breaking spaces and run-length of whitespace are all
    typesetting, not content, and differ freely between a PDF span and a JSON
    string. Everything else must match exactly — this is deliberately not a
    fuzzy match, because a fuzzy match would account for the defects.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def line_id(text: str) -> str:
    """Stable short identifier for a line, carrying no readable text."""
    return hashlib.sha256(squash(text).encode("utf-8")).hexdigest()[:10]


def _fix_whitespace(text: str) -> str:
    """Apply the extractor's own whitespace normalisation to one string.

    Routed through the real function rather than a copy of its replacements, so
    a new artifact fixed in extraction is accounted for here without an edit.
    The probe has to look like an ordinary office — `_normalize_whitespace`
    skips underscore-prefixed keys and only walks list-valued fields.
    """
    probe = {"probe": {"section": [{"type": "leader", "text": text}]}}
    return _normalize_whitespace(probe)["probe"]["section"][0]["text"]


# ── The shipped side ──────────────────────────────────────────────────────────

def iter_segments(node, shared: dict, seen: frozenset = frozenset()):
    """Yield every segment dict reachable from an office field.

    Follows `{"type": "shared"}` into `_shared`, which `corrections_lib`
    deliberately does not: a corrector must not reach a block through one form,
    but a conservation check must see everything the reader is shown. `seen`
    guards a shared block that referenced itself.
    """
    if isinstance(node, list):
        for item in node:
            yield from iter_segments(item, shared, seen)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "shared":
        key = node.get("key")
        if key in shared and key not in seen:
            yield from iter_segments(shared[key], shared, seen | {key})
        return
    if node.get("type") == "alternatives":
        for group in node.get("groups", []):
            if group.get("label"):
                yield {"type": "label", "text": group["label"]}
            yield from iter_segments(group.get("segments", []), shared, seen)
        return
    if isinstance(node.get("text"), str):
        yield node


class ShippedForm:
    """The text one form ships, indexed for both directions of the check."""

    def __init__(self, form: dict, shared: dict):
        self.lines: set[str] = set()       # every shipped line, squashed
        self.blocks: list[tuple[str, str]] = []   # (section, segment flattened)
        self.raw_blocks: list[tuple[str, str]] = []  # (section, segment verbatim)
        self.labels: set[str] = set()      # alternatives group labels
        self.origin: dict[str, tuple[str, str]] = {}  # squashed line → (section, type)
        self.section_shared: dict[str, str] = {}  # field → _shared key, for shared refs

        for section, field in form.items():
            if section in ("title", "subtitle"):
                self._add(section, "header", field)
                continue
            # A field that is nothing but a {type: shared} pointer resolves to a
            # _shared block the applier corrects directly (office "_shared",
            # field == the key). Record the key so apply_manifest can honour a
            # correction whose field is the key, not the form section name.
            if isinstance(field, dict) and field.get("type") == "shared":
                self.section_shared[section] = field.get("key", "")
            for seg in iter_segments(field, shared):
                self._add(section, seg["type"], seg["text"])
                if seg["type"] == "label":
                    self.labels.add(squash(seg["text"]))

    def _add(self, section: str, seg_type: str, text: str) -> None:
        if not isinstance(text, str):
            return
        self.raw_blocks.append((section, text))
        self.blocks.append((section, squash(text.replace("\n", " "))))
        for line in text.split("\n"):
            key = squash(line)
            if key:
                self.lines.add(key)
                self.origin.setdefault(key, (section, seg_type))

    def has(self, text: str) -> bool:
        return squash(text) in self.lines

    def find(self, text: str) -> str | None:
        """The section holding this line, counting one joined by reflow.

        Returns the section name so a caller can ask the manifest whether that
        field was authorised to change — a bare boolean would force the
        correction lookup to guess at which entry it was looking for.
        """
        needle = squash(text)
        if not needle:
            return None
        for section, block in self.blocks:
            if needle in block:
                return section
        return None


# ── The source side ───────────────────────────────────────────────────────────

class SourceLine:
    __slots__ = ("type", "text", "section", "consumed_as")

    def __init__(self, typ: str, text: str):
        self.type = typ
        # A leading space marks a physically indented verse continuation, and a
        # control character is an unmapped glyph; neither is content.
        self.text = _CONTROL_CHARS.sub("", text).strip()
        self.section: str | None = None
        self.consumed_as: str | None = None


def read_source_lines(form_key: str, typed_lines: list) -> list[SourceLine]:
    """The lines extraction sees, tagged with the section each landed in.

    This repeats the shape of `extract_office`'s two walks — the header pass and
    the section-assignment pass — but every decision inside them is made by an
    imported predicate (`_is_noise`, `_heading_to_key`, `_RESPONSE_HDRS`), so
    the two cannot disagree about what a line *is*. What is restated is only the
    bookkeeping: which section a line was in when it was dropped, which the
    extractor has no reason to record and this check cannot work without.
    """
    out: list[SourceLine] = []
    title_seen = header_done = False

    for typ, text, _gap, _slack, _lead in typed_lines:
        if not text.strip() or _is_noise(typ, text):
            continue
        line = SourceLine(typ, text)

        if not header_done:
            if not title_seen and typ == "heading":
                title_seen = True
                line.section, line.consumed_as = "title", "header"
                out.append(line)
                continue
            if title_seen and typ == "leader":
                line.section, line.consumed_as = "subtitle", "header"
                out.append(line)
                continue
            if title_seen and typ == "heading":
                header_done = True

        out.append(line)

    # Second pass: section assignment, using the extractor's heading map.
    current: str | None = None
    for line in out:
        if line.consumed_as == "header":
            continue
        if line.type == "heading":
            key = _heading_to_key(line.text)
            if key is False:
                # An antiphon refrain set in heading style — content, not structure.
                line.section = current
                line.consumed_as = ("response"
                                    if any(p.match(line.text) for p in _RESPONSE_HDRS)
                                    else "rubric")
                continue
            if key is _CONTINUE:
                line.section, line.consumed_as = current, "heading"
                continue
            current = key
            line.section, line.consumed_as = key, "heading"
            continue
        line.section, line.consumed_as = current, line.type
    return out


# ── Rules ─────────────────────────────────────────────────────────────────────
#
# Ordered most-exact first. The first rule that accounts for a line wins, so the
# table reads as a ledger: how many lines ship as printed, and for each that does
# not, the named authority for the difference.

PAGE_RULES: list[tuple[str, str]] = [
    ("verbatim",      "ships exactly as printed"),
    ("reflowed",      "a column wrap joined by _reflow_by_geometry; the joined form ships"),
    ("whitespace",    "_normalize_whitespace: PyMuPDF span-join artifacts (' ,', 'Amen .')"),
    ("heading",       "consumed as structure — becomes a section key; the renderer knows the order"),
    ("separator",     "an Or/or separator consumed into the alternatives group it opens"),
    ("label",         "became an alternatives group label via _alt_label (article and citation stripped)"),
    ("lectionary",    "psalm/reading page content, supplied per day from the lectionary"),
    ("corrected",     "extracted intact, then changed by an audited data/corrections.json entry"),
    ("structure",     "a Penitential-Office subhead or bullet, consumed as a season/time key or list marker"),
    ("variant",       "the ordinary Penitential printing's absolution A, which omits 'your/' (#165)"),
]

DATA_RULES: list[tuple[str, str]] = [
    ("printed",       "appears on the page as printed"),
    ("printed-joined", "printed across a column wrap; ships as the joined line"),
    ("whitespace",    "_normalize_whitespace: PyMuPDF span-join artifacts"),
    ("label",         "an alternatives group label derived from a printed line"),
    ("structural",    "a Roman-numeral group label the extractor assigns, not book text"),
    ("corrected",     "introduced by an audited data/corrections.json entry"),
]

_ROMAN_LABEL = re.compile(r"^(?:I{1,3}|IV|V)$")
# The bare separators _group_alternatives turns into a group boundary. _merge
# absorbs an "Or" that names its option ("Or\nThe Song of Mary"), so only the
# unadorned ones reach here without their text surviving somewhere.
_BARE_SEPARATOR = re.compile(r"^(?:or|and)\.?$", re.IGNORECASE)


def load_corrections(category: str = "office_text") -> list[dict]:
    if not CORRECTIONS.exists():
        return []
    return json.loads(CORRECTIONS.read_text(encoding="utf-8")).get(category, [])


def _texts(value) -> list[str]:
    """Every string a correction's `old`/`new` carries.

    Substring corrections hold one string; whole-field ones hold a segment
    structure, and the text inside it is what a line has to be compared against.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [t for item in value for t in _texts(item)]
    if isinstance(value, dict):
        out = _texts(value.get("text", ""))
        for group in value.get("groups", []):
            out += _texts(group.get("segments", []))
        return out
    return []


def apply_manifest(pre: ShippedForm, corrections: list[dict],
                   form_key: str) -> list[tuple[str, str, str]]:
    """The pre-correction blocks with the manifest applied.

    Returns (section, before, after) per block, both sides flattened for
    comparison. This is the ADR 0005 statement made computable: source plus
    manifest equals shipped. A divergence is accounted for when applying the
    manifest to the extracted text actually reproduces what ships — not merely
    when an entry exists somewhere on the same field.

    Two weaker rules were tried first and both failed on the real corpus.
    Matching `{office, field}` alone let one three-word errata fix vouch for
    every line in the section, and 121 form-fields carry an entry, so nearly
    half the book was excused from the dropped-line defect (#84) this check
    exists to catch. Comparing the line against `old`/`new` directly then broke
    on the two shapes a real correction takes: a printed line straddles the end
    of a substring correction and runs on into the next sentence (the ADR 0019
    reading rubric, 30 forms), or begins mid-phrase and so contains neither side
    of it (the Pentecost litany). Only reconstruction handles both, because only
    reconstruction asks the question the manifest is actually an answer to.
    """
    # "_shared" is included because a correction that addresses a shared block
    # (office "_shared") applies to that block wherever a form's field resolves
    # to it — the same text the reader is shown, so the reconstruction must
    # carry it just as the real applier does (corrections_lib.resolve_offices).
    relevant = [c for c in corrections
                if c.get("office") in (form_key, "*", "_shared")
                and isinstance(c.get("old"), str)]
    whole = [c for c in corrections
             if c.get("office") == form_key and not isinstance(c.get("old"), str)]

    out = []
    # A form field that is a shared reference is corrected by the entry whose
    # field is the _shared key it points to (office "_shared"), not by the form
    # section name — the same text the reader is shown, corrected once in the
    # shared block. Honour both: a correction whose field equals the section, or
    # equals the _shared key that section resolves to.
    def field_matches(section: str, field: str | None) -> bool:
        return field == section or (
            field is not None and field == pre.section_shared.get(section)
        )

    for section, raw in pre.raw_blocks:
        after = raw
        for entry in relevant:
            if field_matches(section, entry.get("field")):
                after = after.replace(entry["old"], entry["new"])
        for entry in whole:
            # A whole-field entry replaces the field, not a segment, so it can
            # only be honoured at that granularity: any text in its `new` is
            # authorised for this section.
            if field_matches(section, entry.get("field")):
                after = "\n".join([after, *_texts(entry.get("new"))])
        out.append((section,
                    squash(raw.replace("\n", " ")),
                    squash(after.replace("\n", " "))))
    return out


# ── The check ─────────────────────────────────────────────────────────────────

class Finding:
    def __init__(self, form: str, section: str | None, seg_type: str,
                 text: str, direction: str):
        self.form = form
        self.section = section or "—"
        self.type = seg_type
        self.text = text
        self.direction = direction

    def render(self, show_text: bool) -> str:
        what = repr(self.text[:72]) if show_text else line_id(self.text)
        return f"    {self.form:<24} {self.section:<20} {self.type:<9} {what}"


def check_form(form_key: str, source: list[SourceLine], shipped: ShippedForm,
               pre: ShippedForm | None, corrections: list[dict],
               ) -> tuple[Counter, Counter, list[Finding]]:
    page_counts: Counter = Counter()
    data_counts: Counter = Counter()
    findings: list[Finding] = []

    # (section, extracted, extracted-with-the-manifest-applied), per block.
    rebuilt = apply_manifest(pre, corrections, form_key) if pre is not None else []

    def explains_loss(text: str) -> bool:
        """The manifest turned a block holding this printed line into shipped text."""
        needle = squash(text)
        return any(needle and needle in before and before != after
                   and shipped.find(after) is not None
                   for _section, before, after in rebuilt)

    def explains_gain(text: str) -> bool:
        """The manifest introduced this shipped line; the extractor did not."""
        needle = squash(text)
        return any(needle and needle in after and needle not in before
                   for _section, before, after in rebuilt)

    # ── PAGE → DATA ───────────────────────────────────────────────────────────
    for line in source:
        text = line.text
        if not squash(text):
            continue

        fixed = _fix_whitespace(text)
        if shipped.has(text):
            page_counts["verbatim"] += 1
        elif shipped.find(text):
            page_counts["reflowed"] += 1
        elif shipped.has(fixed) or shipped.find(fixed):
            page_counts["whitespace"] += 1
        elif line.consumed_as == "heading":
            page_counts["heading"] += 1
        elif _BARE_SEPARATOR.match(squash(text)):
            page_counts["separator"] += 1
        elif squash(_alt_label(text)) in shipped.labels:
            page_counts["label"] += 1
        elif line.section in LECTIONARY_SECTIONS and line.consumed_as not in ("label", "rubric"):
            page_counts["lectionary"] += 1
        elif explains_loss(text):
            page_counts["corrected"] += 1
        else:
            page_counts["UNACCOUNTED"] += 1
            findings.append(Finding(form_key, line.section, line.consumed_as or line.type,
                                    text, "page"))

    # ── DATA → PAGE ───────────────────────────────────────────────────────────
    # The page as flowing text: consecutive lines joined by a single space, in
    # the order they are printed. A shipped line that reflow joined out of two
    # printed lines appears here and nowhere else, so this is the only form of
    # the page that can account for one.
    printed = {squash(line.text) for line in source}
    page_stream = " ".join(squash(line.text) for line in source)
    fixed_stream = squash(_fix_whitespace(page_stream))
    labels_from_page = {squash(_alt_label(line.text)) for line in source}

    for key in sorted(shipped.lines):
        section, seg_type = shipped.origin[key]
        if key in printed:
            data_counts["printed"] += 1
        elif key in page_stream:
            data_counts["printed-joined"] += 1
        elif key in fixed_stream:
            data_counts["whitespace"] += 1
        elif seg_type == "label" and key in labels_from_page:
            data_counts["label"] += 1
        elif seg_type == "label" and _ROMAN_LABEL.match(key):
            data_counts["structural"] += 1
        elif explains_gain(key):
            # New text, and applying the manifest to the extracted block is what
            # produced it. Requiring the line to be absent *before* the manifest
            # ran is what keeps this from excusing invention: a line the
            # extractor made up is already in that artifact, so no correction
            # can be credited with introducing it.
            data_counts["corrected"] += 1
        else:
            data_counts["UNACCOUNTED"] += 1
            findings.append(Finding(form_key, section, seg_type, key, "data"))

    return page_counts, data_counts, findings


# ── The Penitential Office walk (#165) ────────────────────────────────────────
# The Penitential Office is not a form, so it cannot reuse the form walk. The
# extractor reads its pages span-by-span (_pen_span_lines) rather than through
# extract_office_typed_lines — the sentence citations are red on the same line
# as the black text, and the absolution's "Amen." is bold on the leader line, so
# a line's dominant type would swallow both. This walk mirrors that reading.
# Source units are per span, the most naive split available: a span boundary is
# PyMuPDF's own segmentation, not a parse decision, so a wrong split in the
# extractor's sentence/confession grouping cannot be replicated here (the
# fats-chain lesson, #113).

# The ordinary printing's absolution A reads "from our sins," where the
# seasonal printing — and the shipped block — reads "from your/our sins,". The
# book disagrees with itself; a named rule vouches for the exact line rather
# than licensing the whole section.
_PEN_VARIANT = "from our sins,"


def pen_manifest(pre_pen: dict | None, corrections: list[dict]) -> list[tuple[str, str, str]]:
    """The pre-correction `_penitential` segments with its manifest applied.

    Returns (field, before, after) per text segment — the units the shipped
    walk below accounts — so the `corrected` rule fires only when rewriting
    what was extracted with the manifest's `_penitential` entries actually
    produces what ships (ADR 0005, 0022), not merely when an entry sits on the
    field. The replay uses corrections_lib's own walk and replacer, the same
    ones the validator and applier call; a reconstruction that disagreed with
    application would license a divergence nobody applied. Only substring
    `office_text` entries naming office "_penitential" apply: the "*" wildcard
    never resolves here (corrections_lib skips `_`-prefixed keys) and the
    whole-field shape cannot be replayed at segment granularity.
    """
    if pre_pen is None:
        return []
    relevant = [c for c in corrections
                if c.get("office") == "_penitential" and isinstance(c.get("old"), str)]
    if not relevant:
        return []
    out: list[tuple[str, str, str]] = []
    # Walk only the fields an entry names; the walker yields in the same
    # order for the original and the copy, so the segments pair by index.
    for field in sorted({c["field"] for c in relevant}):
        raw = pre_pen.get(field)
        if raw is None:
            continue
        rebuilt = copy.deepcopy(raw)
        for c in relevant:
            if c["field"] == field:
                replace_occurrences(rebuilt, c["old"], c["new"])
        for before, after in zip((s["text"] for s in iter_text_segments(raw)),
                                 (s["text"] for s in iter_text_segments(rebuilt))):
            sb, sa = squash(before), squash(after)
            if sb != sa:
                out.append((field, sb, sa))
    return out


def check_penitential(doc, pen: dict, pre_pen: dict | None,
                      corrections: list[dict]) -> tuple[Counter, Counter, list[Finding]]:
    page_counts: Counter = Counter()
    data_counts: Counter = Counter()
    findings: list[Finding] = []

    # ── shipped side: every text-bearing string in _penitential ─────────────
    shipped_lines: set[str] = set()
    shipped_blocks: list[str] = []

    def add(text) -> None:
        if not isinstance(text, str):
            return
        for ln in text.split("\n"):
            key = squash(ln)
            if key:
                shipped_lines.add(key)
                shipped_blocks.append(key)

    add(pen.get("title"))
    add(pen.get("opening_rubric"))
    for group in pen.get("sentences", {}).get("seasonal", {}).values():
        for items in group.values():
            for item in items:
                add(item.get("text"))
                add(item.get("citation"))
    for items in pen.get("sentences", {}).get("ordinary", {}).values():
        for item in items:
            add(item.get("text"))
            add(item.get("citation"))
    for block in (pen.get("confession"), pen.get("absolution")):
        if not isinstance(block, dict):
            continue
        add(block.get("invitation"))
        add(block.get("call"))
        add(block.get("silence"))
        for alt in block.get("alternatives", []):
            for seg in alt:
                add(seg.get("text"))
    add(pen.get("deacon_rubric"))
    add(pen.get("transition_rubric"))

    def has(text: str) -> bool:
        return squash(text) in shipped_lines

    def find(text: str) -> bool:
        needle = squash(text)
        return bool(needle and any(needle in b for b in shipped_blocks))

    # The manifest's `_penitential` entries replayed over the pre-correction
    # artifact — (field, before, after) per segment, the same units the
    # shipped walk accounts. A printed line that no longer ships, or a shipped
    # line the page never printed, is `corrected` only when the replay
    # reproduces what ships; the source side itself is unchanged (ADR 0022).
    rebuilt = pen_manifest(pre_pen, corrections)

    def explains_loss(text: str) -> bool:
        needle = squash(text)
        return any(needle in before and before != after
                   and after in shipped_lines
                   for _field, before, after in rebuilt)

    def explains_gain(key: str) -> bool:
        return any(key in after and key not in before
                   for _field, before, after in rebuilt)

    # ── source side: per-span units, tagged with section and rule ───────────
    source: list[SourceLine] = []
    phase = "opening"  # title → opening → sentences → confession → absolution → rubrics → transition
    for key, start, end in PENITENTIAL_BOUNDS:
        for page_lines in _pen_span_lines(doc, start, end):
            for entries in page_lines:
                for typ, raw in entries:
                    text = _CONTROL_CHARS.sub("", raw).strip()
                    if not text:
                        continue
                    line = SourceLine(typ, text)
                    sq = squash(text)
                    low = sq.lower()
                    if typ == "heading":
                        line.section, line.consumed_as = "title", "header"
                        phase = "opening"
                    elif phase == "opening":
                        if _PEN_SUBHEAD_RE.match(sq):
                            line.section, line.consumed_as = "sentences", "structure"
                            phase = "sentences"
                        else:
                            line.section = "opening_rubric"
                    elif phase == "sentences":
                        line.section = "sentences"
                        if typ == "rubric" and _PEN_SUBHEAD_RE.match(sq):
                            line.consumed_as = "structure"
                        elif sq == "\u2022":
                            line.consumed_as = "structure"
                        elif low == "the presider then says,":
                            line.section, line.consumed_as = "confession", "rubric"
                            phase = "confession"
                    elif phase == "confession":
                        line.section = "confession"
                        if low in ("or", "or."):
                            line.consumed_as = "separator"
                        elif low == "the presider says,":
                            line.section, line.consumed_as = "absolution", "rubric"
                            phase = "absolution"
                    elif phase == "absolution":
                        line.section = "absolution"
                        if low in ("or", "or."):
                            line.consumed_as = "separator"
                        elif low.startswith("a deacon or lay person"):
                            line.section, line.consumed_as = "deacon_rubric", "rubric"
                            phase = "rubrics"
                        elif sq == _PEN_VARIANT:
                            line.consumed_as = "variant"
                    elif phase == "rubrics":
                        if low.startswith("when this penitential office"):
                            line.section, line.consumed_as = "transition_rubric", "rubric"
                            phase = "transition"
                        else:
                            line.section, line.consumed_as = "deacon_rubric", "rubric"
                    else:  # transition — everything after the hand-off is its rubric
                        line.section, line.consumed_as = "transition_rubric", "rubric"
                    source.append(line)

    # ── PAGE → DATA ─────────────────────────────────────────────────────────
    # Structure/separator/variant first: the ordinary printing's subheads
    # "Morning"/"Evening" are substrings of shipped sentence text, so the text
    # rules would misread a consumed line as shipped content.
    for line in source:
        text = line.text
        if not squash(text):
            continue
        if line.consumed_as == "structure":
            page_counts["structure"] += 1
        elif line.consumed_as == "variant":
            page_counts["variant"] += 1
        elif line.consumed_as == "separator" or _BARE_SEPARATOR.match(squash(text)):
            page_counts["separator"] += 1
        elif has(text):
            page_counts["verbatim"] += 1
        elif find(text):
            page_counts["reflowed"] += 1
        elif has(_pen_clean(text)) or find(_pen_clean(text)):
            page_counts["whitespace"] += 1
        elif explains_loss(text):
            page_counts["corrected"] += 1
        else:
            page_counts["UNACCOUNTED"] += 1
            findings.append(Finding("penitential", line.section,
                                    line.consumed_as or line.type, text, "page"))

    # ── DATA → PAGE ─────────────────────────────────────────────────────────
    # The whitespace rule uses the extractor's own _pen_clean (which folds a
    # span-separated " ." and NBSP), not _fix_whitespace, which mirrors only
    # _normalize_whitespace for the form texts.
    printed = {squash(line.text) for line in source}
    page_stream = " ".join(squash(line.text) for line in source)
    fixed_stream = squash(_pen_clean(page_stream))
    for key in sorted(shipped_lines):
        if key in printed:
            data_counts["printed"] += 1
        elif key in page_stream:
            data_counts["printed-joined"] += 1
        elif key in fixed_stream:
            data_counts["whitespace"] += 1
        elif explains_gain(key):
            data_counts["corrected"] += 1
        else:
            data_counts["UNACCOUNTED"] += 1
            findings.append(Finding("penitential", "—", "text", key, "data"))

    return page_counts, data_counts, findings


def load_baseline() -> list[dict]:
    if not BASELINE.exists():
        return []
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("known", [])


def reconcile(findings: list[Finding], baseline: list[dict],
              by_count: bool = True, chain: str = "offices") -> tuple[list[dict], list[str]]:
    """Match findings against the baseline. Returns (known, errors).

    With `by_count`, counts are compared exactly in both directions: a defect
    that grew is a regression and a defect that shrank is a fix that did not
    finish tidying up after itself, so both fail and the entry gets looked at. A
    baseline that could absorb either would stop being evidence of anything.

    Without it — a single-form run, where a corpus-wide count means nothing —
    matching is by membership only: an entry that does not fire is not stale, it
    just belongs to another form.

    The baseline is shared across chains, so only entries for the active chain
    are considered (`chain` defaults to "offices", which is what an entry
    without the field is).
    """
    actual: Counter = Counter()
    for f in findings:
        actual[(f.direction, f.section, line_id(f.text))] += 1

    known, errors = [], []
    for entry in baseline:
        if entry.get("chain", "offices") != chain:
            continue
        key = (entry["direction"], entry["section"], entry["id"])
        found = actual.pop(key, 0)
        expected = entry["lines"]
        if found and not by_count:
            known.append({**entry, "found": found})
        elif not by_count:
            continue
        elif found == expected:
            known.append({**entry, "found": found})
        elif found == 0:
            errors.append(
                f"baseline entry {entry['id']} (#{entry['issue']}) no longer fires — "
                f"if it is fixed, delete the entry in the same commit")
        else:
            errors.append(
                f"baseline entry {entry['id']} (#{entry['issue']}) expects "
                f"{expected} line(s), found {found}")

    for (direction, section, ident), n in sorted(actual.items()):
        errors.append(f"unaccounted: {direction} {section} {ident} × {n} — "
                      f"no rule accounts for it and no baseline entry claims it")
    return known, errors


def report(direction: str, rules: list[tuple[str, str]], counts: Counter,
           per_form: dict[str, Counter], claimed: int, issues: list[int]) -> None:
    total = sum(counts.values())
    print(f"\n{direction}  ({total:,} lines)")
    width = max(len(name) for name, _ in rules)
    for name, why in rules:
        n = counts.get(name, 0)
        if n:
            print(f"    {name:<{width}}  {n:>6,}   {why}")
    bad = counts.get("UNACCOUNTED", 0)
    if not bad:
        note = "✓"
    elif bad == claimed:
        seen = ", ".join(f"#{i}" for i in sorted(set(issues)))
        note = f"all claimed by {BASELINE.name} ({seen})"
    else:
        note = f"✗ {bad - claimed} not claimed by any baseline entry"
    print(f"    {'UNACCOUNTED':<{width}}  {bad:>6,}   {note}")
    if bad > claimed:
        forms = sorted((c["UNACCOUNTED"], f) for f, c in per_form.items()
                       if c.get("UNACCOUNTED"))
        worst = ", ".join(f"{f} ({n})" for n, f in reversed(forms[-5:]))
        print(f"    {'':<{width}}           worst: {worst}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show-text", action="store_true",
                    help="print unaccounted lines in full (local diagnosis only)")
    ap.add_argument("--form", help="restrict to one office form (or psalm number "
                                   "for --chain psalter, saint name for "
                                   "--chain fats)")
    ap.add_argument("--chain", choices=("offices", "psalter", "fats", "midday"),
                    default="offices",
                    help="which extraction chain to check against its page source")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    if args.chain == "psalter":
        return run_psalter(args)
    if args.chain == "fats":
        return run_fats(args)
    if args.chain == "midday":
        return run_midday(args)
    return run_offices(args)


def run_offices(args) -> int:
    # PRE_CORRECTION is as required as the other two. Falling back to `pre=None`
    # silently disables both `corrected` rules, which turns every authorised
    # divergence into an unaccounted line: ~237 failures with nothing saying
    # why. `.build/` is gitignored, so a fresh clone that runs `make test`
    # without `make extract` first hits exactly that.
    for path, remedy in ((PDF, "make fetch-sources"),
                         (SHIPPED, "make extract"),
                         (PRE_CORRECTION, "make extract")):
        if not path.exists():
            print(f"ERROR: {path} not found\nRun: {remedy}", file=sys.stderr)
            return 1

    data = json.loads(SHIPPED.read_text(encoding="utf-8"))
    shared = data.get("_shared", {})
    pre_data = json.loads(PRE_CORRECTION.read_text(encoding="utf-8"))
    pre_shared = pre_data.get("_shared", {})
    corrections = load_corrections()

    if args.form == "penitential":
        offices: list[tuple[str, int, int]] = []
    else:
        offices = [(k, s, e) for k, s, e in OFFICES if not args.form or k == args.form]
        if not offices:
            print(f"ERROR: unknown form {args.form!r}", file=sys.stderr)
            return 1

    doc = fitz.open(PDF)
    metrics = document_metrics(doc, sorted({p for _, s, e in OFFICES
                                            for p in range(s - 1, e)}))

    page_total: Counter = Counter()
    data_total: Counter = Counter()
    page_by_form: dict[str, Counter] = {}
    data_by_form: dict[str, Counter] = {}
    findings: list[Finding] = []
    sections_seen: dict[str, Counter] = defaultdict(Counter)

    for key, start, end in offices:
        form = data.get(key)
        if form is None:
            print(f"ERROR: {key} missing from {SHIPPED}", file=sys.stderr)
            return 1
        typed = extract_office_typed_lines(doc, key, start, end, metrics=metrics)
        source = read_source_lines(key, typed)
        shipped = ShippedForm(form, shared)
        pre = ShippedForm(pre_data[key], pre_shared) if key in pre_data else None

        page, dat, found = check_form(key, source, shipped, pre, corrections)
        page_total.update(page)
        data_total.update(dat)
        page_by_form[key] = page
        data_by_form[key] = dat
        findings.extend(found)
        for f in found:
            sections_seen[f.direction][f.section] += 1

    # The Penitential Office is not a form: its own walk accounts the two
    # printings' pages against the shipped `_penitential` block (#165).
    if args.form in (None, "penitential"):
        pen = data.get("_penitential")
        if pen is None:
            print(f"ERROR: _penitential missing from {SHIPPED}", file=sys.stderr)
            return 1
        page, dat, found = check_penitential(doc, pen, pre_data.get("_penitential"),
                                              corrections)
        page_total.update(page)
        data_total.update(dat)
        page_by_form["penitential"] = page
        data_by_form["penitential"] = dat
        findings.extend(found)
        for f in found:
            sections_seen[f.direction][f.section] += 1

    doc.close()

    # A baseline entry counts lines across the whole corpus, so a single-form
    # run cannot be reconciled against those counts: every entry would read as
    # stale and every finding as new. It can still be reconciled by membership,
    # which is what makes --form usable — it reports the form's share of a known
    # divergence as known, and still fails on anything the baseline never
    # claimed.
    known, errors = reconcile(findings, load_baseline(), by_count=not args.form)

    # The Penitential Office is one more unit of the offices chain when it ran.
    n_units = len(offices) + (1 if args.form in (None, "penitential") else 0)

    if args.json:
        print(json.dumps({
            "forms": n_units,
            "page_to_data": dict(page_total),
            "data_to_page": dict(data_total),
            "known": [{"id": k["id"], "issue": k["issue"], "lines": k["found"]}
                      for k in known],
            "errors": errors,
            "unaccounted": [
                {"form": f.form, "section": f.section, "type": f.type,
                 "direction": f.direction, "id": line_id(f.text)}
                for f in findings
            ],
        }, indent=2))
        return 1 if errors else 0

    if args.form == "penitential":
        pop_desc = "the Penitential Office"
    else:
        pop_desc = f"{len(offices)} forms" + ("" if args.form else " + the Penitential Office")
    print(f"Conservation check — {PDF.name} ↔ {SHIPPED.relative_to(ROOT)}")
    print(f"Population: {sum(page_total.values()):,} typed source lines across "
          f"{pop_desc}, after the noise filter.")

    for want, heading, rules, totals, by_form in (
        ("page", "PAGE → DATA   is anything printed missing?",
         PAGE_RULES, page_total, page_by_form),
        ("data", "DATA → PAGE   is anything shipped that was never printed?",
         DATA_RULES, data_total, data_by_form),
    ):
        side = [k for k in known if k["direction"] == want]
        report(heading, rules, totals, by_form,
               sum(k["found"] for k in side), [k["issue"] for k in side])

    if known:
        print(f"\nKnown divergences ({sum(k['found'] for k in known)} lines, "
              f"{len(known)} entries in {BASELINE.name})")
        for k in sorted(known, key=lambda e: (e["issue"], e["id"])):
            print(f"    #{k['issue']:<4} {k['direction']:<5} {k['section']:<18} "
                  f"{k['id']}  × {k['found']:<3} {k['why']}")

    if findings and (args.form or errors):
        for direction, heading in (("page", "printed but not shipped"),
                                   ("data", "shipped but never printed")):
            rows = [f for f in findings if f.direction == direction]
            if not rows:
                continue
            print(f"\n  Unaccounted — {heading} ({len(rows)}):")
            print("    by section: " + ", ".join(
                f"{s} ({n})" for s, n in sections_seen[direction].most_common()))
            for f in rows:
                print(f.render(args.show_text))
        if not args.show_text:
            print("\n  Re-run with --show-text to read the lines themselves.")

    if errors:
        print(f"\nFAIL ({len(errors)}):")
        for err in errors:
            print(f"    {err}")
        return 1

    if args.form:
        print(f"\n{args.form}: every printed line is accounted for or claimed by "
              f"a baseline entry. (Entry counts are corpus-wide and are not "
              f"checked here — run without --form for that.)")
        return 0

    print("\nEvery printed line is accounted for or claimed by a baseline entry, "
          "and nothing ships unprinted.")
    return 0


# ── Psalter chain (#102) ──────────────────────────────────────────────────────
#
# The office walk above is shaped to field segments; the psalter is a different
# shape (a dict of psalm → verse text), so it gets its own source reader, its
# own shipped reader and its own `corrected` rule — but the same two-direction
# conservation argument, the same named-rule ledger, the same baseline and the
# same exit code. Without it, a line silently dropped or invented in the
# psalter is invisible to `make qa` — the argument #94 makes for the offices,
# and the psalter is the other half of the same PDF (#102).

PSALTER_PAGE_RULES: list[tuple[str, str]] = [
    ("verbatim",  "ships exactly as printed"),
    ("heading",   "a psalm head: the Latin incipit ships as the title; the number is the key"),
    ("corrected", "extracted intact, then changed by an audited data/corrections.json "
                  "'psalter' entry"),
]

PSALTER_DATA_RULES: list[tuple[str, str]] = [
    ("printed",        "appears on the page as printed"),
    ("printed-joined", "printed across a column wrap; ships as the joined line"),
    ("corrected",      "introduced by an audited data/corrections.json 'psalter' entry"),
]


class PsalterSourceLine:
    """A line extraction sees in the psalter section, tagged with its role."""
    __slots__ = ("type", "text", "psalm", "title")

    def __init__(self, typ: str, text: str, psalm: str | None, title: str = ""):
        self.type = typ
        # A control character is an unmapped glyph, not content; the extractor
        # itself strips none here (it only normalises quotes and rstrips).
        self.text = _CONTROL_CHARS.sub("", text).strip()
        self.psalm = psalm
        self.title = title


def read_psalter_source(lines: list[tuple[float, str]]) -> list[PsalterSourceLine]:
    """Slice `pdf_lines_with_x0` output to the psalter section and tag each line.

    Repeats `extract_psalms`' walk (find the BooK marker, stop at
    Acknowledgements, classify each line with the extractor's own regexes) so
    the two cannot disagree about what a line *is*. What is restated is only the
    psalm a line belongs to, which the extractor has no reason to record.
    """
    start = None
    for i, (_x0, line) in enumerate(lines):
        cleaned = strip_page_header(line)
        if cleaned is not None and RE_BOOK.match(cleaned.strip()):
            start = i
            break
    if start is None:
        raise ValueError("could not locate the Psalter section")

    out: list[PsalterSourceLine] = []
    current: str | None = None
    for _x0, raw in lines[start:]:
        if "Acknowledgements" in raw:
            break
        line = strip_page_header(raw)
        if line is None:
            continue
        line = normalise_quotes(line).rstrip()
        stripped = line.strip()
        if not stripped or RE_BOOK.match(stripped):
            continue
        m = RE_PSALM_HEAD.match(stripped)
        if m:
            current = m.group(1)
            out.append(PsalterSourceLine("head", stripped, current, m.group(2).strip()))
        elif RE_SECTION.match(stripped) or RE_VERSE.match(stripped):
            # A section heading ("Part I", "Aleph") and a verse start are both
            # flush content lines; conservation treats them alike.
            out.append(PsalterSourceLine("verse", stripped, current))
        else:
            out.append(PsalterSourceLine("cont", stripped, current))
    return out


class PsalterShipped:
    """The psalter as shipped, indexed for both directions of the check.

    `data/psalter.json` is {num: {number, book, title, text}}; `text` is the
    psalm body (verse / continuation / section lines joined by newline). The
    `corrected` rule reconstructs each psalm from the pre-correction artifact
    plus the "psalter" corrections — exactly as apply_corrections.py does — and
    a divergence is only accounted as corrected when that reconstruction
    actually reproduces the shipped text (ADR 0005's claim, chain-ported).
    """

    def __init__(self, data: dict, pre: dict, corrections: list[dict]):
        self.data = data
        self.lines: dict[str, set[str]] = {}
        self.titles: dict[str, str] = {}
        self.pre_lines: dict[str, set[str]] = {}
        self.corr_lines: dict[str, set[str]] = {}
        self.valid: dict[str, bool] = {}
        for num, psalm in data.items():
            self.lines[num] = {squash(ln) for ln in psalm["text"].split("\n")
                               if squash(ln)}
            self.titles[num] = squash(psalm.get("title", ""))
        for num, psalm in pre.items():
            text = psalm["text"]
            self.pre_lines[num] = {squash(ln) for ln in text.split("\n") if squash(ln)}
            corrected = text
            for c in corrections:
                if str(c.get("psalm")) == num and isinstance(c.get("old"), str):
                    corrected = corrected.replace(c["old"], c["new"])
            self.corr_lines[num] = {squash(ln) for ln in corrected.split("\n")
                                    if squash(ln)}
            self.valid[num] = (squash(corrected) ==
                               squash(self.data.get(num, {}).get("text", "")))

    def has(self, num: str, text: str) -> bool:
        return squash(text) in self.lines.get(num, set())

    def lost_by_manifest(self, num: str, text: str) -> bool:
        """A printed line the manifest removed: in the pre-correction psalm but
        not shipped, and the reconstruction (pre + corrections = shipped) holds."""
        needle = squash(text)
        return (needle in self.pre_lines.get(num, set())
                and needle not in self.lines.get(num, set())
                and self.valid.get(num, False))

    def gained_by_manifest(self, num: str, key: str) -> bool:
        """A shipped line the manifest introduced: not extracted, but produced by
        a correction, and the reconstruction holds."""
        return (key in self.corr_lines.get(num, set())
                and key not in self.pre_lines.get(num, set())
                and self.valid.get(num, False))


def check_psalter(source: list[PsalterSourceLine], shipped: PsalterShipped,
                  ) -> tuple[Counter, Counter, dict[str, Counter],
                             dict[str, Counter], list[Finding]]:
    page_total: Counter = Counter()
    data_total: Counter = Counter()
    page_by_form: dict[str, Counter] = defaultdict(Counter)
    data_by_form: dict[str, Counter] = defaultdict(Counter)
    findings: list[Finding] = []

    # ── PAGE → DATA ───────────────────────────────────────────────────────────
    for line in source:
        text = line.text
        if not squash(text):
            continue
        num = line.psalm or "?"
        if num not in shipped.data:
            page_total["UNACCOUNTED"] += 1
            page_by_form[num]["UNACCOUNTED"] += 1
            findings.append(Finding("psalter", num, line.type, text, "page"))
            continue
        if line.type == "head":
            # A psalm head is structural except its Latin incipit, which must
            # ship as the psalm's `title` field. Eight psalms (18, 37, 78, 89,
            # 105–107, 119) print no incipit — the head is just "Psalm N" and
            # the shipped title is empty — so an absent title is the correct
            # shipped state, not a dropped line.
            incipit = squash(line.title)
            if (incipit and incipit == shipped.titles[num]) \
                    or (not incipit and not shipped.titles[num]):
                page_total["heading"] += 1
                page_by_form[num]["heading"] += 1
            else:
                page_total["UNACCOUNTED"] += 1
                page_by_form[num]["UNACCOUNTED"] += 1
                findings.append(Finding("psalter", num, "title",
                                        line.title or text, "page"))
            continue
        if shipped.has(num, text):
            page_total["verbatim"] += 1
            page_by_form[num]["verbatim"] += 1
        elif shipped.lost_by_manifest(num, text):
            page_total["corrected"] += 1
            page_by_form[num]["corrected"] += 1
        else:
            page_total["UNACCOUNTED"] += 1
            page_by_form[num]["UNACCOUNTED"] += 1
            findings.append(Finding("psalter", num, line.type, text, "page"))

    # ── DATA → PAGE ───────────────────────────────────────────────────────────
    page_set = {squash(line.text) for line in source if line.type != "head"}
    page_stream = " ".join(squash(line.text) for line in source)

    for num in sorted(shipped.data):
        title = shipped.titles[num]
        if title:
            if title in page_set:
                data_total["printed"] += 1
                data_by_form[num]["printed"] += 1
            elif title in page_stream:
                data_total["printed-joined"] += 1
                data_by_form[num]["printed-joined"] += 1
            else:
                data_total["UNACCOUNTED"] += 1
                data_by_form[num]["UNACCOUNTED"] += 1
                findings.append(Finding("psalter", num, "title", title, "data"))
        for key in sorted(shipped.lines[num]):
            if key in page_set:
                data_total["printed"] += 1
                data_by_form[num]["printed"] += 1
            elif key in page_stream:
                data_total["printed-joined"] += 1
                data_by_form[num]["printed-joined"] += 1
            elif shipped.gained_by_manifest(num, key):
                data_total["corrected"] += 1
                data_by_form[num]["corrected"] += 1
            else:
                data_total["UNACCOUNTED"] += 1
                data_by_form[num]["UNACCOUNTED"] += 1
                findings.append(Finding("psalter", num, "verse", key, "data"))

    return page_total, data_total, page_by_form, data_by_form, findings


def run_psalter(args) -> int:
    psalter_pdf = ROOT / "sources" / "pray-without-ceasing.pdf"
    shipped_path = ROOT / "data" / "psalter.json"
    pre_path = ROOT / ".build" / "psalter.1-extract.json"
    for path, remedy in ((psalter_pdf, "make fetch-sources"),
                         (shipped_path, "make extract"),
                         (pre_path, "make extract")):
        if not path.exists():
            print(f"ERROR: {path} not found\nRun: {remedy}", file=sys.stderr)
            return 1

    data = json.loads(shipped_path.read_text(encoding="utf-8"))
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    corrections = load_corrections("psalter")

    if args.form:
        if args.form not in data:
            print(f"ERROR: unknown psalm {args.form!r}", file=sys.stderr)
            return 1
        data = {args.form: data[args.form]}
        pre = {args.form: pre[args.form]}

    source = read_psalter_source(pdf_lines_with_x0(psalter_pdf))
    if args.form:
        source = [line for line in source if line.psalm == args.form]

    shipped = PsalterShipped(data, pre, corrections)
    page_total, data_total, page_by_form, data_by_form, findings = \
        check_psalter(source, shipped)

    known, errors = reconcile(findings, load_baseline(),
                              by_count=not args.form, chain="psalter")

    if args.json:
        print(json.dumps({
            "chain": "psalter",
            "psalms": len(data),
            "page_to_data": dict(page_total),
            "data_to_page": dict(data_total),
            "known": [{"id": k["id"], "issue": k["issue"], "lines": k["found"]}
                      for k in known],
            "errors": errors,
            "unaccounted": [
                {"psalm": f.section, "type": f.type, "direction": f.direction,
                 "id": line_id(f.text)}
                for f in findings
            ],
        }, indent=2))
        return 1 if errors else 0

    print(f"Conservation check — {psalter_pdf.name} ↔ {shipped_path.relative_to(ROOT)}")
    print(f"Population: {sum(page_total.values()):,} typed source lines across "
          f"{len(data)} psalms, after the header/quote filter.")

    for want, heading, rules, totals, by_form in (
        ("page", "PAGE → DATA   is anything printed missing?",
         PSALTER_PAGE_RULES, page_total, page_by_form),
        ("data", "DATA → PAGE   is anything shipped that was never printed?",
         PSALTER_DATA_RULES, data_total, data_by_form),
    ):
        side = [k for k in known if k["direction"] == want]
        report(heading, rules, totals, by_form,
               sum(k["found"] for k in side), [k["issue"] for k in side])

    if known:
        print(f"\nKnown divergences ({sum(k['found'] for k in known)} lines, "
              f"{len(known)} entries in {BASELINE.name})")
        for k in sorted(known, key=lambda e: (e["issue"], e["id"])):
            print(f"    #{k['issue']:<4} {k['direction']:<5} {k['section']:<18} "
                  f"{k['id']}  × {k['found']:<3} {k['why']}")

    if findings and (args.form or errors):
        for direction, heading in (("page", "printed but not shipped"),
                                   ("data", "shipped but never printed")):
            rows = [f for f in findings if f.direction == direction]
            if not rows:
                continue
            print(f"\n  Unaccounted — {heading} ({len(rows)}):")
            print("    by psalm: " + ", ".join(
                f"{s} ({n})" for s, n in sorted(by_form.items())
                if by_form[s].get("UNACCOUNTED", 0)))
            for f in rows:
                print(f.render(args.show_text))
        if not args.show_text:
            print("\n  Re-run with --show-text to read the lines themselves.")

    if errors:
        print(f"\nFAIL ({len(errors)}):")
        for err in errors:
            print(f"    {err}")
        return 1

    if args.form:
        print(f"\nPsalm {args.form}: every printed line is accounted for or claimed "
              f"by a baseline entry.")
        return 0

    print("\nEvery printed line is accounted for or claimed by a baseline entry, "
          "and nothing ships unprinted.")
    return 0


# ── Fats chain (#102) ─────────────────────────────────────────────────────────
#
# For All The Saints (FATS) is the third published chain with a page source and
# its own correction category. Its shape differs from both offices (field
# segments) and the psalter (psalm → verse text): it is a dict of saint name →
# {date, rank, bio, sentence, sentence_ref, collect, psalm, refrain, readings}.
# The prose the reader is shown is `bio` (multi-line biography), `collect`
# (verse-set prayer), `sentence` and `refrain` (single-line propers); `psalm`,
# `readings` and `sentence_ref` are references, not prose, so this chain scopes
# to the prose fields. What that buys is bounded, and the bound is worth
# stating: both sides of the comparison come from the extractor's own parsers,
# so what the parser cannot see the check cannot see either. A field the parser
# leaves empty balances at zero on both sides and passes (#113).
#
# The source is a third PDF (For-All-The-Saints.pdf), and the extractor walks
# it page-wise — bio page → continuation pages → propers page — rather than
# line-wise. `read_fats_source` repeats that walk with the extractor's own page
# predicates and body parsers (`is_bio_page`, `parse_bio`, `_extract_bio_body`,
# `parse_propers`), restating only the bookkeeping: which saint and which prose
# field each produced line belongs to. A saint's `name`/`date`/`rank` are
# structure (the key and its metadata), not prose, so they are not walked.
#
# The `corrected` rule reconstructs each prose field from the pre-correction
# artifact plus the "fats" corrections (keyed by {saint, field}, substring
# `old`) and excuses a divergence only when the reconstruction reproduces what
# ships — the ADR 0005 claim, chain-ported, exactly as the psalter's.

FATS_PROSE_FIELDS = ("bio", "sentence", "collect", "refrain")

FATS_PAGE_RULES: list[tuple[str, str]] = [
    ("verbatim",  "ships exactly as printed"),
    ("corrected", "extracted intact, then changed by an audited data/corrections.json "
                  "'fats' entry"),
]

FATS_DATA_RULES: list[tuple[str, str]] = [
    ("printed",        "appears on the page as printed"),
    ("printed-joined", "printed across a line break; ships as the joined line"),
    ("corrected",      "introduced by an audited data/corrections.json 'fats' entry"),
]


def _field_lines(text: str) -> set[str]:
    """The squashed lines a prose field contributes, empty ones dropped."""
    return {squash(ln) for ln in text.split("\n") if squash(ln)}


class FatsSourceLine:
    """A prose line the fats extractor reads, tagged with its saint and field."""
    __slots__ = ("type", "text", "saint", "field")

    def __init__(self, text: str, saint: str, field: str):
        self.type = "prose"
        self.text = text.strip()
        self.saint = saint
        self.field = field


def read_fats_source(pdf_path: Path) -> list[FatsSourceLine]:
    """Walk For-All-The-Saints.pdf the way `extract_fats` does, tagging prose.

    Repeats `extract_fats`' page walk (bio page → continuation pages → propers
    page → skip variant propers) using the extractor's own predicates and body
    parsers, so the two cannot disagree about what a line *is*. What is
    restated is only the bookkeeping — which saint and which prose field each
    produced line belongs to — which the extractor has no reason to record and
    this check cannot work without. Key attribution runs through the
    extractor's own `_fats_keys`, so a name collision (the two Augustines)
    lands every line on the same disambiguated key the shipped data uses.
    """
    with fitz.open(pdf_path) as pdf:
        raw_pages = [_page_text_without_margin_artifacts(page) for page in pdf]
    pages = [strip_garbage_header(p) for p in raw_pages]
    page_indices = list(range(36, 385)) + list(range(387, 392))

    entries: list[dict] = []
    i = 0
    while i < len(page_indices):
        pi = page_indices[i]
        page = pages[pi]
        if not is_bio_page(page):
            i += 1
            continue
        bio_info = parse_bio(page)
        if not bio_info:
            i += 1
            continue
        i += 1

        continuation: list[str] = []
        while i < len(page_indices):
            npi = page_indices[i]
            np_ = pages[npi]
            if is_propers_page(np_) or is_bio_page(np_) or not np_:
                break
            extra = _extract_bio_body(np_.split("\n"))
            if extra:
                continuation.append(extra)
            i += 1

        if i >= len(page_indices) or not is_propers_page(pages[page_indices[i]]):
            continue
        propers_info = parse_propers(pages[page_indices[i]])
        i += 1
        while (i < len(page_indices)
               and is_propers_page(pages[page_indices[i]])
               and not is_bio_page(pages[page_indices[i]])):
            i += 1

        entries.append({
            "name": bio_info["name"],
            "description": bio_info.get("description", ""),
            "date": bio_info["date"],
            "bio_lines": [ln for text in [bio_info["bio"], *continuation]
                          for ln in text.split("\n") if ln.strip()],
            "sentence": propers_info.get("sentence") or "",
            "collect_lines": [ln for ln in (propers_info.get("collect") or "").split("\n")
                              if ln.strip()],
            "refrain": propers_info.get("refrain") or "",
        })

    keys = _fats_keys([(e["name"], e["description"], e["date"]) for e in entries])
    out: list[FatsSourceLine] = []
    for key, e in zip(keys, entries):
        for ln in e["bio_lines"]:
            out.append(FatsSourceLine(ln, key, "bio"))
        if e["sentence"]:
            out.append(FatsSourceLine(e["sentence"], key, "sentence"))
        for ln in e["collect_lines"]:
            out.append(FatsSourceLine(ln, key, "collect"))
        if e["refrain"]:
            out.append(FatsSourceLine(e["refrain"], key, "refrain"))
    return out


class FatsShipped:
    """The fats prose as shipped, indexed for both directions of the check.

    `data/fats/saints.json` is {name: {date, rank, bio, sentence, sentence_ref,
    collect, psalm, refrain, readings}}; `bio` and `collect` are multi-line, the
    other prose fields single-line.
    The `corrected` rule reconstructs each prose field from the pre-correction
    artifact plus the "fats" corrections (keyed by {saint, field}, substring
    `old`) — exactly as apply_corrections.py does — and a divergence is
    accounted as corrected only when the reconstruction reproduces the shipped
    field.
    """

    def __init__(self, data: dict, pre: dict, corrections: list[dict]):
        self.data = data
        self.lines: dict[str, dict[str, set[str]]] = {}
        self.pre_lines: dict[str, dict[str, set[str]]] = {}
        self.corr_lines: dict[str, dict[str, set[str]]] = {}
        self.valid: dict[str, dict[str, bool]] = {}
        for name, saint in data.items():
            pre_saint = pre.get(name, {}) if isinstance(pre.get(name), dict) else {}
            self.lines[name] = {}
            self.pre_lines[name] = {}
            self.corr_lines[name] = {}
            self.valid[name] = {}
            for field in FATS_PROSE_FIELDS:
                shipped_text = saint.get(field, "") or ""
                pre_text = pre_saint.get(field, "") or ""
                self.lines[name][field] = _field_lines(shipped_text)
                self.pre_lines[name][field] = _field_lines(pre_text)
                corrected = pre_text
                for c in corrections:
                    # Match apply_corrections._apply_replace exactly: key on
                    # `saint` OR `saint_key`, and replace the FIRST occurrence
                    # only. Over-replacing would fail closed (reconstruction ≠
                    # shipped) but would mislabel a legitimate multi-occurrence
                    # correction as a defect, so the count must agree.
                    if ((c.get("saint") or c.get("saint_key")) == name
                            and c.get("field") == field
                            and isinstance(c.get("old"), str)):
                        corrected = corrected.replace(c["old"], c["new"], 1)
                self.corr_lines[name][field] = _field_lines(corrected)
                # Whole-field equality collapses newlines, which is sound only
                # because the applier derives shipped from pre by substring
                # replace — line structure is preserved, so any difference is a
                # real edit, not a reflow.
                self.valid[name][field] = (squash(corrected) == squash(shipped_text))

    def has(self, name: str, field: str, text: str) -> bool:
        return squash(text) in self.lines.get(name, {}).get(field, set())

    def lost_by_manifest(self, name: str, field: str, text: str) -> bool:
        """A printed line the manifest removed: in the pre-correction field but
        not shipped, and the reconstruction (pre + corrections = shipped) holds."""
        needle = squash(text)
        return (needle in self.pre_lines.get(name, {}).get(field, set())
                and needle not in self.lines.get(name, {}).get(field, set())
                and self.valid.get(name, {}).get(field, False))

    def gained_by_manifest(self, name: str, field: str, key: str) -> bool:
        """A shipped line the manifest introduced: not extracted, but produced
        by a correction, and the reconstruction holds."""
        return (key in self.corr_lines.get(name, {}).get(field, set())
                and key not in self.pre_lines.get(name, {}).get(field, set())
                and self.valid.get(name, {}).get(field, False))


def check_fats(source: list[FatsSourceLine], shipped: FatsShipped,
               ) -> tuple[Counter, Counter, dict[str, Counter],
                          dict[str, Counter], list[Finding]]:
    page_total: Counter = Counter()
    data_total: Counter = Counter()
    page_by_saint: dict[str, Counter] = defaultdict(Counter)
    data_by_saint: dict[str, Counter] = defaultdict(Counter)
    findings: list[Finding] = []

    # ── PAGE → DATA ───────────────────────────────────────────────────────────
    for line in source:
        text = line.text
        if not squash(text):
            continue
        saint = line.saint
        if saint not in shipped.data:
            page_total["UNACCOUNTED"] += 1
            page_by_saint[saint]["UNACCOUNTED"] += 1
            findings.append(Finding("fats", saint, line.field, text, "page"))
            continue
        if shipped.has(saint, line.field, text):
            page_total["verbatim"] += 1
            page_by_saint[saint]["verbatim"] += 1
        elif shipped.lost_by_manifest(saint, line.field, text):
            page_total["corrected"] += 1
            page_by_saint[saint]["corrected"] += 1
        else:
            page_total["UNACCOUNTED"] += 1
            page_by_saint[saint]["UNACCOUNTED"] += 1
            findings.append(Finding("fats", saint, line.field, text, "page"))

    # ── DATA → PAGE ───────────────────────────────────────────────────────────
    page_set = {squash(line.text) for line in source}
    page_stream = " ".join(squash(line.text) for line in source)

    for name in sorted(shipped.data):
        for field in FATS_PROSE_FIELDS:
            for key in sorted(shipped.lines[name][field]):
                if key in page_set:
                    data_total["printed"] += 1
                    data_by_saint[name]["printed"] += 1
                elif key in page_stream:
                    data_total["printed-joined"] += 1
                    data_by_saint[name]["printed-joined"] += 1
                elif shipped.gained_by_manifest(name, field, key):
                    data_total["corrected"] += 1
                    data_by_saint[name]["corrected"] += 1
                else:
                    data_total["UNACCOUNTED"] += 1
                    data_by_saint[name]["UNACCOUNTED"] += 1
                    findings.append(Finding("fats", name, field, key, "data"))

    return page_total, data_total, page_by_saint, data_by_saint, findings


def run_fats(args) -> int:
    fats_pdf = ROOT / "sources" / "For-All-The-Saints.pdf"
    shipped_path = ROOT / "data" / "fats" / "saints.json"
    pre_path = ROOT / ".build" / "fats-saints.1-extract.json"
    for path, remedy in ((fats_pdf, "make fetch-sources"),
                         (shipped_path, "make extract"),
                         (pre_path, "make extract")):
        if not path.exists():
            print(f"ERROR: {path} not found\nRun: {remedy}", file=sys.stderr)
            return 1

    data = json.loads(shipped_path.read_text(encoding="utf-8"))
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    corrections = load_corrections("fats")

    if args.form:
        if args.form not in data:
            print(f"ERROR: unknown saint {args.form!r}", file=sys.stderr)
            return 1
        data = {args.form: data[args.form]}
        pre = {args.form: pre[args.form]} if args.form in pre else {}

    source = read_fats_source(fats_pdf)
    if args.form:
        source = [ln for ln in source if ln.saint == args.form]

    shipped = FatsShipped(data, pre, corrections)
    page_total, data_total, page_by_saint, data_by_saint, findings = \
        check_fats(source, shipped)

    known, errors = reconcile(findings, load_baseline(),
                              by_count=not args.form, chain="fats")

    if args.json:
        print(json.dumps({
            "chain": "fats",
            "saints": len(data),
            "page_to_data": dict(page_total),
            "data_to_page": dict(data_total),
            "known": [{"id": k["id"], "issue": k["issue"], "lines": k["found"]}
                      for k in known],
            "errors": errors,
            "unaccounted": [
                {"saint": f.section, "field": f.type, "direction": f.direction,
                 "id": line_id(f.text)}
                for f in findings
            ],
        }, indent=2))
        return 1 if errors else 0

    print(f"Conservation check — {fats_pdf.name} ↔ {shipped_path.relative_to(ROOT)}")
    print(f"Population: {sum(page_total.values()):,} source prose lines across "
          f"{len(data)} saints.")

    for want, heading, rules, totals, by_form in (
        ("page", "PAGE → DATA   is anything printed missing?",
         FATS_PAGE_RULES, page_total, page_by_saint),
        ("data", "DATA → PAGE   is anything shipped that was never printed?",
         FATS_DATA_RULES, data_total, data_by_saint),
    ):
        side = [k for k in known if k["direction"] == want]
        report(heading, rules, totals, by_form,
               sum(k["found"] for k in side), [k["issue"] for k in side])

    if known:
        print(f"\nKnown divergences ({sum(k['found'] for k in known)} lines, "
              f"{len(known)} entries in {BASELINE.name})")
        for k in sorted(known, key=lambda e: (e["issue"], e["id"])):
            print(f"    #{k['issue']:<4} {k['direction']:<5} {k['section']:<18} "
                  f"{k['id']}  × {k['found']:<3} {k['why']}")

    if findings and (args.form or errors):
        per_saint = {"page": page_by_saint, "data": data_by_saint}
        for direction, heading in (("page", "printed but not shipped"),
                                   ("data", "shipped but never printed")):
            rows = [f for f in findings if f.direction == direction]
            if not rows:
                continue
            print(f"\n  Unaccounted — {heading} ({len(rows)}):")
            print("    by saint: " + ", ".join(
                f"{s} ({n})" for s, n in sorted(per_saint[direction].items())
                if per_saint[direction][s].get("UNACCOUNTED", 0)))
            for f in rows:
                print(f.render(args.show_text))
        if not args.show_text:
            print("\n  Re-run with --show-text to read the lines themselves.")

    if errors:
        print(f"\nFAIL ({len(errors)}):")
        for err in errors:
            print(f"    {err}")
        return 1

    if args.form:
        print(f"\n{args.form}: every printed line is accounted for or claimed "
              f"by a baseline entry.")
        return 0

    print("\nEvery printed line is accounted for or claimed by a baseline entry, "
          "and nothing ships unprinted.")
    return 0


# ── The Mid-day Prayer walk (#166) ───────────────────────────────────────────
# Prayers at Mid-day (BAS pp. 56-59) is a separate source PDF, so it gets its
# own chain like psalter and fats rather than folding into the offices walk.
# The source side reuses the extractor's own page walk, span classification
# and same-type line merge (_page_lines/_merge_lines); what is restated is
# only the bookkeeping the check needs and the extractor has no reason to
# record — which field each merged item opens or lands in, exactly as the
# fats chain restates which saint+field a line belongs to. The title ships as
# the `_midday.title` field rather than a segment, so the walk emits it from
# the extractor's own _TITLE constant (whose presence detect_pages verifies).

MIDDAY_FIELDS = ("title", "opening", "psalm", "psalm_prayer", "reading",
                 "prayers", "collects", "lords_prayer", "dismissal")

MIDDAY_PAGE_RULES: list[tuple[str, str]] = [
    ("verbatim",  "ships exactly as printed"),
    ("whitespace", "the extractor's own _seg normalization (space before punctuation, nbsp)"),
    ("heading",   "consumed as structure — a section heading the renderer knows"),
    ("separator", "an Or/Or-the-following separator consumed into the alternatives it opens"),
    ("corrected", "extracted intact, then changed by an audited data/corrections.json entry"),
]

MIDDAY_DATA_RULES: list[tuple[str, str]] = [
    ("printed",        "appears on the page as printed"),
    ("printed-joined", "printed across a line break; ships as the joined line"),
    ("whitespace",     "the extractor's own _seg normalization"),
    ("structural",     "a Roman-numeral alternatives label the extractor assigns, not book text"),
    ("corrected",      "introduced by an audited data/corrections.json entry"),
]


class MiddaySourceLine:
    """A printed line of the mid-day office, tagged with the field it ships in."""
    __slots__ = ("text", "field", "consumed_as")

    def __init__(self, text: str, field: str, consumed_as: str | None = None):
        self.text = text.strip()
        self.field = field
        self.consumed_as = consumed_as


def read_midday_source(pdf_path: Path) -> list[MiddaySourceLine]:
    """Walk BAS pp. 56-59 the way `extract_midday` does, tagging each line's field.

    Classification (span -> type), the page walk and the same-type line merge
    are the extractor's own functions; what is restated is the boundary-to-field
    dispatch, which is the bookkeeping this check cannot work without. Merged
    items are split back on their newlines so the page set holds each printed
    line individually.
    """
    with fitz.open(pdf_path) as doc:
        start, end = detect_pages(doc)
        items = _merge_lines(_page_lines(doc, start, end))

    out: list[MiddaySourceLine] = [MiddaySourceLine(_TITLE, "title")]
    field = "opening"
    for typ, text in items:
        if typ == "smallheading" and text == "Psalm Prayer":
            field = "psalm_prayer"
            out.append(MiddaySourceLine(text, field, consumed_as="heading"))
            continue
        if typ == "heading" and text == _LORDS_PRAYER:
            field = "lords_prayer"
            out.append(MiddaySourceLine(text, field, consumed_as="heading"))
            continue
        if typ == "label":
            # The folded "Psalm 19:1-6" head; ships as a label segment.
            field = "psalm"
        elif typ == "rubric":
            if _OR_FOLLOWING_RE.match(text) or text.strip().lower() == "or":
                out.append(MiddaySourceLine(text, field, consumed_as="separator"))
                continue
            if _PSALMODY_RUBRIC_RE.match(text):
                field = "psalm"
            elif _READING_RUBRIC_RE.match(text):
                field = "reading"
            elif _COLLECT_RUBRIC_RE.match(text):
                field = "collects"
            elif text.startswith(_FIELD_BOUNDARY_PREFIXES[0]):
                field = "prayers"
            elif text.startswith(_FIELD_BOUNDARY_PREFIXES[1]):
                field = "dismissal"
        for ln in text.split("\n"):
            out.append(MiddaySourceLine(ln, field))
    return out


def _midday_fix(text: str) -> str:
    """The extractor's own _seg normalization, mirrored for the whitespace rule."""
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    return text.replace("\u00a0", " ")


def _field_text(field) -> str:
    """A field's text: segments flattened in order for a list field, the
    string itself for the title."""
    if isinstance(field, str):
        return field
    return "\n".join(seg["text"] for seg in iter_segments(field, {}) if seg.get("text"))


def _field_units(field) -> tuple[set[str], int]:
    """(squashed text lines, roman-label count) for one field.

    The roman I/II/III alternatives labels are assigned by the extractor, not
    printed, so they are counted as structure rather than matched as text.
    """
    if isinstance(field, str):
        return _field_lines(field), 0
    lines: set[str] = set()
    roman = 0
    for seg in iter_segments(field, {}):
        if seg.get("type") == "label" and _ROMAN_LABEL.match(seg.get("text", "")):
            roman += 1
        elif seg.get("text"):
            lines |= _field_lines(seg["text"])
    return lines, roman


class MiddayShipped:
    """The `_midday` form as shipped, indexed for both directions of the check.

    `data/offices.json._midday` is a form whose fields are segment lists (the
    title a plain string). The `corrected` rule reconstructs each field from
    the pre-correction artifact plus the office_text corrections addressed to
    `_midday` — exactly as apply_corrections.py does — and a divergence is
    accounted as corrected only when the reconstruction reproduces the shipped
    field.
    """

    def __init__(self, midday: dict, pre: dict, corrections: list[dict]):
        self.lines: dict[str, set[str]] = {}
        self.pre_lines: dict[str, set[str]] = {}
        self.corr_lines: dict[str, set[str]] = {}
        self.valid: dict[str, bool] = {}
        self.roman_labels: dict[str, int] = {}
        for field in MIDDAY_FIELDS:
            self.lines[field], roman = _field_units(midday.get(field))
            self.roman_labels[field] = roman
            self.pre_lines[field], _ = _field_units(pre.get(field))
            corrected = _field_text(pre.get(field))
            for c in corrections:
                if (c.get("office") == "_midday" and c.get("field") == field
                        and isinstance(c.get("old"), str)):
                    corrected = corrected.replace(c["old"], c["new"], 1)
            self.corr_lines[field] = _field_lines(corrected)
            self.valid[field] = (squash(corrected)
                                 == squash(_field_text(midday.get(field))))

    def has(self, field: str, text: str) -> bool:
        return squash(text) in self.lines.get(field, set())

    def lost_by_manifest(self, field: str, text: str) -> bool:
        """A printed line the manifest removed: in the pre-correction field but
        not shipped, and the reconstruction (pre + corrections = shipped) holds."""
        needle = squash(text)
        return (needle in self.pre_lines.get(field, set())
                and needle not in self.lines.get(field, set())
                and self.valid.get(field, False))

    def gained_by_manifest(self, field: str, key: str) -> bool:
        """A shipped line the manifest introduced: not extracted, but produced
        by a correction, and the reconstruction holds."""
        return (key in self.corr_lines.get(field, set())
                and key not in self.pre_lines.get(field, set())
                and self.valid.get(field, False))


def check_midday(source: list[MiddaySourceLine], shipped: MiddayShipped,
                 ) -> tuple[Counter, Counter, dict[str, Counter],
                            dict[str, Counter], list[Finding]]:
    page_total: Counter = Counter()
    data_total: Counter = Counter()
    page_by_field: dict[str, Counter] = defaultdict(Counter)
    data_by_field: dict[str, Counter] = defaultdict(Counter)
    findings: list[Finding] = []

    # ── PAGE → DATA ───────────────────────────────────────────────────────────
    for line in source:
        text = line.text
        if not squash(text):
            continue
        field = line.field
        if line.consumed_as in ("heading", "separator"):
            page_total[line.consumed_as] += 1
            page_by_field[field][line.consumed_as] += 1
            continue
        if shipped.has(field, text):
            page_total["verbatim"] += 1
            page_by_field[field]["verbatim"] += 1
        elif shipped.has(field, _midday_fix(text)):
            page_total["whitespace"] += 1
            page_by_field[field]["whitespace"] += 1
        elif shipped.lost_by_manifest(field, text):
            page_total["corrected"] += 1
            page_by_field[field]["corrected"] += 1
        else:
            page_total["UNACCOUNTED"] += 1
            page_by_field[field]["UNACCOUNTED"] += 1
            findings.append(Finding("midday", field, line.consumed_as or "text",
                                    text, "page"))

    # ── DATA → PAGE ───────────────────────────────────────────────────────────
    page_set = {squash(line.text) for line in source}
    page_stream = " ".join(squash(line.text) for line in source)
    fixed_stream = squash(_midday_fix(page_stream))

    for field in MIDDAY_FIELDS:
        for key in sorted(shipped.lines.get(field, set())):
            if key in page_set:
                data_total["printed"] += 1
                data_by_field[field]["printed"] += 1
            elif key in page_stream:
                data_total["printed-joined"] += 1
                data_by_field[field]["printed-joined"] += 1
            elif key in fixed_stream:
                data_total["whitespace"] += 1
                data_by_field[field]["whitespace"] += 1
            elif shipped.gained_by_manifest(field, key):
                data_total["corrected"] += 1
                data_by_field[field]["corrected"] += 1
            else:
                data_total["UNACCOUNTED"] += 1
                data_by_field[field]["UNACCOUNTED"] += 1
                findings.append(Finding("midday", field, "text", key, "data"))

    for field, roman in shipped.roman_labels.items():
        if roman:
            data_total["structural"] += roman
            data_by_field[field]["structural"] += roman

    return page_total, data_total, page_by_field, data_by_field, findings


def run_midday(args) -> int:
    bas_pdf = ROOT / "sources" / "BAS.pdf"
    shipped_path = ROOT / "data" / "offices.json"
    pre_path = ROOT / ".build" / "midday.1-extract.json"
    for path, remedy in ((bas_pdf, "make fetch-sources"),
                         (shipped_path, "make extract"),
                         (pre_path, "make extract")):
        if not path.exists():
            print(f"ERROR: {path} not found\nRun: {remedy}", file=sys.stderr)
            return 1

    if args.form:
        print("ERROR: --chain midday is a single form; --form does not apply",
              file=sys.stderr)
        return 1

    offices = json.loads(shipped_path.read_text(encoding="utf-8"))
    midday = offices.get("_midday", {})
    if not midday:
        print("ERROR: _midday missing from data/offices.json\nRun: make extract",
              file=sys.stderr)
        return 1
    pre = json.loads(pre_path.read_text(encoding="utf-8")).get("_midday", {})
    corrections = [c for c in load_corrections("office_text")
                   if c.get("office") == "_midday"]

    source = read_midday_source(bas_pdf)
    shipped = MiddayShipped(midday, pre, corrections)
    page_total, data_total, page_by_field, data_by_field, findings = \
        check_midday(source, shipped)

    known, errors = reconcile(findings, load_baseline(), by_count=True,
                              chain="midday")

    if args.json:
        print(json.dumps({
            "chain": "midday",
            "page_to_data": dict(page_total),
            "data_to_page": dict(data_total),
            "known": [{"id": k["id"], "issue": k["issue"], "lines": k["found"]}
                      for k in known],
            "errors": errors,
            "unaccounted": [
                {"field": f.section, "direction": f.direction, "id": line_id(f.text)}
                for f in findings
            ],
        }, indent=2))
        return 1 if errors else 0

    print(f"Conservation check — {bas_pdf.name} ↔ {shipped_path.relative_to(ROOT)}")
    print(f"Population: {sum(page_total.values()):,} source lines across the "
          "_midday form.")

    for want, heading, rules, totals, by_form in (
        ("page", "PAGE → DATA   is anything printed missing?",
         MIDDAY_PAGE_RULES, page_total, page_by_field),
        ("data", "DATA → PAGE   is anything shipped that was never printed?",
         MIDDAY_DATA_RULES, data_total, data_by_field),
    ):
        side = [k for k in known if k["direction"] == want]
        report(heading, rules, totals, by_form,
               sum(k["found"] for k in side), [k["issue"] for k in side])

    if known:
        print(f"\nKnown divergences ({sum(k['found'] for k in known)} lines, "
              f"{len(known)} entries in {BASELINE.name})")
        for k in sorted(known, key=lambda e: (e["issue"], e["id"])):
            print(f"    #{k['issue']:<4} {k['direction']:<5} {k['section']:<18} "
                  f"{k['id']}  × {k['found']:<3} {k['why']}")

    if findings:
        per_field = {"page": page_by_field, "data": data_by_field}
        for direction, heading in (("page", "printed but not shipped"),
                                   ("data", "shipped but never printed")):
            rows = [f for f in findings if f.direction == direction]
            if not rows:
                continue
            print(f"\n  Unaccounted — {heading} ({len(rows)}):")
            print("    by field: " + ", ".join(
                f"{f} ({n})" for f, n in sorted(per_field[direction].items())
                if per_field[direction][f].get("UNACCOUNTED", 0)))
            for f in rows:
                print(f.render(args.show_text))
        if not args.show_text:
            print("\n  Re-run with --show-text to read the lines themselves.")

    if errors:
        print(f"\nFAIL ({len(errors)}):")
        for err in errors:
            print(f"    {err}")
        return 1

    print("\nEvery printed line is accounted for or claimed by a baseline entry, "
          "and nothing ships unprinted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
