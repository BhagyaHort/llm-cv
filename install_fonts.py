#!/usr/bin/env python3
"""install_fonts.py — build the LM Roman 10 TTF files the ReportLab renderers need.

The ReportLab fallback renderers look for lmroman10-{regular,bold,italic,bolditalic}.ttf
in okf/fonts/. GUST ships Latin Modern only as OpenType/CFF (.otf), and MiKTeX already
has those files on disk, so this script converts them to TrueType (quadratic outlines)
with fontTools instead of downloading anything.

Usage:
    python install_fonts.py                 # auto-find MiKTeX's LM Roman 10 .otf files
    python install_fonts.py --src <dir>     # use a different folder of lmroman10-*.otf
    python install_fonts.py --system        # also copy the TTFs to your per-user Windows fonts
                                            # folder (copy only; no registry changes)
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

SKILL_DIR = Path(__file__).parent.resolve()
OUT_DIR = SKILL_DIR / "okf" / "fonts"
STYLES = ("regular", "bold", "italic", "bolditalic")


def find_source_dir() -> Path | None:
    """Locate the folder holding lmroman10-*.otf (MiKTeX user or shared install)."""
    candidates = []
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", r"C:\Program Files")
    for base in (
        Path(local) / "Programs" / "MiKTeX",
        Path(prog) / "MiKTeX",
        Path(local) / "MiKTeX",
    ):
        candidates.append(base / "fonts" / "opentype" / "public" / "lm")
    for c in candidates:
        if (c / "lmroman10-regular.otf").exists():
            return c
    for base in (Path(local) / "Programs" / "MiKTeX", Path(prog) / "MiKTeX"):
        if base.exists():
            for hit in base.rglob("lmroman10-regular.otf"):
                return hit.parent
    return None


def otf_to_ttf(src: Path, dst: Path, max_err: float = 1.0) -> None:
    """Convert a CFF-flavoured OpenType font to TrueType outlines."""
    font = TTFont(src)
    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()

    glyf = newTable("glyf")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(glyph_set)
        glyph_set[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
        glyf.glyphs[name] = pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf

    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for attr, val in (
        ("maxZones", 1), ("maxTwilightPoints", 0), ("maxStorage", 0),
        ("maxFunctionDefs", 0), ("maxInstructionDefs", 0), ("maxStackElements", 0),
        ("maxSizeOfInstructions", 0), ("maxComponentElements", 0),
        ("maxPoints", 0), ("maxContours", 0), ("maxCompositePoints", 0),
        ("maxCompositeContours", 0), ("maxComponentDepth", 0),
    ):
        setattr(maxp, attr, val)

    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = glyph_order

    font["head"].glyphDataFormat = 0
    font.sfntVersion = "\x00\x01\x00\x00"
    for tag in ("CFF ", "VORG"):
        if tag in font:
            del font[tag]
    font.save(dst)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, help="folder containing lmroman10-*.otf")
    ap.add_argument("--system", action="store_true",
                    help="also copy the TTFs into %%LOCALAPPDATA%%\\Microsoft\\Windows\\Fonts")
    args = ap.parse_args()

    src_dir = args.src or find_source_dir()
    if not src_dir or not src_dir.exists():
        print("ERROR: could not find lmroman10-*.otf. Install the MiKTeX 'lm' package "
              "(mpm --install=lm) or pass --src <folder>.", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for style in STYLES:
        src = src_dir / f"lmroman10-{style}.otf"
        if not src.exists():
            print(f"ERROR: missing {src}", file=sys.stderr)
            return 1
        dst = OUT_DIR / f"lmroman10-{style}.ttf"
        otf_to_ttf(src, dst)
        written.append(dst)
        print(f"  {src.name} -> {dst.relative_to(SKILL_DIR)} ({dst.stat().st_size // 1024} KB)")

    if args.system:
        target = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts"
        target.mkdir(parents=True, exist_ok=True)
        for f in written:
            shutil.copy2(f, target / f.name)
        print(f"Copied to {target} (sign out/in or right-click > Install for Windows to list them).")

    # Drop the cached font lookup so renderers re-scan and pick up the new files.
    cache = SKILL_DIR / "okf" / ".font_cache.json"
    if cache.exists():
        cache.unlink()
    print("LM Roman 10 TTF fonts ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
