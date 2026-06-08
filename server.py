#!/usr/bin/env python3
"""
IB Exam PDF Modifier
- Uses Claude API to intelligently find safe linguistic swaps
- Applies them to ANY IB Chemistry PDF
- Never touches compounds, formulas, values, equations
"""
import json, urllib.request, urllib.error, os, io, zipfile, tempfile, subprocess, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

# Auto-install PyMuPDF
try:
    import fitz
    PYMUPDF_OK = True
except ImportError:
    print("Installing PyMuPDF...")
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "PyMuPDF==1.24.0", "--quiet"])
    import fitz
    PYMUPDF_OK = True

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def find_pdf(prefix):
    for f in os.listdir(BASE):
        if f.startswith(prefix) and f.endswith('.pdf'):
            return os.path.join(BASE, f)
    return None

QP_FILE = find_pdf("IB_Practice_QP") or os.path.join(BASE, "IB_Practice_QP_final.pdf")
MS_FILE = find_pdf("IB_Practice_MS") or os.path.join(BASE, "IB_Practice_MS_final.pdf")
print(f"QP: {QP_FILE}  exists={os.path.exists(QP_FILE)}")
print(f"MS: {MS_FILE}  exists={os.path.exists(MS_FILE)}")

# ── Claude API ────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You analyze IB Chemistry exam question papers.
Find words/phrases safe to swap for linguistic variety WITHOUT affecting:
- Chemical compounds, formulas, ions, elements (e.g. Mg(OH)2, H2SO4, BrO3-)
- Numerical values, units, concentrations (e.g. 0.100 mol dm-3, 1.24 g)
- Chemical equations or half-equations
- Graph labels, table data, experimental values
- The scientific meaning or the answer
- The Mark Scheme

Return ONLY valid JSON array (no markdown, no explanation):
[{"old": "exact text from input", "new": "replacement"}, ...]

Safe examples:
- "A student" -> "A candidate"
- "determined the" -> "calculated the"
- "container" -> "vessel"
- "lumps of" -> "pieces of"
- "Sketch a Maxwell" -> "Draw a Maxwell"
- "Outline why" -> "State why" (for simple recall questions only)
- "depend on" -> "are related to"
- "result from" -> "arise from"

If nothing safe to change on this page, return: []
Max 5 swaps per page. Only return swaps you are 100% certain are safe."""

def get_safe_swaps(page_text, api_key):
    """Ask Claude to find safe linguistic swaps for a page of text."""
    if not api_key or not page_text.strip():
        return []
    
    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Find safe word swaps for this IB exam page:\n\n{page_text[:2000]}"}]
    }).encode()
    
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        text = data["content"][0]["text"].strip()
        # Clean JSON
        if "```" in text:
            text = text.split("```")[1].replace("json","").strip()
        swaps = json.loads(text)
        return swaps if isinstance(swaps, list) else []
    except Exception as e:
        print(f"  Claude API error: {e}")
        return []

# ── PDF span replacement ──────────────────────────────────────────────────────
def apply_swap_to_page(page, old_text, new_text):
    """Replace old_text with new_text on page using redact+htmlbox."""
    count = 0
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0: continue
        for line in b["lines"]:
            for span in line["spans"]:
                if old_text not in span["text"]: continue
                
                new_st = span["text"].replace(old_text, new_text, 1)
                sr  = fitz.Rect(span["bbox"]); pr = page.rect
                sz  = span["size"]; c = span["color"]
                r,g,b_ = ((c>>16)&0xFF),((c>>8)&0xFF),(c&0xFF)
                ff  = "Arial Bold" if "Bold" in span["font"] else "Arial"
                
                page.add_redact_annot(sr)
                page.apply_redactions(images=0)
                
                try: nw = fitz.Font("helv").text_length(new_st, fontsize=sz)
                except: nw = len(new_st)*sz*0.55
                
                ins  = fitz.Rect(sr.x0, sr.y0-1,
                                 min(sr.x0+nw+8, pr.x1-5), sr.y1+2)
                html = (f'<p style="margin:0;padding:0">'
                        f'<span style="font-family:{ff};font-size:{sz}pt;'
                        f'color:rgb({r},{g},{b_})">{new_st}</span></p>')
                page.insert_htmlbox(ins, html, scale_low=0.9)
                count += 1
                break  # one replacement per span
    return count

def modify_pdf(input_bytes, pdf_type, api_key=""):
    """
    Modify PDF:
    - QP: use Claude API to find safe swaps on each page, then apply them
    - MS: no changes (Mark Scheme preserved)
    """
    if not PYMUPDF_OK:
        return input_bytes
    
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(input_bytes); tmp_path = tmp.name
    
    doc = fitz.open(tmp_path)
    total_swaps = 0
    
    if pdf_type == 'qp':
        key = api_key or ANTHROPIC_KEY
        
        for pg_num in range(len(doc)):
            page = doc[pg_num]
            
            # Extract page text (skip dotted lines and headers)
            page_text = ""
            for b in page.get_text("dict")["blocks"]:
                if b["type"] != 0: continue
                for line in b["lines"]:
                    lt = "".join(s["text"] for s in line["spans"])
                    if ". ." not in lt and "M18/" not in lt and "24EP" not in lt:
                        page_text += lt + "\n"
            
            if not page_text.strip() or len(page_text.strip()) < 20:
                continue
            
            # Get safe swaps from Claude
            swaps = get_safe_swaps(page_text, key)
            
            if swaps:
                print(f"  Page {pg_num+1}: {len(swaps)} swaps from Claude")
                for swap in swaps:
                    old = swap.get("old", "").strip()
                    new = swap.get("new", "").strip()
                    if old and new and old != new:
                        n = apply_swap_to_page(page, old, new)
                        if n:
                            print(f"    '{old[:30]}' → '{new[:30]}'")
                            total_swaps += n
    
    print(f"Total swaps applied: {total_swaps}")
    
    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True)
    doc.close()
    os.unlink(tmp_path)
    return buf.getvalue()

# ── HTTP Handler ──────────────────────────────────────────────────────────────
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
            self._json(200, {
                "qp": qp_ok, "ms": ms_ok,
                "qp_size": os.path.getsize(QP_FILE) if qp_ok else 0,
                "ms_size": os.path.getsize(MS_FILE) if ms_ok else 0,
                "pymupdf": PYMUPDF_OK,
                "api_key": bool(ANTHROPIC_KEY),
            })
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = self.path

        # Anthropic API proxy
        if path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            key    = self.headers.get("X-Api-Key", ANTHROPIC_KEY)
            if not key:
                self._json(400, {"error": "No API key"}); return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"Content-Type":"application/json","x-api-key":key,
                         "anthropic-version":"2023-06-01"}, method="POST")
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

        # Generate modified PDF
        elif path == "/api/generate-pdf":
            try:
                content_type = self.headers.get('Content-Type','')
                api_key = self.headers.get("X-Api-Key", ANTHROPIC_KEY)

                if 'multipart/form-data' in content_type:
                    length   = int(self.headers.get("Content-Length", 0))
                    body     = self.rfile.read(length)
                    boundary = content_type.split('boundary=')[1].encode()
                    parts    = body.split(b'--' + boundary)
                    pdf_bytes = None; pdf_type = 'qp'

                    for part in parts:
                        if b'name="type"' in part:
                            pdf_type = part.split(b'\r\n\r\n')[1].split(b'\r\n')[0].decode().strip()
                        if b'name="file"' in part and b'filename=' in part:
                            pdf_bytes = part.split(b'\r\n\r\n',1)[1].rsplit(b'\r\n',1)[0]

                    if not pdf_bytes:
                        self._json(400, {"error": "No file uploaded"}); return

                    print(f"Processing uploaded {pdf_type.upper()} ({len(pdf_bytes)//1024} KB)")
                    result = modify_pdf(pdf_bytes, pdf_type, api_key)

                else:
                    length   = int(self.headers.get("Content-Length", 0))
                    payload  = json.loads(self.rfile.read(length))
                    pdf_type = payload.get("type", "qp")
                    src      = QP_FILE if pdf_type == 'qp' else MS_FILE

                    if not os.path.exists(src):
                        self._json(404, {"error": f"{pdf_type} file not found"}); return

                    with open(src,'rb') as f: pdf_bytes = f.read()
                    result = modify_pdf(pdf_bytes, pdf_type, api_key)

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

    def _serve_file(self, filename, ct):
        try:
            with open(os.path.join(BASE, filename),'rb') as f: c=f.read()
            self.send_response(200); self._cors()
            self.send_header("Content-Type",ct)
            self.send_header("Content-Length",len(c))
            self.end_headers(); self.wfile.write(c)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def _serve_pdf(self, path, name):
        if not path or not os.path.exists(path):
            self._json(404,{"error":f"{name} not found"}); return
        with open(path,'rb') as f: c=f.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type","application/pdf")
        self.send_header("Content-Disposition",f'attachment; filename="{name}"')
        self.send_header("Content-Length",len(c))
        self.end_headers(); self.wfile.write(c)

    def _serve_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as zf:
            for fp,fn in [(QP_FILE,'IB_Practice_QP.pdf'),(MS_FILE,'IB_Practice_MS.pdf')]:
                if fp and os.path.exists(fp): zf.write(fp,fn)
        buf.seek(0); c=buf.read()
        self.send_response(200); self._cors()
        self.send_header("Content-Type","application/zip")
        self.send_header("Content-Disposition",'attachment; filename="IB_Practice_Papers.zip"')
        self.send_header("Content-Length",len(c))
        self.end_headers(); self.wfile.write(c)

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
