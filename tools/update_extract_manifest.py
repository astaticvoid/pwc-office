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
    "tools/corrections_lib.py",
    "tools/extract_lib.py",
    "data/corrections.json",
    # The lectionary CSV is committed, and is the sole input to detect_bounds()
    # — so data/season_bounds.json can be stale with respect to it while its own
    # hash still matches. Same argument as the tools above: a matching output
    # hash proves nobody hand-edited the output, not that it came from the input
    # sitting beside it. The source PDFs are legitimately absent from this list;
    # they are gitignored and obtained separately, so there is no committed
    # state for them to drift from.
    "sources/bas_short_*.csv",
)


# Every file the pipeline publishes under data/ that the app or the CLI reads.
# `data/lectionary` is hashed separately as a composite of its monthly files.
#
# A published file missing from here is invisible to check_data_integrity.py:
# with no recorded hash there is nothing to compare, so it can be hand-edited or
# left stale and the integrity check still passes. season_bounds.json was absent
# for exactly that reason — written by convert_lectionary.py, fetched by
# web/app.js and cli/office.js, required by check_dist.py, and unguarded.
#
# Deliberately absent, all for the same reason — git already guards them, so a
# hand-edit shows in `git status`, which sets the release's `-dirty` suffix and
# makes `make promote` refuse it (#53):
#   data/corrections.json   committed input, also hashed in EXTRACTION_SOURCES
#   data/paragraphs.json    committed static asset, not pipeline output
#   data/translations/kjv/  74 committed public-domain files
# data/translations/nrsvue/ must stay out for a stronger reason: it is absent in
# most checkouts, and a listed file that does not exist is a hard failure below.
PUBLISHED_FILES = (
    "data/offices.json",
    "data/collects.json",
    "data/psalter.json",
    "data/season_bounds.json",
    "data/fats/saints.json",
)


def source_hashes(root: Path) -> dict[str, str | None]:
    """SHA-256 of every source that determines extraction output.

    Entries containing `*` are globbed and recorded under their concrete paths,
    so the lectionary CSV is hashed under the year it is actually for.

    A named source that does not exist is recorded as `null`, not omitted.
    Omitting it means the key simply disappears from the committed manifest on
    the next run, taking with it any record that the input was ever expected —
    so `rm data/corrections.json && make extract && make test` was green while
    republishing every office with the corrections silently dropped, including
    the Synod errata. Recording the absence keeps the manifest a statement of
    the full expected input set rather than of whatever happened to be present,
    and check_data_integrity.py treats a null as drift, so that sequence now
    fails instead of deploying. Retiring an input means removing it from
    EXTRACTION_SOURCES — a reviewable edit, not a file vanishing from a worktree.
    """
    out: dict[str, str | None] = {}
    for rel in EXTRACTION_SOURCES:
        if "*" in rel:
            # A pattern names a set, not a file, so there is no absence to
            # record — zero matches is indistinguishable from a year not yet
            # added. convert_lectionary.py fails loudly on a missing CSV.
            for path in sorted(root.glob(rel)):
                out[str(path.relative_to(root))] = file_sha256(path)
            continue
        path = root / rel
        out[rel] = file_sha256(path) if path.exists() else None
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
    tracked_files = {rel: ROOT / rel for rel in PUBLISHED_FILES}
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
