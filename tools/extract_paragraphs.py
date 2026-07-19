#!/usr/bin/env python3
"""
Extract paragraph boundaries from WEB USFX XML → data/paragraphs.json

The World English Bible (WEB) is public domain and includes Apocrypha.
Its USFX XML uses <p> elements to group verses into paragraphs.
This script extracts the starting verse of each paragraph per chapter.

Output format: {"Book Name": {"chapter": [first_verse_of_each_paragraph]}}
"""

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

USFX_PATH = Path("/tmp/eng-web_usfx.xml")
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "paragraphs.json"

# WEB book name → our data file name (from ABBREV_TO_FILE values in render.js)
BOOK_MAP = {
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numbers", "Deuteronomy": "Deuteronomy", "Joshua": "Joshua",
    "Judges": "Judges", "Ruth": "Ruth", "1 Samuel": "1 Samuel",
    "2 Samuel": "2 Samuel", "1 Kings": "1 Kings", "2 Kings": "2 Kings",
    "1 Chronicles": "1 Chronicles", "2 Chronicles": "2 Chronicles",
    "Ezra": "Ezra", "Nehemiah": "Nehemiah", "Esther": "Esther",
    "Job": "Job", "Psalms": "Psalm", "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes", "Song of Solomon": "Song Of Songs",
    "Isaiah": "Isaiah", "Jeremiah": "Jeremiah", "Lamentations": "Lamentations",
    "Ezekiel": "Ezekiel", "Daniel": "Daniel", "Hosea": "Hosea",
    "Joel": "Joel", "Amos": "Amos", "Obadiah": "Obadiah", "Jonah": "Jonah",
    "Micah": "Micah", "Nahum": "Nahum", "Habakkuk": "Habakkuk",
    "Zephaniah": "Zephaniah", "Haggai": "Haggai", "Zechariah": "Zechariah",
    "Malachi": "Malachi",
    "Matthew": "Matthew", "Mark": "Mark", "Luke": "Luke", "John": "John",
    "Acts": "Acts", "Romans": "Romans", "1 Corinthians": "1 Corinthians",
    "2 Corinthians": "2 Corinthians", "Galatians": "Galatians",
    "Ephesians": "Ephesians", "Philippians": "Philippians",
    "Colossians": "Colossians",
    "1 Thessalonians": "1 Thessalonians", "2 Thessalonians": "2 Thessalonians",
    "1 Timothy": "1 Timothy", "2 Timothy": "2 Timothy", "Titus": "Titus",
    "Philemon": "Philemon", "Hebrews": "Hebrews", "James": "James",
    "1 Peter": "1 Peter", "2 Peter": "2 Peter", "1 John": "1 John",
    "2 John": "2 John", "3 John": "3 John", "Jude": "Jude",
    "Revelation": "Revelation",
    # Apocrypha
    "Tobit": "Tobit", "Judith": "Judith",
    "Esther (Greek)": None,  # we don't have this
    "Wisdom": "Wisdom Of Solomon", "Wisdom of Solomon": "Wisdom Of Solomon",
    "Sirach": "Sirach",
    "Baruch": "Baruch", "Letter of Jeremiah": None,
    "Prayer of Azariah": None, "Susanna": None, "Bel and the Dragon": None,
    "1 Maccabees": "1 Maccabees", "2 Maccabees": "2 Maccabees",
    "1 Esdras": None, "Prayer of Manasseh": None,
    "Psalm 151": None, "3 Maccabees": None,
    "2 Esdras": "2 Esdras", "4 Maccabees": None,
}


def extract_paragraphs(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    result = {}
    skipped = []

    for book in root:
        h = book.find("h")
        if h is None or not h.text:
            continue
        web_name = h.text.strip()
        our_name = BOOK_MAP.get(web_name)
        if our_name is None:
            skipped.append(web_name)
            continue

        chapters = {}
        current_chapter = None

        for elem in book:
            if elem.tag == "c":
                current_chapter = elem.get("id", "0")
                continue
            if elem.tag == "p" and current_chapter is not None:
                verses = elem.findall("v")
                if not verses:
                    continue
                first_verse = int(verses[0].get("id", "0"))
                chapters.setdefault(current_chapter, []).append(first_verse)

        if chapters:
            result[our_name] = chapters

    return result, skipped


def main():
    if not USFX_PATH.exists():
        print(f"USFX not found at {USFX_PATH}. Download it first:")
        print("  curl -sLo /tmp/eng-web_usfx.zip https://eBible.org/Scriptures/eng-web_usfx.zip")
        print("  unzip -o /tmp/eng-web_usfx.zip -d /tmp/")
        sys.exit(1)

    result, skipped = extract_paragraphs(USFX_PATH)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    total_books = len(result)
    total_breaks = sum(
        sum(len(v) for v in chs.values()) for chs in result.values()
    )
    print(f"Extracted {total_breaks} paragraph breaks across {total_books} books → {OUTPUT_PATH}")
    if skipped:
        print(f"Skipped {len(skipped)} books not in our data: {', '.join(skipped)}")


if __name__ == "__main__":
    main()
