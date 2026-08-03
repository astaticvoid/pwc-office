#!/usr/bin/env python3
"""
update_extract_manifest.py — record hashes and entry counts of extracted data files.

Run at the end of `make extract` (after apply_patches.py) so the manifest
reflects the final patched state. Writes tools/extract_manifest.json.

`make check-integrity` compares current file hashes against this manifest to
detect files edited outside the extraction pipeline.
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
MANIFEST_PATH = ROOT / "tools" / "extract_manifest.json"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def lectionary_composite_hash(lect_dir: Path) -> tuple[str, int]:
    """Hash all monthly JSON files as a single composite; return (hash, month_count)."""
    files = sorted(f for f in lect_dir.iterdir() if f.suffix == ".json")
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest(), len(files)


def count_entries(path: Path) -> int:
    """Return top-level entry count for a JSON file (dict keys or array length)."""
    data = json.loads(path.read_bytes())
    if isinstance(data, dict):
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


# Sources that determine extraction output. Their hashes go in the manifest so
# check_data_integrity.py can tell that an extractor changed without the pipeline
# being re-run — data matching the manifest proves only that nobody edited it by
# hand, not that it came from the code sitting beside it (#51).
#
# corrections.json is here for the same reason: it is an input, and editing it
# changes output exactly as editing source does.
EXTRACTION_SOURCES = (
    "tools/extract_offices.py",
    "tools/extract_office_styles.py",
    "tools/normalize_offices.py",
    "tools/extract_psalter.py",
    "tools/extract_collects.py",
    "tools/extract_fats.py",
    "tools/convert_lectionary.py",
    "tools/apply_corrections.py",
    "tools/extract_lib.py",
    "data/corrections.json",
)


def source_hashes(root: Path) -> dict[str, str]:
    """SHA-256 of every source that determines extraction output."""
    out = {}
    for rel in EXTRACTION_SOURCES:
        path = root / rel
        if path.exists():
            out[rel] = file_sha256(path)
    return out


def tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    try:
        import fitz
        versions["fitz"] = fitz.version
    except ImportError:
        versions["fitz"] = "not found"
    return versions


def main():
    tracked_files = {
        "data/offices.json": ROOT / "data" / "offices.json",
        "data/collects.json": ROOT / "data" / "collects.json",
        "data/psalter.json": ROOT / "data" / "psalter.json",
        "data/fats/saints.json": ROOT / "data" / "fats" / "saints.json",
    }
    lect_dir = ROOT / "data" / "lectionary"

    missing = [k for k, p in tracked_files.items() if not p.exists()]
    if missing:
        print(f"ERROR: missing data files: {missing}", file=sys.stderr)
        sys.exit(1)

    files_entry: dict[str, dict] = {}
    for rel, path in tracked_files.items():
        files_entry[rel] = {
            "sha256": file_sha256(path),
            "entries": count_entries(path),
        }

    lect_hash, lect_months = lectionary_composite_hash(lect_dir)
    files_entry["data/lectionary"] = {
        "sha256": lect_hash,
        "months": lect_months,
    }

    manifest = {
        "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool_versions": tool_versions(),
        "source_hashes": source_hashes(ROOT),
        "files": files_entry,
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH}")
    for rel, info in files_entry.items():
        count_key = "months" if rel == "data/lectionary" else "entries"
        print(f"  {rel}: {info['sha256'][:12]}…  ({info[count_key]} {count_key})")


if __name__ == "__main__":
    main()
