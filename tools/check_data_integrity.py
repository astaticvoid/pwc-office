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


def _same_version(a, b) -> bool:
    """Compare two recorded versions across the JSON round-trip.

    `fitz.version` is a tuple; the manifest holds whatever json.load returns,
    which is a list. `("1.28.0", "1.28.0", None) == ["1.28.0", "1.28.0", None]`
    is False in Python, so the equality this replaced could never be true — it
    printed VERSION WARN on every run since the check was written, including
    every run where the versions matched exactly.
    """
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b


def check_tool_versions(manifest: dict) -> None:
    """Report PyMuPDF drift. Warns; never changes the exit status.

    This is the only automatic signal for a real gap. PyMuPDF supplies every
    coordinate `extract_offices.py` decides line breaks from, against a window
    the code documents as sitting 0.5pt off a false positive, and ADR 0011
    records that nothing here catches a version-induced decoding regression.
    The file hashes cannot cover it: `make extract` rewrites them and
    `tool_versions` in the same run, so they are consistent with whatever
    produced them by construction — the same laundering that let a stale
    offices.json pass check-integrity. Upgrading PyMuPDF is changing an
    extractor; re-extract and `make extract-diff EXPECT=0`.

    It warns rather than fails for a practical reason, not a principled one.
    `make test` depends on check-integrity, so failing here would lock any
    contributor whose PyMuPDF differs out of the entire suite until they run
    `make fetch-sources && make extract` — a network fetch of three PDFs. CI
    never exercises the comparison at all: it runs `make extract` first, so the
    manifest is regenerated with its own fitz and the check compares a value
    against itself.
    """
    expected_versions = manifest.get("tool_versions", {})
    if not expected_versions:
        return

    fitz_expected = expected_versions.get("fitz")
    try:
        import fitz
        fitz_ver = fitz.version
    except ImportError:
        if fitz_expected and fitz_expected != "not found":
            print(f"VERSION WARN fitz not found (manifest recorded {fitz_expected})")
        # Required: fitz_ver is bound only on the success path, so falling
        # through raises UnboundLocalError — the one way this function can
        # change the exit status, via an uncaught traceback out of main().
        return

    if fitz_expected == "not found":
        print(f"VERSION WARN fitz {fitz_ver} now available (manifest recorded 'not found')")
    elif not fitz_expected:
        print(f"VERSION OK   fitz {fitz_ver}")
    elif _same_version(fitz_ver, fitz_expected):
        print(f"VERSION OK   fitz {fitz_ver} (matches manifest)")
    else:
        print(f"VERSION WARN fitz {fitz_ver} (manifest recorded {fitz_expected})")
        print("             PyMuPDF produces the geometry extraction reads. Re-run")
        print("             `make extract`, then `make extract-diff EXPECT=0`.")


def check_sources(manifest: dict) -> list[str]:
    """Sources that changed since the manifest was written.

    data/ matching the manifest proves only that nobody hand-edited it. It says
    nothing about whether the extractor that produced it is the one committed
    beside it — change a threshold and skip `make extract`, and every hash still
    matches while the data is stale. This closes that (#51).
    """
    expected = manifest.get("source_hashes")
    if not expected:
        print("SOURCES  not recorded in manifest — run `make extract` to add them")
        return []
    drifted = []
    for rel, want in sorted(expected.items()):
        path = ROOT / rel
        if want is None:
            # An input EXTRACTION_SOURCES names, that was gone when the manifest
            # was written. Fatal either way: still absent means data/ was
            # published without an input the pipeline declares it needs; back
            # again means data/ predates it. Retiring an input for real is an
            # edit to EXTRACTION_SOURCES, which is a reviewable change — not a
            # file quietly disappearing from a worktree.
            drifted.append(
                f"{rel} (absent when the manifest was written"
                f"{'; present again now' if path.exists() else ''})"
            )
        elif not path.exists():
            drifted.append(f"{rel} (missing)")
        elif file_sha256(path) != want:
            drifted.append(rel)
    if drifted:
        print(f"SOURCE DRIFT  {len(drifted)} extraction source(s) changed since the "
              f"last run:")
        for rel in drifted:
            print(f"    {rel}")
        print("    data/ is stale with respect to the code that produces it.")
        print("    Run `make extract`. If an input was removed deliberately,")
        print("    drop it from EXTRACTION_SOURCES in update_extract_manifest.py")
        print("    in the same commit — that is what retires it.")
    else:
        print(f"SOURCES OK   {len(expected)} extraction source(s) match the manifest")
    return drifted


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
    source_drift = check_sources(manifest)
    tracked = manifest.get("files", {})

    drift = False
    for rel, expected in tracked.items():
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
            print("         → File was modified outside the extraction pipeline.")
            print("           Migrate the change to the extractor or data/corrections.json,")
            print("           then re-run `make extract`.")
            drift = True

    if drift or source_drift:
        print("\nIntegrity check FAILED — deploy blocked.", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nIntegrity check passed.")


if __name__ == "__main__":
    main()
