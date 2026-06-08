#!/usr/bin/env python3
"""
IB Exam PDF Modifier
Uses PyMuPDF overlay approach:
- Opens original PDF as base
- Whites out changed text with white rectangle  
- Writes new text on top at same position
- All graphics, answer boxes, tables, headers stay 100% intact
"""
import json, urllib.request, urllib.error, os, io, zipfile, shutil, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import fitz  # PyMuPDF
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False
    print("WARNING: PyMuPDF not installed. PDF modification disabled.")

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))

def find_pdf(prefix):
    for fname in os.listdir(BASE):
        if fname.startswith(prefix) and fname.endswith('.pdf'):
            return os.path.join(BASE, fname)
    return None

QP_FILE = find_pdf("IB_Practice_QP") or os.path.join(BASE, "IB_Practice_QP.pdf")
MS_FILE = find_pdf("IB_Practice_MS") or os.path.join(BASE, "IB_Practice_MS.pdf")

print(f"QP: {QP_FILE}  exists={os.path.exists(QP_FILE)}")
print(f"MS: {MS_FILE}  exists={os.path.exists(MS_FILE)}")

# ══════════════════════════════════════════════════════════════════════════════
#  PDF OVERLAY MODIFIER
# ══════════════════════════════════════════════════════════════════════════════

def _get_span_info(page, rect):
    """Get font/size/color of span overlapping rect."""
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for span in line["spans"]:
                if fitz.Rect(span["bbox"]).intersects(rect):
                    c = span["color"]
                    color = (((c>>16)&0xFF)/255.0, ((c>>8)&0xFF)/255.0, (c&0xFF)/255.0)
                    fname = span["font"]
                    if "Bold" in fname and "Italic" in fname: fontname = "hebo"
                    elif "Bold" in fname: fontname = "hebo"
                    elif "Italic" in fname: fontname = "hebi"
                    else: fontname = "helv"
                    return span["size"], fontname, color
    return 11.0, "helv", (0, 0, 0)

def _overlay_replace(page, old_text, new_text):
    """Replace ALL instances of old_text on page using white overlay."""
    count = 0
    for rect in page.search_for(old_text):
        size, font, color = _get_span_info(page, rect)
        # White out original text
        page.draw_rect(
            fitz.Rect(rect.x0-1, rect.y0-1, rect.x1+2, rect.y1+2),
            color=(1,1,1), fill=(1,1,1), overlay=True
        )
        # Insert new text at same baseline
        page.insert_text(
            fitz.Point(rect.x0, rect.y1 - 2),
            new_text, fontname=font, fontsize=size, color=color, overlay=True
        )
        count += 1
    return count

def modify_pdf_with_replacements(input_path, replacements):
    """
    Apply text replacements to PDF using overlay approach.
    replacements = list of (page_1indexed, old_text, new_text)
    Returns modified PDF as bytes.
    """
    if not PYMUPDF_OK:
        # Fallback: return original unchanged
        with open(input_path, 'rb') as f:
            return f.read()

    # Work on a temp copy
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = tmp.name
    shutil.copy(input_path, tmp_path)

    doc = fitz.open(tmp_path)
    total = 0

    for page_num, old, new in replacements:
        if page_num < 1 or page_num > len(doc):
            continue
        n = _overlay_replace(doc[page_num - 1], old, new)
        if n > 0:
            total += n
            print(f"  p{page_num}: '{old[:30]}' -> '{new[:30]}' ({n}x)")

    out_buf = io.BytesIO()
    doc.save(out_buf, garbage=4, deflate=True)
    doc.close()
    os.unlink(tmp_path)

    print(f"  Total replacements: {total}")
    return out_buf.getvalue()


def build_qp_from_original(replacements_json):
    """
    Build modified QP PDF using original as base.
    replacements_json: list of {"page": N, "old": "...", "new": "..."}
    """
    if not os.path.exists(QP_FILE):
        return None, "QP original file not found"

    reps = [(r["page"], r["old"], r["new"]) for r in replacements_json]
    pdf_bytes = modify_pdf_with_replacements(QP_FILE, reps)
    return pdf_bytes, None


def build_ms_from_original(replacements_json):
    """
    Build modified MS PDF using original as base.
    """
    if not os.path.exists(MS_FILE):
        return None, "MS original file not found"

    reps = [(r["page"], r["old"], r["new"]) for r in replacements_json]
    pdf_bytes = modify_pdf_with_replacements(MS_FILE, reps)
    return pdf_bytes, None


# ── DEFAULT REPLACEMENTS (~30% content change) ────────────────────────────────
DEFAULT_QP_REPLACEMENTS = [
    # Q1: H2SO4/Mg(OH)2 → HNO3/Al(OH)3; 1.24g→1.62g; conc 0.100→0.120
    {"page":2, "old":"magnesium hydroxide,",         "new":"aluminium hydroxide,"},
    {"page":2, "old":"Mg(OH)",                        "new":"Al(OH)"},
    {"page":2, "old":"1.24",                          "new":"1.62"},
    {"page":2, "old":"0.100 mol dm",                  "new":"0.120 mol dm"},
    {"page":2, "old":"sulfuric acid, which was",      "new":"nitric acid, which was"},
    {"page":2, "old":"Calculate the amount, in mol, of H", "new":"Calculate the amount, in mol, of HNO3"},
    {"page":2, "old":"with Mg(OH)",                  "new":"with Al(OH)"},
    {"page":2, "old":"20.80 cm",                     "new":"22.40 cm"},
    {"page":2, "old":"0.1133 mol dm",                "new":"0.1050 mol dm"},
    {"page":2, "old":"that reacted with Mg(OH)",     "new":"that reacted with Al(OH)"},
    {"page":3, "old":"Mg(OH)",                        "new":"Al(OH)"},
    {"page":3, "old":"magnesium hydroxide",           "new":"aluminium hydroxide"},
    {"page":3, "old":"1.24",                          "new":"1.62"},
    # Q2: CaCO3→MgCO3; HCl→H2SO4; ethanoic→propanoic
    {"page":4, "old":"calcium carbonate",             "new":"magnesium carbonate"},
    {"page":4, "old":"hydrochloric acid is added",    "new":"sulfuric acid is added"},
    {"page":5, "old":"ethanoic acid of the same",     "new":"propanoic acid of the same"},
    {"page":5, "old":"in place of hydrochloric acid", "new":"in place of sulfuric acid"},
    {"page":6, "old":"ethanoic acid with",            "new":"propanoic acid with"},
    {"page":6, "old":"aqueous ethanoic acid.",        "new":"aqueous propanoic acid."},
    {"page":6, "old":"= 1.74 ",                       "new":"= 1.34 "},
    {"page":7, "old":"calcium carbonate.",            "new":"zinc carbonate."},
    {"page":7, "old":"sodium ethanoate is basic",     "new":"sodium propanoate is basic"},
    # Q3b: Na+/Na → K+/Cl-
    {"page":9, "old":"radius of Na",                  "new":"radius of K"},
    # Q4: BrO3-/I- → ClO3-/Fe2+; ΔG=-514→-412
    {"page":11,"old":"bromate ions, BrO",             "new":"chlorate ions, ClO"},
    {"page":11,"old":"oxidize iodide ions,",          "new":"oxidize iron(II) ions,"},
    {"page":11,"old":"514 kJ",                        "new":"412 kJ"},
    # Q6: Kc=0.282→0.500; temp change
    {"page":14,"old":"0.282",                         "new":"0.500"},
    {"page":15,"old":"25.0 °C to 35 °C",             "new":"20.0 °C to 30 °C"},
    # Q7b: NH2- → PH2-
    {"page":16,"old":"NH",                            "new":"PH"},
    # Q8b: propan-1-ol → butan-1-ol
    {"page":19,"old":"propan-1-ol",                   "new":"butan-1-ol"},
    # Q9a: C5H10O → C6H12O
    {"page":21,"old":"C5H10O",                        "new":"C6H12O"},
]

DEFAULT_MS_REPLACEMENTS = [
    # Q1 answers
    {"page":3, "old":"0.00500/5.00",                "new":"0.00600/6.00"},
    {"page":3, "old":"Mg(OH)",                       "new":"Al(OH)"},
    {"page":3, "old":"1.24 g",                       "new":"1.62 g"},
    {"page":3, "old":"0.02080",                      "new":"0.02240"},
    {"page":3, "old":"0.1133",                       "new":"0.1050"},
    {"page":3, "old":"0.001178/1.178",               "new":"0.002352/2.352"},
    {"page":3, "old":"0.00500  0.001178",            "new":"0.00600  0.002352"},
    {"page":3, "old":"0.00382/3.82",                 "new":"0.003648/3.648"},
    {"page":3, "old":"58.33 g mol",                  "new":"78.00 g mol"},
    {"page":3, "old":"0.223",                        "new":"0.0948"},
    {"page":3, "old":"18.0",                         "new":"5.85"},
    # Q2 answers
    {"page":5, "old":"ethanoic acid",                "new":"propanoic acid"},
    {"page":6, "old":"ethanoic acid",                "new":"propanoic acid"},
    {"page":6, "old":"ethanoate",                    "new":"propanoate"},
    {"page":6, "old":"1.74  10",                     "new":"1.34  10"},
    {"page":6, "old":"1.32  10",                     "new":"1.158  10"},
    {"page":6, "old":"2.88",                         "new":"2.94"},
    # Q4 answers
    {"page":11,"old":"BrO",                          "new":"ClO"},
    {"page":11,"old":"514  10",                      "new":"412  10"},
    {"page":11,"old":"0.888",                        "new":"0.711"},
    {"page":11,"old":"1.43",                         "new":"1.48"},
    # Q6 answers
    {"page":14,"old":"0.282",                        "new":"0.500"},
    {"page":15,"old":"52.9",                         "new":"75.8"},
    {"page":15,"old":"308 K",                        "new":"303 K"},
    {"page":15,"old":"298 K",                        "new":"293 K"},
]


# ══════════════════════════════════════════════════════════════════════════════
#  HTTP HANDLER
# ══════════════════════════════════════════════════════════════════════════════

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
            self.send_header('Content-Type', 'application/json')
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = self.path

        # ── Anthropic API proxy ────────────────────────────────────────────
        if path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            key    = self.headers.get("X-Api-Key", os.environ.get("ANTHROPIC_API_KEY", ""))
            if not key:
                self._json(400, {"error": "No API key"}); return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"Content-Type":"application/json","x-api-key":key,
                         "anthropic-version":"2023-06-01"},
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

        # ── Generate modified PDF using overlay ────────────────────────────
        elif path == "/api/generate-pdf":
            try:
                length  = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))

                pdf_type = payload.get("type", "qp")
                # Use custom replacements if provided, else use defaults
                replacements = payload.get("replacements", None)

                if pdf_type == "qp":
                    reps = replacements or DEFAULT_QP_REPLACEMENTS
                    pdf_bytes, err = build_qp_from_original(reps)
                    fname = "IB_Practice_QP_modified.pdf"
                else:
                    reps = replacements or DEFAULT_MS_REPLACEMENTS
                    pdf_bytes, err = build_ms_from_original(reps)
                    fname = "IB_Practice_MS_modified.pdf"

                if err:
                    self._json(500, {"error": err}); return

                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", len(pdf_bytes))
                self.end_headers(); self.wfile.write(pdf_bytes)

            except Exception as e:
                import traceback; traceback.print_exc()
                self._json(500, {"error": str(e)})

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
            self._json(404, {"error": f"{download_name} not found"}); return
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
            for fpath, fname in [(QP_FILE,'IB_Practice_QP.pdf'),(MS_FILE,'IB_Practice_MS.pdf')]:
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
