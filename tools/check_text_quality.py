#!/usr/bin/env python3
"""
check_text_quality.py — scan extracted data files for PDF extraction artifacts.

Checks for:
  - Missing spaces (merged words from pdftotext/pdfplumber font-encoding issues)
  - Duplicate adjacent words
  - Suspiciously long merged tokens
  - Hanging hyphens at line breaks
  - Column wraps in prose fields (collect texts, seasonal_collects leaders):
    a non-final line ending mid-clause is a suspected PDF column wrap (BUG-29
    regression guard; should be zero after Batch 18 Fix G)

Exits 0 always (warnings only).  Pass --strict to exit 1 on any finding.

Usage:
    python3 tools/check_text_quality.py [--strict]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── False-positive exclusions ────────────────────────────────────────────────

# All-caps tokens are rubric labels (MINISTER, PEOPLE, etc.) — skip.
_ALL_CAPS = re.compile(r'^[A-Z]{2,}$')

# Metadata field names that contain enum/identifier values, not liturgical prose.
_SKIP_FIELDS = {"season", "section", "form", "type", "label", "key", "op"}

# Allowed hyphenated liturgical words (not hanging hyphens).
_HYPHEN_ALLOWLIST = {
    "ever-living", "ever-blessed", "well-beloved", "long-suffering",
    "ever-present", "all-knowing", "all-powerful", "ever-lasting",
    "well-pleasing",
}

# Scripture citation pattern — digits and colons are normal in citations.
_CITATION = re.compile(r'\b\d+:\d+')

# Legitimate camelCase identifiers that appear in prose (not garbling).
# "OrdinaryTime" is a season enum used as display text in some fields.
_CAMEL_ALLOWLIST = re.compile(r'\b(?:OrdinaryTime)\b')

# "Mc/Mac" prefixes: McDonald, MacPherson, etc. are proper surname patterns.
_NAME_PREFIX = re.compile(r'\b(?:Mc|Mac)[A-Z]')

# ── Checks ───────────────────────────────────────────────────────────────────

_MISSING_SPACE = re.compile(r'[a-z][A-Z]')
_DUPLICATE_WORD = re.compile(r'\b(\w{3,})\s+\1\b', re.IGNORECASE)
_LONG_TOKEN = re.compile(r'\b[a-z]{30,}\b')
_HANGING_HYPHEN = re.compile(r'\w-\s*\n')


def _check_string(text: str, location: str, findings: list) -> None:
    if not isinstance(text, str) or not text:
        return

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip all-caps rubric tokens.
        if _ALL_CAPS.match(stripped):
            continue
        # Skip scripture citation lines.
        if _CITATION.search(stripped):
            continue
        # Skip lines that are entirely known-allowlisted camelCase identifiers.
        if _CAMEL_ALLOWLIST.fullmatch(stripped):
            continue

        # Missing space (merged words): [a-z][A-Z] mid-word.
        for m in _MISSING_SPACE.finditer(stripped):
            start = max(0, m.start() - 4)
            snippet = stripped[start: m.start() + 10]
            # Skip Mc/Mac name prefixes (McDonald, MacPherson, etc.)
            if _NAME_PREFIX.search(stripped[max(0, m.start()-2): m.end()+2]):
                continue
            # Skip allowlisted camelCase identifiers at the match site.
            if _CAMEL_ALLOWLIST.search(stripped[max(0, m.start()-10): m.end()+10]):
                continue
            findings.append((location, "missing_space", f"near {snippet!r}"))

    # Duplicate adjacent words (across the full text block).
    for m in _DUPLICATE_WORD.finditer(text):
        findings.append((location, "duplicate_word", f"{m.group()!r}"))

    # Suspiciously long merged token.
    for m in _LONG_TOKEN.finditer(text):
        findings.append((location, "long_token", f"{m.group()!r}"))

    # Hanging hyphen before line break (not in the allowlist).
    for m in _HANGING_HYPHEN.finditer(text):
        token = m.group().rstrip()
        if token not in _HYPHEN_ALLOWLIST:
            findings.append((location, "hanging_hyphen", f"{token!r}"))


def _walk_json(obj, path: str, findings: list, field_name: str = "") -> None:
    """Recursively walk JSON object, checking all string leaf values."""
    if isinstance(obj, str):
        if field_name not in _SKIP_FIELDS:
            _check_string(obj, path, findings)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _walk_json(v, f"{path}[{k!r}]", findings, field_name=k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_json(v, f"{path}[{i}]", findings, field_name=field_name)


def check_file(rel_path: str, findings: list) -> None:
    path = ROOT / rel_path
    if not path.exists():
        return
    try:
        data = json.loads(path.read_bytes())
    except json.JSONDecodeError as e:
        print(f"ERROR: cannot parse {rel_path}: {e}", file=sys.stderr)
        return
    _walk_json(data, rel_path, findings)


# ── Column-wrap detector (BUG-29 regression guard) ────────────────────────────

# Collect prayers are single prose sentences (Batch 18 Fix G reflowed them). A
# non-final line that ends WITHOUT terminal punctuation is a suspected PDF
# column wrap ("…and who\nlives and reigns…"). These chars legitimately end a
# line: , ; : . ! ? — ’ ” )
_TERMINAL_PUNCT = tuple(",;:.!?—’”)")


def _check_prose_wraps(text: str, location: str, findings: list) -> None:
    if not isinstance(text, str) or "\n" not in text:
        return
    lines = [ln.strip() for ln in text.split("\n")]
    for ln in lines[:-1]:              # every line except the last
        if ln and not ln.endswith(_TERMINAL_PUNCT):
            snippet = ln[-40:] if len(ln) > 40 else ln
            findings.append((location, "column_wrap", f"line ends mid-clause: …{snippet!r}"))


def _seasonal_collect_leaders(segs, path, out):
    """Collect (location, text) for leader segments inside seasonal_collects,
    recursing shared refs and alternatives groups."""
    if isinstance(segs, dict) and segs.get("type") == "shared":
        return  # seasonal_collects is never a whole-field shared ref
    if not isinstance(segs, list):
        return
    for i, seg in enumerate(segs):
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "alternatives":
            for j, group in enumerate(seg.get("groups", [])):
                _seasonal_collect_leaders(group.get("segments", []), f"{path}[{i}].groups[{j}]", out)
        elif seg.get("type") == "leader" and seg.get("text"):
            out.append((f"{path}[{i}]", seg["text"]))


def check_prose_fields(findings: list) -> None:
    """Column-wrap scan of prose-expected fields only: collect texts and
    seasonal_collects leader segments. Applied narrowly — psalms, litanies and
    canticles legitimately break lines without terminal punctuation."""
    collects_path = ROOT / "data" / "collects.json"
    if collects_path.exists():
        collects = json.loads(collects_path.read_bytes())
        for page, entry in collects.items():
            if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                _check_prose_wraps(entry["text"], f"collects.json[{page!r}].text", findings)

    offices_path = ROOT / "data" / "offices.json"
    if offices_path.exists():
        offices = json.loads(offices_path.read_bytes())
        for office_key, form in offices.items():
            if office_key.startswith("_") or not isinstance(form, dict):
                continue
            sc = form.get("seasonal_collects")
            if sc is None:
                continue
            leaders: list = []
            _seasonal_collect_leaders(sc, f"offices.json[{office_key!r}].seasonal_collects", leaders)
            for loc, text in leaders:
                _check_prose_wraps(text, loc, findings)


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scan extracted JSON for PDF artifacts.")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any finding.")
    args = ap.parse_args()

    target_files = [
        "data/offices.json",
        "data/collects.json",
        "data/psalter.json",
        "data/fats/saints.json",
    ]

    findings: list[tuple[str, str, str]] = []
    for rel in target_files:
        check_file(rel, findings)
    check_prose_fields(findings)

    if findings:
        for loc, kind, detail in findings:
            print(f"{loc}: {kind} {detail}")
        print(f"\n{len(findings)} finding(s).")
        if args.strict:
            sys.exit(1)
    else:
        print("No text quality issues found.")


if __name__ == "__main__":
    main()
