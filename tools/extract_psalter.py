#!/usr/bin/env python3
"""
extract_psalter.py — extract the PWC Liturgical Psalter.

Reads sources/pray-without-ceasing.pdf and writes:

  data/psalter.json         — combined dict {str(num): psalm}, loaded by
                               the web SPA on first load

Schema: { number: int, book: int, title: str, text: str }
  (source-corrected entries also carry source_corrections: [...])

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

from extract_lib import check_manifest, normalise_quotes, pdf_as_text, write_json


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


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_psalms(path: Path) -> list[dict]:
    """
    Read the source text and return a list of psalm dicts:
        {number: int, book: int, title: str, text: str}
    """
    raw_lines = path.read_text(encoding="utf-8").splitlines()

    psalter_start = None
    for i, line in enumerate(raw_lines):
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

    for raw in raw_lines[psalter_start:]:
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
            continue

        if cur_num is None:
            continue

        if RE_SECTION.match(stripped):
            cur_lines.append(stripped)
            continue

        if RE_VERSE.match(stripped):
            cur_lines.append(stripped)
            continue

        cur_lines.append(" " + stripped)

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

    with pdf_as_text(root / "sources" / "pray-without-ceasing.pdf") as src:
        psalms_list = extract_psalms(src)

    found   = {p["number"] for p in psalms_list}
    missing = [n for n in range(1, 151) if n not in found]
    if missing:
        print(f"WARNING: missing psalms: {missing}", file=sys.stderr)

    # Apply corrections: keyed by int for in-place mutation.
    psalms_by_num: dict[int, dict] = {p["number"]: p for p in psalms_list}

    # Fix typographic error: double period in Psalm 78 v72
    # PyMuPDF uses non-breaking spaces in liturgical text; match both.
    if 78 in psalms_by_num:
        text = psalms_by_num[78]["text"]
        text = text.replace("God's hands\u00a0..", "God's hands.")  # nbsp variant
        text = text.replace("God's hands..", "God's hands.")        # regular space
        psalms_by_num[78]["text"] = text

    # British/Canadian orthography (source PDF uses American spelling)
    for num, (old, new) in {
        51: ("offenses.", "offences."),
        61: ("fulfill",   "fulfil"),
        64: ("recognize", "recognise"),
    }.items():
        if num in psalms_by_num:
            psalms_by_num[num]["text"] = psalms_by_num[num]["text"].replace(old, new)

    # Psalm 119 uses non-standard "Sadhe" for the 18th section
    if 119 in psalms_by_num:
        psalms_by_num[119]["text"] = psalms_by_num[119]["text"].replace("Sadhe ", "Tsadhe ")

    # Psalm 35 v25 — missing "not" (meaning reversed)
    if 35 in psalms_by_num:
        psalms_by_num[35]["text"] = (
            psalms_by_num[35]["text"]
            .replace("\u00a0Do let them say", "\u00a0Do not let them say")
            .replace("\nDo let them say", "\nDo not let them say"))
        psalms_by_num[35]["source_corrections"] = [{
            "verse": 25,
            "original":  "Do let them say in their hearts, *",
            "corrected": "Do not let them say in their hearts, *",
            "reason": "Missing 'not' in source — meaning reversed.",
        }]

    # Tag spelling fixes with provenance
    for num, old, new, verse, reason in [
        (51, "offenses.", "offences.", 1, "American spelling; psalter uses British/Canadian orthography"),
        (61, "fulfill", "fulfil", 8, "American spelling; psalter uses British/Canadian orthography"),
        (64, "recognize", "recognise", 9, "American spelling; psalter uses British/Canadian orthography"),
    ]:
        if num in psalms_by_num:
            psalms_by_num[num]["source_corrections"] = [{
                "verse": verse, "original": old, "corrected": new, "reason": reason,
            }]

    if 78 in psalms_by_num:
        psalms_by_num[78]["source_corrections"] = [{
            "verse": 72,
            "original": "skillfulness of God's hands..",
            "corrected": "skillfulness of God's hands.",
            "reason": "Typographic error: double period in printed source.",
        }]

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

    # Section B corrections
    checks += [
        ("Ps 2 v12 present",       any(l.startswith("12 ") for l in t(2).split("\n"))),
        ("Ps 35 v25 not restored", "Do not let them say" in t(35)),
        ("Ps 51 v1 offences",      "offences" in t(51)),
        ("Ps 61 v8 fulfil",        "fulfil" in t(61)),
        ("Ps 64 v9 recognise",     "recognise" in t(64)),
        ("Ps 78 v72 single period","God's hands.." not in t(78)),
        ("Ps 119 Tsadhe header",   "Tsadhe " in t(119) and "Sadhe " not in t(119)),
        ("Ps 114 v1 Hallelujah",   "1 Hallelujah!\n When Israel came out of Egypt" in t(114)),
        ("book field on all 150",  all("book" in psalms_by_num[n] for n in psalms_by_num)),
        ("no curly quotes",        not any(c in t(n) for n in psalms_by_num for c in "“”‘’")),
        ("source_corrections × 5", all("source_corrections" in psalms_by_num.get(n, {}) for n in [35, 51, 61, 64, 78])),
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
