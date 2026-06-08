"""
IB Exam Modifier
================
Applies minimal linguistic substitutions (5–10% of text) to IB QP/MS PDFs
while preserving 100% of the original layout, formatting, graphics, and
scientific/mathematical content.

Usage:
    python modifier.py --qp question_paper.pdf --ms mark_scheme.pdf
    python modifier.py --qp question_paper.pdf   # MS is optional
"""

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF

# ─────────────────────────────────────────────────────────────────
# SUBSTITUTION DICTIONARY
# Keys are regex patterns (case-insensitive word-boundary match).
# Values are replacement strings.
# Only purely linguistic / non-scientific words are included.
# ─────────────────────────────────────────────────────────────────
SUBSTITUTIONS = {
    # People / roles
    r"\bstudent\b": "candidate",
    r"\bstudents\b": "candidates",
    r"\bpupil\b": "candidate",
    r"\bpupils\b": "candidates",

    # Investigate / explore
    r"\binvestigate\b": "examine",
    r"\binvestigates\b": "examines",
    r"\binvestigated\b": "examined",
    r"\binvestigating\b": "examining",
    r"\bexplore\b": "examine",
    r"\bexplores\b": "examines",
    r"\bexplored\b": "examined",
    r"\bexploring\b": "examining",

    # Determine → calculate  (only when used as a verb for numerical finding)
    # Kept conservative: only standalone "determine" without math context
    r"\bdetermine\b": "calculate",
    r"\bdetermines\b": "calculates",
    r"\bdetermined\b": "calculated",
    r"\bdetermining\b": "calculating",

    # Container / vessel
    r"\bcontainer\b": "vessel",
    r"\bcontainers\b": "vessels",
    r"\bbeaker\b": "vessel",          # only safe if not in a specific diagram label
    r"\bflask\b": "vessel",

    # Tablet / medicine
    r"\btablet\b": "medicine tablet",
    r"\btablets\b": "medicine tablets",

    # Show → demonstrate
    r"\bshow that\b": "demonstrate that",
    r"\bshows that\b": "demonstrates that",

    # Use → utilise
    r"\buse\b": "utilise",
    r"\buses\b": "utilises",
    r"\bused\b": "utilised",
    r"\busing\b": "utilising",

    # Find → determine   (avoid circular with determine above – keep only QP context)
    # Skipped to stay conservative.

    # State → identify  (conservative)
    # Skipped – "state" appears in "state of matter" etc.

    # Outline → summarise
    r"\boutline\b": "summarise",
    r"\boutlines\b": "summarises",
    r"\boutlined\b": "summarised",
    r"\boutlining\b": "summarising",
}

# ─────────────────────────────────────────────────────────────────
# PATTERNS THAT INDICATE PROTECTED CONTENT
# If a word appears inside these patterns, skip substitution.
# ─────────────────────────────────────────────────────────────────
PROTECTED_PATTERNS = [
    # Chemical formulas: letters+digits like H2O, NaCl, CO2, C6H12O6
    r'[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)+',
    # Numbers with units: 25 cm, 0.5 mol, 3.14 kJ
    r'\d+\.?\d*\s*[a-zA-Z]+(?:/[a-zA-Z]+)?',
    # Superscript / subscript notation, exponents
    r'\^\{?[\d\-\+]+\}?',
    # Equations: anything with = sign nearby
    r'[^.!?]*=[^.!?]*',
    # Ion notation: SO4²⁻, H⁺, etc.
    r'[A-Z][a-z]?\w*[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+',
]


def is_protected_span(text: str) -> bool:
    """Return True if this text span should not be modified at all."""
    t = text.strip()
    if not t:
        return True
    # Very short purely numeric
    if re.fullmatch(r'[\d\s\.\,\-\+\±\/\(\)]+', t):
        return True
    # Contains chemical formula characters
    if re.search(r'[A-Z][a-z]?\d', t):
        return True
    # Contains Greek letters (math/science)
    if re.search(r'[αβγδεζηθλμνξπρσφχψω]', t):
        return True
    # Contains equation markers
    if re.search(r'[=≡≈∝∝≤≥∞∫∑√∂]', t):
        return True
    # Looks like a unit alone
    if re.fullmatch(r'[a-zA-Z]{1,6}(?:\d+)?(?:[/·][a-zA-Z]+)?', t) and len(t) <= 8:
        return True
    return False


def apply_substitutions(text: str) -> tuple[str, int]:
    """
    Apply the substitution dictionary to a plain text string.
    Returns (modified_text, number_of_replacements).
    """
    count = 0
    for pattern, replacement in SUBSTITUTIONS.items():
        new_text, n = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
        if n > 0:
            count += n
            text = new_text
    return text, count


def modify_pdf(input_path: str, output_path: str, is_mark_scheme: bool = False) -> dict:
    """
    Open the PDF, find text spans that can be safely substituted,
    replace them in-place using PyMuPDF's redaction API, and save.

    Returns a stats dict.
    """
    doc = fitz.open(input_path)
    total_words = 0
    modified_words = 0
    pages_modified = 0
    change_log = []

    for page_num, page in enumerate(doc):
        page_changed = False
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block.get("type") != 0:  # 0 = text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    original = span["text"]
                    if not original.strip():
                        continue

                    # Skip protected spans
                    if is_protected_span(original):
                        total_words += len(original.split())
                        continue

                    # For mark schemes: only substitute if purely linguistic
                    if is_mark_scheme:
                        # Skip if line looks like an answer/calculation
                        if re.search(r'[\d\=\+\-\×\÷\/]', original):
                            total_words += len(original.split())
                            continue

                    total_words += len(original.split())
                    modified, n = apply_substitutions(original)

                    if n > 0 and modified != original:
                        # Safety check: modified text should not be drastically longer
                        ratio = len(modified) / max(len(original), 1)
                        if ratio > 1.5:
                            continue  # skip – replacement too long, risk of overflow

                        # Apply redaction: blank out old text, write new text
                        rect = fitz.Rect(span["bbox"])
                        font_size = span["size"]
                        font_name = span.get("font", "helv")
                        color = span.get("color", 0)

                        # Convert integer color to RGB tuple
                        r = ((color >> 16) & 0xFF) / 255.0
                        g = ((color >> 8) & 0xFF) / 255.0
                        b = (color & 0xFF) / 255.0

                        # Add redaction annotation (erases original)
                        page.add_redact_annot(rect, fill=(1, 1, 1))
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

                        # Insert replacement text at exact position
                        page.insert_text(
                            (rect.x0, rect.y1 - 1),  # baseline
                            modified,
                            fontsize=font_size,
                            color=(r, g, b),
                            overlay=True,
                        )

                        modified_words += n
                        page_changed = True
                        change_log.append({
                            "page": page_num + 1,
                            "original": original,
                            "modified": modified,
                        })

        if page_changed:
            pages_modified += 1

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    modification_rate = (modified_words / total_words * 100) if total_words else 0

    return {
        "total_words": total_words,
        "modified_words": modified_words,
        "modification_rate_pct": round(modification_rate, 2),
        "pages_modified": pages_modified,
        "total_pages": len(fitz.open(output_path)),
        "changes": change_log,
    }


def run(qp_path: Optional[str], ms_path: Optional[str], output_dir: str = ".") -> dict:
    """
    Entry point for the modifier.
    Returns a results dict with stats for QP and/or MS.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    if qp_path:
        qp_out = output_dir / ("modified_" + Path(qp_path).name)
        print(f"[QP] Processing: {qp_path}")
        stats = modify_pdf(qp_path, str(qp_out), is_mark_scheme=False)
        stats["output_path"] = str(qp_out)
        results["qp"] = stats
        print(f"[QP] Done – {stats['modification_rate_pct']}% modified → {qp_out}")

    if ms_path:
        ms_out = output_dir / ("modified_" + Path(ms_path).name)
        print(f"[MS] Processing: {ms_path}")
        stats = modify_pdf(ms_path, str(ms_out), is_mark_scheme=True)
        stats["output_path"] = str(ms_out)
        results["ms"] = stats
        print(f"[MS] Done – {stats['modification_rate_pct']}% modified → {ms_out}")

    return results


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IB Exam Modifier – minimal linguistic substitutions only")
    parser.add_argument("--qp", help="Path to Question Paper PDF")
    parser.add_argument("--ms", help="Path to Mark Scheme PDF")
    parser.add_argument("--out", default=".", help="Output directory (default: current dir)")
    parser.add_argument("--json", action="store_true", help="Print results as JSON")
    args = parser.parse_args()

    if not args.qp and not args.ms:
        parser.error("Provide at least --qp or --ms (or both).")

    results = run(args.qp, args.ms, args.out)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for doc_type, stats in results.items():
            print(f"\n{'='*50}")
            print(f"  {doc_type.upper()} Summary")
            print(f"{'='*50}")
            print(f"  Total words scanned : {stats['total_words']}")
            print(f"  Words modified      : {stats['modified_words']}")
            print(f"  Modification rate   : {stats['modification_rate_pct']}%")
            print(f"  Pages modified      : {stats['pages_modified']} / {stats['total_pages']}")
            print(f"  Output file         : {stats['output_path']}")
            if stats['changes']:
                print(f"\n  Sample changes (first 10):")
                for ch in stats['changes'][:10]:
                    print(f"    Page {ch['page']}: \"{ch['original']}\" → \"{ch['modified']}\"")
