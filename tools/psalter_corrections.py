"""
psalter_corrections.py — verified text corrections for the PWC Liturgical Psalter.

Called by extract_psalter.py as the final pass before writing output.
Not a standalone script.

Sections:
  A — Missing verse text (dropped lines / page-break artefacts)
  B — Source errors with source_corrections metadata
"""


# ── Helpers ───────────────────────────────────────────────────────────────────
# All operate on psalms[num]["text"] in-place and return warnings.

def _get(psalms: dict, num: int) -> str:
    return psalms[num]["text"]

def _set(psalms: dict, num: int, text: str) -> None:
    psalms[num]["text"] = text

def _insert_before(psalms: dict, warnings: list, num: int, marker: str, new_line: str) -> None:
    text = _get(psalms, num)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            if i > 0 and lines[i - 1] == new_line:
                return
            lines.insert(i, new_line)
            _set(psalms, num, "\n".join(lines))
            return
    warnings.append(f"Psalm {num}: insert_before marker not found: {marker!r}")

def _insert_after(psalms: dict, warnings: list, num: int, marker: str, new_line: str) -> None:
    text = _get(psalms, num)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            if i + 1 < len(lines) and lines[i + 1] == new_line:
                return
            lines.insert(i + 1, new_line)
            _set(psalms, num, "\n".join(lines))
            return
    warnings.append(f"Psalm {num}: insert_after marker not found: {marker!r}")

def _replace(psalms: dict, warnings: list, num: int, old: str, new: str) -> None:
    text = _get(psalms, num)
    if old not in text:
        warnings.append(f"Psalm {num}: text not found: {old!r}")
        return
    _set(psalms, num, text.replace(old, new, 1))

def _add_source_corrections(psalms: dict, num: int, corrections: list[dict]) -> None:
    p = psalms[num]
    psalms[num] = {
        "number": p["number"],
        "book":   p["book"],
        "title":  p["title"],
        "source_corrections": corrections,
        "text":   p["text"],
    }


# ── Apply ─────────────────────────────────────────────────────────────────────

def apply(psalms: dict[int, dict]) -> list[str]:
    """Apply all corrections to psalms (keyed by int) in-place.

    Returns a list of warning strings for fixes that couldn't be applied
    (e.g. marker already fixed upstream in the extractor).
    """
    w: list[str] = []

    # ── Section A — Missing verse text ────────────────────────────────────────

    # Psalm 2 v12 — page-break artefact: continuation lines displaced/duplicated.
    # Normalise everything from v11's final line to end of psalm.
    _PS2_V11_TAIL = " and bow with trembling before the presence of the Lord;"
    _PS2_V12_BLOCK = (
        "12 lest God be angry and you perish; *\n"
        " for the divine wrath is quickly kindled.\n"
        " Happy are they all *\n"
        " who take refuge in God!"
    )
    if _PS2_V11_TAIL + "\n" + _PS2_V12_BLOCK not in _get(psalms, 2):
        text = _get(psalms, 2)
        cut = text.rfind(_PS2_V11_TAIL)
        if cut < 0:
            w.append("Psalm 2: v11 tail not found")
        else:
            _set(psalms, 2, text[:cut + len(_PS2_V11_TAIL)] + "\n" + _PS2_V12_BLOCK)

    _insert_before(psalms, w, 27, "an oblation with sounds of great gladness; *",
                   " Therefore I will offer in your dwelling")
    _insert_after(psalms, w, 41, "Happy are they who consider the poor and needy! *",
                  " The Lord will deliver them in the time of trouble.")
    _insert_before(psalms, w, 45, "with the oil of gladness above your companions.",
                   " Therefore God, your God, has anointed you")
    _insert_before(psalms, w, 53, "Jacob will rejoice and Israel be glad.",
                   " When God restores the fortune of this people,")
    _insert_before(psalms, w, 68, "Blessed be God!",
                   " The God of Israel gives strength and power to this people!")
    _insert_after(psalms, w, 69, "my lying foes who would destroy me are mighty. *",
                  " Must I then give back what I never stole?")
    _insert_after(psalms, w, 81, "Oh, that my people would listen to me! *",
                  " That Israel would walk in my ways!")
    _insert_before(psalms, w, 93, "that it cannot be moved;",
                   " The Lord has made the whole world so sure")
    _insert_before(psalms, w, 146, "and loves the righteous.",
                   " The Lord lifts up those who are bowed down")

    # Psalm 119 — source uses non-standard "Sadhe" for the 18th section
    _replace(psalms, w, 119, "Sadhe ", "Tsadhe ")

    # ── Section B — Source errors with source_corrections metadata ────────────

    # Ps 35 v25 — missing "not" reverses meaning
    _replace(psalms, w, 35,
             "Do let them say in their hearts, *",
             "Do not let them say in their hearts, *")
    _add_source_corrections(psalms, 35, [{
        "verse": 25,
        "original":  "Do let them say in their hearts, *",
        "corrected": "Do not let them say in their hearts, *",
        "reason": (
            "Missing 'not' in source — meaning reversed. "
            "All parallel sources (BCP 1979, NRSV, ELW) read 'Do not let them say.'"
        ),
    }])

    # Ps 51 v1 — American spelling
    _replace(psalms, w, 51, "blot out my offenses.", "blot out my offences.")
    _add_source_corrections(psalms, 51, [{
        "verse": 1,
        "original":  "blot out my offenses.",
        "corrected": "blot out my offences.",
        "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
    }])

    # Ps 61 v8 — American spelling
    _replace(psalms, w, 61,
             "and day by day I will fulfill my vows.",
             "and day by day I will fulfil my vows.")
    _add_source_corrections(psalms, 61, [{
        "verse": 8,
        "original":  "and day by day I will fulfill my vows.",
        "corrected": "and day by day I will fulfil my vows.",
        "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
    }])

    # Ps 64 v9 — American spelling
    _replace(psalms, w, 64,
             "they will recognize your works.",
             "they will recognise your works.")
    _add_source_corrections(psalms, 64, [{
        "verse": 9,
        "original":  "they will recognize your works.",
        "corrected": "they will recognise your works.",
        "reason": "American spelling in source; psalter uses British/Canadian orthography throughout",
    }])

    # Ps 78 v72 — double period (straight apostrophe already normalised by extractor)
    _replace(psalms, w, 78,
             "skillfulness of God's hands..",
             "skillfulness of God's hands.")
    _add_source_corrections(psalms, 78, [{
        "verse": 72,
        "original":  "and guided them with the skillfulness of God's hands..",
        "corrected": "and guided them with the skillfulness of God's hands.",
        "reason": "Typographic error: double period in printed source, p. 301",
    }])

    return w


# ── Spot checks ───────────────────────────────────────────────────────────────

def spot_checks(psalms: dict[int, dict]) -> list[tuple[str, bool]]:
    """Return (label, ok) pairs for post-fix verification."""
    def text(n: int) -> str:
        return psalms[n]["text"]

    return [
        ("Ps 2 v12 no duplicate",    text(2).count("12 ") == 1 and "12  " not in text(2)),
        ("Ps 2 v12 present",         any(l.startswith("12 ") for l in text(2).split("\n"))),
        ("Ps 27 v6 restored",        "Therefore I will offer in your dwelling" in text(27)),
        ("Ps 41 v1 second half",     "The Lord will deliver them in the time of trouble" in text(41)),
        ("Ps 45 v7 restored",        "Therefore God, your God, has anointed you" in text(45)),
        ("Ps 53 v6 restored",        "When God restores the fortune of this people" in text(53)),
        ("Ps 68 v35 restored",       "The God of Israel gives strength and power to this people" in text(68)),
        ("Ps 69 v4 second half",     "Must I then give back what I never stole" in text(69)),
        ("Ps 81 v13 second half",    "That Israel would walk in my ways" in text(81)),
        ("Ps 93 v1 restored",        "The Lord has made the whole world so sure" in text(93)),
        ("Ps 96 v10 present",        "world so firm that it cannot be moved" in text(96)),
        ("Ps 114 v1 Hallelujah",     "1 Hallelujah!\n When Israel came out of Egypt" in text(114)),
        ("Ps 146 v8 restored",       "The Lord lifts up those who are bowed down" in text(146)),
        ("Ps 35 v25 'not' restored", "Do not let them say" in text(35)),
        ("Ps 51 v1 offences",        "offences" in text(51) and "offenses" not in text(51)),
        ("Ps 61 v8 fulfil",          "fulfil" in text(61) and "fulfill" not in text(61)),
        ("Ps 64 v9 recognise",       "recognise" in text(64) and "recognize" not in text(64)),
        ("Ps 78 v72 single period",  "God's hands.." not in text(78)),
        ("Ps 119 Tsadhe header",     "Tsadhe " in text(119) and "Sadhe " not in text(119)),
        ("source_corrections × 5",  all("source_corrections" in psalms[n] for n in [35, 51, 61, 64, 78])),
        ("book field on all 150",    all("book" in psalms[n] for n in psalms)),
        ("no curly quotes",          not any(c in text(n) for n in psalms for c in "“”‘’")),
    ]
