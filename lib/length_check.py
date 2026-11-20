#!/usr/bin/env python3
"""length_check.py — measure how many A4 pages of content a resume PDF holds.

The resume must be at least 1.5 pages long (non-negotiable) and at most 2 pages.
The enforced threshold is 1.55: the 1.5 requirement plus a 0.05 margin for pixel-measurement error.
Length = (pages - 1) + how full the last page is (0..1). The fill is measured from the
rendered pixels of the last page, so it works for LaTeX and ReportLab PDFs alike.

Usage:  python lib/length_check.py <resume.pdf> [--min 1.5] [--max 2.0]
Prints: LENGTH=1.62 PAGES=2 FILL=0.62 STATUS=OK|SHORT|LONG
Exit:   0 OK, 3 SHORT (< min), 4 LONG (> max)
"""
import argparse
import sys

import pypdfium2 as pdfium

SCALE = 0.5            # render scale (72 dpi * 0.5) — plenty to find the lowest text pixel
DARK = 200             # grey level below which a pixel counts as ink


def _content_bbox(page):
    img = page.render(scale=SCALE).to_pil().convert("L")
    mask = img.point(lambda p: 255 if p < DARK else 0)
    return mask.getbbox(), img.size


def measure(pdf_path):
    pdf = pdfium.PdfDocument(pdf_path)
    pages = len(pdf)
    last_bbox, (_, height) = _content_bbox(pdf[pages - 1])
    if last_bbox is None:                       # blank trailing page
        return pages - 1 if pages > 1 else 0.0, pages, 0.0
    top, bottom = last_bbox[1], last_bbox[3]
    if pages > 1:
        first_bbox, _ = _content_bbox(pdf[0])   # page 1 is full: its lowest text ~ capacity
        cap_bottom = first_bbox[3] if first_bbox else height * 0.96
    else:
        cap_bottom = height * 0.96
    cap_bottom = max(cap_bottom, bottom)
    fill = (bottom - top) / max(1, (cap_bottom - top))
    fill = max(0.0, min(1.0, fill))
    return (pages - 1) + fill, pages, fill


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--min", type=float, default=1.55,
                    help="enforced minimum: the required 1.5 pages plus 0.05 measurement margin")
    ap.add_argument("--max", type=float, default=2.0)
    args = ap.parse_args()
    length, pages, fill = measure(args.pdf)
    status = "OK"
    code = 0
    if length < args.min:
        status, code = "SHORT", 3
    elif length > args.max + 1e-6 or pages > 2:
        status, code = "LONG", 4
    print(f"LENGTH={length:.2f} PAGES={pages} FILL={fill:.2f} STATUS={status}")
    return code


if __name__ == "__main__":
    sys.exit(main())
