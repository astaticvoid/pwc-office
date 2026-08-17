#!/usr/bin/env python3
"""Hoist shared office blocks — pipeline stage 2 of `make extract`.

Reads  .build/offices.1-extract.json
Writes .build/offices.2-normalized.json

Nothing is published from here; `apply_corrections.py` derives data/offices.json
from this artifact later in the pipeline (#48, #49).

Three blocks are identical across many forms and belong in `_shared`:
  - reading_response_seasonal   (all seasonal forms)
  - reading_response_ordinary   (all ordinary-time forms)
  - opening_responses_ep_seasonal (7 seasonal EP forms, advent through pentecost;
                                   AllSaints EP has different opening responses)

Each repeated block is replaced with a {"type": "shared", "key": "..."} reference.
The app already handles shared references via lookupShared() — no app change needed.

This is not redundant with _dedup_shared() in extract_offices.py, which runs
first: that one matches `alternatives` blocks structurally and catches
affirmation, doxology and berakah_blessings. The three keys here are named
fields identified by liturgical rule (which forms count as seasonal, and that
AllSaints EP is the one seasonal EP with different opening responses), which a
structural match cannot derive. Together: 6 keys, 127 references.

Normally run as part of the pipeline (`make extract`). Standalone, from the
repo root, for inspection:
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
        # reading_response ships as a single alternatives block, not the
        # list-wrapped field value: the renderer consumes it via
        # renderAlternatives(shared[key], …) and the CLI via
        # renderSegmentsText, both of which take the block directly (#91).
        # opening_responses, by contrast, is a list-valued field the renderer
        # iterates as a list — each keeps its own convention.
        block = (canonical[0] if (isinstance(canonical, list) and len(canonical) == 1
                                  and isinstance(canonical[0], dict)
                                  and canonical[0].get('type') == 'alternatives')
                 else canonical)
        if all(blocks_equal(f['reading_response'], canonical) for f in vals):
            if rr_key not in shared:
                shared[rr_key] = block
                print(f'  + shared.{rr_key} ({len(matching)} forms)')
            for k in matching:
                if not isinstance(data[k].get('reading_response'), dict) or data[k]['reading_response'].get('type') != 'shared':
                    data[k]['reading_response'] = {'type': 'shared', 'key': rr_key}
                    changed += 1
        else:
            print(f'  WARNING: {rr_key} not identical across all matching forms — skipping')

    # ── opening_responses_ep_seasonal (all seasonal EP except AllSaints) ────────
    ep_seasonal_forms = {
        k: v for k, v in forms.items()
        if k.endswith('-ep') and 'ordinary' not in k and 'allsaints' not in k
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
    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description='Normalize shared blocks (stage 2 of the offices chain).')
    parser.add_argument('--dry-run', action='store_true', help='Print what would change without writing.')
    parser.add_argument('--in', dest='in_path', type=Path,
                        default=root / '.build' / 'offices.1-extract.json',
                        help='extract_offices.py output')
    parser.add_argument('--out', dest='out_path', type=Path,
                        default=root / '.build' / 'offices.2-normalized.json',
                        help='normalized output, read by apply_corrections.py')
    args = parser.parse_args()

    path, out_path = args.in_path, args.out_path

    if not path.exists():
        sys.exit(f'Not found: {path}\nRun the extraction pipeline first.')

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    changed = normalize(data, dry_run=args.dry_run)

    if args.dry_run:
        print('(dry-run — no files written)')
        return

    # Written unconditionally, including when nothing changed: the next stage
    # reads this artifact by name, and skipping the write would leave it stale.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(f'Wrote {out_path}' + ('' if changed else ' (no changes needed)'))


if __name__ == '__main__':
    main()
