#!/usr/bin/env python3
"""
Convert sources/bible.json (NRSVUE) → data/bible/<BookName>.json

One file per book so the Go runtime only loads the books needed for a given day.

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
import sys
from pathlib import Path

root = Path(__file__).parent.parent

# Superscript digits the source uses as in-text verse numbers.
_SUPERSCRIPTS = '⁰¹²³⁴⁵⁶⁷⁸⁹'
_STRIP_RE = re.compile(rf'^[{re.escape(_SUPERSCRIPTS)}]+\s*')

def strip_verse_num(text: str) -> str:
    return _STRIP_RE.sub('', text).rstrip()


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
            clean: dict[str, dict] = {}
            for ch_str, verses in chapters.items():
                clean[ch_str] = {}
                for v_str, text in verses.items():
                    clean[ch_str][v_str] = strip_verse_num(text)
                    total_verses += 1
            dst = dst_dir / f"{book_name}.json"
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, separators=(',', ':'))
            books_written += 1

    total_kb = sum(f.stat().st_size for f in dst_dir.glob("*.json")) // 1024
    print(f"Wrote {books_written} books, {total_verses} verses to {dst_dir}/ ({total_kb} KB total)")


if __name__ == "__main__":
    main()
