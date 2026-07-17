#!/usr/bin/env python3
"""
Download KJV with Apocrypha (1769) from getbible.net and convert to
the per-book JSON format used by LocalBible.

Output format:  { "chapter": { "verse": "text" } }
Output dir:     ~/.local/share/pwc_office/translations/kjv/

Usage:
    python3 boneyard/download_kjv.py [--out DIR]
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request

API_BASE = "https://api.getbible.net/v2/kjva"

# getbible stores data per-chapter inside {repo}/kjva/{book_num}/ subdirs.
# Fetching assembled per-book JSON from api.getbible.net is simpler and is
# the intended use of that public API — 74 requests, done once, ~15 seconds.

# getbible book number -> output filename
BOOKS = {
    # Old Testament
    1:  "Genesis",
    2:  "Exodus",
    3:  "Leviticus",
    4:  "Numbers",
    5:  "Deuteronomy",
    6:  "Joshua",
    7:  "Judges",
    8:  "Ruth",
    9:  "1 Samuel",
    10: "2 Samuel",
    11: "1 Kings",
    12: "2 Kings",
    13: "1 Chronicles",
    14: "2 Chronicles",
    15: "Ezra",
    16: "Nehemiah",
    17: "Esther",
    18: "Job",
    19: "Psalm",           # getbible says "Psalms"; we normalise to "Psalm"
    20: "Proverbs",
    21: "Ecclesiastes",
    22: "Song Of Songs",   # getbible says "Song of Solomon"; we normalise
    23: "Isaiah",
    24: "Jeremiah",
    25: "Lamentations",
    26: "Ezekiel",
    27: "Daniel",
    28: "Hosea",
    29: "Joel",
    30: "Amos",
    31: "Obadiah",
    32: "Jonah",
    33: "Micah",
    34: "Nahum",
    35: "Habakkuk",
    36: "Zephaniah",
    37: "Haggai",
    38: "Zechariah",
    39: "Malachi",
    # New Testament
    40: "Matthew",
    41: "Mark",
    42: "Luke",
    43: "John",
    44: "Acts",
    45: "Romans",
    46: "1 Corinthians",
    47: "2 Corinthians",
    48: "Galatians",
    49: "Ephesians",
    50: "Philippians",
    51: "Colossians",
    52: "1 Thessalonians",
    53: "2 Thessalonians",
    54: "1 Timothy",
    55: "2 Timothy",
    56: "Titus",
    57: "Philemon",
    58: "Hebrews",
    59: "James",
    60: "1 Peter",
    61: "2 Peter",
    62: "1 John",
    63: "2 John",
    64: "3 John",
    65: "Jude",
    66: "Revelation",
    # Apocrypha / Deuterocanon (getbible kjva book numbers)
    68: "2 Esdras",
    69: "Tobit",
    70: "Judith",
    73: "Wisdom Of Solomon",  # getbible says "Wisdom"; we normalise
    74: "Sirach",             # getbible may say "Ecclesiasticus"; we normalise
    75: "Baruch",
    80: "1 Maccabees",
    81: "2 Maccabees",
}


def fetch(book_num: int) -> dict:
    url = f"{API_BASE}/{book_num}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def strip_strongs(text: str) -> str:
    """Remove Strong's number markup if present, e.g. <S>H1234</S>."""
    return re.sub(r"<[^>]+>", "", text).strip()


def convert(data: dict) -> dict:
    """Convert getbible chapter-array format to { "ch": { "v": "text" } }."""
    out = {}
    for ch_obj in data.get("chapters", []):
        ch = str(ch_obj["chapter"])
        verses = {}
        for v_obj in ch_obj.get("verses", []):
            v = str(v_obj["verse"])
            verses[v] = strip_strongs(v_obj["text"])
        if verses:
            out[ch] = verses
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=os.path.join(
            os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
            "pwc_office", "translations", "kjv",
        ),
    )
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print(f"Writing to {args.out}")

    for num, filename in sorted(BOOKS.items()):
        dest = os.path.join(args.out, filename + ".json")
        if os.path.exists(dest):
            print(f"  skip  {filename} (already exists)")
            continue
        print(f"  fetch {filename} (book {num}) ...", end=" ", flush=True)
        try:
            data = fetch(num)
            converted = convert(data)
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(converted, f, ensure_ascii=False)
            print("ok")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(0.2)  # be polite to the API

    print("Done.")


if __name__ == "__main__":
    main()
