#!/usr/bin/env python3
"""
bump_ios_version.py — bump CURRENT_PROJECT_VERSION (CFBundleVersion) in the
Xcode project.

TestFlight rejects an upload whose build number was already used, so every ship
must carry a fresh, monotonically increasing CFBundleVersion. The value lives
in ios/App/App.xcodeproj/project.pbxproj (two build configurations, Debug and
Release, which must move together). Run it as part of the ship:
`make mobile-bump-version`, commit, then archive.

Usage: python3 tools/bump_ios_version.py [N]
  N = number of build numbers to add (default 1)

Exit 0 on success; fails without writing if the two configurations disagree or
the value cannot be parsed.
"""

import re
import sys
from pathlib import Path

PBXPROJ = (Path(__file__).parent.parent / "ios" / "App" / "App.xcodeproj"
          / "project.pbxproj")
PATTERN = re.compile(r"^(\s*CURRENT_PROJECT_VERSION = )(\d+)(;)$", re.MULTILINE)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        n = int(args[0]) if args else 1
    except ValueError:
        print(f"usage: {Path(__file__).name} [N]  (N = build numbers to add)")
        return 1
    if n < 1:
        print("N must be >= 1")
        return 1

    if not PBXPROJ.is_file():
        print(f"missing: {PBXPROJ}")
        return 1

    src = PBXPROJ.read_text()
    matches = list(PATTERN.finditer(src))
    if len(matches) != 2:
        print(
            "expected 2 CURRENT_PROJECT_VERSION entries (Debug + Release),"
            f" found {len(matches)} — refusing to rewrite")
        return 1

    values = {int(m.group(2)) for m in matches}
    if len(values) != 1:
        print(
            "Debug/Release CURRENT_PROJECT_VERSION disagree"
            f" ({sorted(values)}) — fix by hand first")
        return 1

    old = values.pop()
    new = old + n
    updated = PATTERN.sub(lambda m: f"{m.group(1)}{new}{m.group(3)}", src)
    PBXPROJ.write_text(updated)
    print(f"CURRENT_PROJECT_VERSION {old} -> {new} in {PBXPROJ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
