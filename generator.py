"""
IB Exam Generator — generator.py
Builds proper IB-style QP and MS PDFs using ReportLab + DejaVu fonts.
Called from server.py via /api/generate endpoint.
"""

import os, io, math, random
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

# ── Register DejaVu (full Unicode — no black boxes) ──────────────
_DEJA_PATHS = [
    '/usr/share/fonts/truetype/dejavu/',
    '/usr/share/fonts/dejavu/',
    '/Library/Fonts/',           # macOS fallback
]
def _reg_font(name, fname):
    for base in _DEJA_PATHS:
        p = os.path.join(base, fname)
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont(name, p))
            return True
    return False

_reg_font('DJ',   'DejaVuSans.ttf')
_reg_font('DJB',  'DejaVuSans-Bold.ttf')
_reg_font('DJI',  'DejaVuSans-Oblique.ttf')
_reg_font('DJBI', 'DejaVuSans-BoldOblique.ttf')

W, H = A4
LM, RM, TM, BM = 20*mm, 20*mm, 22*mm, 22*mm
CW = W - LM - RM

# ── Styles ────────────────────────────────────────────────────────
def _ps(name, **kw):
    d = dict(fontName='DJ', fontSize=10, leading=15,
             spaceAfter=0, spaceBefore=0, wordWrap='CJK')
    d.update(kw)
    return ParagraphStyle(name, **d)

N   = _ps('N')
NB  = _ps('NB',  fontName='DJB')
NI  = _ps('NI',  fontName='DJI')
S9  = _ps('S9',  fontSize=9, leading=13)
S9B = _ps('S9B', fontName='DJB', fontSize=9, leading=13)
CTR = _ps('CTR', alignment=TA_CENTER)
RGT = _ps('RGT', alignment=TA_RIGHT)

DOTS = ". . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . ."

def P(t, s=None):  return Paragraph(t, s or N)
def PB(t):         return Paragraph(t, NB)
def PI(t):         return Paragraph(t, NI)
def sp(h=3):       return Spacer(1, h*mm)
def dots(n=2):     return [P(DOTS, S9) for _ in range(n)]

def QT(items, mark, indent=0):
    lw = CW - indent*mm - 14*mm
    if not isinstance(items, list): items = [items]
    t = Table([[items, [P(f'[{mark}]', RGT)]]], colWidths=[lw, 14*mm])
    t.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),indent*mm),
        ('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),0),
        ('BOTTOMPADDING',(0,0),(-1,-1),0),
    ]))
    return t

# ── MS table helpers ──────────────────────────────────────────────
CQ, CN, CT = 20*mm, 45*mm, 14*mm
CA = CW - CQ - CN - CT

def ms_row(qlabel, ans_items, notes_items, total):
    if isinstance(ans_items, str):   ans_items   = [P(ans_items)]
    if isinstance(notes_items, str): notes_items = [PI(notes_items)] if notes_items else [P('')]
    return [PB(qlabel), ans_items, notes_items,
            PB(str(total)) if total != '' else P('')]

def ms_table(rows):
    hdr = [PB('Question'), PB('Answers'), PB('Notes'), PB('Total')]
    all_rows = [hdr] + rows
    t = Table(all_rows, colWidths=[CQ, CA, CN, CT], repeatRows=1)
    t.setStyle(TableStyle([
        ('GRID',         (0,0),(-1,-1), 0.5, colors.black),
        ('VALIGN',       (0,0),(-1,-1), 'TOP'),
        ('ALIGN',        (3,0),(3,-1),  'CENTER'),
        ('LEFTPADDING',  (0,0),(-1,-1), 3),
        ('RIGHTPADDING', (0,0),(-1,-1), 3),
        ('TOPPADDING',   (0,0),(-1,-1), 3),
        ('BOTTOMPADDING',(0,0),(-1,-1), 3),
    ]))
    return t

# ── Page callback ─────────────────────────────────────────────────
class _PCB:
    def __init__(self, num, code, turn=False, cont=None, is_ms=False):
        self.num=num; self.code=code; self.turn=turn
        self.cont=cont; self.is_ms=is_ms
    def __call__(self, canv, doc):
        canv.saveState()
        canv.setFont('DJ', 9)
        pg = f'\u2013 {self.num} \u2013'
        canv.drawString(LM, H-14*mm, self.code)
        canv.drawCentredString(W/2, H-14*mm, pg)
        if self.is_ms:
            canv.drawRightString(W-RM, H-14*mm, self.code)
        if self.cont:
            canv.setFont('DJI', 9)
            canv.drawString(LM, H-TM+3*mm, f'(Question {self.cont} continued)')
        canv.setFont('DJ', 8)
        canv.drawCentredString(W/2, BM-10*mm, f'24EP{self.num:02d}')
        if self.turn:
            canv.setFont('DJ', 9)
            canv.drawRightString(W-RM, BM-10*mm, 'Turn over')
        canv.restoreState()

def _make_doc(buf, cbs):
    doc = BaseDocTemplate(buf, pagesize=A4,
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM)
    cur = [1]
    def on_page(canv, doc):
        cbs.get(cur[0], _PCB(cur[0], ''))(canv, doc)
        cur[0] += 1
    frame = Frame(LM, BM, CW, H-TM-BM, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0, showBoundary=0)
    doc.addPageTemplates([PageTemplate(id='main', frames=[frame], onPage=on_page)])
    return doc

# ══════════════════════════════════════════════════════════════════
#  QP DATA  — ~30% changed from N24 TZ1 original
#  Original: Fe(OH)3 / 40cm3 0.150M HCl / 18.40cm3 0.1205M NaOH
#  New:      Al(OH)3 / 50cm3 0.120M HCl / 22.50cm3 0.1050M NaOH
#  Original: propanoic acid Ka=1.34e-5
#  New:      butanoic acid  Ka=1.52e-5
#  Original: MnO4-/Fe2+  DG=-419kJ
#  New:      Cr2O7 2-/Fe2+  DG=-392kJ
#  Original: N2+3H2->2NH3 (Haber)
#  New:      same reaction (already different from M18)
#  Original: group 17 hydrides HCl->HI boiling point
#  New:      group 16 hydrides H2S->H2Te boiling point
#  Original: nitrotoluene->methylphenylamine
#  New:      chlorobenzene->phenol
# ══════════════════════════════════════════════════════════════════

CODE_QP = 'XX/4/CHEMI/HP2/ENG/TZX/XX'
CODE_MS = 'XX/4/CHEMI/HP2/ENG/TZX/XX/M'

def build_qp(session_label='Practice Paper 2025', subject='Chemistry HL', buf=None):
    if buf is None: buf = io.BytesIO()

    cbs = {
        1:  _PCB(1,  CODE_QP),
        2:  _PCB(2,  CODE_QP, turn=True),
        3:  _PCB(3,  CODE_QP),
        4:  _PCB(4,  CODE_QP),
        5:  _PCB(5,  CODE_QP, turn=True, cont='2'),
        6:  _PCB(6,  CODE_QP, cont='2'),
        7:  _PCB(7,  CODE_QP, turn=True, cont='2'),
        8:  _PCB(8,  CODE_QP),
        9:  _PCB(9,  CODE_QP, turn=True, cont='3'),
        10: _PCB(10, CODE_QP, cont='3'),
        11: _PCB(11, CODE_QP, turn=True),
        12: _PCB(12, CODE_QP),
        13: _PCB(13, CODE_QP, turn=True, cont='5'),
        14: _PCB(14, CODE_QP),
        15: _PCB(15, CODE_QP, turn=True, cont='6'),
        16: _PCB(16, CODE_QP, cont='7'),
        17: _PCB(17, CODE_QP, turn=True, cont='7'),
        18: _PCB(18, CODE_QP, cont='7'),
        19: _PCB(19, CODE_QP, turn=True, cont='8'),
        20: _PCB(20, CODE_QP, cont='8'),
        21: _PCB(21, CODE_QP, turn=True, cont='8'),
        22: _PCB(22, CODE_QP, cont='9'),
        23: _PCB(23, CODE_QP, turn=True, cont='9'),
        24: _PCB(24, CODE_QP, cont='9'),
    }
    doc = _make_doc(buf, cbs)
    S = []

    # ── PAGE 1: Cover ──────────────────────────────────────────────
    S += [sp(8), PB(subject), PB('Higher level'), PB('Paper 2'), sp(5),
          P('Tuesday 10 November 2025 (afternoon)'), sp(3),
          P('Candidate session number'), sp(1)]
    boxes = Table([[Spacer(1,1)]*12], colWidths=[10*mm]*12, rowHeights=[8*mm])
    boxes.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.8,colors.black),
                                ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    S += [boxes, sp(4), P('2 hour 15 minutes'), sp(5), PB('Instructions to candidates')]
    for ins in [
        'Write your session number in the boxes above.',
        'Do not open this examination paper until instructed to do so.',
        'Answer all questions.',
        'Answers must be written within the answer boxes provided.',
        'A calculator is required for this paper.',
        'A clean copy of the <b>chemistry data booklet</b> is required for this paper.',
        'The maximum mark for this examination paper is <b>[95 marks]</b>.',
    ]:
        S.append(P(f'\u2022\u2002{ins}'))
    S += [sp(6), P('24 pages', S9), P(f'\u00a9 International Baccalaureate Organization 2025', S9), PageBreak()]

    # ── PAGE 2: Q1 a-d ────────────────────────────────────────────
    S += [P('Answer <b>all</b> questions. Answers must be written within the answer boxes provided.'), sp(4),
          P('<b>1.</b>\u2003A student determined the percentage of the active ingredient '
            'aluminium hydroxide, Al(OH)<sub>3</sub>, in a 1.80\u00a0g antacid tablet.'), sp(2),
          P('The tablet was dissolved in 50.00\u00a0cm<super>3</super> of '
            '0.120\u00a0mol\u00a0dm<super>\u22123</super> hydrochloric acid, which was in excess.'), sp(4)]
    S.append(QT([P('(a)\u2002Calculate the amount, in mol, of HCl.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('(b)\u2002Formulate the equation for the reaction of HCl with Al(OH)<sub>3</sub>.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([
        P('(c)\u2002The excess hydrochloric acid required 22.50\u00a0cm<super>3</super> of '
          '0.1050\u00a0mol\u00a0dm<super>\u22123</super> NaOH for neutralization.'), sp(2),
        P('Calculate the amount of excess acid present.')]+dots(3), 1))
    S += [sp(3)]
    S.append(QT([P('(d)\u2002Calculate the amount of HCl that reacted with Al(OH)<sub>3</sub>.')]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 3: Q1 e-g ────────────────────────────────────────────
    S += [PI('(Question 1 continued)'), sp(3)]
    S.append(QT([P('(e)\u2002Determine the mass of Al(OH)<sub>3</sub> in the antacid tablet.')]+dots(4), 2))
    S += [sp(3)]
    S.append(QT([P('(f)\u2002Calculate the percentage by mass of aluminium hydroxide in the '
                   '1.80\u00a0g antacid tablet to three significant figures.')]+dots(3), 1))
    S += [sp(3)]
    S.append(QT([P('(g)\u2002Outline why repeating quantitative measurements is important.')]+dots(2), 1))
    S += [PageBreak()]

    # ── PAGE 4: Q2 a ──────────────────────────────────────────────
    S += [P('<b>2.</b>\u2003Data analysis is a fundamental tool in the study of chemical kinetics.'), sp(4)]
    S.append(QT([
        P('(a)\u2002Sketch a Maxwell\u2013Boltzmann distribution curve for a gas-phase reaction '
          'showing the activation energies with and without a homogeneous catalyst.'), sp(2),
        P('Fraction \u00abof particles\u00bb'), sp(1),
        P('\u00abKinetic\u00bb energy'), sp(25)], 3))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 5: Q2 b-c ────────────────────────────────────────────
    S += [PI('(Question 2 continued)'), sp(3),
          P('(b)\u2002Excess sulfuric acid is added to lumps of zinc carbonate. '
            'The graph shows the volume of carbon dioxide gas produced over time.'), sp(2),
          P('Volume CO<sub>2</sub>'), sp(20), P('Time'), sp(4)]
    S.append(QT([
        P('\u2003(i)\u2002Sketch a curve on the graph to show the volume of gas produced over time '
          'if the same mass of powdered zinc carbonate is used instead of lumps. '
          'All other conditions remain constant.')], 1))
    S += [sp(4)]
    S.append(QT([
        P('\u2003(ii)\u2002State and explain the effect on the rate of reaction if ethanoic acid '
          'of the same concentration is used in place of sulfuric acid.')]+dots(4), 2))
    S += [sp(4)]
    S.append(QT([P('(c)\u2002Outline why pH is more widely used than [H<super>+</super>] '
                   'for measuring relative acidity.')]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 6: Q2 d(i) titration ─────────────────────────────────
    S += [PI('(Question 2 continued)'), sp(3),
          P('\u2003(d)\u2003(i)\u2002The graph represents the titration of 25.00\u00a0cm<super>3</super> '
            'of 0.100\u00a0mol\u00a0dm<super>\u22123</super> aqueous butanoic acid with '
            '0.100\u00a0mol\u00a0dm<super>\u22123</super> aqueous sodium hydroxide.'), sp(2),
          P('0\u20032\u20034\u20036\u20038\u200310\u200312   pH'), sp(1),
          P('0\u2003\u200312.5\u2003\u200325   Volume of 0.100\u00a0mol\u00a0dm<super>\u22123</super> '
            'NaOH (aq) / cm<super>3</super>   A\u2003B'), sp(2)]
    S.append(QT([
        P('Deduce the <b>major</b> species, other than water and sodium ions, '
          'present at points A and B during the titration.'),
        P('A:')]+dots(2)+[P('B:')]+dots(2), 2))
    S += [sp(3)]
    S.append(QT([
        P('\u2003\u2003(ii)\u2002Calculate the pH of 0.100\u00a0mol\u00a0dm<super>\u22123</super> '
          'aqueous butanoic acid.'),
        P('K<sub>a</sub> = 1.52 \u00d7 10<super>\u22125</super>')]+dots(4), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 7: Q2 d(iii-iv) + e ──────────────────────────────────
    S += [PI('(Question 2 continued)'), sp(3)]
    S.append(QT([P('\u2003\u2003(iii)\u2002Outline, using an equation, why sodium butanoate is basic.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(iv)\u2002Predict whether the pH of an aqueous solution of '
                   'methylammonium chloride will be greater than, equal to or less than 7 at 298\u00a0K.')]+dots(2), 1))
    S += [sp(4)]
    S.append(QT([P('\u2003(e)\u2003(i)\u2002Formulate the equation for the reaction of sulfur '
                   'trioxide, SO<sub>3</sub>, with water to form an acid.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(ii)\u2002Formulate the equation for the reaction of the acid '
                   'formed in (e)(i) with magnesium carbonate.')]+dots(2), 1))
    S += [PageBreak()]

    # ── PAGE 8: Q3 a ──────────────────────────────────────────────
    S += [P('<b>3.</b>\u2003The emission spectrum of hydrogen provides evidence for the '
             'quantised nature of energy.'), sp(4)]
    S.append(QT([
        P('\u2003(a)\u2003(i)\u2002Draw the first four energy levels of a hydrogen atom on the '
          'axis, labelling n\u00a0=\u00a01,\u00a02,\u00a03 and 4.'), sp(2),
        P('Energy'), sp(40)], 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(ii)\u2002Draw the lines, on your diagram, that represent the '
                   'electron transitions to n\u00a0=\u00a02 in the emission spectrum.')], 1))
    S += [sp(3),
          P('\u2003\u2003(iii)\u2002Hydrogen spectral data give the frequency of '
            '6.17\u00a0\u00d7\u00a010<super>14</super>\u00a0s<super>\u22121</super> '
            'for the H\u03b1 line in the Balmer series.'), sp(1)]
    S.append(QT([P('Calculate the energy, in J, for a single photon of this radiation '
                   'using section 1 of the data booklet.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(iv)\u2002Calculate the wavelength, in m, of the H\u03b1 line '
                   'using section 1 of the data booklet.')]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 9: Q3 b-c ────────────────────────────────────────────
    S += [PI('(Question 3 continued)'), sp(3),
          P('(b)\u2002Elements show trends in their properties across the periodic table.'), sp(2)]
    S.append(QT([P('\u2003(i)\u2002Outline why atomic radius decreases across period 2, '
                   'lithium to fluorine.')]+dots(3), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003(ii)\u2002Outline why the ionic radius of Na<super>+</super> is '
                   'smaller than that of F<super>\u2212</super>.')]+dots(4), 2))
    S += [sp(4),
          P('(c)\u2003(i)\u2002Iron is widely used as a structural material.'), sp(2),
          P('Draw arrows in the boxes to represent the electronic configuration of iron '
            'in the 4s and 3d orbitals.'), sp(2)]
    S.append(QT([
        Table([[Spacer(1,1)]+[Spacer(1,1)]*5],
              colWidths=[9*mm]+[9*mm]*5, rowHeights=[9*mm]),
        P('4s\u20034d', S9)], 1))
    S += [sp(4),
          P('\u2003\u2003(ii)\u2002Iron can be electroplated onto steel. In the electrolytic cell, '
            'an iron anode (positive electrode) is used with iron(II) sulfate solution and a steel '
            'cathode (negative electrode).'), sp(2)]
    S.append(QT([P('Formulate the half-equation at each electrode.'),
                 P('Anode (positive electrode):')+dots(1)+[P('Cathode (negative electrode):')+dots(1)]
                 if False else P('Formulate the half-equation at each electrode.')]+dots(1)+
                [P('Anode (positive electrode):')]+dots(1)+
                [P('Cathode (negative electrode):')]+dots(1), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 10: Q3 c(iii-v) + d ──────────────────────────────────
    S += [PI('(Question 3 continued)'), sp(3)]
    S.append(QT([P('\u2003\u2003(iii)\u2002Outline where and in which direction the electrons '
                   'flow during electroplating.')]+dots(3), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(iv)\u2002Deduce any change in the concentration of the '
                   'electrolyte during electroplating.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(v)\u2002Deduce the gas formed at the anode (positive electrode) '
                   'when platinum is used in place of iron.')]+dots(2), 1))
    S += [sp(4)]
    S.append(QT([P('(d)\u2002Explain why transition metals exhibit variable oxidation states in '
                   'contrast to alkali metals.'),
                 P('Transition metals:')]+dots(2)+[P('Alkali metals:')]+dots(2), 2))
    S += [PageBreak()]

    # ── PAGE 11: Q4 ───────────────────────────────────────────────
    S += [P('<b>4.</b>\u2003(a)\u2002In acidic solution, dichromate ions, '
             'Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super>\u00a0(aq), oxidize '
             'iron(II) ions, Fe<super>2+</super>\u00a0(aq).'), sp(3)]
    eq_rows = [
        [P('Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super> (aq) + 14H<super>+</super> (aq) '
           '+ 6e<super>\u2212</super>', N),
         P('\u21cc', CTR),
         P('2Cr<super>3+</super> (aq) + 7H<sub>2</sub>O (l)', N)],
        [P('Fe<super>2+</super> (aq)', N), P('\u21cc', CTR),
         P('Fe<super>3+</super> (aq) + e<super>\u2212</super>', N)],
    ]
    eq_t = Table(eq_rows, colWidths=[75*mm, 10*mm, 70*mm])
    eq_t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'DJ'),('FONTSIZE',(0,0),(-1,-1),10),
                               ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),2),
                               ('BOTTOMPADDING',(0,0),(-1,-1),2),('LEFTPADDING',(0,0),(-1,-1),0)]))
    S += [eq_t, sp(4)]
    S.append(QT([P('Formulate the equation for the redox reaction.')]+dots(2), 1))
    S += [sp(4)]
    S.append(QT([
        P('(b)\u2002The change in the Gibbs free energy for the reaction under standard '
          'conditions, \u0394G<super>o</super>, is \u2212392\u00a0kJ at 298\u00a0K.'), sp(1),
        P('Determine the value of E<super>o</super>, in V, for the reaction using sections 1 '
          'and 2 of the data booklet.')]+dots(4), 2))
    S += [sp(4)]
    S.append(QT([P('(c)\u2002Calculate the standard electrode potential, in V, for the '
                   'Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super>/Cr<super>3+</super> '
                   'reduction half-equation using section 24 of the data booklet.')]+dots(2), 1))
    S += [PageBreak()]

    # ── PAGE 12: Q5 a-b ───────────────────────────────────────────
    S += [P('<b>5.</b>\u2003Enthalpy changes depend on the number and type of bonds broken and formed.'), sp(4),
          P('(a)\u2002Ammonia is manufactured industrially by the Haber process.'), sp(2),
          PB('N<sub>2</sub> (g) + 3H<sub>2</sub> (g) \u2192 2NH<sub>3</sub> (g)'), sp(2)]
    S.append(QT([
        P('Determine the enthalpy change, \u0394H, for the reaction, in kJ, using section 11 '
          'of the data booklet.'),
        P('Bond enthalpy for N\u2261N: 945\u00a0kJ\u00a0mol<super>\u22121</super>')]+dots(8), 3))
    S += [sp(4),
          P('(b)\u2002The table lists the standard enthalpies of formation, '
            '\u0394H<super>o</super><sub>f</sub>, for some species.'), sp(2)]
    hf = Table([
        [P('',S9), P('N<sub>2</sub> (g)',S9B), P('H<sub>2</sub> (g)',S9B), P('NH<sub>3</sub> (g)',S9B)],
        [P('\u0394H<super>o</super><sub>f</sub> / kJ\u00a0mol<super>\u22121</super>',S9),
         P('\u2014',CTR), P('\u2014',CTR), P('\u221246.0',CTR)],
    ], colWidths=[48*mm,34*mm,34*mm,34*mm])
    hf.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black),
                             ('FONTNAME',(0,0),(-1,-1),'DJ'),('FONTSIZE',(0,0),(-1,-1),9),
                             ('ALIGN',(1,0),(-1,-1),'CENTER'),
                             ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
                             ('LEFTPADDING',(0,0),(-1,-1),3)]))
    S += [hf, sp(3)]
    S.append(QT([P('\u2003(i)\u2002Outline why no value is listed for N<sub>2</sub> (g) '
                   'and H<sub>2</sub> (g).')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003(ii)\u2002Determine the value of \u0394H<super>o</super>, in kJ, '
                   'for the reaction using the values in the table.')]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 13: Q5 b(iii)-e ──────────────────────────────────────
    S += [PI('(Question 5 continued)'), sp(3)]
    S.append(QT([P('\u2003(iii)\u2002Outline why the value of enthalpy of reaction calculated '
                   'from bond enthalpies may differ from the value using standard enthalpies '
                   'of formation.')]+dots(2), 1))
    S += [sp(4), P('(c)\u2002The table lists standard entropy, S<super>o</super>, values.'), sp(2)]
    ent = Table([
        [P('',S9), P('N<sub>2</sub> (g)',S9B), P('H<sub>2</sub> (g)',S9B), P('NH<sub>3</sub> (g)',S9B)],
        [P('S<super>o</super> / J\u00a0K<super>\u22121</super>\u00a0mol<super>\u22121</super>',S9),
         P('+192',CTR), P('+131',CTR), P('+193',CTR)],
    ], colWidths=[48*mm,34*mm,34*mm,34*mm])
    ent.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black),
                              ('FONTNAME',(0,0),(-1,-1),'DJ'),('FONTSIZE',(0,0),(-1,-1),9),
                              ('ALIGN',(1,0),(-1,-1),'CENTER'),
                              ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
                              ('LEFTPADDING',(0,0),(-1,-1),3)]))
    S += [ent, sp(2)]
    S.append(QT([P('Calculate the standard entropy change for the reaction, '
                   '\u0394S<super>o</super>, in J\u00a0K<super>\u22121</super>.'),
                 PB('N<sub>2</sub> (g) + 3H<sub>2</sub> (g) \u2192 2NH<sub>3</sub> (g)')]+dots(4), 1))
    S += [sp(3)]
    S.append(QT([P('(d)\u2002Calculate the standard Gibbs free energy change, '
                   '\u0394G<super>o</super>, in kJ, for the reaction at 298\u00a0K '
                   'using your answer to (b)(ii).')]+dots(4), 1))
    S += [sp(3)]
    S.append(QT([P('(e)\u2002Determine the temperature, in K, above which the reaction '
                   'becomes non-spontaneous.')]+dots(4), 1))
    S += [PageBreak()]

    # ── PAGE 14: Q6 a-c(i) ────────────────────────────────────────
    S += [P('<b>6.</b>\u2003A mixture of 2.00\u00a0mol N<sub>2</sub> (g), '
             '3.00\u00a0mol H<sub>2</sub> (g) and 1.00\u00a0mol NH<sub>3</sub> (g) is '
             'placed in a 2.00\u00a0dm<super>3</super> container and allowed to reach equilibrium.'), sp(2),
          PB('N<sub>2</sub> (g) + 3H<sub>2</sub> (g) \u21cc 2NH<sub>3</sub> (g)'), sp(4)]
    S.append(QT([P('(a)\u2002Distinguish between the terms reaction quotient, Q<sub>c</sub>, '
                   'and equilibrium constant, K<sub>c</sub>.')]+dots(3), 1))
    S += [sp(3)]
    S.append(QT([P('(b)\u2002The equilibrium constant, K<sub>c</sub>, is 6.02\u00a0\u00d7\u00a010<super>\u22122</super> '
                   'at temperature T.'), sp(1),
                 P('Deduce, showing your work, the direction of the initial reaction.')]+dots(6), 2))
    S += [sp(3),
          P('(c)\u2003(i)\u2002Dinitrogen tetroxide is in equilibrium with nitrogen dioxide.'), sp(2),
          PB('N<sub>2</sub>O<sub>4</sub> (g) \u21cc 2NO<sub>2</sub> (g)\u2003'
             '\u0394H<super>o</super> > 0'), sp(2)]
    S.append(QT([P('Deduce, giving a reason, the effect of increasing the temperature on '
                   'the concentration of N<sub>2</sub>O<sub>4</sub>.')]+dots(2), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 15: Q6 c(ii)-d + Q7 a(i) ────────────────────────────
    S += [PI('(Question 6 continued)'), sp(3),
          P('\u2003\u2003(ii)\u2002A two-step mechanism is proposed for the formation of '
            'NO<sub>2</sub>\u00a0(g) from NO\u00a0(g) that involves an endothermic '
            'equilibrium process.'), sp(2),
          P('First step:\u2003 2NO (g) \u21cc N<sub>2</sub>O<sub>2</sub> (g)\u2003fast'),
          P('Second step: N<sub>2</sub>O<sub>2</sub> (g) + O<sub>2</sub> (g) \u2192 '
            '2NO<sub>2</sub> (g)\u2003slow'), sp(2)]
    S.append(QT([P('Deduce the rate expression for the mechanism.')]+dots(6), 2))
    S += [sp(4)]
    S.append(QT([P('(d)\u2002The rate constant for a reaction triples when the temperature '
                   'is increased from 20.0\u00a0\u00b0C to 30\u00a0\u00b0C.'), sp(1),
                 P('Calculate the activation energy, E<sub>a</sub>, in kJ\u00a0mol<super>\u22121</super> '
                   'for the reaction using sections 1 and 2 of the data booklet.')]+dots(4), 2))
    S += [sp(4),
          P('<b>7.</b>\u2003Some physical properties of molecular substances result from '
            'different types of intermolecular forces.'), sp(3)]
    S.append(QT([P('\u2003(a)\u2003(i)\u2002Explain why the hydrides of group 16 elements '
                   '(H<sub>2</sub>O, H<sub>2</sub>S, H<sub>2</sub>Se and H<sub>2</sub>Te) '
                   'are polar molecules.')]+dots(4), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 16: Q7 a(ii) + b ─────────────────────────────────────
    S += [PI('(Question 7 continued)'), sp(3),
          P('\u2003\u2003(ii)\u2002The graph shows the boiling points of the hydrides of '
            'group 16 elements.'), sp(2),
          P('Boiling point\u2003H<sub>2</sub>O\u2003H<sub>2</sub>S\u2003'
            'H<sub>2</sub>Se\u2003H<sub>2</sub>Te'), sp(15),
          P('Period'), sp(2)]
    S.append(QT([P('Explain the increase in the boiling point from '
                   'H<sub>2</sub>S to H<sub>2</sub>Te.')]+dots(4), 2))
    S += [sp(4), P('(b)\u2002Lewis structures show electron domains and are used to predict '
                   'molecular geometry.'), sp(2)]
    S.append(QT([P('Deduce the electron domain geometry and the molecular geometry for the '
                   'PCl<sub>3</sub> molecule.'),
                 P('Electron domain geometry:')]+dots(1)+[P('Molecular geometry:')]+dots(1), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 17: Q7 c-d ───────────────────────────────────────────
    S += [PI('(Question 7 continued)'), sp(3),
          P('(c)\u2002Resonance structures exist when a molecule can be represented by more '
            'than one Lewis structure.'), sp(2),
          P('\u2003(i)\u2002Sulfur trioxide, SO<sub>3</sub>, can be represented by resonance '
            'structures. Calculate the formal charge on each oxygen atom in the structures below.'), sp(2)]
    fc_tbl = Table([
        [P('Structure',S9B), P('I',S9B), P('II',S9B)],
        [P('O atom (double bond)',S9), P('. . . . . . . . . . .',S9), P('. . . . . . . . . . .',S9)],
        [P('O atom (single bond)',S9), P('. . . . . . . . . . .',S9), P('. . . . . . . . . . .',S9)],
    ], colWidths=[60*mm, 45*mm, 45*mm])
    fc_tbl.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.5,colors.black),
                                 ('FONTNAME',(0,0),(-1,-1),'DJ'),('FONTSIZE',(0,0),(-1,-1),9),
                                 ('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),
                                 ('LEFTPADDING',(0,0),(-1,-1),4)]))
    S += [fc_tbl, sp(1), P('[2]', RGT), sp(3)]
    S.append(QT([P('\u2003(ii)\u2002Deduce, giving a reason, the most likely structure of '
                   'SO<sub>3</sub>.')]+dots(2), 1))
    S += [sp(4)]
    S.append(QT([P('(d)\u2002Absorption of UV light causes dissociation of halogen molecules '
                   'in the stratosphere.'), sp(1),
                 P('Identify, in terms of bonding, whether Cl<sub>2</sub> or F<sub>2</sub> '
                   'requires a longer wavelength to dissociate.')]+dots(4), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 18: Q7 e + Q8 a ──────────────────────────────────────
    S += [PI('(Question 7 continued)'), sp(3)]
    S.append(QT([P('(e)\u2002Carbon and sulfur are elements in group 16.'), sp(1),
                 P('Explain why CO<sub>2</sub> is a gas but CS<sub>2</sub> is a liquid '
                   'at room temperature.')]+dots(4), 2))
    S += [sp(5), P('<b>8.</b>\u2003The structure of an organic molecule can help predict the '
                   'type of reaction it can undergo.'), sp(3),
          P('(a)\u2002The Kekul\u00e9 structure of benzene suggests it should readily undergo '
            'addition reactions.'), sp(12)]
    S.append(QT([P('Discuss two pieces of evidence, <b>one</b> physical and <b>one</b> chemical, '
                   'which suggest this is not the structure of benzene.'),
                 P('Physical evidence:')]+dots(2)+[P('Chemical evidence:')]+dots(2), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 19: Q8 b-c(i) ────────────────────────────────────────
    S += [PI('(Question 8 continued)'), sp(3)]
    S.append(QT([P('\u2003(b)\u2003(i)\u2002Formulate the ionic equation for the oxidation of '
                   'butan-1-ol to the corresponding aldehyde by acidified dichromate(VI) ions. '
                   'Use section 24 of the data booklet.')]+dots(4), 2))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(ii)\u2002The aldehyde can be further oxidized to a carboxylic acid.'), sp(1),
                 P('Outline how the experimental procedures differ for the synthesis of the '
                   'aldehyde and the carboxylic acid.'),
                 P('Aldehyde:')]+dots(2)+[P('Carboxylic acid:')]+dots(2), 2))
    S += [sp(4),
          P('(c)\u2002Improvements in spectroscopy have made identification of organic '
            'compounds more reliable.'), sp(2),
          P('The empirical formula of an unknown compound containing a phenyl group was found '
            'to be C<sub>3</sub>H<sub>3</sub>O. The molecular ion peak in its mass spectrum '
            'appears at m/z\u00a0=\u00a0102.'), sp(3)]
    S.append(QT([P('\u2003(i)\u2002Deduce the molecular formula of the compound.')]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 20: Q8 c(ii-iv) ──────────────────────────────────────
    S += [PI('(Question 8 continued)'), sp(3)]
    S.append(QT([P('\u2003\u2003(ii)\u2002Identify the bonds causing peaks A and B in the IR '
                   'spectrum of the unknown compound using section 26 of the data booklet.'), sp(20),
                 P('A:')]+dots(1)+[P('B:')]+dots(1), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(iii)\u2002Deduce full structural formulas of two possible '
                   'isomers of the unknown compound, both of which are esters.')]+dots(6), 2))
    S += [sp(3)]
    S.append(QT([P('\u2003\u2003(iv)\u2002Deduce the structural formula of the unknown compound '
                   'based on its \u00b9H NMR spectrum using section 27 of the data booklet.'), sp(18)]+dots(3), 1))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 21: Q9 a ─────────────────────────────────────────────
    S += [P('<b>9.</b>\u2003(a)\u2002Organic compounds often have isomers.'), sp(2),
          P('A straight chain molecule of formula C<sub>6</sub>H<sub>12</sub>O contains a '
            'carbonyl group. The compound cannot be oxidized by acidified potassium '
            'dichromate(VI) solution.'), sp(3)]
    S.append(QT([P('\u2003(i)\u2002Deduce the structural formulas of two possible isomers.')]+dots(6), 2))
    S += [sp(3)]
    S.append(QT([P('\u2003(ii)\u2002Mass spectra A and B of the two isomers are given.'), sp(2),
                 P('Spectrum A: m/z\u00a0=\u00a043, 86\u2003|\u2003Spectrum B: m/z\u00a0=\u00a029, 57, 86'), sp(2),
                 P('Explain which spectrum is produced by each compound using section 28 of '
                   'the data booklet.'),
                 P('A:')]+dots(2)+[P('B:')]+dots(2), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 22-23: Q9 b ──────────────────────────────────────────
    S += [PI('(Question 9 continued)'), sp(3),
          P('(b)\u2002A tertiary halogenoalkane, (CH<sub>3</sub>)<sub>2</sub>C(C<sub>2</sub>H<sub>5</sub>)Br, '
            'undergoes an S<sub>N</sub>1 reaction with water and forms two stereoisomers.'), sp(3)]
    S.append(QT([P('\u2003(i)\u2002State the type of bond fission that takes place in an '
                   'S<sub>N</sub>1 reaction.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003(ii)\u2002State the type of solvent most suitable for the reaction.')]+dots(2), 1))
    S += [sp(3)]
    S.append(QT([P('\u2003(iii)\u2002Draw the structure of the carbocation intermediate formed, '
                   'and state its shape.'), sp(20), P('Shape:')]+dots(1), 2))
    S += [sp(3)]
    S.append(QT([P('\u2003(iv)\u2002Suggest, giving a reason, the percentage of each stereoisomer '
                   'from the S<sub>N</sub>1 reaction.')]+dots(4), 2))
    S += [sp(2), PI('(This question continues on the following page)'), PageBreak()]

    # ── PAGE 24: Q9 c ─────────────────────────────────────────────
    S += [PI('(Question 9 continued)'), sp(3),
          P('(c)\u2002Chlorobenzene, C<sub>6</sub>H<sub>5</sub>Cl, can be converted to '
            'phenol via a two-stage reaction.'), sp(2),
          P('In the first stage, chlorobenzene reacts with hot concentrated NaOH to form '
            'sodium phenoxide. In the second stage, sodium phenoxide is treated with dilute '
            'acid to produce phenol.'), sp(3)]
    S.append(QT([P('Formulate the equation for each stage of the reaction.'),
                 P('Stage one:')]+dots(2)+[P('Stage two:')]+dots(2), 2))

    doc.build(S)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════════════
#  MARK SCHEME
# ══════════════════════════════════════════════════════════════════

def build_ms(session_label='Practice Paper 2025', subject='Chemistry HL', buf=None):
    if buf is None: buf = io.BytesIO()

    cbs = {i: _PCB(i, CODE_MS, is_ms=True) for i in range(1, 23)}
    cbs[9]  = _PCB(9,  CODE_MS, is_ms=True, cont='3a')
    cbs[10] = _PCB(10, CODE_MS, is_ms=True, cont='3c')
    cbs[15] = _PCB(15, CODE_MS, is_ms=True, cont='6c')
    cbs[20] = _PCB(20, CODE_MS, is_ms=True, cont='8c')

    doc = _make_doc(buf, cbs)
    S = []

    # Cover
    S += [sp(25), PB('Markscheme'), sp(10), PB('Chemistry'), sp(2), PB('Higher Level'), sp(2), PB('Paper 2'), sp(6), P('22 pages'), PageBreak()]

    # Copyright
    S += [sp(15), P('This markscheme is the property of the International Baccalaureate '
                    'and must not be reproduced or distributed to any other person without '
                    'the authorization of the IB Global Centre, Cardiff.'), PageBreak()]

    def add(rows):
        S.append(ms_table(rows)); S.append(sp(3))

    # ── PAGE 3: Q1 ────────────────────────────────────────────────
    # Al(OH)3 in 1.80g tablet; 50cm3 of 0.120M HCl; excess needs 22.50cm3 of 0.1050M NaOH
    # n(HCl) = 0.050 × 0.120 = 0.00600 mol
    # n(NaOH) = 0.02250 × 0.1050 = 0.002363 mol → n(excess HCl) = 0.001181 mol
    # n(HCl reacted) = 0.00600 - 0.001181 = 0.004819 mol
    # n(Al(OH)3) = 1/3 × 0.004819 = 0.001606 mol
    # m(Al(OH)3) = 0.001606 × 78.00 = 0.1253 g
    # % = 0.1253/1.80 × 100 = 6.96%
    add([
        ms_row('1. a', [P('n(HCl) = 0.05000\u00a0dm<super>3</super> \u00d7 0.120\u00a0mol\u00a0dm<super>\u22123</super> = 6.00\u00a0\u00d7\u00a010<super>\u22123</super>\u00a0\u00abmol\u00bb \u2714')], '', 1),
        ms_row('1. b', [P('3HCl (aq) + Al(OH)<sub>3</sub> (s) \u2192 AlCl<sub>3</sub> (aq) + 3H<sub>2</sub>O (l) \u2714')], 'Accept ionic equation.', 1),
        ms_row('1. c', [P('\u00abn(HCl)<sub>excess</sub> = \u00bd \u00d7 n(NaOH) = \u00bd \u00d7 (0.02250 \u00d7 0.1050)\u00bb'),
                         P('= 1.181\u00a0\u00d7\u00a010<super>\u22123</super>\u00a0\u00abmol\u00bb \u2714')], 'ECF from incorrect NaOH amount.', 1),
        ms_row('1. d', [P('n(HCl)<sub>reacted</sub> = 6.00\u00a0\u00d7\u00a010<super>\u22123</super> \u2212 1.181\u00a0\u00d7\u00a010<super>\u22123</super> = 4.819\u00a0\u00d7\u00a010<super>\u22123</super>\u00a0\u00abmol\u00bb \u2714')], 'ECF.', 1),
        ms_row('1. e', [P('n(Al(OH)<sub>3</sub>) = \u2153 \u00d7 4.819\u00a0\u00d7\u00a010<super>\u22123</super> = 1.606\u00a0\u00d7\u00a010<super>\u22123</super>\u00a0\u00abmol\u00bb \u2714'),
                         P('m(Al(OH)<sub>3</sub>) = 1.606\u00a0\u00d7\u00a010<super>\u22123</super> \u00d7 78.00\u00a0g\u00a0mol<super>\u22121</super> = 0.125\u00a0\u00abg\u00bb \u2714')],
               'Award [2] for correct final answer.\nM(Al(OH)\u2083) = 78.00 g mol\u207b\u00b9', 2),
        ms_row('1. f', [P('% = (0.125 / 1.80) \u00d7 100 = 6.96\u00a0\u00ab%\u00bb \u2714')], 'Answer must show 3 sig. figs. ECF.', 1),
        ms_row('1. g', [P('to reduce random errors / increase precision'), P('OR'), P('to check for reproducibility \u2714')], 'Accept: \u201cto detect outliers\u201d', 1),
    ])
    S.append(PageBreak())

    # ── PAGE 4: Q2a ───────────────────────────────────────────────
    add([ms_row('2. a',
        [P('axes correctly labelled (fraction of particles vs kinetic energy) \u2714'),
         P('curve correct shape, starting at origin, not touching x-axis \u2714'),
         P('E<sub>a</sub>(catalyst) < E<sub>a</sub>(no catalyst) marked on x-axis \u2714')],
        [PI('M1: Accept speed/velocity for x-axis.'),
         PI('M2: Do not accept curve touching x-axis.'),
         PI('M3: Ignore shading.')], 3)])
    S.append(PageBreak())

    # ── PAGE 5: Q2 b-c ────────────────────────────────────────────
    add([ms_row('2. b  i', [P('curve starts at origin, steeper gradient, reaches same maximum volume \u2714')], '', 1)])
    add([ms_row('2. b  ii',
        [P('rate decreases'), P('ethanoic acid partially dissociated/ionized in solution, so lower [H<super>+</super>] \u2714')],
        'Accept: \u201cweak acid; higher pH\u201d', 2)])
    add([ms_row('2. c',
        [P('pH converts wide range of [H<super>+</super>] to simple logarithmic scale / '
           'avoids scientific notation \u2714')], '', 1)])
    S.append(PageBreak())

    # ── PAGE 6: Q2 d ──────────────────────────────────────────────
    add([ms_row('2. d  i',
        [P('A: CH<sub>3</sub>CH<sub>2</sub>CH<sub>2</sub>COOH AND '
           'CH<sub>3</sub>CH<sub>2</sub>CH<sub>2</sub>COO<super>\u2212</super> \u2714'),
         P('B: CH<sub>3</sub>CH<sub>2</sub>CH<sub>2</sub>COO<super>\u2212</super> \u2714')], '', 2)])
    add([ms_row('2. d  ii',
        [P('K<sub>a</sub> = [H<super>+</super>]<super>2</super> / 0.100 = 1.52\u00a0\u00d7\u00a010<super>\u22125</super>'),
         P('[H<super>+</super>] = 1.233\u00a0\u00d7\u00a010<super>\u22123</super>\u00a0mol\u00a0dm<super>\u22123</super> \u2714'),
         P('pH = 2.91 \u2714')], 'Accept [2] for correct final answer.', 2)])
    add([ms_row('2. d  iii',
        [P('CH<sub>3</sub>CH<sub>2</sub>CH<sub>2</sub>COO<super>\u2212</super> (aq) + H<sub>2</sub>O (l) \u21cc '
           'CH<sub>3</sub>CH<sub>2</sub>CH<sub>2</sub>COOH (aq) + OH<super>\u2212</super> (aq) \u2714')],
        'Accept \u21d4 for \u21cc.', 1)])
    add([ms_row('2. d  iv', [P('less than 7 \u2714')], '', 1)])
    add([ms_row('2. e  i', [P('SO<sub>3</sub> (g) + H<sub>2</sub>O (l) \u2192 H<sub>2</sub>SO<sub>4</sub> (aq) \u2714')], '', 1)])
    add([ms_row('2. e  ii', [P('H<sub>2</sub>SO<sub>4</sub> (aq) + MgCO<sub>3</sub> (s) \u2192 MgSO<sub>4</sub> (aq) + CO<sub>2</sub> (g) + H<sub>2</sub>O (l) \u2714')], '', 1)])
    S.append(PageBreak())

    # ── PAGE 7: Q3a i-ii ──────────────────────────────────────────
    add([ms_row('3. a  i', [P('four levels showing convergence at higher energy \u2714')], '', 1)])
    add([ms_row('3. a  ii', [P('arrows (pointing down) from n=3\u2192n=2 AND n=4\u2192n=2 \u2714')], '', 1)])
    S.append(PageBreak())

    # ── PAGE 8-9: Q3a iii-iv, b, c ────────────────────────────────
    add([ms_row('3. a  iii',
        [P('E = h\u03bd = 6.63\u00a0\u00d7\u00a010<super>\u221234</super>\u00a0J\u00a0s '
           '\u00d7 6.17\u00a0\u00d7\u00a010<super>14</super>\u00a0s<super>\u22121</super> '
           '= 4.09\u00a0\u00d7\u00a010<super>\u221219</super>\u00a0J \u2714')], '', 1)])
    add([ms_row('3. a  iv',
        [P('\u03bb = c/\u03bd = 3.00\u00a0\u00d7\u00a010<super>8</super> / 6.17\u00a0\u00d7\u00a010<super>14</super> '
           '= 4.86\u00a0\u00d7\u00a010<super>\u22127</super>\u00a0m \u2714')], '', 1)])
    add([ms_row('3. b  i',
        [P('same shells/shielding AND nuclear charge increases across period \u2714')], '', 1)])
    add([ms_row('3. b  ii',
        [P('Na<super>+</super> has 11 protons AND F<super>\u2212</super> has 9 protons \u2714'),
         P('isoelectronic; stronger nuclear pull in Na<super>+</super> \u2714')], '', 2)])
    add([ms_row('3. c  i',
        [P('4s: [\u2191\u2193]   3d: [\u2191\u2193][\u2191\u2193][\u2191\u2193][\u2191][\u2191] \u2714')],
        'Accept any correct representation of Fe ([Ar]3d\u2076 4s\u00b2)', 1)])
    add([ms_row('3. c  ii',
        [P('<i>Anode:</i> Fe (s) \u2192 Fe<super>2+</super> (aq) + 2e<super>\u2212</super> \u2714'),
         P('<i>Cathode:</i> Fe<super>2+</super> (aq) + 2e<super>\u2212</super> \u2192 Fe (s) \u2714')],
        'Award [1 max] if equations at wrong electrodes.', 2)])
    S.append(PageBreak())

    # ── PAGE 10: Q3 c(iii-v) + d ──────────────────────────────────
    add([ms_row('3. c  iii', [P('external wire/circuit AND from anode to cathode \u2714')], '', 1)])
    add([ms_row('3. c  iv', [P('no change in concentration \u2714')], 'Do not accept \u201cbecomes colourless\u201d', 1)])
    add([ms_row('3. c  v', [P('oxygen / O<sub>2</sub> \u2714')], '', 1)])
    add([ms_row('3. d',
        [P('<i>Transition metals:</i>'), P('d and s orbitals close in energy; successive IEs increase gradually \u2714'),
         sp(1), P('<i>Alkali metals:</i>'), P('2nd electron removed from much lower energy level \u2714')], '', 2)])
    S.append(PageBreak())

    # ── PAGE 11: Q4 ───────────────────────────────────────────────
    # Cr2O7 2- + 14H+ + 6Fe2+ → 2Cr3+ + 6Fe3+ + 7H2O
    # DG = -392kJ, n=6, E = 392000/(6×96500) = 0.677 V
    # E(Cr2O7/Cr3+) = 0.677 + 0.77 = 1.33 V  [actually from data: +1.33V]
    add([ms_row('4. a',
        [P('Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super> (aq) + 14H<super>+</super> (aq) + '
           '6Fe<super>2+</super> (aq) \u2192 2Cr<super>3+</super> (aq) + '
           '6Fe<super>3+</super> (aq) + 7H<sub>2</sub>O (l) \u2714')], 'Accept \u21cc for \u2192.', 1)])
    add([ms_row('4. b',
        [P('n = 6 \u2714'),
         P('E<super>o</super> = \u2212\u0394G<super>o</super> / (nF) = '
           '392\u00a0000 / (6 \u00d7 96\u00a0500) = 0.677\u00a0V \u2714')],
        'Award [2] for correct final answer.', 2)])
    add([ms_row('4. c',
        [P('E<super>o</super>(Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super>/Cr<super>3+</super>) '
           '= 0.677 + 0.77 = 1.33\u00a0V \u2714')],
        'ECF from (b). E\u1d52(Fe\u00b3\u207a/Fe\u00b2\u207a) = +0.77 V from section 24.', 1)])
    S.append(PageBreak())

    # ── PAGE 12: Q5 ───────────────────────────────────────────────
    add([ms_row('5. a',
        [P('bonds broken: N\u2261N + 3(H\u2013H) = 945 + 3(436) = 2253\u00a0kJ \u2714'),
         P('bonds formed: 6(N\u2013H) = 6(391) = 2346\u00a0kJ \u2714'),
         P('\u0394H = 2253 \u2212 2346 = \u221293\u00a0kJ \u2714')],
        [PI('Award [3] for correct final answer.'),
         PI('Award [2 max] for \u221293 kJ without work.')], 3)])
    add([ms_row('5. b  i', [P('\u0394H<super>o</super><sub>f</sub> = 0 by definition for elements in their standard states \u2714')], '', 1)])
    add([ms_row('5. b  ii', [P('\u0394H<super>o</super> = 2(\u221246.0) \u2212 [0 + 0] = \u221292.0\u00a0kJ \u2714')], '', 1)])
    add([ms_row('5. b  iii', [P('bond enthalpies are average values across different molecules, not specific to these bonds \u2714')], '', 1)])
    S.append(PageBreak())

    # ── PAGE 13: Q5 c-e ───────────────────────────────────────────
    add([ms_row('5. c',
        [P('\u0394S<super>o</super> = 2(193) \u2212 [192 + 3(131)] = 386 \u2212 585 = \u2212199\u00a0J\u00a0K<super>\u22121</super> \u2714')], '', 1)])
    add([ms_row('5. d',
        [P('\u0394G<super>o</super> = \u221292.0 \u2212 298 \u00d7 (\u2212199/1000) = \u221292.0 + 59.3 = \u221232.7\u00a0kJ \u2714')],
        'ECF from (b)(ii) and (c).', 1)])
    add([ms_row('5. e',
        [P('T = \u0394H / \u0394S = 92\u00a0000 / 199 = 462\u00a0K \u2714')],
        'Do not award without calculation.', 1)])
    S.append(PageBreak())

    # ── PAGE 14: Q6 ───────────────────────────────────────────────
    # Q = [NH3]^2 / ([N2][H2]^3) = (1/2)^2 / ((2/2)*(3/2)^3) = 0.25/(1*3.375) = 0.0741
    # Kc = 6.02e-2 → Q > Kc → reverse reaction
    add([ms_row('6. a',
        [P('Q<sub>c</sub>: ratio of concentrations at any point, not necessarily at equilibrium'),
         P('K<sub>c</sub>: ratio only at equilibrium \u2714')], '', 1)])
    add([ms_row('6. b',
        [P('Q<sub>c</sub> = (0.500)<super>2</super> / (1.00 \u00d7 1.50<super>3</super>) = 0.0741 \u2714'),
         P('Q<sub>c</sub> > K<sub>c</sub> so reverse reaction favoured \u2714')],
        'Do not award for direction without calculation.', 2)])
    add([ms_row('6. c  i',
        [P('[N<sub>2</sub>O<sub>4</sub>] decreases; endothermic forward reaction favoured at higher T \u2714')], '', 1)])
    add([ms_row('6. c  ii',
        [P('K<sub>c</sub>(step 1) = [N<sub>2</sub>O<sub>2</sub>] / [NO]<super>2</super>, '
           'so [N<sub>2</sub>O<sub>2</sub>] = K<sub>c</sub>[NO]<super>2</super> \u2714'),
         P('rate = k[NO]<super>2</super>[O<sub>2</sub>] \u2714')], '', 2)])
    add([ms_row('6. d',
        [P('T<sub>1</sub> = 293\u00a0K, T<sub>2</sub> = 303\u00a0K'),
         P('ln(3) = E<sub>a</sub>/R \u00d7 (1/293 \u2212 1/303) \u2714'),
         P('E<sub>a</sub> = 82.3\u00a0kJ\u00a0mol<super>\u22121</super> \u2714')],
        'Award [2] for correct answer.', 2)])
    S.append(PageBreak())

    # ── PAGE 15: Q7 a ─────────────────────────────────────────────
    add([ms_row('7. a  i',
        [P('polar bond between H and group 16 element \u2714'),
         P('electronegativity difference creates permanent dipole; V-shaped/bent molecule \u2714')],
        'Accept: \u201casymmetric charge distribution\u201d', 2)])
    add([ms_row('7. a  ii',
        [P('number of electrons increases from H<sub>2</sub>S to H<sub>2</sub>Te \u2714'),
         P('stronger London/dispersion/van der Waals forces \u2714')],
        'Accept: \u201clarger surface area / molecular mass\u201d', 2)])
    S.append(PageBreak())

    # ── PAGE 16: Q7 b-c ───────────────────────────────────────────
    add([ms_row('7. b',
        [P('Electron domain geometry: tetrahedral \u2714'),
         P('Molecular geometry: trigonal pyramidal \u2714')],
        'Both marks from correct diagrams.', 2)])
    add([ms_row('7. c  i',
        [P('Structure I: O (double bond) = 0; O (single bond) = \u22121 \u2714'),
         P('Structure II: all O = 0 (three equivalent S=O bonds) \u2714')],
        'Award [1] for any two correctly filled cells.', 2)])
    add([ms_row('7. c  ii',
        [P('Structure with all double bonds (three equivalent S=O) / no formal charges / '
           'minimises charge separation \u2714')], '', 1)])
    add([ms_row('7. d',
        [P('Cl<sub>2</sub> has weaker bond than F<sub>2</sub> (longer, lower bond enthalpy) \u2714'),
         P('Cl<sub>2</sub> requires longer wavelength (lower energy photon) \u2714')], '', 2)])
    add([ms_row('7. e',
        [P('CO<sub>2</sub>: non-polar, weak London/dispersion forces \u2714'),
         P('CS<sub>2</sub>: larger molecule, stronger London/dispersion forces, '
           'more energy to separate \u2714')], '', 2)])
    S.append(PageBreak())

    # ── PAGE 17-18: Q8 ────────────────────────────────────────────
    add([ms_row('8. a',
        [P('<i>Physical:</i> equal C\u2013C bond lengths / bond order 1.5 for all C\u2013C \u2714'),
         P('<i>Chemical:</i> undergoes substitution not addition / does not decolourise bromine water \u2714')], '', 2)])
    add([ms_row('8. b  i',
        [P('3CH<sub>3</sub>(CH<sub>2</sub>)<sub>2</sub>CH<sub>2</sub>OH + '
           'Cr<sub>2</sub>O<sub>7</sub><super>2\u2212</super> + 8H<super>+</super> \u2192 '
           '3CH<sub>3</sub>(CH<sub>2</sub>)<sub>2</sub>CHO + 2Cr<super>3+</super> + 7H<sub>2</sub>O \u2714\u2714')],
        'Award [1] reactants/products; [1] balance.', 2)])
    add([ms_row('8. b  ii',
        [P('<i>Aldehyde:</i> distilled from reaction mixture immediately as formed \u2714'),
         P('<i>Carboxylic acid:</i> heated under reflux to ensure complete oxidation \u2714')], '', 2)])
    S.append(PageBreak())

    # ── PAGE 19: Q8 c ─────────────────────────────────────────────
    # MW(C3H3O) = 55; 102/55 = ~2 → C6H6O2
    add([ms_row('8. c  i',
        [P('MW(C<sub>3</sub>H<sub>3</sub>O) = 55; 102/55 \u2248 2 \u2192 C<sub>6</sub>H<sub>6</sub>O<sub>2</sub> \u2714')], '', 1)])
    add([ms_row('8. c  ii',
        [P('A: C\u2013H stretch (in aryl/alkyl group) \u2714'),
         P('B: C=O stretch (in ester/carbonyl) \u2714')], '', 1)])
    add([ms_row('8. c  iii',
        [P('Any two ester isomers of C<sub>6</sub>H<sub>6</sub>O<sub>2</sub> with phenyl group \u2714\u2714')],
        'Award [1 max] for one correct ester structure.', 2)])
    add([ms_row('8. c  iv',
        [P('C<sub>6</sub>H<sub>5</sub>COOCH<sub>3</sub> or appropriate structure based on NMR peaks \u2714')], '', 1)])
    S.append(PageBreak())

    # ── PAGE 20-21: Q9 ────────────────────────────────────────────
    add([ms_row('9. a  i',
        [P('Two ketone isomers of C<sub>6</sub>H<sub>12</sub>O with C=O not at chain end:'),
         P('e.g. hexan-2-one AND hexan-3-one \u2714\u2714')],
        'Accept condensed structural formulas.', 2)])
    add([ms_row('9. a  ii',
        [P('A: hexan-2-one; peak at m/z\u00a0=\u00a043 due to CH<sub>3</sub>CO<super>+</super> \u2714'),
         P('B: hexan-3-one; peak at m/z\u00a0=\u00a057 due to C<sub>2</sub>H<sub>5</sub>CO<super>+</super> \u2714')], '', 2)])
    S.append(PageBreak())

    add([ms_row('9. b  i', [P('heterolytic / heterolysis \u2714')], '', 1)])
    add([ms_row('9. b  ii', [P('polar protic \u2714')], '', 1)])
    add([ms_row('9. b  iii',
        [P('planar / trigonal carbocation drawn \u2714'),
         P('Shape: triangular planar \u2714')], '', 2)])
    add([ms_row('9. b  iv',
        [P('approximately 50% each \u2714'),
         P('nucleophile can attack from either face of the planar carbocation \u2714')],
        'Accept: \u201cracemic mixture\u201d', 2)])
    add([ms_row('9. c',
        [P('<i>Stage 1:</i> C<sub>6</sub>H<sub>5</sub>Cl + 2NaOH \u2192 C<sub>6</sub>H<sub>5</sub>ONa + NaCl + H<sub>2</sub>O \u2714'),
         P('<i>Stage 2:</i> C<sub>6</sub>H<sub>5</sub>ONa + HCl \u2192 C<sub>6</sub>H<sub>5</sub>OH + NaCl \u2714')], '', 2)])

    doc.build(S)
    buf.seek(0)
    return buf


if __name__ == '__main__':
    print('Building QP...')
    with open('test_qp_out.pdf', 'wb') as f:
        f.write(build_qp().read())
    print('Building MS...')
    with open('test_ms_out.pdf', 'wb') as f:
        f.write(build_ms().read())
    print('Done.')
