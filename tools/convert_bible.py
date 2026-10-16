#!/usr/bin/env python3
"""
Convert sources/bible.json (NRSVUE) → data/bible/<BookName>.json

One file per book for efficient loading — only the books needed for a given day
are fetched.

Input structure:  {testament: {book_name: {ch_str: {v_str: text}}}}
Output per file:  {ch_str: {v_str: text}}

Transformation:
  - Testament grouping flattened; each book becomes its own file
  - Leading superscript verse numbers stripped from each verse text
    (¹²³⁴⁵⁶⁷⁸⁹⁰ → U+00B9/00B2/00B3/2074-2079/2070)
  - Trailing whitespace stripped from each verse

Run from repo root:
  python3 tools/convert_bible.py
"""

import json
import re
from pathlib import Path

root = Path(__file__).parent.parent

# Superscript digits the source uses as in-text verse numbers.
_SUPERSCRIPTS = '⁰¹²³⁴⁵⁶⁷⁸⁹'
_STRIP_RE = re.compile(rf'^\s*[{re.escape(_SUPERSCRIPTS)}]+(?:[,–\-][{re.escape(_SUPERSCRIPTS)}]+)*\s*')
_TRANS = str.maketrans(_SUPERSCRIPTS, '0123456789')


def strip_verse_num(text: str) -> str:
    return _STRIP_RE.sub('', text).rstrip()


def get_superscript_num(text: str) -> int | None:
    m = re.match(r'^([⁰¹²³⁴⁵⁶⁷⁸⁹]+)', text.strip())
    if m:
        return int(m.group(1).translate(_TRANS))
    return None


def normalize_book(book_name: str, chapters: dict[str, dict]) -> dict[str, dict]:
    """
    Normalize book chapters to ensure verse numbers match true versification
    rather than raw array indices, separating prefaces/prologues where needed.
    """
    clean: dict[str, dict] = {}

    if book_name == "Sirach":
        ch1_raw = chapters.get("1", {})
        if "35" in ch1_raw and "34" in ch1_raw and "\n\n" in ch1_raw["34"]:
            # Prologue lines were conflated into chapter 1
            prologue_clean = {}
            for k in range(1, 34):
                if str(k) in ch1_raw:
                    prologue_clean[str(k)] = strip_verse_num(ch1_raw[str(k)])
            v34 = ch1_raw["34"]
            parts = v34.split("\n\n", 1)
            prologue_clean["34"] = strip_verse_num(parts[0])
            clean["Prologue"] = prologue_clean

            ch1_clean = {"1": strip_verse_num(parts[1])}
            for k_int in sorted(int(k) for k in ch1_raw if k.isdigit() and int(k) >= 35):
                raw = ch1_raw.get(str(k_int))
                if not raw:
                    continue
                num = get_superscript_num(raw)
                key = str(num) if num is not None else str(k_int)
                ch1_clean[key] = strip_verse_num(raw)
            clean["1"] = ch1_clean
        else:
            if "Prologue" in chapters:
                clean["Prologue"] = {k: strip_verse_num(v) for k, v in chapters["Prologue"].items()}
            ch1_clean = {}
            for k, v in ch1_raw.items():
                num = get_superscript_num(v)
                key = str(num) if num is not None else k
                ch1_clean[key] = strip_verse_num(v)
            clean["1"] = ch1_clean

        for ch_str, verses in chapters.items():
            if ch_str in ("1", "Prologue"):
                continue
            clean[ch_str] = {}
            for k, text in verses.items():
                num = get_superscript_num(text)
                key = str(num) if num is not None else k
                clean[ch_str][key] = strip_verse_num(text)
        return clean

    if book_name == "James":
        for ch_str, verses in chapters.items():
            clean[ch_str] = {}
            if ch_str == "1" and "7" in verses and ("⁷,⁸" in verses["7"] or "7,8" in verses["7"]):
                for k, text in verses.items():
                    if k == "7":
                        t = strip_verse_num(text)
                        clean["1"]["7"] = t
                        clean["1"]["8"] = t
                    elif k == "8" and ("⁷,⁸" in text or "7,8" in text):
                        continue
                    else:
                        num = get_superscript_num(text)
                        key = str(num) if num is not None else k
                        clean["1"][key] = strip_verse_num(text)
            else:
                for k, text in verses.items():
                    num = get_superscript_num(text)
                    key = str(num) if num is not None else k
                    clean[ch_str][key] = strip_verse_num(text)
        return clean

    # Standard books
    for ch_str, verses in chapters.items():
        clean[ch_str] = {}
        for v_str, text in verses.items():
            clean[ch_str][v_str] = strip_verse_num(text)
    return clean


def main():
    src = root / "sources" / "bible.json"
    dst_dir = root / "data" / "translations" / "nrsvue"
    dst_dir.mkdir(parents=True, exist_ok=True)

    with open(src, encoding="utf-8") as f:
        data = json.load(f)

    total_verses = 0
    books_written = 0

    for testament, books in data.items():
        for book_name, chapters in books.items():
            clean = normalize_book(book_name, chapters)
            for ch_dict in clean.values():
                total_verses += len(ch_dict)
            dst = dst_dir / f"{book_name}.json"
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, separators=(',', ':'))
            books_written += 1

    total_kb = sum(f.stat().st_size for f in dst_dir.glob("*.json")) // 1024
    print(f"Wrote {books_written} books, {total_verses} verses to {dst_dir}/ ({total_kb} KB total)")


if __name__ == "__main__":
    main()
