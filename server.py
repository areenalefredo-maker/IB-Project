#!/usr/bin/env python3
"""
IB Exam Generator - Local Proxy Server
Run this once, then open index.html in your browser.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, urllib.request, urllib.error, os, sys

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            key = self.headers.get("X-Api-Key", API_KEY)
            if not key:
                self.send_response(400)
                self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error":"No API key provided"}).encode())
                return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01"
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp_body = r.read()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(resp_body)
            except urllib.error.HTTPError as e:
                err_body = e.read()
                self.send_response(e.code)
                self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers()
                self.wfile.write(err_body)
        else:
            self.send_response(404)
            self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","Content-Type,X-Api-Key")
        self.send_header("Access-Control-Allow-Methods","POST,OPTIONS")

PORT = 5050
print(f"""
╔══════════════════════════════════════════╗
║   IB Exam Generator - Proxy Server       ║
╠══════════════════════════════════════════╣
║  Server running at http://localhost:{PORT}  ║
║  Open index.html in your browser         ║
║  Press Ctrl+C to stop                    ║
╚══════════════════════════════════════════╝
""")
HTTPServer(("localhost", PORT), Handler).serve_forever()
