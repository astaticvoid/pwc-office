#!/usr/bin/env python3
"""
check_mobile_sync.py — verify the Capacitor-synced native web assets match dist/.

`npx cap sync` removes each native platform's public directory and re-copies it
from webDir (dist/), so a sync is authoritative — but only as fresh as the last
time it ran, and the synced directories are gitignored, so staleness is
invisible to git. An Xcode archive bundles whatever public/ held at archive
time; a stale public/ ships a stale app behind a clean `git status` (runbook:
docs/runbooks/ios-testflight-ship.md).

For each native platform present (ios/App/App/public, android/app/.../public):
  - every file under dist/ must exist in the synced directory with identical
    content (the direction that catches "forgot to sync")
  - every file under the synced directory must exist in dist/ unless Capacitor
    injects it after the copy (the direction that catches stale debris)

Run as the final step of `make mobile-sync`; exit 0 = native assets match
dist/, 1 = stale (remediation: run `make mobile-sync`, then archive in the
same sitting).
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DIST = ROOT / "dist"

# Platforms, keyed by the native directory Capacitor copies webDir into.
PLATFORMS = {
    "ios": ROOT / "ios" / "App" / "App" / "public",
    "android": ROOT / "android" / "app" / "src" / "main" / "assets" / "public",
}

# Files Capacitor CLI writes into the copied web dir after the copy itself
# (plugin loader shims); they have no counterpart in dist/.
INJECTED = {"capacitor-plugins.js", "cordova.js", "cordova_plugins.js"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_platform(name: str, public_dir: Path, errors: list[str]) -> None:
    if not public_dir.is_dir():
        return  # platform not present in this checkout / not yet synced

    # Direction 1: dist is the source of truth — nothing may lag behind it.
    missing = []
    for dist_file in sorted(DIST.rglob("*")):
        if not dist_file.is_file():
            continue
        rel = dist_file.relative_to(DIST)
        synced = public_dir / rel
        if not synced.is_file():
            missing.append(f"  {rel}  (present in dist/, absent from {name})")
        elif sha256(synced) != sha256(dist_file):
            missing.append(f"  {rel}  (differs from dist/)")
    if missing:
        errors.append(
            f"stale {name} web assets — {len(missing)} file(s) out of date:")
        errors.extend(missing)

    # Direction 2: nothing may linger in the synced dir that dist/ no longer has,
    # and Capacitor's post-copy shims must all be present (interrupted sync).
    leftover = []
    injected_missing = [
        f"  {f}  (Capacitor shim absent — sync was interrupted)"
        for f in sorted(INJECTED)
        if not (public_dir / f).is_file()
    ]
    if injected_missing:
        errors.append(f"incomplete {name} web assets:")
        errors.extend(injected_missing)
    for synced_file in sorted(public_dir.rglob("*")):
        if not synced_file.is_file():
            continue
        rel = synced_file.relative_to(public_dir)
        if rel.as_posix() in INJECTED:
            continue
        if not (DIST / rel).is_file():
            leftover.append(f"  {rel}  (in {name}, not in dist/)")
    if leftover:
        errors.append(f"leftover files in {name} web assets:")
        errors.extend(leftover)


def main() -> int:
    if not DIST.is_dir():
        print("dist/ missing — run `make mobile-sync` (or `make build`) first")
        return 1

    errors: list[str] = []
    checked = []
    for name, public_dir in PLATFORMS.items():
        if public_dir.is_dir():
            checked.append(name)
            check_platform(name, public_dir, errors)

    if not checked:
        print("no native platforms present — nothing to check")
        return 0

    if errors:
        print("mobile web assets are stale — this is what a TestFlight archive"
              " would have bundled:")
        print("\n".join(errors))
        print("\nfix: run `make mobile-sync`, then archive in the same sitting"
              " (docs/runbooks/ios-testflight-ship.md)")
        return 1

    print(f"mobile web assets match dist/ for: {', '.join(checked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
