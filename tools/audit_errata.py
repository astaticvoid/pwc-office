#!/usr/bin/env python3
"""
audit_errata.py — does data/offices.json carry what the errata asks for?

The errata corrects the printed book, not our extractor: the geometry we read
off the page is faithful and the page is what is wrong. So its requests become
`office_text` corrections (ADR 0005), and nothing else verifies they all landed.
They did not — the first reflow pass dropped four breaks, three of them beside a
wording divergence, while `make test` and a 100/100 coherence score stayed green.

For each ```text block in docs/errata/*.md this aligns the errata's text against
the office named by the enclosing heading and reports:

    MISSING-BREAK   the errata breaks here, the data does not
    EXTRA-BREAK     the data breaks here, the errata does not
    WORDING         the texts diverge, so no break can be adjudicated
    UNALIGNED       the block matches nothing in the form it belongs to

WORDING is the load-bearing class: a divergence is where breaks get dropped.
Each is cleared by a row in the declarations table of docs/errata/README.md,
and a declaration matching no finding is itself reported — a stale exemption is
how one outlives its reason.

Reports; does not gate. Run it whenever the errata or the corrections change.
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERRATA_DIR = ROOT / "docs" / "errata"

SEASONS = {"Advent": "advent", "Christmas": "christmas", "Epiphany": "epiphany",
           "Lent": "lent", "Passiontide": "passiontide", "Easter": "easter",
           "Pentecost": "pentecost", "All Saints": "allsaints"}
WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

# A field boundary in the concatenated stream. No match may straddle one, so a
# block can never be aligned half against one section and half against the next.
BOUNDARY = "\x00"


def heading_to_form(heading: str):
    m = re.match(r"(Morning|Evening) Prayer for (.+)", heading.strip())
    if not m:
        return None
    office = "mp" if m.group(1) == "Morning" else "ep"
    who = m.group(2).strip()
    if who in SEASONS:
        return f"{SEASONS[who]}-{office}"
    if who in WEEKDAYS:
        return f"ordinary-{who.lower()}-{office}"
    return None


def norm(word: str) -> str:
    w = word.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9']", "", w)


def to_stream(text: str):
    """(display, normalised, break_after) per word. break_after marks a newline."""
    disp, keys, brk = [], [], []
    for line in text.split("\n"):
        toks = [t for t in re.split(r"\s+", line.replace("*", " ")) if t]
        toks = [(t, norm(t)) for t in toks]
        toks = [t for t in toks if t[1]]
        for i, (d, k) in enumerate(toks):
            disp.append(d)
            keys.append(k)
            brk.append(i == len(toks) - 1)
    if brk:
        brk[-1] = False
    return disp, keys, brk


def office_stream(offices: dict, form_key: str):
    """Every text-bearing segment of a form, in document order, `_shared`
    resolved. Segment ends carry a break: a break there is structural, never a
    wrap, so it must be reported as neither missing nor extra."""
    disp, keys, brk, field_of = [], [], [], []
    structural = set()          # indices where the break is a segment end
    shared = offices.get("_shared", {})

    def walk(node, field):
        if isinstance(node, dict):
            if node.get("type") == "shared":
                key = node.get("key")
                if key in shared:
                    walk(shared[key], field)
                return
            text = node.get("text")
            if isinstance(text, str):
                d, k, b = to_stream(text)
                if d:
                    b[-1] = True          # segment boundary
                    structural.add(len(disp) + len(d) - 1)
                    disp.extend(d)
                    keys.extend(k)
                    brk.extend(b)
                    field_of.extend([field] * len(d))
            for name, value in node.items():
                if name != "text":
                    walk(value, field)
        elif isinstance(node, list):
            for item in node:
                walk(item, field)

    for field, value in offices[form_key].items():
        if field == "title":
            continue
        if disp:
            structural.add(len(disp))
            disp.append(BOUNDARY)
            keys.append(BOUNDARY)
            brk.append(True)
            field_of.append(field)
        walk(value, field)
    return disp, keys, brk, field_of, structural


def parse_blocks(path: Path):
    """(heading, page, note, block_text) for each fenced block."""
    out, heading, page, note = [], None, None, None
    lines = path.read_text().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            heading = line[3:].strip()
        m = re.match(r"\*\*(p\.\s?[\d, ]+)\*\*\s*—\s*(.*)", line)
        if m:
            page, note = m.group(1).strip(), m.group(2).strip()
        if line.strip().startswith("```"):
            j = i + 1
            body = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                body.append(lines[j])
                j += 1
            out.append((heading, page, note, "\n".join(body)))
            i = j
        i += 1
    return out


def parse_declarations():
    """Rows of the declarations table in docs/errata/README.md.

    | Document | Page | Errata reads | We read | Ruling | Why |

    Ruling is `ours` (the errata retyped it wrong), `errata` (ours is wrong and
    a correction is owed), or `n/a` (the erratum asks for something we do not
    represent — clears its whole block, and `Errata reads` is `—`).
    """
    readme = ERRATA_DIR / "README.md"
    if not readme.exists():
        return []
    rows, in_table = [], False
    for line in readme.read_text().split("\n"):
        if re.match(r"^\|\s*Document\s*\|\s*Page\s*\|", line):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                in_table = False
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 5 or set(cells[0]) <= set("-: "):
                continue
            rows.append({"document": cells[0], "page": cells[1],
                         "errata_reads": cells[2], "we_read": cells[3],
                         "ruling": cells[4].lower()})
    return rows


def audit():
    offices_path = ROOT / "data" / "offices.json"
    if not offices_path.exists():
        print("data/offices.json is missing — run `make extract` first.", file=sys.stderr)
        return [], []
    offices = json.loads(offices_path.read_bytes())
    declarations = parse_declarations()
    used = set()
    findings = []

    for doc in sorted(ERRATA_DIR.glob("*.md")):
        if doc.name == "README.md":
            continue
        label = "Ordinary" if "ordinary" in doc.name else "Seasonal"
        for heading, page, note, block in parse_blocks(doc):
            form = heading_to_form(heading or "")
            declared_na = next((d for d in declarations
                                if d["document"] == label and d["page"] == page
                                and d["ruling"] == "n/a"), None)
            if declared_na:
                used.add(id(declared_na))
                continue
            if form is None or form not in offices:
                findings.append((label, page, "UNALIGNED",
                                 f"heading {heading!r} maps to no office form"))
                continue

            e_disp, e_keys, e_brk = to_stream(block)
            if not e_disp:
                continue
            o_disp, o_keys, o_brk, o_field, o_struct = office_stream(offices, form)
            ops = SequenceMatcher(None, o_keys, e_keys, autojunk=False).get_opcodes()
            anchors = [o for o in ops if o[0] == "equal" and o[2] - o[1] >= 3]
            if not anchors:
                findings.append((label, page, "UNALIGNED",
                                 f"{form}: no anchor for {' '.join(e_disp[:8])}…"))
                continue
            lo, hi = min(a[1] for a in anchors), max(a[2] for a in anchors)

            for tag, i1, i2, j1, j2 in ops:
                if tag == "equal":
                    for k in range(i2 - i1 - 1):
                        oi, ej = i1 + k, j1 + k
                        # A segment end is structural, never a wrap: the book
                        # runs versicle and response together on one line where
                        # we hold them as separate segments.
                        if oi in o_struct or o_brk[oi] == e_brk[ej]:
                            continue
                        kind = "MISSING-BREAK" if e_brk[ej] else "EXTRA-BREAK"
                        before = " ".join(w for w in o_disp[max(i1, oi - 5):oi + 1]
                                          if w != BOUNDARY)
                        after = " ".join(w for w in o_disp[oi + 1:oi + 6] if w != BOUNDARY)
                        findings.append((label, page, kind,
                                         f"{form} [{o_field[oi]}] …{before} ⏎ {after}…"))
                elif i1 >= lo and i2 <= hi:
                    ours = " ".join(w for w in o_disp[i1:i2] if w != BOUNDARY)
                    theirs = " ".join(e_disp[j1:j2])
                    if not ours and not theirs:
                        continue
                    # "—" stands for an empty side: the errata omits a word we
                    # have, so there is no errata text to quote.
                    match = next((d for d in declarations
                                  if d["document"] == label and d["page"] == page
                                  and (d["errata_reads"] == theirs
                                       or (d["errata_reads"] == "—" and not theirs))), None)
                    if match:
                        used.add(id(match))
                        continue
                    findings.append((label, page, "WORDING",
                                     f"{form}: ours {ours!r} vs errata {theirs!r}"))

    stale = [d for d in declarations if id(d) not in used]
    return findings, stale


def main():
    findings, stale = audit()
    for label, page, kind, detail in findings:
        print(f"[{kind:14}] {label} {page or '?'}\n                 {detail}")
    for d in stale:
        print(f"[{'STALE-DECL':14}] {d['document']} {d['page']}\n"
              f"                 declaration matches no finding: {d['errata_reads']!r}")
    total = len(findings) + len(stale)
    print(f"\n{total} finding(s)." if total else "\nErrata fully applied.")


if __name__ == "__main__":
    main()
