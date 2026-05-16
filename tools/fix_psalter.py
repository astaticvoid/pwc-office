#!/usr/bin/env python3
"""
Apply verified corrections to data/psalms/*.json.

Sections:
  A — Missing verse text (12 fixes)
  B — Spurious section/book markers appended to verse lines (32 fixes)
  C — Source errors with source_corrections metadata (5 fixes)

Run from repo root:
  python3 tools/fix_psalter.py
"""

import json
import sys
from pathlib import Path

root = Path(__file__).parent.parent
psalms_dir = root / "data" / "psalms"

if not psalms_dir.exists():
    print(f"ERROR: {psalms_dir} not found — run extract_psalter.py first", file=sys.stderr)
    sys.exit(1)

psalms: dict[int, dict] = {}
for path in psalms_dir.glob("*.json"):
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    psalms[p["number"]] = p

warnings = []


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_text(num: int) -> str:
    return psalms[num]["text"]

def set_text(num: int, text: str) -> None:
    psalms[num]["text"] = text

def insert_before(num: int, marker: str, new_line: str) -> None:
    """Insert new_line immediately before the first line containing marker.
    Idempotent: no-op if new_line is already the line immediately before marker."""
    text = get_text(num)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            if i > 0 and lines[i - 1] == new_line:
                return  # already present
            lines.insert(i, new_line)
            set_text(num, "\n".join(lines))
            return
    warnings.append(f"Psalm {num}: insert_before marker not found: {marker!r}")

def insert_after(num: int, marker: str, new_line: str) -> None:
    """Insert new_line immediately after the first line containing marker.
    Idempotent: no-op if new_line is already the line immediately after marker."""
    text = get_text(num)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            if i + 1 < len(lines) and lines[i + 1] == new_line:
                return  # already present
            lines.insert(i + 1, new_line)
            set_text(num, "\n".join(lines))
            return
    warnings.append(f"Psalm {num}: insert_after marker not found: {marker!r}")

def append_lines(num: int, new_lines: list[str]) -> None:
    """Append lines to end of psalm text.
    Idempotent: no-op if the lines are already at the end of the text."""
    text = get_text(num)
    existing = text.split("\n")
    if len(existing) >= len(new_lines) and existing[-len(new_lines):] == new_lines:
        return  # already present
    set_text(num, text + "\n" + "\n".join(new_lines))

def strip_suffix(num: int, suffix: str) -> None:
    """Remove suffix from the line it appears on (must be at line-end)."""
    text = get_text(num)
    # Replace suffix when followed by newline or at end of string.
    if suffix + "\n" in text:
        set_text(num, text.replace(suffix + "\n", "\n", 1))
    elif text.endswith(suffix):
        set_text(num, text[: -len(suffix)])
    else:
        warnings.append(f"Psalm {num}: suffix not found at line-end: {suffix!r}")

def replace_text(num: int, old: str, new: str) -> None:
    """Replace first occurrence of old with new."""
    text = get_text(num)
    if old not in text:
        warnings.append(f"Psalm {num}: text not found: {old!r}")
        return
    set_text(num, text.replace(old, new, 1))

def add_source_corrections(num: int, corrections: list[dict]) -> None:
    """Insert source_corrections field between title and text."""
    p = psalms[num]
    new_p = {
        "number": p["number"],
        "book": p["book"],
        "title": p["title"],
        "source_corrections": corrections,
        "text": p["text"],
    }
    psalms[num] = new_p


# ── Section A — Missing verse text ─────────────────────────────────────────────

# Psalm 2 v12 — page-break artefact: continuation lines are displaced to after
# v11's last line in the PDF layout, appearing again correctly after "12 lest...".
# Idempotent: normalise everything from v11's final line to end of psalm.
# Handles both pdfplumber (displaced+duplicate) and pdftotext (incomplete v12) forms.
_PS2_V11_TAIL = " and bow with trembling before the presence of the Lord;"
_PS2_V12_BLOCK = (
    "12 lest God be angry and you perish; *\n"
    " for the divine wrath is quickly kindled.\n"
    " Happy are they all *\n"
    " who take refuge in God!"
)
if _PS2_V11_TAIL + "\n" + _PS2_V12_BLOCK not in get_text(2):
    text = get_text(2)
    cut = text.rfind(_PS2_V11_TAIL)
    if cut < 0:
        warnings.append("Psalm 2: v11 tail not found")
    else:
        set_text(2, text[:cut + len(_PS2_V11_TAIL)] + "\n" + _PS2_V12_BLOCK)

# Psalm 27 v6 — dropped line before "an oblation"
insert_before(27,
    "an oblation with sounds of great gladness; *",
    " Therefore I will offer in your dwelling")

# Psalm 41 v1 — second half-verse missing
insert_after(41,
    "Happy are they who consider the poor and needy! *",
    " The Lord will deliver them in the time of trouble.")

# Psalm 45 v7 — dropped line before "with the oil of gladness"
insert_before(45,
    "with the oil of gladness above your companions.",
    " Therefore God, your God, has anointed you")

# Psalm 53 v6 — dropped line before "Jacob will rejoice"
insert_before(53,
    "Jacob will rejoice and Israel be glad.",
    " When God restores the fortune of this people,")

# Psalm 68 v35 — dropped line before "Blessed be God!"
insert_before(68,
    "Blessed be God!",
    " The God of Israel gives strength and power to this people!")

# Psalm 69 v4 — second half-verse missing
insert_after(69,
    "my lying foes who would destroy me are mighty. *",
    " Must I then give back what I never stole?")

# Psalm 81 v13 — second half-verse missing
insert_after(81,
    "Oh, that my people would listen to me! *",
    " That Israel would walk in my ways!")

# Psalm 93 v1 — dropped line before "that it cannot be moved"
insert_before(93,
    "that it cannot be moved;",
    " The Lord has made the whole world so sure")

# Psalm 96 v10 — the fresh extraction already captures the missing line correctly
# from the source PDF. No fix needed.

# Psalm 114 v1 — the extractor already splits "Hallelujah!" onto its own line.
# No fix needed.

# Psalm 146 v8 — dropped line before "and loves the righteous"
insert_before(146,
    "and loves the righteous.",
    " The Lord lifts up those who are bowed down")

# Psalm 119 — source uses "Sadhe" for the 18th section; rename to the standard "Tsadhe"
replace_text(119, "Sadhe  ", "Tsadhe  ")


# ── Section B — NOTE: No-op ─────────────────────────────────────────────────────
# The error list described section/book markers concatenated to verse endings.
# In the actual YAML, these markers appear as standalone lines (Part I/II, Aleph,
# Beth, etc.) because RE_SECTION in extract_psalter.py correctly separates them.
# No stripping is needed or applied.


# ── Section C — Source errors + source_corrections metadata ────────────────────

# C1: Psalm 35 v25 — missing "not" reverses meaning
replace_text(35,
    "Do let them say in their hearts, *",
    "Do not let them say in their hearts, *")
add_source_corrections(35, [{
    "verse": 25,
    "original": "Do let them say in their hearts, *",
    "corrected": "Do not let them say in their hearts, *",
    "reason": (
        "Missing 'not' in source — meaning reversed. "
        "All parallel sources (BCP 1979, NRSV, ELW) read 'Do not let them say.'"
    ),
}])

# C2: Psalm 51 v1 — American spelling
replace_text(51, "blot out my offenses.", "blot out my offences.")
add_source_corrections(51, [{
    "verse": 1,
    "original": "blot out my offenses.",
    "corrected": "blot out my offences.",
    "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
}])

# C3: Psalm 61 v8 — American spelling
replace_text(61, "and day by day I will fulfill my vows.", "and day by day I will fulfil my vows.")
add_source_corrections(61, [{
    "verse": 8,
    "original": "and day by day I will fulfill my vows.",
    "corrected": "and day by day I will fulfil my vows.",
    "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
}])

# C4: Psalm 64 v9 — American spelling
replace_text(64, "they will recognize your works.", "they will recognise your works.")
add_source_corrections(64, [{
    "verse": 9,
    "original": "they will recognize your works.",
    "corrected": "they will recognise your works.",
    "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
}])

# C5: Psalm 78 v72 — double period
# Use the suffix "hands.." (straight apostrophe normalised by extractor).
replace_text(78,
    "skillfulness of God's hands..",
    "skillfulness of God's hands.")
add_source_corrections(78, [{
    "verse": 72,
    "original": "and guided them with the skillfulness of God's hands..",
    "corrected": "and guided them with the skillfulness of God's hands.",
    "reason": "Typographic error: double period in printed source, p. 301",
}])


# ── Write ──────────────────────────────────────────────────────────────────────

for num, psalm in psalms.items():
    path = psalms_dir / f"{num}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(psalm, f, ensure_ascii=False, indent=2)

# ── Report ─────────────────────────────────────────────────────────────────────

if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  {w}")
else:
    print("All corrections applied — no warnings.")

print()
print("Section A: 12 missing-text fixes (11 + Ps 96 v10)")
print("Section B: no-op — section headers already on own lines in YAML")
print("Section C: 5 source-error corrections with source_corrections metadata")

checks = [
    ("Ps 2 v12 no duplicate",     psalms[2]["text"].count("12 ") == 1 and "12  " not in psalms[2]["text"]),
    ("Ps 2 v12 present",          any(l.startswith("12 ") for l in psalms[2]["text"].split("\n"))),
    ("Ps 27 v6 line restored",    "Therefore I will offer in your dwelling" in psalms[27]["text"]),
    ("Ps 41 v1 second half",      "The Lord will deliver them in the time of trouble" in psalms[41]["text"]),
    ("Ps 45 v7 line restored",    "Therefore God, your God, has anointed you" in psalms[45]["text"]),
    ("Ps 53 v6 line restored",    "When God restores the fortune of this people" in psalms[53]["text"]),
    ("Ps 68 v35 line restored",   "The God of Israel gives strength and power to this people" in psalms[68]["text"]),
    ("Ps 69 v4 second half",      "Must I then give back what I never stole" in psalms[69]["text"]),
    ("Ps 81 v13 second half",     "That Israel would walk in my ways" in psalms[81]["text"]),
    ("Ps 93 v1 line restored",    "The Lord has made the whole world so sure" in psalms[93]["text"]),
    ("Ps 96 v10 line present",    "world so firm that it cannot be moved" in psalms[96]["text"]),
    ("Ps 114 v1 Hallelujah split","1 Hallelujah!\n When Israel came out of Egypt" in psalms[114]["text"]),
    ("Ps 146 v8 line restored",   "The Lord lifts up those who are bowed down" in psalms[146]["text"]),
    ("Ps 35 v25 'not' restored",  "Do not let them say" in psalms[35]["text"]),
    ("Ps 51 v1 offences",         "offences" in psalms[51]["text"] and "offenses" not in psalms[51]["text"]),
    ("Ps 61 v8 fulfil",           "fulfil" in psalms[61]["text"] and "fulfill" not in psalms[61]["text"]),
    ("Ps 64 v9 recognise",        "recognise" in psalms[64]["text"] and "recognize" not in psalms[64]["text"]),
    ("Ps 78 v72 single period",   "God's hands.." not in psalms[78]["text"]),
    ("Ps 119 Waw header",         "Waw  " in psalms[119]["text"] and " Waw" not in psalms[119]["text"]),
    ("Ps 119 Tsadhe header",      "Tsadhe  " in psalms[119]["text"] and "Sadhe  " not in psalms[119]["text"]),
    ("Ps 119 Taw header",         "Taw  " in psalms[119]["text"] and " Taw" not in psalms[119]["text"]),
    ("source_corrections on 5",   all("source_corrections" in psalms[n] for n in [35, 51, 61, 64, 78])),
    ("book field on all 150",     all("book" in psalms[n] for n in psalms)),
    ("no curly quotes remain",    not any(c in psalms[n]["text"] for n in psalms for c in "\u201c\u201d\u2018\u2019")),
]
print()
all_ok = True
for label, ok in checks:
    if not ok:
        all_ok = False
    print(f"  [{'OK' if ok else 'FAIL'}] {label}")
if all_ok:
    print("\nAll checks passed.")
else:
    print("\nSome checks FAILED — see above.")
