#!/usr/bin/env python3
"""Normalize shared office blocks in data/offices.json.

Four blocks are identical across many forms and belong in `_shared`:
  - reading_response_seasonal   (all seasonal forms)
  - reading_response_ordinary   (all ordinary-time forms)
  - lords_prayer_ordinary       (all ordinary-time forms)
  - opening_responses_ep_seasonal (most seasonal EP forms, except Advent)

Each repeated block is replaced with a {"type": "shared", "key": "..."} reference.
The app already handles shared references via lookupShared() — no app change needed.

Run from the repo root:
  python3 tools/normalize_offices.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path


def blocks_equal(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def find_unique_block(forms, field):
    """Return the unique value of `field` across all forms that have it, or None if multiple differ."""
    values = []
    for key, form in forms.items():
        if key.startswith('_'):
            continue
        val = form.get(field)
        if val is None:
            continue
        if not any(blocks_equal(val, existing) for existing in values):
            values.append(val)
    return values[0] if len(values) == 1 else None


def normalize(data, dry_run=False):
    forms = {k: v for k, v in data.items() if not k.startswith('_')}
    shared = dict(data.get('_shared', {}))
    changed = 0

    # ── reading_response: split into seasonal and ordinary ────────────────────
    for rr_key, form_filter in [
        ('reading_response_seasonal', lambda k: 'ordinary' not in k),
        ('reading_response_ordinary', lambda k: 'ordinary' in k),
    ]:
        matching = {k: v for k, v in forms.items() if form_filter(k) and 'reading_response' in v}
        if not matching:
            continue
        vals = list(matching.values())
        canonical = vals[0]['reading_response']
        if all(blocks_equal(f['reading_response'], canonical) for f in vals):
            if rr_key not in shared:
                shared[rr_key] = canonical
                print(f'  + shared.{rr_key} ({len(matching)} forms)')
            for k in matching:
                if not isinstance(data[k].get('reading_response'), dict) or data[k]['reading_response'].get('type') != 'shared':
                    data[k]['reading_response'] = {'type': 'shared', 'key': rr_key}
                    changed += 1
        else:
            print(f'  WARNING: {rr_key} not identical across all matching forms — skipping')

    # ── lords_prayer_ordinary ─────────────────────────────────────────────────
    ordinary_forms = {k: v for k, v in forms.items() if 'ordinary' in k and 'lords_prayer_intro' in v}
    if ordinary_forms:
        vals = list(ordinary_forms.values())
        canonical = vals[0]['lords_prayer_intro']
        if all(blocks_equal(f['lords_prayer_intro'], canonical) for f in vals):
            key = 'lords_prayer_ordinary'
            if key not in shared:
                shared[key] = canonical
                print(f'  + shared.{key} ({len(ordinary_forms)} forms)')
            for k in ordinary_forms:
                if not isinstance(data[k].get('lords_prayer_intro'), dict) or data[k]['lords_prayer_intro'].get('type') != 'shared':
                    data[k]['lords_prayer_intro'] = {'type': 'shared', 'key': key}
                    changed += 1
        else:
            print('  WARNING: lords_prayer_intro not identical across ordinary forms — skipping')

    # ── opening_responses_ep_seasonal (all seasonal EP except Advent) ─────────
    ep_seasonal_forms = {
        k: v for k, v in forms.items()
        if k.endswith('-ep') and 'ordinary' not in k and 'advent' not in k
        and 'opening_responses' in v
    }
    if ep_seasonal_forms:
        vals = list(ep_seasonal_forms.values())
        canonical = vals[0]['opening_responses']
        if all(blocks_equal(f['opening_responses'], canonical) for f in vals):
            key = 'opening_responses_ep_seasonal'
            if key not in shared:
                shared[key] = canonical
                print(f'  + shared.{key} ({len(ep_seasonal_forms)} forms)')
            for k in ep_seasonal_forms:
                if not isinstance(data[k].get('opening_responses'), dict) or data[k]['opening_responses'].get('type') != 'shared':
                    data[k]['opening_responses'] = {'type': 'shared', 'key': key}
                    changed += 1
        else:
            print('  WARNING: opening_responses not identical across seasonal EP forms — skipping')

    data['_shared'] = shared
    print(f'  {changed} form field(s) replaced with shared references')
    return changed


def main():
    parser = argparse.ArgumentParser(description='Normalize shared blocks in data/offices.json.')
    parser.add_argument('--dry-run', action='store_true', help='Print what would change without writing.')
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    path = root / 'data' / 'offices.json'

    if not path.exists():
        sys.exit(f'Not found: {path}\nRun the extraction pipeline first.')

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    changed = normalize(data, dry_run=args.dry_run)

    if args.dry_run:
        print('(dry-run — no files written)')
        return

    if changed == 0:
        print('Already normalized — no changes needed.')
        return

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'Wrote {path}')


if __name__ == '__main__':
    main()
