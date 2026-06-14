#!/usr/bin/env python3
"""Validate patches in data/patches.json against current JSON data files.

Each patch's `old` value must match the content at `path` in the `target` file.
Exits non-zero if any patch is stale or invalid.

Run from the repo root:
  python3 tools/validate_patches.py
"""

import json
import sys
from pathlib import Path


def get_at_path(obj, path):
    for key in path:
        if isinstance(obj, list):
            obj = obj[int(key)]
        elif isinstance(obj, dict):
            obj = obj[key]
        else:
            raise KeyError(f'Cannot index {type(obj).__name__} with {key!r}')
    return obj


def main():
    root = Path(__file__).parent.parent
    patches_path = root / 'data' / 'patches.json'

    if not patches_path.exists():
        print('No patches.json found — nothing to validate.')
        return

    with open(patches_path, encoding='utf-8') as f:
        patches = json.load(f)

    if not patches:
        print('patches.json is empty — nothing to validate.')
        return

    errors = []
    for patch in patches:
        pid = patch.get('id', '?')
        target_path = root / 'data' / patch['target']
        if not target_path.exists():
            errors.append(f'{pid}: target file not found: {target_path}')
            continue
        with open(target_path, encoding='utf-8') as f:
            data = json.load(f)
        try:
            current = get_at_path(data, patch['path'])
        except (KeyError, IndexError, ValueError, TypeError) as e:
            errors.append(f'{pid}: path {patch["path"]} not found in {patch["target"]}: {e}')
            continue
        if current != patch['old']:
            errors.append(
                f'{pid}: old value mismatch at {patch["path"]}\n'
                f'  expected: {patch["old"]!r}\n'
                f'  found:    {current!r}'
            )

    if errors:
        print(f'{len(errors)} patch validation error(s):')
        for e in errors:
            print(f'  {e}')
        sys.exit(1)

    print(f'All {len(patches)} patch(es) validated OK.')


if __name__ == '__main__':
    main()
