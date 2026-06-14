#!/usr/bin/env python3
"""Apply patches from data/patches.json to their target JSON data files.

Always run validate_patches.py first. Each patch must have:
  id, target, path (list), op, old, new

Supported ops:
  replace — replace the value at `path` with `new` (verifies `old` first)

Run from the repo root:
  python3 tools/validate_patches.py && python3 tools/apply_patches.py
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


def set_at_path(obj, path, value):
    """Set value at path in obj (mutates in place)."""
    for key in path[:-1]:
        if isinstance(obj, list):
            obj = obj[int(key)]
        else:
            obj = obj[key]
    last = path[-1]
    if isinstance(obj, list):
        obj[int(last)] = value
    else:
        obj[last] = value


def main():
    root = Path(__file__).parent.parent
    patches_path = root / 'data' / 'patches.json'

    if not patches_path.exists():
        print('No patches.json found — nothing to apply.')
        return

    with open(patches_path, encoding='utf-8') as f:
        patches = json.load(f)

    if not patches:
        print('patches.json is empty — nothing to apply.')
        return

    # Group patches by target file so we load/write each file once.
    by_target: dict[str, list] = {}
    for patch in patches:
        by_target.setdefault(patch['target'], []).append(patch)

    total_applied = 0
    for target_rel, target_patches in by_target.items():
        target_path = root / 'data' / target_rel
        if not target_path.exists():
            print(f'ERROR: target not found: {target_path}')
            sys.exit(1)
        with open(target_path, encoding='utf-8') as f:
            data = json.load(f)

        for patch in target_patches:
            pid = patch.get('id', '?')
            op = patch.get('op', 'replace')
            if op != 'replace':
                print(f'ERROR {pid}: unsupported op {op!r}')
                sys.exit(1)

            current = get_at_path(data, patch['path'])
            if current != patch['old']:
                print(
                    f'ERROR {pid}: old value mismatch (run validate_patches.py first)\n'
                    f'  expected: {patch["old"]!r}\n'
                    f'  found:    {current!r}'
                )
                sys.exit(1)

            set_at_path(data, patch['path'], patch['new'])
            print(f'  applied {pid}: {patch.get("description", "")}')
            total_applied += 1

        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print(f'  wrote {target_path}')

    print(f'Applied {total_applied} patch(es).')


if __name__ == '__main__':
    main()
