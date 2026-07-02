#!/usr/bin/env python3
"""
html_to_pdf.py — Convert a kagaz HTML artifact to a print-clean PDF.

What it does, in order:
  1. Ensures the brand fonts (Fraunces, Inter, JetBrains Mono) are installed so
     the serif/mono stack embeds instead of falling back. Uses the fonts bundled
     in ../assets/fonts/; if those are missing, fetches them from Google Fonts.
  2. Renders the HTML to PDF with WeasyPrint (deterministic, no JavaScript).
  3. Rasterizes every page to PNG so the result can be visually inspected for
     text cutoff / alignment problems — this is the step that actually catches
     layout bugs. WeasyPrint won't run JS, so charts must be inline SVG (see
     charts.py) and any rgba() tag backgrounds must be converted to solid hex.

Usage:
  python html_to_pdf.py INPUT.html OUTPUT.pdf [--qa-dir DIR] [--dpi 90] [--no-qa]

Exit code is non-zero if rendering fails. After a successful run, OPEN the QA
PNGs and check every page before delivering the PDF.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

FONT_FILES = {
    "Fraunces.ttf":         "https://github.com/google/fonts/raw/main/ofl/fraunces/Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf",
    "Fraunces-Italic.ttf":  "https://github.com/google/fonts/raw/main/ofl/fraunces/Fraunces-Italic%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf",
    "Inter.ttf":            "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
    "JetBrainsMono.ttf":    "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}


def ensure_fonts() -> None:
    """Install brand fonts into the user font dir. Prefer bundled copies."""
    dest = Path.home() / ".fonts"
    dest.mkdir(parents=True, exist_ok=True)
    bundled = Path(__file__).resolve().parent.parent / "assets" / "fonts"

    installed = 0
    for name, url in FONT_FILES.items():
        target = dest / name
        if target.exists():
            installed += 1
            continue
        src = bundled / name
        if src.exists():
            shutil.copy(src, target)
            installed += 1
            continue
        # last resort: fetch (requires network access to github)
        try:
            subprocess.run(["curl", "-sSL", "-o", str(target), url], check=True)
            installed += 1
        except Exception as e:
            print(f"  ! could not obtain {name}: {e}", file=sys.stderr)

    subprocess.run(["fc-cache", "-f", str(dest)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  fonts ready ({installed}/{len(FONT_FILES)})")


def preflight(html_path: Path) -> list:
    """Cheap static checks that catch the most common print bugs before render."""
    warnings = []
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    # rgba on tag/badge backgrounds triggers WeasyPrint's double-rectangle bug
    import re
    for m in re.finditer(r"\.(tag|badge|chip)[^{]*\{[^}]*background[^;]*rgba\(", text):
        warnings.append("rgba() background on a tag/badge — convert to solid hex (print.md table)")
    if "chart.js" in text.lower() or "cdn.jsdelivr.net/npm/chart" in text.lower():
        warnings.append("Chart.js detected — WeasyPrint does NOT run JS; use inline SVG (charts.py)")
    if "<canvas" in text.lower():
        warnings.append("<canvas> detected — will render blank in PDF; use inline SVG instead")
    return warnings


def render(html_path: Path, pdf_path: Path) -> None:
    from weasyprint import HTML
    HTML(str(html_path)).write_pdf(str(pdf_path))


def rasterize(pdf_path: Path, qa_dir: Path, dpi: int) -> list:
    qa_dir.mkdir(parents=True, exist_ok=True)
    prefix = qa_dir / "page"
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(prefix)],
                   check=True)
    return sorted(qa_dir.glob("page*.png"))


def page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(pdf_path)).pages)


def count_slides(html_path: Path) -> int:
    """Count slide elements (class containing 'slide') in the source."""
    import re
    text = html_path.read_text(encoding="utf-8", errors="ignore")
    return len(re.findall(r'class\s*=\s*"[^"]*\bslide\b', text))


def main() -> int:
    ap = argparse.ArgumentParser(description="kagaz HTML → print-clean PDF")
    ap.add_argument("input", help="input .html")
    ap.add_argument("output", help="output .pdf")
    ap.add_argument("--qa-dir", default=None, help="where to write QA page PNGs")
    ap.add_argument("--dpi", type=int, default=90, help="QA raster DPI (default 90)")
    ap.add_argument("--no-qa", action="store_true", help="skip rasterization")
    ap.add_argument("--slides", action="store_true",
                    help="slide-deck mode: assert PDF page count == number of .slide elements")
    args = ap.parse_args()

    html_path = Path(args.input).resolve()
    pdf_path = Path(args.output).resolve()
    if not html_path.exists():
        print(f"input not found: {html_path}", file=sys.stderr)
        return 1

    print("1/4  ensuring fonts")
    ensure_fonts()

    print("2/4  preflight checks")
    for w in preflight(html_path):
        print(f"  ! {w}")

    print("3/4  rendering PDF")
    render(html_path, pdf_path)
    print(f"  wrote {pdf_path}")

    if args.slides:
        slides = count_slides(html_path)
        pages = page_count(pdf_path)
        if slides == 0:
            print("  ! --slides set but no .slide elements found")
        elif pages == slides:
            print(f"  CONTINUITY OK — {slides} slides = {pages} pages (1 slide per page)")
        else:
            print(f"  !! CONTINUITY BROKEN — {slides} slides but {pages} pages.")
            if pages > slides:
                print("     A slide overflowed onto an extra page. Fix: ensure each .slide is")
                print("     height:<page-height> with overflow:hidden, and shorten/scale its content.")
            else:
                print("     Fewer pages than slides — a slide may be empty or collapsed.")

    if not args.no_qa:
        qa_dir = Path(args.qa_dir).resolve() if args.qa_dir else pdf_path.parent / (pdf_path.stem + "_qa")
        print("4/4  rasterizing pages for visual QA")
        pages = rasterize(pdf_path, qa_dir, args.dpi)
        print(f"  {len(pages)} page(s) -> {qa_dir}")
        print("  NEXT: open each PNG and check for text cutoff, overflow, and alignment.")
    else:
        print("4/4  skipped QA (--no-qa)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
