#!/usr/bin/env python3
"""
extract_psalter.py — extract the PWC Liturgical Psalter.

Reads sources/pray-without-ceasing.pdf and writes:

  data/psalter.json         — combined dict {str(num): psalm}, loaded by
                               the web SPA on first load

Schema: { number: int, book: int, title: str, text: str }
  (source-corrected entries also carry source_corrections: [...] — stamped
  on by apply_corrections.py, not here; see data/corrections.json "psalter")

Text format inside each psalm:
  • verse lines:      "N  verse text *"
  • continuation:     " continuation text"
  • section headings: "Part I", "Aleph", "Beth", … (multi-part / Ps 119)

Run from repo root:
  python3 tools/extract_psalter.py [--individual] [--accept]

  --individual  Also write data/psalms/{num}.json (one file per psalm).
  --accept      Update tools/manifest.json with current output hashes.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from extract_lib import check_manifest, normalise_quotes, write_json


# ── Patterns ──────────────────────────────────────────────────────────────────

RE_PSALM_HEAD = re.compile(r'^Psalm\s+(\d+)\s*(.*)')
RE_VERSE      = re.compile(r'^\d+\s')
RE_SECTION    = re.compile(
    r'^(?:Part\s+[IVX]+\b'           # "Part I", "Part II", …
    r'|(?:Aleph|Beth|Gimel|Daleth|He\b|Waw|Zayin|Heth|Teth|Yodh'
    r'|Kaph|Lamedh|Mem|Nun|Samekh|Ayin|Pe|Tsadhe|Qoph|Resh|Sin|Shin|Taw)'
    r'\s+)',
    re.IGNORECASE,
)
RE_BOOK = re.compile(r'^BooK\s+[ivxIVX]+', re.IGNORECASE)


# ── Page-header stripping ─────────────────────────────────────────────────────

_HDR_PREFIX = re.compile(r'^\d{1,3}\s{3,}Liturgical Psalter(.*)', re.IGNORECASE)
_HDR_SUFFIX = re.compile(r'^\s*Liturgical Psalter\s+\d{1,3}(.*)', re.IGNORECASE)

def strip_page_header(line: str) -> str | None:
    """Return the content after stripping page-header artefacts, or None to skip."""
    m = _HDR_PREFIX.match(line)
    if m:
        rest = m.group(1)
        return rest if rest.strip() else None
    m = _HDR_SUFFIX.match(line)
    if m:
        rest = m.group(1)
        return rest if rest.strip() else None
    return line


# ── PDF line geometry ─────────────────────────────────────────────────────────

def pdf_lines_with_x0(pdf_path: Path) -> list[tuple[float, str]]:
    """Return (x0, text) for every visual line in the PDF, in reading order.

    Unlike page.get_text(), this keeps each line's left-edge x-coordinate so
    callers can tell a physically-indented line (a verse's second half) from
    an ordinary line-wrap — see the "second half" indent tracking below.
    """
    import fitz  # noqa: PLC0415

    out: list[tuple[float, str]] = []
    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            d = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT)
            for block in d["blocks"]:
                if "lines" not in block:
                    continue
                for line in block["lines"]:
                    text = "".join(span["text"] for span in line["spans"])
                    if not text.strip():
                        continue
                    out.append((line["bbox"][0], text))
    return out


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_psalms(lines: list[tuple[float, str]]) -> list[dict]:
    """
    Read the source lines (with x0) and return a list of psalm dicts:
        {number: int, book: int, title: str, text: str}
    """
    psalter_start = None
    for i, (_x0, line) in enumerate(lines):
        cleaned = strip_page_header(line)
        if cleaned is not None and RE_BOOK.match(cleaned.strip()):
            psalter_start = i
            break

    if psalter_start is None:
        sys.exit("Could not locate the Psalter section.")

    psalms: list[dict] = []
    cur_num: int | None = None
    cur_title: str = ""
    cur_lines: list[str] = []
    # Verse second-halves (and section headings) are typeset with a physical
    # ~36pt indent relative to the verse's first half, and a second half can
    # itself run onto multiple indented lines. Track the flush left margin
    # established by the last verse-start/section-heading line as the
    # baseline, and mark any later line indented past it with a leading
    # space — the continuation marker formatLiturgicalText() reads in
    # render.js. Reset the baseline on every verse-start/section line (they
    # are always flush), not just when a "*" is seen: a verse can contain
    # several first-half/second-half pairs, and a first half returning to
    # the flush margin doesn't necessarily end in "*" on its last line.
    baseline_x0: float | None = None

    def psalm_book(n: int) -> int:
        if n <= 41:  return 1
        if n <= 72:  return 2
        if n <= 89:  return 3
        if n <= 106: return 4
        return 5

    def flush():
        if cur_num is not None:
            psalms.append({
                "number": cur_num,
                "book":   psalm_book(cur_num),
                "title":  cur_title,
                "text":   "\n".join(cur_lines).strip(),
            })

    for x0, raw in lines[psalter_start:]:
        raw = normalise_quotes(raw)
        if "Acknowledgements" in raw:
            break
        line = strip_page_header(raw)
        if line is None:
            continue
        line = line.rstrip()
        stripped = line.strip()

        if not stripped or RE_BOOK.match(stripped):
            continue

        m = RE_PSALM_HEAD.match(stripped)
        if m:
            flush()
            cur_num   = int(m.group(1))
            cur_title = m.group(2).strip()
            cur_lines = []
            baseline_x0 = None
            continue

        if cur_num is None:
            continue

        if RE_SECTION.match(stripped):
            cur_lines.append(stripped)
            baseline_x0 = x0
            continue

        if RE_VERSE.match(stripped):
            cur_lines.append(stripped)
            baseline_x0 = x0
            continue

        indented = baseline_x0 is not None and x0 > baseline_x0 + 8
        cur_lines.append((" " if indented else "") + stripped)

    flush()
    return psalms


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--individual", action="store_true",
                    help="Also write data/psalms/{num}.json (one file per psalm)")
    ap.add_argument("--accept", action="store_true",
                    help="Update tools/manifest.json with current output hashes")
    args = ap.parse_args()

    root = Path(__file__).parent.parent

    print("Extracting pray-without-ceasing.pdf…", file=sys.stderr)
    lines = pdf_lines_with_x0(root / "sources" / "pray-without-ceasing.pdf")
    psalms_list = extract_psalms(lines)

    found   = {p["number"] for p in psalms_list}
    missing = [n for n in range(1, 151) if n not in found]
    if missing:
        print(f"WARNING: missing psalms: {missing}", file=sys.stderr)

    # One-off text corrections (spelling, typos, missing words) are no longer
    # hardcoded here -- they live in data/corrections.json ("psalter") and are
    # applied by apply_corrections.py later in the pipeline (make extract),
    # the same mechanism used for office text and lectionary data. This
    # extractor only does extraction. See issue #13 and ADR 0005.
    psalms_by_num: dict[int, dict] = {p["number"]: p for p in psalms_list}

    # ── Write: combined dict ─────────────────────────────────────────────
    psalter_path = root / "data" / "psalter.json"
    psalter_path.parent.mkdir(parents=True, exist_ok=True)
    combined = {str(n): p for n, p in sorted(psalms_by_num.items())}
    write_json(combined, psalter_path)

    msg = f"Wrote {len(psalms_by_num)} psalms → {psalter_path}"

    if args.individual:
        psalms_dir = root / "data" / "psalms"
        psalms_dir.mkdir(parents=True, exist_ok=True)
        for n, psalm in sorted(psalms_by_num.items()):
            write_json(psalm, psalms_dir / f"{n}.json")
        msg += f" + {psalms_dir}/"

    print(msg)

    # ── Spot checks ───────────────────────────────────────────────────────────
    checks: list[tuple[str, bool]] = []
    def t(n):
        return psalms_by_num[n]["text"]

    # Section A insertions (page-break restoration — PyMuPDF handles these natively)
    for n, chk in [(27, "Therefore I will offer in your dwelling"),
                   (41, "The Lord will deliver them in the time of trouble"),
                   (45, "Therefore God, your God, has anointed you"),
                   (53, "When God restores the fortune of this people"),
                   (68, "The God of Israel gives strength and power to this people"),
                   (69, "Must I then give back what I never stole"),
                   (81, "That Israel would walk in my ways"),
                   (93, "The Lord has made the whole world so sure"),
                   (146, "The Lord lifts up those who are bowed down")]:
        checks.append((f"Ps {n} verse restored", chk in t(n)))

    # Section B: extraction structure (one-off text corrections — spelling,
    # typos, missing words — are checked separately by apply_corrections.py,
    # which is what actually applies them; see data/corrections.json "psalter").
    checks += [
        ("Ps 2 v12 present",       any(l.startswith("12 ") for l in t(2).split("\n"))),
        # "Hallelujah!" sits on its own line, flush with "When Israel came out
        # of Egypt," below it (both at PDF x0=30.0 — verified against source
        # geometry) — no leading space, since it's the first half of v1, not
        # a second half.
        ("Ps 114 v1 Hallelujah",   "1 Hallelujah!\nWhen Israel came out of Egypt" in t(114)),
        ("book field on all 150",  all("book" in psalms_by_num[n] for n in psalms_by_num)),
        ("no curly quotes",        not any(c in t(n) for n in psalms_by_num for c in "“”‘’")),
    ]
    all_ok = True
    for label, ok in checks:
        if not ok:
            all_ok = False
            print(f"  [FAIL] {label}")
    if all_ok:
        print(f"  All {len(checks)} spot checks passed.")
    else:
        sys.exit(1)

    check_manifest([psalter_path], root, accept=args.accept)


if __name__ == "__main__":
    main()
