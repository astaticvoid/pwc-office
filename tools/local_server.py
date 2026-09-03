#!/usr/bin/env python3
"""
tools/local_server.py
Local development server for PWC with /api/readings support and /private/* blocking,
matching CloudFront edge gate-readings.js behavior (ADR 0024).

Usage:
  python3 tools/local_server.py [port] [--directory web]
"""

import argparse
import http.server
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent


class PwcDevHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for local testing & Capacitor WebViews
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # 1. Block direct access to /private/ and un-gated copyrighted translations
        if parsed.path.startswith("/private/") or parsed.path.startswith("/data/translations/nrsvue"):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode("utf-8"))
            return

        # 2. Handle /api/readings endpoint (mirrors gate-readings.js behavior)
        if parsed.path == "/api/readings":
            qs = urllib.parse.parse_qs(parsed.query)
            date_list = qs.get("date", [])
            trans_list = qs.get("translation", ["nrsvue"])

            if not date_list or not date_list[0]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing or invalid date parameter"}).encode("utf-8"))
                return

            date_str = date_list[0]
            translation = trans_list[0]

            # Path traversal & translation allowlist check
            if translation != "nrsvue":
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unsupported translation"}).encode("utf-8"))
                return

            # Temporal gate check (±31 days in UTC)
            try:
                target_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid date format (YYYY-MM-DD)"}).encode("utf-8"))
                return

            now_utc = datetime.now(timezone.utc)
            diff_days = abs((target_dt.date() - now_utc.date()).days)

            if diff_days > 31:
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "Temporal restriction: Readings only available within ±30 days of current date.",
                    "requestedDate": date_str,
                    "daysDifference": diff_days
                }).encode("utf-8"))
                return

            # Fetch from .build/private/readings/
            sliced_path = ROOT / ".build" / "private" / "readings" / translation / f"{date_str}.json"
            if not sliced_path.exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"No readings found for {date_str}"}).encode("utf-8"))
                return

            data = sliced_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)
            return

        # 3. Fall back to standard static file serving
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="PWC Local Development Server")
    parser.add_argument("port", nargs="?", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--directory", "-d", default="web", help="Directory to serve static files from (default: web)")
    args = parser.parse_args()

    serve_dir = Path(args.directory).resolve()

    def handler_factory(*h_args, **h_kwargs):
        return PwcDevHandler(*h_args, directory=str(serve_dir), **h_kwargs)

    server = http.server.ThreadingHTTPServer(("", args.port), handler_factory)
    print(f"Serving HTTP on 0.0.0.0 port {args.port} (serving {serve_dir}) ...", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
