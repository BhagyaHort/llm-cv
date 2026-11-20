#!/usr/bin/env python3
"""pdf_pages.py — print the page count of a PDF ("error" if it cannot be read)."""
import sys

from pypdf import PdfReader

try:
    print(len(PdfReader(sys.argv[1]).pages))
except Exception:
    print("error")
