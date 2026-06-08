# IB Exam Modifier

## Overview
Applies **5–10% minimal linguistic substitutions** to IB Question Papers and Mark Schemes, preserving 100% of layout, formatting, graphics, equations, and scientific content.

---

## Files
| File | Purpose |
|---|---|
| `modifier.py` | Core Python script – reads PDF, applies substitutions, saves output |
| `IB_Modifier_App.jsx` | React web UI – upload PDFs, preview changes via Claude API |

---

## Installation (Python Script)

```bash
pip install pymupdf
python modifier.py --qp paper.pdf --ms markscheme.pdf --out ./output
```

---

## Substitution Rules

| Original | Replacement |
|---|---|
| student/students | candidate/candidates |
| investigate → | examine |
| explore → | examine |
| determine → | calculate |
| container/containers | vessel/vessels |
| tablet/tablets | medicine tablet/medicine tablets |
| show that | demonstrate that |
| outline → | summarise |
| use/used/using | utilise/utilised/utilising |

---

## Strict Protections

**Never modified:**
- Chemical equations / formulas
- Mathematical equations
- Numbers, values, constants
- Units (mol, dm³, kJ, etc.)
- Tables, graphs, diagrams
- Mark scheme answers/solutions
- Page numbers, headers, footers
- Answer boxes / response areas

---

## Quality Checks (automatic)
1. Modification rate check – must stay between 5–10%
2. Text overflow check – skips replacement if new text is >150% original length
3. Protected span detection – skips any span containing math/chemistry
4. Page count verification – output page count must match input
5. Mark scheme safety – skips any span containing `= + - × ÷` or digits in MS

---

## Usage Examples

```bash
# Process QP only
python modifier.py --qp paper1.pdf --out ./modified

# Process both QP and MS
python modifier.py --qp paper1.pdf --ms markscheme1.pdf --out ./modified

# Get JSON output for programmatic use
python modifier.py --qp paper1.pdf --ms markscheme1.pdf --json
```
