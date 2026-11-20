#!/usr/bin/env python3
"""Convert every document in okf/raw to Markdown with markitdown.

Output goes to okf/raw_md/ (reference only, to diff against the hand-written
base_files). Scanned images/certificates have no text layer, so markitdown
returns little or nothing for them; those are listed as needing OCR.

Usage:  python okf/convert_raw.py
"""
from pathlib import Path

from markitdown import MarkItDown

HERE = Path(__file__).parent
RAW = HERE / "raw"
OUT = HERE / "raw_md"
OUT.mkdir(exist_ok=True)

md = MarkItDown()
for src in sorted(RAW.iterdir()):
    if not src.is_file() or src.suffix.lower() not in {".pdf", ".jpg", ".jpeg", ".png", ".docx"}:
        continue
    try:
        text = md.convert(str(src)).text_content.strip()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL   {src.name}: {exc}")
        continue
    dest = OUT / (src.stem + ".md")
    dest.write_text(text, encoding="utf-8")
    status = "OK    " if len(text) > 50 else "NO TEXT (needs OCR)"
    print(f"{status} {src.name} -> {dest.name} ({len(text)} chars)")
