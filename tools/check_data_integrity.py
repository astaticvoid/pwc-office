#!/usr/bin/env python3
"""
check_data_integrity.py — compare current data/ hashes against extract_manifest.json.

Exits 0 if all tracked files match the manifest.
Exits 1 if any file diverges, with a clear remediation message.

Wired into `make deploy` as a gate: deploy fails if data drift is detected,
preventing accidentally deploying monkey-patched data files.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
MANIFEST_PATH = ROOT / "tools" / "extract_manifest.json"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def lectionary_composite_hash(lect_dir: Path) -> str:
    files = sorted(f for f in lect_dir.iterdir() if f.suffix == ".json")
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def check_tool_versions(manifest: dict) -> None:
    expected_versions = manifest.get("tool_versions", {})
    if not expected_versions:
        return

    try:
        import fitz
        fitz_ver = fitz.version
        fitz_expected = expected_versions.get("fitz")
        if fitz_expected and fitz_expected != "not found":
            if fitz_ver == fitz_expected:
                print(f"VERSION OK   fitz {fitz_ver} (matches manifest)")
            else:
                print(f"VERSION WARN fitz {fitz_ver} (manifest recorded {fitz_expected})")
        elif fitz_expected == "not found":
            print(f"VERSION WARN fitz {fitz_ver} now available (manifest recorded 'not found')")
        else:
            print(f"VERSION OK   fitz {fitz_ver}")
    except ImportError:
        fitz_expected = expected_versions.get("fitz")
        if fitz_expected and fitz_expected != "not found":
            print(f"VERSION WARN fitz not found (manifest recorded {fitz_expected})")

    pdftotext_expected = expected_versions.get("pdftotext")
    if pdftotext_expected:
        try:
            result = subprocess.run(
                ["pdftotext", "-v"], capture_output=True, text=True
            )
            actual = (result.stdout + result.stderr).splitlines()[0].strip()
        except (FileNotFoundError, OSError):
            print("VERSION NOTE pdftotext not found (optional; manifest recorded " 
                  + pdftotext_expected + ")")
            return
        if actual == pdftotext_expected:
            print(f"VERSION OK   {actual} (matches manifest)")
        else:
            print(f"VERSION WARN {actual} (manifest recorded {pdftotext_expected})")
            print(
                "             → pdftotext version changed. Run make extract then\n"
                "               make check-text to catch any new garbled-text regressions\n"
                "               before deploying."
            )


def main():
    if not MANIFEST_PATH.exists():
        print(
            "ERROR: tools/extract_manifest.json not found.\n"
            "       Run `make extract` to generate it.",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest = json.loads(MANIFEST_PATH.read_bytes())
    check_tool_versions(manifest)
    tracked = manifest.get("files", {})

    drift = False
    for rel, expected in tracked.items():
        path = ROOT / rel if rel != "data/lectionary" else ROOT / "data" / "lectionary"

        if rel == "data/lectionary":
            lect_dir = ROOT / "data" / "lectionary"
            if not lect_dir.exists():
                print(f"MISSING  {rel}")
                drift = True
                continue
            actual_hash = lectionary_composite_hash(lect_dir)
        else:
            file_path = ROOT / rel
            if not file_path.exists():
                print(f"MISSING  {rel}")
                drift = True
                continue
            actual_hash = file_sha256(file_path)

        exp_hash = expected["sha256"]
        if actual_hash == exp_hash:
            print(f"OK       {rel} ({actual_hash[:12]}…)")
        else:
            print(f"DRIFT    {rel}")
            print(f"         expected: {exp_hash[:12]}…")
            print(f"         actual:   {actual_hash[:12]}…")
            print(f"         → File was modified outside the extraction pipeline.")
            print(f"           Migrate the change to the extractor or patches.json,")
            print(f"           then re-run `make extract`.")
            drift = True

    if drift:
        print("\nIntegrity check FAILED — deploy blocked.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nIntegrity check passed.")


if __name__ == "__main__":
    main()
