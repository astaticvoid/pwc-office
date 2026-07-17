#!/usr/bin/env python3
"""
generate_version_manifest.py — write dist/data/version.json with SHA-256
hashes of all data files in the build directory.

Run as the final step of `make build`.

Usage: python3 tools/generate_version_manifest.py [--dist-dir dist]
"""

import argparse
import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist-dir", type=Path, default=Path("dist"))
    args = ap.parse_args()

    data_dir = args.dist_dir / "data"
    if not data_dir.exists():
        print(f"Data dir not found: {data_dir}")
        return

    files = {}
    for path in sorted(data_dir.rglob("*.json")):
        rel = str(path.relative_to(args.dist_dir))
        files[rel] = file_sha256(path)

    manifest = {
        "files": files,
    }

    out_path = data_dir / "version.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(files)} file hashes to {out_path}")


if __name__ == "__main__":
    main()
