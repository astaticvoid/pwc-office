"""
extract_lib.py — shared utilities for PDF extraction tools.

Imported by: extract_psalter.py, extract_collects.py, extract_offices.py,
             and any future BAS office-form extractor.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


# ── PDF → text ────────────────────────────────────────────────────────────────

def _generate_txt(pdf_path: Path, dest: Path, prefer_pdftotext: bool = True) -> None:
    print(f"Extracting {pdf_path.name}…", file=sys.stderr)
    try:
        subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), str(dest)],
            check=True, capture_output=True,
        )
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        if prefer_pdftotext:
            print(
                "WARNING: pdftotext not found — falling back to PyMuPDF "
                "(some pages may have garbled text)",
                file=sys.stderr,
            )
    try:
        import fitz  # noqa: PLC0415
    except ImportError:
        print(
            "ERROR: neither pdftotext nor PyMuPDF (fitz) is available — cannot extract PDF",
            file=sys.stderr,
        )
        sys.exit(1)
    pages = []
    with fitz.open(pdf_path) as pdf:
        for page in pdf:
            pages.append(page.get_text() or "")
    dest.write_text("\n\f\n".join(pages), encoding="utf-8")


@contextmanager
def pdf_as_txt(pdf_path: Path, prefer_pdftotext: bool = True):
    """Context manager: yield a transient Path to a text extraction of pdf_path.

    Uses pdftotext (poppler) if available, falls back to PyMuPDF (fitz).
    The temp file is deleted on exit — no persistent .txt files in sources/.
    """
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    try:
        _generate_txt(pdf_path, tmp, prefer_pdftotext)
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


# ── JSON output ───────────────────────────────────────────────────────────────

def write_json(data: object, path: Path) -> None:
    """Write data to path as indented JSON with a trailing newline."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── Extraction manifest ───────────────────────────────────────────────────────

_MANIFEST = Path(__file__).parent / "manifest.json"


def check_manifest(outputs: list[Path], repo_root: Path, *, accept: bool = False) -> bool:
    """Compare output file hashes against tools/manifest.json.

    If accept=True, update the manifest entries for these files and return True.
    Otherwise, warn on any hash drift and return False if drift is found.

    Workflow:
      normal run       — warns if any output diverges from committed baseline
      --accept         — promotes current hashes as new baseline (commit the result)
    """
    manifest = json.loads(_MANIFEST.read_text()) if _MANIFEST.exists() else {}

    current = {
        str(p.relative_to(repo_root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in outputs if p.exists()
    }

    if accept:
        manifest.update(current)
        _MANIFEST.write_text(
            json.dumps(dict(sorted(manifest.items())), indent=2, ensure_ascii=False) + "\n"
        )
        print(f"  Manifest: accepted {len(current)} file(s) → tools/manifest.json")
        return True

    if not manifest:
        print(
            "  Manifest: tools/manifest.json not found — run with --accept to initialise",
            file=sys.stderr,
        )
        return True

    diffs = []
    for key in sorted(current):
        if key not in manifest:
            diffs.append(f"  NEW      {key}")
        elif manifest[key] != current[key]:
            diffs.append(f"  CHANGED  {key}")

    if diffs:
        print("  Manifest drift — run with --accept to update tools/manifest.json:")
        for d in diffs:
            print(d)
        return False

    print(f"  Manifest: {len(current)} file(s) match baseline ✓")
    return True


# ── Typography ────────────────────────────────────────────────────────────────

_QUOTE_MAP = str.maketrans({
    "“": '"',   # LEFT DOUBLE QUOTATION MARK
    "”": '"',   # RIGHT DOUBLE QUOTATION MARK
    "‘": "'",   # LEFT SINGLE QUOTATION MARK
    "’": "'",   # RIGHT SINGLE QUOTATION MARK
})


def normalise_quotes(s: str) -> str:
    """Replace curly/smart quotes with straight ASCII equivalents.

    Also fixes a PDF indentation artifact where an opening quote is followed
    by extra spaces before the verse text (e.g. '"  The mercy' → '"The mercy').
    """
    import re  # noqa: PLC0415
    s = s.translate(_QUOTE_MAP)
    s = re.sub(r'^"( +)(?=\S)', '"', s, flags=re.MULTILINE)
    return s
