#!/usr/bin/env python3
"""
server.py  —  IB Exam Booklet Generator Server
Serves index.html, proxies Claude API, and generates proper IB-style PDFs
using generator.py (ReportLab + DejaVu fonts, zero black boxes).
"""

import json, urllib.request, urllib.error, os, io, zipfile, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))

# ── Find pre-built PDFs ───────────────────────────────────────────
def find_pdf(prefix):
    for fname in sorted(os.listdir(BASE)):
        if fname.startswith(prefix) and fname.endswith('.pdf'):
            return os.path.join(BASE, fname)
    return None

QP_FILE = find_pdf("IB_Practice_QP") or os.path.join(BASE, "IB_Practice_QP.pdf")
MS_FILE = find_pdf("IB_Practice_MS") or os.path.join(BASE, "IB_Practice_MS.pdf")

print(f"QP: {QP_FILE}  exists={os.path.exists(QP_FILE)}")
print(f"MS: {MS_FILE}  exists={os.path.exists(MS_FILE)}")

# ── In-memory cache for generated PDFs (keyed by session_id) ─────
_cache = {}   # { session_id: {'qp': bytes, 'ms': bytes, 'done': bool, 'error': str} }
_cache_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  [{args[1]}] {self.path}")

    # ── CORS pre-flight ───────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── GET routes ────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split('?')[0]

        if path in ('/', '/index.html'):
            self._serve_file('index.html', 'text/html; charset=utf-8')

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
            self.send_response(200); self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers(); self.wfile.write(body)

        elif path == '/download/qp':
            self._serve_pdf(QP_FILE, 'IB_Practice_QP.pdf')

        elif path == '/download/ms':
            self._serve_pdf(MS_FILE, 'IB_Practice_MS.pdf')

        elif path == '/download/all':
            self._serve_zip(QP_FILE, MS_FILE)

        # Fetch generated PDF from cache: /download/gen/<session_id>/<qp|ms>
        elif path.startswith('/download/gen/'):
            parts = path.split('/')  # ['', 'download', 'gen', session_id, 'qp|ms']
            if len(parts) == 5:
                sid, ftype = parts[3], parts[4]
                with _cache_lock:
                    entry = _cache.get(sid)
                if entry and entry.get('done'):
                    data = entry.get(ftype)
                    if data:
                        fname = f'IB_Practice_{ftype.upper()}_generated.pdf'
                        self.send_response(200); self._cors()
                        self.send_header('Content-Type', 'application/pdf')
                        self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
                        self.send_header('Content-Length', len(data))
                        self.end_headers(); self.wfile.write(data)
                        return
                self._json(404, {'error': 'Not found or not ready'})
            else:
                self.send_response(404); self.end_headers()

        # Poll status: /gen-status/<session_id>
        elif path.startswith('/gen-status/'):
            sid = path.split('/')[-1]
            with _cache_lock:
                entry = _cache.get(sid, {})
            self._json(200, {
                'done':  entry.get('done', False),
                'error': entry.get('error', None),
                'has_qp': bool(entry.get('qp')),
                'has_ms': bool(entry.get('ms')),
            })

        else:
            self.send_response(404); self.end_headers()

    # ── POST routes ───────────────────────────────────────────────
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(length)

        # Proxy to Anthropic
        if self.path == '/api/claude':
            key = self.headers.get('X-Api-Key', os.environ.get('ANTHROPIC_API_KEY', ''))
            if not key:
                self._json(400, {'error': 'No API key'}); return
            req = urllib.request.Request(
                'https://api.anthropic.com/v1/messages', data=body_bytes,
                headers={'Content-Type': 'application/json',
                         'x-api-key': key,
                         'anthropic-version': '2023-06-01'},
                method='POST')
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    resp = r.read()
                self.send_response(200); self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(resp)
            except urllib.error.HTTPError as e:
                self.send_response(e.code); self._cors()
                self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(e.read())

        # Generate IB-quality PDFs using generator.py
        elif self.path == '/api/generate':
            try:
                params = json.loads(body_bytes.decode())
            except Exception:
                self._json(400, {'error': 'Bad JSON'}); return

            import uuid
            sid = str(uuid.uuid4())[:8]
            with _cache_lock:
                _cache[sid] = {'done': False, 'error': None, 'qp': None, 'ms': None}

            # Kick off generation in background thread
            t = threading.Thread(target=_generate_worker,
                                 args=(sid, params), daemon=True)
            t.start()

            self._json(202, {'session_id': sid,
                             'poll_url': f'/gen-status/{sid}',
                             'download_qp': f'/download/gen/{sid}/qp',
                             'download_ms': f'/download/gen/{sid}/ms'})

        else:
            self.send_response(404); self.end_headers()

    # ── Helpers ───────────────────────────────────────────────────
    def _serve_file(self, filename, content_type):
        try:
            with open(os.path.join(BASE, filename), 'rb') as f:
                content = f.read()
            self.send_response(200); self._cors()
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.end_headers(); self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _serve_pdf(self, filepath, download_name):
        if not filepath or not os.path.exists(filepath):
            self._json(404, {'error': f'{download_name} not found'}); return
        with open(filepath, 'rb') as f:
            content = f.read()
        self.send_response(200); self._cors()
        self.send_header('Content-Type', 'application/pdf')
        self.send_header('Content-Disposition', f'attachment; filename="{download_name}"')
        self.send_header('Content-Length', len(content))
        self.end_headers(); self.wfile.write(content)

    def _serve_zip(self, qp_path, ms_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fpath, fname in [(qp_path, 'IB_Practice_QP.pdf'),
                                  (ms_path, 'IB_Practice_MS.pdf')]:
                if fpath and os.path.exists(fpath):
                    zf.write(fpath, fname)
        buf.seek(0); content = buf.read()
        self.send_response(200); self._cors()
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Disposition', 'attachment; filename="IB_Practice_Papers.zip"')
        self.send_header('Content-Length', len(content))
        self.end_headers(); self.wfile.write(content)

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code); self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers(); self.wfile.write(body)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type,X-Api-Key')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')


def _generate_worker(sid, params):
    """Background thread: build QP + MS PDFs and store in cache."""
    try:
        from generator import build_qp, build_ms
        session = params.get('session', 'Practice Paper')
        subject = params.get('subject', 'Chemistry HL')

        qp_buf = build_qp(session_label=session, subject=subject)
        ms_buf = build_ms(session_label=session, subject=subject)

        with _cache_lock:
            _cache[sid]['qp'] = qp_buf.read()
            _cache[sid]['ms'] = ms_buf.read()
            _cache[sid]['done'] = True

        print(f"  [GEN] Session {sid} done.")
    except Exception as e:
        print(f"  [GEN] Session {sid} ERROR: {e}")
        import traceback; traceback.print_exc()
        with _cache_lock:
            _cache[sid]['error'] = str(e)
            _cache[sid]['done'] = True


print(f"✅  Server running on http://localhost:{PORT}")
HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
