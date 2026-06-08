#!/usr/bin/env python3
import json, urllib.request, urllib.error, os, io, zipfile
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── ReportLab imports ──────────────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable, PageBreak, KeepTogether,
                                 Flowable)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

PORT = int(os.environ.get("PORT", 8080))
BASE = os.path.dirname(os.path.abspath(__file__))

PAGE_W, PAGE_H = A4

# ══════════════════════════════════════════════════════════════════════════════
#  PDF BUILDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def make_styles():
    s = {}
    s['n']   = ParagraphStyle('n',   fontName='Times-Roman',  fontSize=10, leading=14, spaceAfter=3)
    s['b']   = ParagraphStyle('b',   fontName='Times-Bold',   fontSize=10, leading=14)
    s['it']  = ParagraphStyle('it',  fontName='Times-Italic', fontSize=9,  leading=12)
    s['c']   = ParagraphStyle('c',   fontName='Times-Roman',  fontSize=10, leading=14, alignment=TA_CENTER)
    s['cb']  = ParagraphStyle('cb',  fontName='Times-Bold',   fontSize=13, leading=18, alignment=TA_CENTER)
    s['sm']  = ParagraphStyle('sm',  fontName='Times-Roman',  fontSize=8,  leading=11)
    s['q']   = ParagraphStyle('q',   fontName='Times-Bold',   fontSize=11, leading=15)
    s['ms_h']= ParagraphStyle('ms_h',fontName='Times-Bold',   fontSize=10, leading=14, textColor=colors.HexColor('#185fa5'))
    return s


class AnswerBox(Flowable):
    """Bordered rectangle with dotted lines inside — for student answers."""
    def __init__(self, lines=2, extra_top=0, width=None):
        Flowable.__init__(self)
        self.lines    = lines
        self.line_h   = 14
        self.width    = width or (PAGE_W - 4*cm)
        self.height   = lines * self.line_h + 10 + extra_top
        self.extra_top= extra_top

    def draw(self):
        c = self.canv
        c.setLineWidth(0.5)
        c.rect(0, 0, self.width - 6, self.height, stroke=1, fill=0)
        c.setDash(1, 3); c.setLineWidth(0.4)
        for i in range(self.lines):
            y = self.height - (i+1)*self.line_h - 4
            if y > 4:
                c.line(6, y, self.width - 12, y)
        c.setDash()


def _header_footer(header_code):
    def fn(canvas, doc):
        canvas.saveState()
        canvas.setFont('Times-Roman', 8)
        pg = doc.page
        canvas.line(1.5*cm, PAGE_H-1.5*cm, PAGE_W-1.5*cm, PAGE_H-1.5*cm)
        if pg > 1:
            canvas.drawString(1.5*cm, PAGE_H-1.3*cm, header_code)
            canvas.drawRightString(PAGE_W-1.5*cm, PAGE_H-1.3*cm, f'– {pg} –')
        canvas.line(1.5*cm, 1.5*cm, PAGE_W-1.5*cm, 1.5*cm)
        canvas.drawCentredString(PAGE_W/2, 0.9*cm, f'24EP{pg:02d}')
        canvas.restoreState()
    return fn


def build_qp_pdf(questions, subject, paper, level, session):
    """
    Build a QP PDF from a list of question dicts.
    questions = [{"number":"1","subparts":[{"part":"a","question":"...","marks":1}]}]
    Returns bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=1.8*cm, rightMargin=1.5*cm)
    S   = make_styles()
    hdr = f'XX/4/{subject[:5].upper()}/{paper}/ENG/TZ2/XX'
    story = []

    def P(t, st='n'): return Paragraph(t, S[st])
    def SP(h=0.2):    return Spacer(1, h*cm)
    def HR():         return HRFlowable(width='100%', thickness=0.5, color=colors.black)
    def box(n=2, extra=0): return AnswerBox(lines=n, extra_top=extra)

    # ── Cover ──────────────────────────────────────────────────────────────
    story += [
        SP(0.5),
        P(f'<b>{subject}</b>', 'cb'), SP(0.3),
        P(f'<b>{level}</b>',   'cb'), SP(0.3),
        P(f'<b>{paper}</b>',   'cb'), SP(1.5),
        P(session, 'c'), SP(2), HR(), SP(0.3),
        P('<b>Instructions to candidates</b>', 'b'),
        P('• Answer all questions.', 'n'),
        P('• Answers must be written within the answer boxes provided.', 'n'),
        P('• A calculator is required for this paper.', 'n'),
        P('• A clean copy of the <b>data booklet</b> is required for this paper.', 'n'),
        SP(8),
        P('© Practice paper — AI generated', 'sm'),
        PageBreak(),
        P('<b>Answer all questions. Answers must be written within the answer boxes provided.</b>', 'n'),
        SP(0.4),
    ]

    # ── Questions ──────────────────────────────────────────────────────────
    for q in questions:
        qnum  = q.get('number', '')
        parts = q.get('subparts', [])

        story.append(KeepTogether([
            Table([[P(f'<b>{qnum}.</b>', 'q'), P('', 'n')]],
                  colWidths=[1*cm, PAGE_W-3.8*cm]),
            SP(0.2),
        ]))

        for p in parts:
            part_label = p.get('part', '')
            qtext      = p.get('question', '')
            marks      = p.get('marks', 1)
            n_lines    = max(2, int(marks) * 2)

            story.append(
                Table([[P(f'({part_label})', 'n') if part_label else P('', 'n'),
                        P(qtext, 'n'),
                        P(f'[{marks}]', 'n')]],
                      colWidths=[0.9*cm, PAGE_W-5.2*cm, 0.8*cm],
                      style=[('VALIGN',(0,0),(-1,-1),'TOP'),
                             ('ALIGN', (2,0),(2,0),'RIGHT')]))
            story += [SP(0.15), box(n_lines), SP(0.3)]

    doc.build(story,
              onFirstPage=_header_footer(hdr),
              onLaterPages=_header_footer(hdr))
    return buf.getvalue()


def build_ms_pdf(questions, subject, paper, level, session):
    """
    Build a Markscheme PDF from question dicts (same structure as QP but with 'answer' key).
    Returns bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=1.8*cm, rightMargin=1.5*cm)
    S   = make_styles()
    hdr = f'XX/4/{subject[:5].upper()}/{paper}/ENG/TZ2/XX/M'
    story = []

    def P(t, st='n'): return Paragraph(t, S[st])
    def SP(h=0.2):    return Spacer(1, h*cm)
    def HR():         return HRFlowable(width='100%', thickness=0.5, color=colors.black)

    # ── Cover ──────────────────────────────────────────────────────────────
    story += [
        SP(0.5),
        P('<b>Markscheme</b>', 'cb'), SP(2),
        P(f'<b>{session}</b>', 'cb'), SP(2),
        P(f'<b>{subject}</b>', 'cb'), SP(2),
        P(f'<b>{level}</b>',   'cb'), SP(2),
        P(f'<b>{paper}</b>',   'cb'), SP(6),
        P('Practice paper — AI generated', 'sm'),
        PageBreak(),
        HR(), SP(0.3),
        P('This markscheme is AI-generated for practice purposes only.', 'it'),
        SP(0.5), HR(), PageBreak(),
    ]

    # ── MS Table ───────────────────────────────────────────────────────────
    col_w = [1.2*cm, 0.8*cm, 9.5*cm, 1.1*cm]

    def ms_row(qnum, sub, ans, total=''):
        return [P(str(qnum), 'b'), P(str(sub), 'b'), P(ans, 'n'), P(str(total), 'b')]

    header = [[P('<b>Question</b>', 'b'), P('', 'b'),
               P('<b>Answers</b>', 'b'), P('<b>Total</b>', 'b')]]

    for q in questions:
        qnum  = q.get('number', '')
        parts = q.get('subparts', [])

        rows = list(header)
        for p in parts:
            part_label = p.get('part', '')
            answer     = p.get('answer', '—')
            question   = p.get('question', '')
            marks      = p.get('marks', 1)

            ans_text = (f'<i>Q: {question}</i><br/>' if question else '') + \
                       answer + ' &#10003;'

            rows.append(ms_row(qnum, part_label, ans_text, marks))

        t = Table(rows, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ('GRID',       (0,0),(-1,-1), 0.4, colors.black),
            ('VALIGN',     (0,0),(-1,-1), 'TOP'),
            ('BACKGROUND', (0,0),(-1,0),  colors.lightgrey),
            ('FONTNAME',   (0,0),(-1,0),  'Times-Bold'),
            ('FONTSIZE',   (0,0),(-1,-1), 9),
            ('TOPPADDING', (0,0),(-1,-1), 3),
            ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ]))
        story += [P(f'<b>Question {qnum}</b>', 'b'), SP(0.2), t, SP(0.5)]

    doc.build(story,
              onFirstPage=_header_footer(hdr),
              onLaterPages=_header_footer(hdr))
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  STATIC FILE FINDER
# ══════════════════════════════════════════════════════════════════════════════

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
#  HTTP HANDLER
# ══════════════════════════════════════════════════════════════════════════════

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
            self.send_response(200); self._cors()
            self.send_header('Content-Type', 'application/json')
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        path = self.path

        # ── Anthropic proxy ────────────────────────────────────────────────
        if path == "/api/claude":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            key    = self.headers.get("X-Api-Key", os.environ.get("ANTHROPIC_API_KEY", ""))
            if not key:
                self._json(400, {"error": "No API key"}); return
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=body,
                headers={"Content-Type":"application/json",
                         "x-api-key":key,
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

        # ── Generate PDF via ReportLab ─────────────────────────────────────
        elif path == "/api/generate-pdf":
            try:
                length  = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))

                pdf_type  = payload.get("type", "qp")       # "qp" or "ms"
                questions = payload.get("questions", [])
                subject   = payload.get("subject",  "Chemistry")
                paper     = payload.get("paper",    "Paper 2")
                level     = payload.get("level",    "HL")
                session   = payload.get("session",  "Practice Paper")

                if pdf_type == "qp":
                    pdf_bytes = build_qp_pdf(questions, subject, paper, level, session)
                    fname     = "IB_Practice_QP.pdf"
                else:
                    pdf_bytes = build_ms_pdf(questions, subject, paper, level, session)
                    fname     = "IB_Practice_MS.pdf"

                self.send_response(200); self._cors()
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", len(pdf_bytes))
                self.end_headers()
                self.wfile.write(pdf_bytes)

            except Exception as e:
                self._json(500, {"error": str(e)})

        else:
            self.send_response(404); self.end_headers()

    # ── helpers ───────────────────────────────────────────────────────────
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
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Api-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")


print(f"Server running on port {PORT}")
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
