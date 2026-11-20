#!/bin/bash
###############################################################################
# lib/env.sh — Windows (Git Bash) environment bootstrap for the llm-cv pipeline
#
# Sourced by run_pipeline.sh. Sets, as MIXED-style paths (C:/Users/...) that both
# Git Bash and native Windows programs understand:
#   SCRIPT_DIR        project folder (works with spaces, OneDrive, any cwd)
#   VENV_PYTHON       .venv\Scripts\python.exe (falls back to python on PATH)
#   APPLICATIONS_DIR  where application folders are written (config.py default)
#   LLM_TMP           per-run scratch folder (replaces /tmp, which Windows Python can't see)
# and puts MiKTeX (pdflatex) on PATH. Also forces UTF-8 for Python output.
###############################################################################

# Mixed-style path helper: C:/Users/... on Git Bash, unchanged elsewhere.
to_win() {
    if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}
# Strip Windows CRs from captured Python output.
strip_cr() { tr -d '\r'; }

# Project root = parent of this lib/ folder (independent of who sources this file or the cwd).
SCRIPT_DIR="$(to_win "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)")"

if [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
    VENV_PYTHON="$SCRIPT_DIR/.venv/Scripts/python.exe"
elif [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
else
    # No venv yet: use any working system Python (skips the Microsoft Store 'python3' stub).
    VENV_PYTHON=""
    for cand in python py; do
        if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
            VENV_PYTHON="$(command -v "$cand")"; break
        fi
    done
    [[ -n "$VENV_PYTHON" ]] || { echo "[error] No Python found. Run setup_windows.ps1 first." >&2; exit 1; }
fi

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

# Paths come from config.py so the shell and Python always agree.
APPLICATIONS_DIR="$(cd "$SCRIPT_DIR" && "$VENV_PYTHON" -c \
    "import config; print(config.APPLICATIONS_DIR.replace(chr(92), '/'))" | strip_cr)"
export LLM_CV_APPLICATIONS_DIR="$APPLICATIONS_DIR"
mkdir -p "$APPLICATIONS_DIR"

MIKTEX_BIN="$(cd "$SCRIPT_DIR" && "$VENV_PYTHON" -c \
    "import config; print(config.find_miktex_bin() or '')" | strip_cr)"
if [[ -n "$MIKTEX_BIN" ]] && ! command -v pdflatex >/dev/null 2>&1; then
    if command -v cygpath >/dev/null 2>&1; then
        PATH="$(cygpath -u "$MIKTEX_BIN"):$PATH"
    else
        PATH="$MIKTEX_BIN:$PATH"
    fi
    export PATH
fi

LLM_TMP="$(to_win "$(mktemp -d -t llm-cv-XXXXXX)")"
trap 'rm -rf "$LLM_TMP"' EXIT
