#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, urllib.request, urllib.error, os

PORT = int(os.environ.get("PORT", 8080))

SYSTEM_PROMPT = """You are an IB exam question rewriter. Your ONLY job is:
1. Keep the EXACT same question structure, format, marks, command terms, and layout
2. Only change: specific names, organisms, chemicals, substances, scenarios, numbers, contexts
3. Do NOT change: question format, number of parts, marks allocation, command terms (Define/Explain/Evaluate etc)
4. Update the mark scheme answers to match ONLY the changed words/context
5. Keep everything else identical - same difficulty, same skills tested, same structure
Always respond with valid JSON only - no markdown, no backticks."""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/' or path == '/index.html':
            self._serve_file('index.html', 'text/html')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            
            try:
                payload = json.loads(body)
                payload['system'] = SYSTEM_PROMPT
                payload['model'] = 'claude-sonnet-4-5'
                body = json.dumps(payload).encode()
            except:
                pass

            key = self.headers.get("X-Api-Key", os.environ.get("ANTHROPIC_API_KEY", ""))
            if not key:
                self._json_response(400, {"error": "No API key provided"})
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
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(resp_body)
            except urllib.error.HTTPError as e:
                err_body = e.read()
                self.send_response(e.code)
                self._cors()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err_body)
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Api-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

print(f"Server running on port {PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
