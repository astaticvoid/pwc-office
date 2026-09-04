#!/usr/bin/env python3
"""
tools/audit_copyright_leak.py
Audit script to verify zero leakage of copyrighted NRSVue scripture texts (ADR 0023 / ADR 0024).

Modes:
  1. Static Dist Audit: Scans dist/ to verify no full books or nrsvue files exist.
  2. Live CDN Probe Audit: Probes an endpoint (staging or production) with 5 attack/leak scenarios.

Usage:
  python3 tools/audit_copyright_leak.py [--dist-dir dist] [--url https://staging-domain]
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent


def audit_dist(dist_dir: Path) -> list[str]:
    """Scan dist/ directory for any unauthorized copyrighted translation files."""
    errors = []
    if not dist_dir.exists():
        errors.append(f"Dist directory does not exist: {dist_dir}")
        return errors

    # Check data/translations directory
    trans_dir = dist_dir / "data" / "translations"
    if trans_dir.exists():
        for item in trans_dir.iterdir():
            if item.name != "kjv":
                errors.append(f"Found unauthorized translation folder in dist: {item}")

    # Recursive scan for any file containing 'nrsvue' in path or filename
    for p in dist_dir.rglob("*"):
        if "nrsvue" in p.name.lower():
            errors.append(f"Found copyrighted file/path in dist: {p.relative_to(dist_dir)}")

    return errors


def probe_url(url: str, auth: str | None = None) -> tuple[int, str]:
    """Perform HTTP GET request, returning status code and response body/error."""
    headers = {"User-Agent": "PwcCopyrightAuditor/1.0"}
    if auth:
        import base64
        token = base64.b64encode(auth.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body or str(e.reason)
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def audit_live_cdn(base_url: str, auth: str | None = None) -> list[str]:
    """Run the 5 live security/compliance probes against CDN."""
    errors = []
    base_url = base_url.rstrip("/")
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    future_date = (now + timedelta(days=60)).strftime("%Y-%m-%d")
    past_date = (now - timedelta(days=60)).strftime("%Y-%m-%d")

    print(f"Auditing live CDN probes against: {base_url}")

    # Probe 1: Direct book path access
    url = f"{base_url}/data/translations/nrsvue/Genesis.json"
    status, _ = probe_url(url, auth=auth)
    print(f"  Probe 1: Direct book fetch ({url}) -> Status {status}")
    if status not in (403, 404):
        errors.append(f"Probe 1 failed: Direct book URL returned status {status} (expected 403 or 404)")

    # Probe 2: Direct private S3 bypass
    url = f"{base_url}/private/readings/v1/nrsvue/1999-01-01.json"
    status, _ = probe_url(url, auth=auth)
    print(f"  Probe 2: Direct private bypass ({url}) -> Status {status}")
    if status != 403:
        errors.append(f"Probe 2 failed: Direct private bypass returned status {status} (expected 403 Forbidden)")

    # Probe 3: Temporal gate boundaries (future & past out-of-window)
    url_future = f"{base_url}/api/v1/readings?date={future_date}&translation=nrsvue"
    status_f, _ = probe_url(url_future, auth=auth)
    print(f"  Probe 3a: Out-of-window future (+60d) -> Status {status_f}")
    if status_f != 403:
        errors.append(f"Probe 3a failed: Date +60d returned status {status_f} (expected 403 Forbidden)")

    url_past = f"{base_url}/api/v1/readings?date={past_date}&translation=nrsvue"
    status_p, _ = probe_url(url_past, auth=auth)
    print(f"  Probe 3b: Out-of-window past (-60d) -> Status {status_p}")
    if status_p != 403:
        errors.append(f"Probe 3b failed: Date -60d returned status {status_p} (expected 403 Forbidden)")

    # Probe 4: Path traversal attempt
    url_trav = f"{base_url}/api/v1/readings?date={today_str}&translation=../../secret"
    status_t, _ = probe_url(url_trav, auth=auth)
    print(f"  Probe 4: Path traversal attempt -> Status {status_t}")
    if status_t not in (400, 403):
        errors.append(f"Probe 4 failed: Path traversal returned status {status_t} (expected 400 Bad Request)")

    # Probe 5: Unversioned path check (expected 400)
    url_unversioned = f"{base_url}/api/readings?date={today_str}&translation=nrsvue"
    status_u, _ = probe_url(url_unversioned, auth=auth)
    print(f"  Probe 5: Unversioned path check -> Status {status_u}")
    if status_u not in (400, 403):
        errors.append(f"Probe 5 failed: Unversioned path returned status {status_u} (expected 400 Bad Request)")

    # Probe 6: In-window verification (if live)
    url_valid = f"{base_url}/api/v1/readings?date={today_str}&translation=nrsvue"
    status_v, body = probe_url(url_valid, auth=auth)
    print(f"  Probe 6: Valid in-window query -> Status {status_v}")
    if status_v == 200:
        try:
            data = json.loads(body)
            # Verify data is strictly date-grained lectionary readings
            if "readings" not in data or not isinstance(data["readings"], dict):
                errors.append("Probe 6 failed: 200 response missing 'readings' dictionary")
            # Verify no full-book payloads
            for cit, reading in data.get("readings", {}).items():
                verses = reading.get("verses", [])
                if len(verses) > 150:  # Daily office readings rarely exceed 100 verses
                    errors.append(f"Probe 6 warning: Abnormally large reading '{cit}' ({len(verses)} verses)")
        except Exception as e:
            errors.append(f"Probe 6 failed: Unable to parse JSON response: {e}")
    elif status_v == 403 and "<Code>AccessDenied</Code>" in body:
        print("  Notice: CloudFront Function gate-readings not yet attached to /api/v1/readings* on this distribution.")
    else:
        errors.append(f"Probe 6 failed: Valid in-window query returned status {status_v} (expected 200 OK)")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Audit copyright non-leakage for PWC.")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist", help="Path to dist directory")
    default_auth = os.environ.get("HTTP_AUTH")
    if not default_auth:
        user = os.environ.get("AUTH_USER") or os.environ.get("BASIC_AUTH_USER")
        pw = os.environ.get("AUTH_PASSWORD") or os.environ.get("BASIC_AUTH_PASSWORD")
        if user and pw:
            default_auth = f"{user}:{pw}"

    parser.add_argument("--auth", type=str, default=default_auth, help="HTTP Basic Auth (user:pass)")
    args = parser.parse_args()
    all_errors = []

    # 1. Dist audit
    print(f"Auditing static build in: {args.dist_dir}")
    dist_errors = audit_dist(args.dist_dir)
    if dist_errors:
        print("  FAIL: Static dist audit found leaks:")
        for e in dist_errors:
            print(f"    - {e}")
        all_errors.extend(dist_errors)
    else:
        print("  PASS: Static dist contains no unauthorized copyrighted files.")

    # 2. Live CDN probes (if URL provided)
    if args.url:
        cdn_errors = audit_live_cdn(args.url, auth=args.auth)
        if cdn_errors:
            print("  FAIL: Live CDN probes detected vulnerabilities:")
            for e in cdn_errors:
                print(f"    - {e}")
            all_errors.extend(cdn_errors)
        else:
            print("  PASS: All live CDN probes passed.")

    if all_errors:
        sys.exit(1)

    print("\nCopyright Non-Leakage Audit passed successfully.")


if __name__ == "__main__":
    main()
