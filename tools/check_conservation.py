#!/usr/bin/env python3
"""check_conservation.py — compare the shipped offices against the printed page.

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

Usage:
    python3 tools/check_conservation.py [--show-text] [--json] [--form KEY]
"""

import argparse
import contextlib
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
    from extract_office_styles import document_metrics, extract_office_typed_lines

    # The extractor's own predicates, imported rather than restated: every
    # decision that can drift is made by the code under test, not by a copy of
    # it here.
    from extract_offices import (
        _CONTINUE,
        _CONTROL_CHARS,
        _RESPONSE_HDRS,
        OFFICES,
        _alt_label,
        _heading_to_key,
        _is_noise,
        _normalize_whitespace,
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

        for section, field in form.items():
            if section in ("title", "subtitle"):
                self._add(section, "header", field)
                continue
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


def load_corrections() -> list[dict]:
    if not CORRECTIONS.exists():
        return []
    return json.loads(CORRECTIONS.read_text(encoding="utf-8")).get("office_text", [])


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
    for section, raw in pre.raw_blocks:
        after = raw
        for entry in relevant:
            if entry.get("field") == section:
                after = after.replace(entry["old"], entry["new"])
        for entry in whole:
            # A whole-field entry replaces the field, not a segment, so it can
            # only be honoured at that granularity: any text in its `new` is
            # authorised for this section.
            if entry.get("field") == section:
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


def load_baseline() -> list[dict]:
    if not BASELINE.exists():
        return []
    return json.loads(BASELINE.read_text(encoding="utf-8")).get("known", [])


def reconcile(findings: list[Finding], baseline: list[dict],
              by_count: bool = True) -> tuple[list[dict], list[str]]:
    """Match findings against the baseline. Returns (known, errors).

    With `by_count`, counts are compared exactly in both directions: a defect
    that grew is a regression and a defect that shrank is a fix that did not
    finish tidying up after itself, so both fail and the entry gets looked at. A
    baseline that could absorb either would stop being evidence of anything.

    Without it — a single-form run, where a corpus-wide count means nothing —
    matching is by membership only: an entry that does not fire is not stale, it
    just belongs to another form.
    """
    actual: Counter = Counter()
    for f in findings:
        actual[(f.direction, f.section, line_id(f.text))] += 1

    known, errors = [], []
    for entry in baseline:
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
    ap.add_argument("--form", help="restrict to one form key")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

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

    doc.close()

    # A baseline entry counts lines across the whole corpus, so a single-form
    # run cannot be reconciled against those counts: every entry would read as
    # stale and every finding as new. It can still be reconciled by membership,
    # which is what makes --form usable — it reports the form's share of a known
    # divergence as known, and still fails on anything the baseline never
    # claimed.
    known, errors = reconcile(findings, load_baseline(), by_count=not args.form)

    if args.json:
        print(json.dumps({
            "forms": len(offices),
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

    print(f"Conservation check — {PDF.name} ↔ {SHIPPED.relative_to(ROOT)}")
    print(f"Population: {sum(page_total.values()):,} typed source lines across "
          f"{len(offices)} forms, after the noise filter.")

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


if __name__ == "__main__":
    sys.exit(main())
