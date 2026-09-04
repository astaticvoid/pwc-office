#!/usr/bin/env python3
"""
tools/local_server.py
Local development server for PWC with /api/v1/readings support and /private/* blocking,
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

        # 2. Handle /api endpoints (mirrors gate-readings.js behavior)
        if parsed.path.startswith("/api/"):
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) == 2:
                resource = path_parts[1]
                expected_ver = "v1" if resource == "readings" else "v2"
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Missing API version in path. Expected /api/{expected_ver}/{resource}"}).encode("utf-8"))
                return
            elif len(path_parts) == 3 and path_parts[0] == "api":
                version = path_parts[1]
                resource = path_parts[2]
                if resource == "readings" and version != "v1":
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Unsupported API version: {version}"}).encode("utf-8"))
                    return
                elif resource == "calendar" and version != "v2":
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Unsupported API version: {version}"}).encode("utf-8"))
                    return
                elif resource not in ("readings", "calendar"):
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Invalid endpoint path."}).encode("utf-8"))
                    return
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Invalid endpoint path."}).encode("utf-8"))
                return

            qs = urllib.parse.parse_qs(parsed.query)

            if resource == "readings":
                date_list = qs.get("date", [])
                trans_list = qs.get("translation", ["nrsvue"])

                if not date_list or not date_list[0]:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing or invalid date parameter (YYYY-MM-DD)"}).encode("utf-8"))
                    return

                date_str = date_list[0]
                translation = trans_list[0]

                if translation != "nrsvue":
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Unsupported translation. Only nrsvue is served via this endpoint."}).encode("utf-8"))
                    return

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

                sliced_path = ROOT / ".build" / "private" / "readings" / version / translation / f"{date_str}.json"
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

            if resource == "calendar":
                trans_list = qs.get("translation", ["nrsvue"])
                req_trans = trans_list[0] if trans_list else "nrsvue"
                if req_trans not in ("nrsvue", "kjv"):
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Unsupported translation. Supported: nrsvue, kjv"}).encode("utf-8"))
                    return

                now_utc = datetime.now(timezone.utc)

                def get_diff(d_str):
                    t_dt = datetime.strptime(d_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    return abs((t_dt.date() - now_utc.date()).days)

                # Batch query
                start_list = qs.get("start", [])
                end_list = qs.get("end", [])
                if start_list or end_list:
                    if not (start_list and end_list and start_list[0] and end_list[0]):
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Both start and end date parameters (YYYY-MM-DD) are required for batch queries."}).encode("utf-8"))
                        return

                    start_str = start_list[0]
                    end_str = end_list[0]
                    if start_str > end_str:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Invalid date range: start date must be <= end date."}).encode("utf-8"))
                        return

                    try:
                        s_diff = get_diff(start_str)
                        e_diff = get_diff(end_str)
                    except ValueError:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Invalid date format (YYYY-MM-DD)"}).encode("utf-8"))
                        return

                    use_trans = req_trans
                    if use_trans == "nrsvue" and (s_diff > 31 or e_diff > 31):
                        use_trans = "kjv"

                    batch_path = ROOT / ".build" / "private" / "calendar" / "v2" / use_trans / "batch" / f"{start_str}_{end_str}.json"
                    if batch_path.exists():
                        data = batch_path.read_bytes()
                    else:
                        # Fallback: assemble dynamically from day files
                        cur_dt = datetime.strptime(start_str, "%Y-%m-%d")
                        stop_dt = datetime.strptime(end_str, "%Y-%m-%d")
                        days_dict = {}
                        from datetime import timedelta
                        while cur_dt <= stop_dt:
                            cur_str = cur_dt.strftime("%Y-%m-%d")
                            day_p = ROOT / ".build" / "private" / "calendar" / "v2" / use_trans / f"{cur_str}.json"
                            if day_p.exists():
                                days_dict[cur_str] = json.loads(day_p.read_text(encoding="utf-8"))
                            cur_dt += timedelta(days=1)
                        data = json.dumps({"start": start_str, "end": end_str, "days": days_dict}).encode("utf-8")

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
                    return

                # Single date query
                date_list = qs.get("date", [])
                if not date_list or not date_list[0]:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Missing or invalid date parameter (YYYY-MM-DD) or date range (start & end)."}).encode("utf-8"))
                    return

                date_str = date_list[0]
                try:
                    diff_days = get_diff(date_str)
                except ValueError:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Invalid date format (YYYY-MM-DD)"}).encode("utf-8"))
                    return

                use_trans = req_trans
                if use_trans == "nrsvue" and diff_days > 31:
                    use_trans = "kjv"

                day_path = ROOT / ".build" / "private" / "calendar" / "v2" / use_trans / f"{date_str}.json"
                if not day_path.exists():
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"No calendar entry found for {date_str}"}).encode("utf-8"))
                    return

                data = day_path.read_bytes()
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
