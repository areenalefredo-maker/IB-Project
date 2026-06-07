#!/usr/bin/env python3
import json, urllib.request, urllib.error, os, io, zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))

def find_pdf(prefix):
    """Find any PDF starting with prefix — handles _final, (2), (5), etc."""
    for fname in os.listdir(BASE):
        if fname.startswith(prefix) and fname.endswith('.pdf'):
            return os.path.join(BASE, fname)
    return None

QP_FILE = find_pdf("IB_Practice_QP") or os.path.join(BASE, "IB_Practice_QP.pdf")
MS_FILE = find_pdf("IB_Practice_MS") or os.path.join(BASE, "IB_Practice_MS.pdf")

print(f"QP: {QP_FILE}  exists={os.path.exists(QP_FILE)}")
print(f"MS: {MS_FILE}  exists={os.path.exists(MS_FILE)}")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]

        if path in ('/', '/index.html'):
            self._serve_file('index.html', 'text/html')
        elif path == '/download/qp':
            self._serve_pdf(QP_FILE, 'IB_Practice_QP_final.pdf')
        elif path == '/download/ms':
            self._serve_pdf(MS_FILE, 'IB_Practice_MS_final.pdf')
        elif path == '/download/all':
            self._serve_zip()
        elif path == '/status':
            qp_ok = os.path.exists(QP_FILE)
            ms_ok = os.path.exists(MS_FILE)
            body = json.dumps({
                "qp": qp_ok, "ms": ms_ok,
                "qp_file": os.path.basename(QP_FILE),
                "ms_file": os.path.basename(MS_FILE),
                "qp_size": os.path.getsize(QP_FILE) if qp_ok else 0,
                "ms_size": os.path.getsize(MS_FILE) if ms_ok else 0,
            }).encode()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            key = self.headers.get("X-Api-Key", os.environ.get("ANTHROPIC_API_KEY", ""))
            if not key:
                self._json(400, {"error": "No API key"}); return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"Content-Type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"},
                method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp = r.read()
                self.send_response(200); self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers(); self.wfile.write(resp)
            except urllib.error.HTTPError as e:
                self.send_response(e.code); self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers(); self.wfile.write(e.read())
        else:
            self.send_response(404); self.end_headers()

    def _serve_file(self, filename, content_type):
        try:
            with open(os.path.join(BASE, filename), 'rb') as f:
                content = f.read()
            self.send_response(200); self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content))
            self.end_headers(); self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _serve_pdf(self, filepath, download_name):
        if not filepath or not os.path.exists(filepath):
            self._json(404, {"error": f"{download_name} not found on server"}); return
        with open(filepath, 'rb') as f:
            content = f.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", len(content))
        self.end_headers(); self.wfile.write(content)

    def _serve_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fpath, fname in [
                (QP_FILE, 'IB_Practice_QP_final.pdf'),
                (MS_FILE, 'IB_Practice_MS_final.pdf')
            ]:
                if fpath and os.path.exists(fpath):
                    zf.write(fpath, fname)
        buf.seek(0); content = buf.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="IB_Practice_Papers.zip"')
        self.send_header("Content-Length", len(content))
        self.end_headers(); self.wfile.write(content)

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code); self._cors()
        self.send_header("Content-Type","application/json")
        self.end_headers(); self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","Content-Type,X-Api-Key")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

print(f"Server running on port {PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
