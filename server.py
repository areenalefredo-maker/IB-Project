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

# ── PDF modifier ──────────────────────────────────────────────────────────
TS = '\u2009'  # thin space used in IB PDFs

import fitz, io, tempfile, os

TS = '\u2009'  # thin space

def _whole_line(page, line_key, new_content, font_override=None):
    """Replace entire line containing line_key with new_content."""
    norm_key = line_key.replace(TS,' ')
    for b in page.get_text("dict")["blocks"]:
        if b["type"]!=0: continue
        for line in b["lines"]:
            lt = "".join(s["text"] for s in line["spans"])
            if norm_key not in lt.replace(TS,' '): continue
            lr = fitz.Rect(line["bbox"])
            sp = line["spans"][0]
            size = font_override or sp["size"]
            c = sp["color"]
            r,g,b_ = ((c>>16)&0xFF),((c>>8)&0xFF),(c&0xFF)
            ff = "Arial Bold" if "Bold" in sp["font"] else "Arial"
            page.add_redact_annot(lr)
            page.apply_redactions(images=0)
            ins = fitz.Rect(lr.x0, lr.y0-1, lr.x1+10, lr.y1+2)
            html = (f'<p style="margin:0;padding:0">'
                    f'<span style="font-family:{ff};font-size:{size}pt;'
                    f'color:rgb({r},{g},{b_})">{new_content}</span></p>')
            page.insert_htmlbox(ins, html, scale_low=0.85)
            return True
    return False

def _span_only(page, line_key, span_text, new_text):
    """Replace a specific span (not subscript) within a line."""
    norm_key = line_key.replace(TS,' ')
    for b in page.get_text("dict")["blocks"]:
        if b["type"]!=0: continue
        for line in b["lines"]:
            lt = "".join(s["text"] for s in line["spans"])
            if norm_key not in lt.replace(TS,' '): continue
            to_del = []
            to_write = []
            for span in line["spans"]:
                st = span["text"].replace(TS,' ')
                norm_st2 = span_text.replace(TS,' ')
                if norm_st2 == st or (norm_st2 in st and new_text is not None):
                    to_del.append(dict(span))
                    if new_text:
                        to_write.append((dict(span), st.replace(norm_st2, new_text, 1)))
            if not to_del: continue
            for s in to_del:
                page.add_redact_annot(fitz.Rect(s["bbox"]))
            page.apply_redactions(images=0)
            for span, ntxt in to_write:
                if ntxt:
                    sr=fitz.Rect(span["bbox"]); pr=page.rect
                    size=span["size"]; c=span["color"]
                    r,g,b_=((c>>16)&0xFF),((c>>8)&0xFF),(c&0xFF)
                    ff="Arial Bold" if "Bold" in span["font"] else "Arial"
                    try: new_w=fitz.Font("helv").text_length(ntxt,fontsize=size)
                    except: new_w=len(ntxt)*size*0.55
                    ins=fitz.Rect(sr.x0,sr.y0-1,min(sr.x0+new_w+8,pr.x1-5),sr.y1+2)
                    html=(f'<p style="margin:0;padding:0">'
                          f'<span style="font-family:{ff};font-size:{size}pt;'
                          f'color:rgb({r},{g},{b_})">{ntxt}</span></p>')
                    page.insert_htmlbox(ins,html,scale_low=0.85)
            return True
    return False

def _apply_qp(doc):
    # Page 2
    p = doc[1]
    _whole_line(p, "active ingredient magnesium",
        "A student determined the percentage of the active ingredient aluminium hydroxide,")
    _whole_line(p, "in a 1.24"+TS+"g",
        "Al(OH)\u2083, in a 1.62\u2009g antacid tablet.")
    _whole_line(p, "0.100"+TS+"mol"+TS+"dm",
        "The antacid tablet was added to 50.00\u2009cm\u00b3 of 0.120\u2009mol\u2009dm\u207b\u00b3 nitric acid, which was")
    _whole_line(p, "Calculate the amount, in mol, of H",
        "Calculate the amount, in mol, of HNO\u2083.")
    _whole_line(p, "Formulate the equation for the reaction of H",
        "Formulate the equation for the reaction of HNO\u2083 with Al(OH)\u2083.")
    _whole_line(p, "20.80"+TS+"cm",
        "The excess nitric acid required 22.40\u2009cm\u00b3 of 0.1050\u2009mol\u2009dm\u207b\u00b3 NaOH for neutralization.")
    _whole_line(p, "that reacted with Mg(OH)",
        "Calculate the amount of HNO\u2083 that reacted with Al(OH)\u2083.")
    # Page 3
    p = doc[2]
    _whole_line(p, "Determine the mass of Mg(OH)",
        "Determine the mass of Al(OH)\u2083 in the antacid tablet.")
    _span_only(p, "magnesium hydroxide in the",
        "magnesium hydroxide in the", "aluminium hydroxide in the")
    _span_only(p, "1.24"+TS+"g antacid tablet to three",
        "1.24", "1.62")
    # Page 4
    p = doc[3]
    _span_only(p, "hydrochloric acid is added to lumps of calc",
        "hydrochloric acid is added to lumps of calc",
        "sulfuric acid is added to lumps of magne")
    _span_only(p, "crushed calcium carbonate",
        "crushed calcium carbonate", "powdered magnesium carbonate")
    # Page 5
    p = doc[4]
    _span_only(p, "ethanoic acid of the same",
        "ethanoic acid of the same", "propanoic acid of the same")
    _span_only(p, "in place of hydrochloric acid",
        "in place of hydrochloric acid", "in place of sulfuric acid.")
    # Page 6
    p = doc[5]
    _span_only(p, "ethanoic acid with 0.100",
        "ethanoic acid with 0.100", "propanoic acid with 0.100")
    _span_only(p, "aqueous ethanoic acid.",
        "aqueous ethanoic acid.", "aqueous propanoic acid.")
    _span_only(p, "= 1.74", "1.74", "1.34")
    # Page 7
    p = doc[6]
    _span_only(p, "sodium ethanoate is basic",
        "sodium ethanoate is basic", "sodium propanoate is basic")
    _span_only(p, "calcium carbonate.",
        "calcium carbonate.", "zinc carbonate.")
    # Page 9
    p = doc[8]
    _span_only(p, "radius of Na", "radius of Na", "radius of K")
    # Page 11
    p = doc[10]
    _span_only(p, "bromate ions, BrO", "bromate ions, BrO", "chlorate ions, ClO")
    _span_only(p, "oxidize iodide ions,", "oxidize iodide ions,", "oxidize iron(II) ions,")
    _span_only(p, "514"+TS+"kJ", "514", "412")
    # Page 14
    p = doc[13]
    _span_only(p, "is 0.282 at temperature", "0.282", "0.500")
    # Page 15
    p = doc[14]
    _whole_line(p, "25.0"+TS,
        "The rate constant for a reaction triples when the temperature is increased from 20.0\u2009\u00b0C to 30\u2009\u00b0C.")
    # Page 16
    p = doc[15]
    _span_only(p, "for the NH", "NH", "PH")
    # Page 19
    p = doc[18]
    _span_only(p, "propan-1-ol", "propan-1-ol", "butan-1-ol")
    # Page 21
    p = doc[20]
    _span_only(p, "C5H10O", "C5H10O", "C6H12O")

def _apply_ms(doc):
    p = doc[2]
    _span_only(p, "0.00500/5.00", "0.00500/5.00", "0.00600/6.00")
    _span_only(p, "Mg(OH)", "Mg(OH)", "Al(OH)")
    _span_only(p, "1.24"+TS+"g", "1.24", "1.62")
    _span_only(p, "0.02080", "0.02080", "0.02240")
    _span_only(p, "0.1133", "0.1133", "0.1050")
    _span_only(p, "0.001178", "0.001178/1.178", "0.002352/2.352")
    _span_only(p, "0.00382", "0.00382/3.82", "0.003648/3.648")
    _span_only(p, "58.33", "58.33", "78.00")
    _span_only(p, "0.223", "0.223", "0.0948")
    _span_only(p, "18.0", " 18.0", " 5.85")
    p = doc[4]
    _span_only(p, "ethanoic acid", "ethanoic acid", "propanoic acid")
    p = doc[5]
    _span_only(p, "ethanoic acid", "ethanoic acid", "propanoic acid")
    _span_only(p, "ethanoate", "ethanoate", "propanoate")
    _span_only(p, "1.74", "1.74", "1.34")
    _span_only(p, "1.32", "1.32", "1.158")
    _span_only(p, "2.88", "2.88", "2.94")
    p = doc[10]
    _span_only(p, "BrO", "BrO", "ClO")
    _span_only(p, "514", "514", "412")
    _span_only(p, "0.888", "0.888", "0.711")
    _span_only(p, "1.43", "1.43", "1.48")
    p = doc[13]
    _span_only(p, "0.282", "0.282", "0.500")
    p = doc[14]
    _span_only(p, "52.9", "52.9", "75.8")
    _span_only(p, "308", "308", "303")
    _span_only(p, "298 K", "298", "293")



def modify_pdf(input_bytes, pdf_type):
    if not PYMUPDF_OK:
        return input_bytes
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(input_bytes); tmp_path = tmp.name
    doc = fitz.open(tmp_path)
    if pdf_type == 'qp':
        _apply_qp(doc)
    else:
        _apply_ms(doc)
    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close(); os.unlink(tmp_path)
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

                    print(f"Processing uploaded {pdf_type.upper()} ({len(pdf_bytes)//1024} KB)")
                    result = modify_pdf(pdf_bytes, pdf_type)

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

                    result = modify_pdf(pdf_bytes, pdf_type)

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
