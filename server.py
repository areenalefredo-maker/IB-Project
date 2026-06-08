#!/usr/bin/env python3
import json, urllib.request, urllib.error, os, io, zipfile, shutil, tempfile, subprocess, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Auto-install PyMuPDF if not present
try:
    import fitz
except ImportError:
    print("Installing PyMuPDF...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyMuPDF==1.24.0", "--quiet"])
    print("PyMuPDF installed successfully.")

try:
    import fitz
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False
    print("WARNING: PyMuPDF not installed.")

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))

def find_pdf(prefix):
    for fname in os.listdir(BASE):
        if fname.startswith(prefix) and fname.endswith('.pdf'):
            return os.path.join(BASE, fname)
    return None

QP_FILE = find_pdf("IB_Practice_QP") or os.path.join(BASE, "IB_Practice_QP_final.pdf")
MS_FILE = find_pdf("IB_Practice_MS") or os.path.join(BASE, "IB_Practice_MS_final.pdf")

print(f"QP: {QP_FILE}  exists={os.path.exists(QP_FILE)}")
print(f"MS: {MS_FILE}  exists={os.path.exists(MS_FILE)}")

# ── Default replacements (~30% content change) ────────────────────────────
DEFAULT_QP_REPS = [
    (2,  "magnesium hydroxide,",        "aluminium hydroxide,"),
    (2,  "Mg(OH)",                       "Al(OH)"),
    (2,  "1.24",                         "1.62"),
    (2,  "of 0.100 mol dm",             "of 0.120 mol dm"),
    (2,  "sulfuric acid, which was",     "nitric acid, which was"),
    (2,  "with Mg(OH)",                 "with Al(OH)"),
    (2,  "20.80 cm",                    "22.40 cm"),
    (2,  "0.1133 mol dm",               "0.1050 mol dm"),
    (2,  "that reacted with Mg(OH)",    "that reacted with Al(OH)"),
    (3,  "Mg(OH)",                       "Al(OH)"),
    (3,  "magnesium hydroxide",          "aluminium hydroxide"),
    (3,  "1.24",                         "1.62"),
    (4,  "calcium carbonate",            "magnesium carbonate"),
    (4,  "hydrochloric acid is added",   "sulfuric acid is added"),
    (5,  "ethanoic acid of the same",    "propanoic acid of the same"),
    (5,  "in place of hydrochloric acid","in place of sulfuric acid"),
    (6,  "ethanoic acid with",           "propanoic acid with"),
    (6,  "aqueous ethanoic acid.",       "aqueous propanoic acid."),
    (6,  "= 1.74 ",                      "= 1.34 "),
    (7,  "calcium carbonate.",           "zinc carbonate."),
    (7,  "sodium ethanoate is basic",    "sodium propanoate is basic"),
    (9,  "radius of Na",                 "radius of K"),
    (11, "bromate ions, BrO",            "chlorate ions, ClO"),
    (11, "oxidize iodide ions,",         "oxidize iron(II) ions,"),
    (11, "514 kJ",                       "412 kJ"),
    (14, "0.282",                        "0.500"),
    (15, "25.0 °C to 35 °C",            "20.0 °C to 30 °C"),
    (16, "NH",                           "PH"),
    (19, "propan-1-ol",                  "butan-1-ol"),
    (21, "C5H10O",                       "C6H12O"),
]

DEFAULT_MS_REPS = [
    (3,  "0.00500/5.00",               "0.00600/6.00"),
    (3,  "Mg(OH)",                      "Al(OH)"),
    (3,  "1.24 g",                      "1.62 g"),
    (3,  "0.02080",                     "0.02240"),
    (3,  "0.1133",                      "0.1050"),
    (3,  "0.001178/1.178",              "0.002352/2.352"),
    (3,  "0.00382/3.82",               "0.003648/3.648"),
    (3,  "58.33 g mol",                 "78.00 g mol"),
    (3,  "0.223",                       "0.0948"),
    (3,  "18.0",                        "5.85"),
    (5,  "ethanoic acid",               "propanoic acid"),
    (6,  "ethanoic acid",               "propanoic acid"),
    (6,  "ethanoate",                   "propanoate"),
    (6,  "1.74  10",                    "1.34  10"),
    (6,  "1.32  10",                    "1.158  10"),
    (6,  "2.88",                        "2.94"),
    (11, "BrO",                         "ClO"),
    (11, "514  10",                     "412  10"),
    (11, "0.888",                       "0.711"),
    (11, "1.43",                        "1.48"),
    (14, "0.282",                       "0.500"),
    (15, "52.9",                        "75.8"),
    (15, "308 K",                       "303 K"),
    (15, "298 K",                       "293 K"),
]

# ── PDF modifier helpers ──────────────────────────────────────────────────
def _text_w(text, fontname, size):
    try:
        return fitz.Font(fontname).text_length(text, fontsize=size)
    except:
        return len(text) * size * 0.55

def _fit(text, avail, fontname, size, min_s=7.5):
    s = size
    while s >= min_s:
        if _text_w(text, fontname, s) <= avail:
            return text, s
        s -= 0.4
    while len(text) > 3 and _text_w(text+"...", fontname, min_s) > avail:
        text = text[:-1]
    return text+"...", min_s

def _span_at(page, rect):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for span in line["spans"]:
                if fitz.Rect(span["bbox"]).intersects(rect):
                    return span
    return None

def _color(c):
    return (((c>>16)&0xFF)/255.0, ((c>>8)&0xFF)/255.0, (c&0xFF)/255.0)

def _font(face):
    if "Bold" in face and "Italic" in face: return "hebo"
    if "Bold" in face: return "hebo"
    if "Italic" in face: return "hebi"
    return "helv"

# ── PDF modifier ──────────────────────────────────────────────────────────
def modify_pdf(input_bytes, replacements):
    if not PYMUPDF_OK:
        return input_bytes

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(input_bytes); tmp_path = tmp.name

    doc = fitz.open(tmp_path)
    PAGE_M = 8  # margin from page edge pts

    for page_num, old, new in replacements:
        if page_num < 1 or page_num > len(doc): continue
        page = doc[page_num - 1]
        pr   = page.rect
        hits = page.search_for(old)

        for rect in hits:
            span = _span_at(page, rect)
            if span:
                orig_size = span["size"]
                color     = _color(span["color"])
                fontname  = _font(span["font"])
            else:
                orig_size, color, fontname = 11.0, (0,0,0), "helv"

            # Available width = original span width + small buffer
            avail = rect.width + 4
            fitted, size = _fit(new, avail, fontname, orig_size)

            # White-out box (covers original text fully)
            w_rect = fitz.Rect(
                rect.x0 - 1, rect.y0 - 1,
                min(rect.x0 + _text_w(fitted, fontname, size) + 4, pr.x1 - PAGE_M),
                rect.y1 + 2
            )
            page.draw_rect(w_rect, color=(1,1,1), fill=(1,1,1), overlay=True)

            # Baseline point
            pt = fitz.Point(rect.x0, rect.y1 - 2)

            # Clamp x so text stays on page
            if pt.x + _text_w(fitted, fontname, size) > pr.x1 - PAGE_M:
                fitted, size = _fit(fitted, pr.x1 - PAGE_M - pt.x - 2, fontname, size)

            page.insert_text(pt, fitted,
                fontname=fontname, fontsize=size,
                color=color, overlay=True)

        if hits:
            print(f"  p{page_num}: '{old[:25]}' -> '{new[:25]}' ({len(hits)}x, sz={orig_size:.1f})")

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    os.unlink(tmp_path)
    return buf.getvalue()

# ── HTTP Handler ──────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  {args[0]} {args[1]}")

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            self._serve_file('index.html', 'text/html')
        elif path == '/download/qp':
            self._serve_pdf(QP_FILE, 'IB_Practice_QP.pdf')
        elif path == '/download/ms':
            self._serve_pdf(MS_FILE, 'IB_Practice_MS.pdf')
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
                "pymupdf": PYMUPDF_OK,
            }).encode()
            self.send_response(200); self._cors()
            self.send_header('Content-Type','application/json')
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = self.path

        # ── Anthropic proxy ────────────────────────────────────────────
        if path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            key    = self.headers.get("X-Api-Key", os.environ.get("ANTHROPIC_API_KEY",""))
            if not key: self._json(400,{"error":"No API key"}); return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"Content-Type":"application/json","x-api-key":key,
                         "anthropic-version":"2023-06-01"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as r: resp = r.read()
                self.send_response(200); self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers(); self.wfile.write(resp)
            except urllib.error.HTTPError as e:
                self.send_response(e.code); self._cors()
                self.send_header("Content-Type","application/json")
                self.end_headers(); self.wfile.write(e.read())

        # ── Generate PDF (accepts uploaded file via multipart) ─────────
        elif path == "/api/generate-pdf":
            try:
                content_type = self.headers.get('Content-Type','')

                if 'multipart/form-data' in content_type:
                    # User uploaded their own PDF
                    length = int(self.headers.get("Content-Length", 0))
                    body   = self.rfile.read(length)

                    # Parse multipart
                    boundary = content_type.split('boundary=')[1].encode()
                    parts    = body.split(b'--' + boundary)
                    pdf_bytes = None
                    pdf_type  = 'qp'

                    for part in parts:
                        if b'name="type"' in part:
                            pdf_type = part.split(b'\r\n\r\n')[1].split(b'\r\n')[0].decode().strip()
                        if b'name="file"' in part and b'filename=' in part:
                            pdf_bytes = part.split(b'\r\n\r\n', 1)[1].rsplit(b'\r\n', 1)[0]

                    if not pdf_bytes:
                        self._json(400, {"error": "No file uploaded"}); return

                    reps = DEFAULT_QP_REPS if pdf_type == 'qp' else DEFAULT_MS_REPS
                    print(f"Processing uploaded {pdf_type.upper()} ({len(pdf_bytes)//1024} KB)")
                    result = modify_pdf(pdf_bytes, reps)

                else:
                    # JSON body — use server's own PDF files
                    length  = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(length))
                    pdf_type = payload.get("type", "qp")
                    src_file = QP_FILE if pdf_type == 'qp' else MS_FILE

                    if not os.path.exists(src_file):
                        self._json(404, {"error": f"{pdf_type.upper()} file not found on server"}); return

                    with open(src_file, 'rb') as f:
                        pdf_bytes = f.read()

                    reps   = DEFAULT_QP_REPS if pdf_type == 'qp' else DEFAULT_MS_REPS
                    result = modify_pdf(pdf_bytes, reps)

                fname = f'IB_Practice_{"QP" if pdf_type=="qp" else "MS"}_modified.pdf'
                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", len(result))
                self.end_headers(); self.wfile.write(result)

            except Exception as e:
                import traceback; traceback.print_exc()
                self._json(500, {"error": str(e)})

        else:
            self.send_response(404); self.end_headers()

    def _serve_file(self, filename, content_type):
        try:
            with open(os.path.join(BASE, filename), 'rb') as f: content = f.read()
            self.send_response(200); self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content))
            self.end_headers(); self.wfile.write(content)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _serve_pdf(self, filepath, download_name):
        if not filepath or not os.path.exists(filepath):
            self._json(404, {"error": f"{download_name} not found"}); return
        with open(filepath, 'rb') as f: content = f.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", len(content))
        self.end_headers(); self.wfile.write(content)

    def _serve_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as zf:
            for fpath, fname in [(QP_FILE,'IB_Practice_QP.pdf'),(MS_FILE,'IB_Practice_MS.pdf')]:
                if fpath and os.path.exists(fpath): zf.write(fpath, fname)
        buf.seek(0); content = buf.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type","application/zip")
        self.send_header("Content-Disposition",'attachment; filename="IB_Practice_Papers.zip"')
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
