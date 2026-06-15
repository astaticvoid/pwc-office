#!/usr/bin/env python3
"""compare_book.py — Diff a book-mode renderer output against a golden file.

Usage: python3 tools/compare_book.py FORM [DATE]
  FORM  e.g. ordinary-sunday-ep
  DATE  YYYY-MM-DD (defaults to today)

Runs: node cli/book.js FORM DATE
Diffs stdout against: tests/fixtures/book/FORM.txt

Normalisation applied before diff:
  - Strip lines starting with '#' (golden-file comments)
  - Strip leading/trailing whitespace per line
  - Collapse 3+ consecutive blank lines to 2
  - Normalise curly quotes to straight quotes
  - Lowercase both sides (comparison and diff display)

Exits 0 if clean, 1 with unified diff if not.
"""

import subprocess
import sys
import difflib
from datetime import date
from pathlib import Path


REPO = Path(__file__).parent.parent


def normalise(text: str) -> str:
    """Strip comments, normalise whitespace/quotes, collapse blank lines, lowercase."""
    lines = text.splitlines()
    # Strip comment lines (golden-file metadata header)
    lines = [l for l in lines if not l.lstrip().startswith('#')]
    # Strip trailing whitespace per line
    lines = [l.rstrip() for l in lines]
    # Normalise curly quotes to straight
    normalised = []
    for l in lines:
        l = l.replace('‘', "'").replace('’', "'")
        l = l.replace('“', '"').replace('”', '"')
        normalised.append(l)
    # Collapse 3+ consecutive blank lines to 2
    result = []
    blank_count = 0
    for l in normalised:
        if l == '':
            blank_count += 1
            if blank_count <= 2:
                result.append(l)
        else:
            blank_count = 0
            result.append(l)
    # Remove leading/trailing blank lines from the whole file
    while result and result[0] == '':
        result.pop(0)
    while result and result[-1] == '':
        result.pop()
    # Lowercase for comparison and diff display
    return '\n'.join(l.lower() for l in result)


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        sys.exit(2)

    form = args[0]
    today = date.today().isoformat()
    date_arg = args[1] if len(args) > 1 else today

    golden_path = REPO / 'tests' / 'fixtures' / 'book' / f'{form}.txt'
    if not golden_path.exists():
        print(f'ERROR: golden file not found: {golden_path}', file=sys.stderr)
        sys.exit(2)

    result = subprocess.run(
        ['node', 'cli/book.js', form, date_arg],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    if result.returncode != 0:
        print(f'ERROR: cli/book.js exited {result.returncode}', file=sys.stderr)
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.exit(2)

    rendered = normalise(result.stdout)
    golden   = normalise(golden_path.read_text(encoding='utf-8'))

    if rendered == golden:
        print(f'PASS: {form} {date_arg}')
        sys.exit(0)

    rendered_lines = rendered.splitlines(keepends=True)
    golden_lines   = golden.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        golden_lines,
        rendered_lines,
        fromfile=f'golden/{form}.txt',
        tofile=f'book.js output ({date_arg})',
    ))
    sys.stdout.writelines(diff)
    sys.exit(1)


if __name__ == '__main__':
    main()
