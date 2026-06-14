#!/usr/bin/env python3
"""Download all PWC source files from their public URLs.

Run:  python3 tools/fetch_sources.py [--force]

Skips files that already exist unless --force is passed.
Rate-limited to 1 request/second.
"""

import argparse
import os
import sys
import time
import urllib.request

SOURCES = {
    # ACC liturgical PDFs (anglican.ca)
    'sources/pray-without-ceasing.pdf': 'https://www.anglican.ca/wp-content/uploads/pray-without-ceasing.pdf',
    'sources/BAS.pdf':                  'https://www.anglican.ca/wp-content/uploads/BAS.pdf',
    'sources/For-All-The-Saints.pdf':   'https://www.anglican.ca/wp-content/uploads/For-All-The-Saints.pdf',
    # RCL Daily Readings (commontexts.org)
    'sources/rcl/rcl_year_a.rtf':          'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearA.rtf',
    'sources/rcl/rcl_year_b.rtf':          'https://www.commontexts.org/wp-content/uploads/2015/11/dailyreadingsB.rtf',
    'sources/rcl/rcl_year_c.doc':          'https://www.commontexts.org/wp-content/uploads/2015/11/RCLDailyReadings_YearC.doc',
    'sources/rcl/rcl_year_a_expanded.pdf': 'https://www.commontexts.org/wp-content/uploads/2025/12/RCL-Expanded-Daily-Readings-Year-A.pdf',
}


def main():
    parser = argparse.ArgumentParser(description='Download PWC source files.')
    parser.add_argument('--force', action='store_true',
                        help='Re-download files that already exist.')
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    errors = []

    for rel_path, url in SOURCES.items():
        dest = os.path.join(repo_root, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if os.path.exists(dest) and not args.force:
            size_kb = os.path.getsize(dest) // 1024
            print(f'  skip  {rel_path} ({size_kb} KB already present)')
            continue

        print(f'  fetch {rel_path} ...', end=' ', flush=True)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PWC-fetch/1.0'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            with open(dest, 'wb') as f:
                f.write(data)
            print(f'{len(data) // 1024} KB')
        except Exception as exc:
            print(f'ERROR: {exc}')
            errors.append((rel_path, str(exc)))
        time.sleep(1)

    if errors:
        print(f'\n{len(errors)} download(s) failed:')
        for path, msg in errors:
            print(f'  {path}: {msg}')
        sys.exit(1)

    print('\nAll source files present.')


if __name__ == '__main__':
    main()
