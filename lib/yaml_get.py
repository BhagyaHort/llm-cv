#!/usr/bin/env python3
"""yaml_get.py — print one value from a YAML file (used by run_pipeline.sh).

Replaces the inline `python -c "..."` snippets so shell code never has to embed
Windows paths inside Python source (backslashes/spaces break those).

Usage:
    python lib/yaml_get.py <file.yaml> <dotted.key.path> [default]

Lists print comma-joined; a missing key prints the default ("" if none given).
"""
import sys

import yaml


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: yaml_get.py <file.yaml> <dotted.key> [default]", file=sys.stderr)
        return 2
    path, key = sys.argv[1], sys.argv[2]
    default = sys.argv[3] if len(sys.argv) > 3 else ""
    try:
        with open(path, encoding="utf-8") as fh:
            node = yaml.safe_load(fh)
        for part in key.split("."):
            node = node[part]
    except Exception:
        print(default)
        return 0
    if isinstance(node, list):
        print(", ".join(str(x) for x in node) if node else default)
    elif node is None or node == "":
        print(default)
    else:
        print(node)
    return 0


if __name__ == "__main__":
    sys.exit(main())
