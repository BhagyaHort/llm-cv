"""
config.py — Centralized configuration for the LLM-CV pipeline (Windows + Claude Desktop).

Provides default paths, tool discovery and constants with environment variable
override support. Everything is resolved relative to this folder or to standard
Windows locations, so the project can live anywhere (OneDrive included).
"""
import glob
import json
import os
import shutil
import sys


# Base paths (override with environment variables if needed)
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SKILL_DIR  # self-contained; Applications/ lives inside it

DEFAULT_BASE_FILES_DIR = os.getenv(
    "LLM_CV_BASE_FILES_DIR",
    os.path.join(SKILL_DIR, "okf", "base_files")
)

# Applications directory (where the pipeline saves application folders).
# Defaults to <project>/Applications (git-ignored). Override via LLM_CV_APPLICATIONS_DIR.
APPLICATIONS_DIR = os.getenv(
    "LLM_CV_APPLICATIONS_DIR",
    os.path.join(SKILL_DIR, "Applications")
)

# Obsidian vault used by sync_to_obsidian.py / check_duplicate_application.py.
# Optional: if the folder does not exist those steps are skipped with a warning.
OBSIDIAN_VAULT_DIR = os.getenv(
    "LLM_CV_VAULT_DIR",
    os.path.join(os.path.expanduser("~"), "Documents", "Obsidian Vault")
)


# ─── Tool discovery (Windows) ─────────────────────────────────────────────────

def find_venv_python() -> str:
    """Python interpreter inside the project's .venv (Scripts/ on Windows, bin/ elsewhere)."""
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        cand = os.path.join(SKILL_DIR, ".venv", *rel)
        if os.path.exists(cand):
            return cand
    return sys.executable


def find_claude_cli() -> str | None:
    """Locate the Claude Code executable that ships with the Claude Desktop app.

    Order: LLM_CV_CLAUDE_CLI env var, `claude` on PATH, then the newest
    claude.exe under %LOCALAPPDATA%/Claude-Data/*/claude-code/<version>/*/.
    The version folder changes on every Desktop update, so it is globbed, not hardcoded.
    """
    env = os.getenv("LLM_CV_CLAUDE_CLI")
    if env and os.path.exists(env):
        return env
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    local = os.environ.get("LOCALAPPDATA", "")
    roaming = os.environ.get("APPDATA", "")
    hits = []
    for base in (local, roaming):
        if base:
            hits += glob.glob(os.path.join(base, "Claude-Data", "*", "claude-code", "*", "*", "claude.exe"))
            hits += glob.glob(os.path.join(base, "Claude", "claude-code", "*", "claude.exe"))
    if not hits:
        return None

    def _version_key(path: str):
        parts = os.path.normpath(path).split(os.sep)
        ver = next((p for p in parts if p[:1].isdigit() and "." in p), "0")
        return tuple(int(x) if x.isdigit() else 0 for x in ver.split("."))

    return max(hits, key=_version_key)


def find_miktex_bin() -> str | None:
    """Folder containing pdflatex.exe (MiKTeX per-user or all-users install)."""
    on_path = shutil.which("pdflatex")
    if on_path:
        return os.path.dirname(on_path)
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("ProgramFiles", r"C:\Program Files")
    for base in (
        os.path.join(local, "Programs", "MiKTeX"),
        os.path.join(prog, "MiKTeX"),
        os.path.join(local, "MiKTeX"),
    ):
        cand = os.path.join(base, "miktex", "bin", "x64")
        if os.path.exists(os.path.join(cand, "pdflatex.exe")):
            return cand
    return None


# ─── Candidate personal info ──────────────────────────────────────────────────
# Used by renderers as fallback defaults and by step docs as reference values.
# The YAML `name`/`sender` fields always take precedence over these defaults.
CANDIDATE_NAME = os.getenv("LLM_CV_CANDIDATE_NAME", "Bhagya Lekshmi Vikraman Nair")
CANDIDATE_FILE_PREFIX = os.getenv("LLM_CV_CANDIDATE_FILE_PREFIX", "BHAGYA_LEKSHMI_VIKRAMAN_NAIR")
CANDIDATE_PHONE = os.getenv("LLM_CV_CANDIDATE_PHONE", "+49 176 87731064")
CANDIDATE_EMAIL = os.getenv("LLM_CV_CANDIDATE_EMAIL", "bhagyanair224@gmail.com")
CANDIDATE_LINKEDIN = os.getenv("LLM_CV_CANDIDATE_LINKEDIN", "https://www.linkedin.com/in/bhagyalekshmi224")
CANDIDATE_GITHUB = os.getenv("LLM_CV_CANDIDATE_GITHUB", "")  # no GitHub portfolio

# Candidate photo (headshot) for resume — stamped onto the final PDF's top-right
# corner as a post-processing step. Empty/missing file = no photo is stamped.
# Drop a headshot at okf/BHAGYA_LEKSHMI_foto.jpg (or set LLM_CV_CANDIDATE_PHOTO).
CANDIDATE_PHOTO = os.getenv(
    "LLM_CV_CANDIDATE_PHOTO",
    os.path.join(SKILL_DIR, "okf", "BHAGYA_LEKSHMI_foto.jpg")
)

# Candidate signature image for cover letter — PNG with transparent background.
# Empty/missing file = the cover letter falls back to the typed name only.
CANDIDATE_SIGNATURE = os.getenv(
    "LLM_CV_CANDIDATE_SIGNATURE",
    os.path.join(SKILL_DIR, "okf", "BHAGYA_LEKSHMI_signature.png")
)

# ATS terms the parseability audit must always find in the final PDF text, in addition to
# the skills/tools listed in Resume.yaml. Empty by default (the YAML's own skills are checked).
# Example: LLM_CV_CRITICAL_TERMS="ImageJ,Excel"
CRITICAL_ATS_TERMS = [t.strip() for t in os.getenv("LLM_CV_CRITICAL_TERMS", "").split(",") if t.strip()]

# Diversity audit thresholds
DIVERSITY_VENDOR_CLUSTER_THRESHOLD = int(os.getenv("LLM_CV_DIVERSITY_VENDOR_THRESHOLD", "3"))
DIVERSITY_REFERRAL_RATE_MIN = float(os.getenv("LLM_CV_DIVERSITY_REFERRAL_MIN", "0.20"))
DIVERSITY_LOOKBACK_DAYS = int(os.getenv("LLM_CV_DIVERSITY_LOOKBACK_DAYS", "14"))


# ─── Candidate home city ──────────────────────────────────────────────────────
# Single home city (Berlin): nearest_candidate_city() returns it for every job
# location. Add more cities + JOB_LOCATION_TO_CANDIDATE_CITY entries to restore
# nearest-city matching.
CANDIDATE_CITIES = {
    "Berlin": (52.52, 13.40),
}

# Only consulted when CANDIDATE_CITIES has more than one entry.
JOB_LOCATION_TO_CANDIDATE_CITY = {
    "Berlin": "Berlin, Germany",
    "Potsdam": "Berlin, Germany",
    "Remote": "Berlin, Germany",
    "Germany": "Berlin, Germany",
}


def nearest_candidate_city(job_location: str) -> str:
    """Look up the nearest candidate city for a job location string.

    Uses the static JOB_LOCATION_TO_CANDIDATE_CITY table first, then falls back
    to a persistent location cache (okf/.location_cache.json) for locations
    previously resolved via web search. Returns None if the location is not
    found in either the table or the cache (caller should fall back to web
    search and then call cache_location_result() to store the answer).
    Normalizes input by stripping whitespace and trying case-insensitive match.
    """
    if not job_location:
        return None
    loc = job_location.strip()
    # Single home city: every job location maps to it, no lookup needed.
    if len(CANDIDATE_CITIES) == 1:
        return f"{next(iter(CANDIDATE_CITIES))}, Germany"
    # Try exact match first
    if loc in JOB_LOCATION_TO_CANDIDATE_CITY:
        return JOB_LOCATION_TO_CANDIDATE_CITY[loc]
    # Try case-insensitive match
    loc_lower = loc.lower()
    for key, value in JOB_LOCATION_TO_CANDIDATE_CITY.items():
        if key.lower() == loc_lower:
            return value
    # Try substring match (e.g., "Munich, Germany" contains "Munich")
    for key, value in JOB_LOCATION_TO_CANDIDATE_CITY.items():
        if key.lower() in loc_lower:
            return value
    # Check the location cache (for locations previously resolved via web search)
    cached = _lookup_location_cache(loc)
    if cached:
        return cached
    return None


# ─── Location web search cache ────────────────────────────────────────────────
# Caches results of web searches for job locations not in the static table.
# Geography doesn't change, so cache entries are permanent.

_LOCATION_CACHE_PATH = os.path.join(SKILL_DIR, "okf", ".location_cache.json")


def _load_location_cache() -> dict:
    """Load the location cache from disk."""
    try:
        if os.path.exists(_LOCATION_CACHE_PATH):
            with open(_LOCATION_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_location_cache(cache: dict) -> None:
    """Save the location cache to disk."""
    try:
        os.makedirs(os.path.dirname(_LOCATION_CACHE_PATH), exist_ok=True)
        with open(_LOCATION_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _lookup_location_cache(job_location: str) -> str | None:
    """Check the location cache for a previously resolved location.

    Tries exact, case-insensitive, and substring matches (same strategy as
    the static table).
    """
    cache = _load_location_cache()
    if not cache:
        return None
    loc = job_location.strip()
    if loc in cache:
        return cache[loc]
    loc_lower = loc.lower()
    for key, value in cache.items():
        if key.lower() == loc_lower:
            return value
    for key, value in cache.items():
        if key.lower() in loc_lower:
            return value
    return None


def cache_location_result(job_location: str, nearest_city: str) -> None:
    """Store a web-search-resolved location in the persistent cache.

    Called by the pipeline after a web search resolves a location that wasn't
    in the static table. Future runs with the same location will hit the cache
    instead of doing another web search.
    """
    if not job_location or not nearest_city:
        return
    cache = _load_location_cache()
    cache[job_location.strip()] = nearest_city.strip()
    _save_location_cache(cache)


