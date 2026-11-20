#!/usr/bin/env python3
"""set_boost.py — set `layout_boost: N` (0-4) in a Resume.yaml without touching anything else.

Usage: python lib/set_boost.py <Resume.yaml> <level>
"""
import re
import sys
from pathlib import Path

path, level = Path(sys.argv[1]), int(sys.argv[2])
text = path.read_text(encoding="utf-8")
line = f"layout_boost: {level}"
if re.search(r"^layout_boost:.*$", text, flags=re.M):
    text = re.sub(r"^layout_boost:.*$", line, text, flags=re.M)
else:
    text = text.rstrip("\n") + "\n" + line + "\n"
path.write_text(text, encoding="utf-8")
print(line)
