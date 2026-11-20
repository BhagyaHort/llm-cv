#!/usr/bin/env python3
"""
api_pipeline.py — Claude Code-backed model calls for the llm-cv pipeline (Windows).

Architecture: Shared system prompt with one isolated Claude Code (print mode) call per step.
  - Large SYSTEM_PROMPT loaded once at module import.
  - The claude.exe bundled with the Claude Desktop app is used (auto-discovered; see
    config.find_claude_cli). Authentication comes from `claude auth login` (one-time) or
    the ANTHROPIC_API_KEY / CLAUDE_CODE_OAUTH_TOKEN environment variables.
  - Optional: LLM_CV_MODEL and LLM_CV_EFFORT choose a specific model / effort level.
  - Variable user message contains JD, ATS report, config, and task instructions.

Usage:
    python api_pipeline.py step1 --jd-file jd.txt --render latex \
        --style german --source "Cold Apply" --language English
    python api_pipeline.py step2 --app-dir /path/to/app --render latex \
        --style german --language English --stuffing none --score-boost true
    python api_pipeline.py step3 --app-dir /path/to/app --render latex \
        --language English
    python api_pipeline.py fix --app-dir /path/to/app --error "parseability failed: ..."
"""

import argparse
import json
import os
import re
import sys
import time
import threading
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

from tqdm import tqdm

SKILL_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SKILL_DIR))
import config  # noqa: E402

APPLICATIONS_DIR = Path(config.APPLICATIONS_DIR)
VENV_PYTHON = config.find_venv_python()
CANDIDATE_NAME = config.CANDIDATE_NAME
CANDIDATE_NAME_UPPER = CANDIDATE_NAME.upper()
FILE_PREFIX = config.CANDIDATE_FILE_PREFIX
CANDIDATE_LINKEDIN_SHORT = config.CANDIDATE_LINKEDIN.replace("https://", "").replace("http://", "")

# ─── Harness Configuration ───────────────────────────────────────────────────

API_TIMEOUT = int(os.getenv("LLM_CV_API_TIMEOUT", "900"))


# ─── File Reading Helpers ────────────────────────────────────────────────────

def read_file(path: Path) -> str:
    """Read a file, return empty string if not found."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"WARN: Could not read {path}: {e}", file=sys.stderr)
        return ""


def detect_archetype(jd_text: str) -> str:
    """Detect role archetype from JD text."""
    jd_lower = jd_text.lower()
    archetypes = {
        "Plant Research & Experiments": [
            "plant experiment", "plant science", "research assistant", "research", "laboratory",
            "lab ", "phenotyp", "plant physiology", "plant breeding", "isotope", "greenhouse",
            "pflanzenversuch", "pflanzenwissenschaft", "labor", "forschung", "werkstudent",
            "product development", "produktentwicklung"],
        "Quality Control & Food Safety": [
            "quality control", "quality assurance", "qualitätskontrolle", "qualitätssicherung",
            "food safety", "lebensmittelsicherheit", "haccp", "qa ", "qc ", "compliance",
            "audit", "inspection", "contamination", "lebensmittel", "hygiene"],
        "Hydroponics & Controlled-Environment Agriculture": [
            "hydroponic", "hydroponik", "controlled environment", "controlled-environment",
            "vertical farm", "indoor farm", "indoor farming", "microgreen", "aquaponic",
            "soilless", "substrat", "cea ", "urban farming", "urban agriculture"],
    }
    best = "Plant Research & Experiments"
    best_score = 0
    for archetype, keywords in archetypes.items():
        score = sum(1 for kw in keywords if kw in jd_lower)
        if score > best_score:
            best_score = score
            best = archetype
    return best


def get_base_resume(language: str, archetype: str) -> str:
    """Load the base resume file for the given language and archetype."""
    lang_dir = "english" if language == "English" else "german"
    base_dir = SKILL_DIR / "okf" / "base_files" / lang_dir

    archetype_files = {
        "Plant Research & Experiments": "resume_plant_research.md",
        "Quality Control & Food Safety": "resume_quality_control.md",
        "Hydroponics & Controlled-Environment Agriculture": "resume_hydroponics_cea.md",
    }

    filename = archetype_files.get(archetype, "resume.md")
    if language == "German":
        filename = filename.replace(".md", "_de.md")
        if not (base_dir / filename).exists():
            filename = "resume_de.md"

    path = base_dir / filename
    content = read_file(path)
    if not content:
        fallback = "resume.md" if language == "English" else "resume_de.md"
        content = read_file(base_dir / fallback)
    return content


def get_nearest_city(job_location: str) -> str:
    """Get nearest candidate city using config.py."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", SKILL_DIR / "config.py")
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        city = config.nearest_candidate_city(job_location)
        return city or "Berlin, Germany"
    except Exception:
        return "Berlin, Germany"


# ─── Static System Prompt (cached across all calls) ──────────────────────────

def _load_system_prompt() -> str:
    """Build the large static system prompt with step docs, schemas, and golden examples.

    This is loaded ONCE at module import and sent as the system message for every
    harness invocation. Provider caching is managed by the harness.
    """
    # Load step docs
    step2_doc = read_file(SKILL_DIR / "02_resume_and_visual_audit.md")
    step3_doc = read_file(SKILL_DIR / "03_cover_letter.md")
    score_boost_doc = read_file(SKILL_DIR / "prompts" / "score_boost.md")

    # Optional golden examples: drop a finished, interview-winning application into
    # okf/golden/Resume.yaml and okf/golden/Cover_Letter.yaml and they are added to the
    # system prompt automatically. Without them the prompt simply omits the section.
    golden_resume = read_file(SKILL_DIR / "okf" / "golden" / "Resume.yaml")
    golden_cover = read_file(SKILL_DIR / "okf" / "golden" / "Cover_Letter.yaml")
    golden_section = ""
    if golden_resume or golden_cover:
        golden_section = f"""
# GOLDEN EXAMPLE — RESUME (interview-winning application)
# Match this format and level of specificity.

{golden_resume}

# GOLDEN EXAMPLE — COVER LETTER (same application)

{golden_cover}
"""

    return f"""You are an expert ATS resume optimization system for a German job market candidate ({CANDIDATE_NAME}).
The candidate is a plant scientist: M.Sc. Horticultural Sciences (Humboldt-Universität zu Berlin, in progress),
B.Sc. Agriculture, with plant-experiment, hydroponics, laboratory and food-safety quality-control experience.
You output ONLY valid YAML or markdown as instructed. No explanations, no commentary outside the requested output.
Follow schemas exactly. Quote all string values containing colons, dashes, or special characters.
Use block scalars (|) for multi-line content. Never fabricate metrics, projects, employers, dates or skills.

# GUARDRAILS (NON-NEGOTIABLE)

## Anti-Hallucination
1. Projects/experience items: ONLY those in the provided catalog and base resume. No inventing/splitting/merging.
2. Metrics: ONLY numbers present in catalog key_metrics, catalog bullets or the base resume
   (e.g. dates, 40 hours per month, studies from 2018-2022, 23-page report). NEVER invent percentages,
   sample sizes, yields or results. If no number exists, write a concrete qualitative outcome instead.
3. Technologies / methods: Only from catalog, base resume, or JD required skills the candidate genuinely has.
4. Company & Role: Verbatim from JD.
5. Employment History: Dates/titles/employers from the base resume are immutable.
6. Repo URLs: Verbatim from catalog repo_url field. If empty (the default), omit the link entirely.
7. Never claim a work permit/visa status, a GitHub portfolio, certifications or language levels that are not in the base resume.

## YAML Safety
1. Quote all string values containing : - # > | {{ }} [] or quotes.
2. Use block scalars (|) for multi-line content.
3. Never paste raw text into YAML without quoting or block-scaling.

## Stop-Slop Writing Rules
1. Strict active voice — every sentence leads with action.
2. No adverbs ending in -ly (successfully, effectively, genuinely, actually, really).
3. No em-dashes (—) in prose. Use commas or periods. --- separators in project names are OK.
4. No throat-clearing ("at its core", "it is worth noting", "the reality is").
5. No AI fluff ("passionate", "thrilled", "excited", "delighted", "eager").

# RESUME CONSTRAINTS (NON-NEGOTIABLE)

1. Project summaries: exactly 3 bullets per project, each 60-100 chars, total <= 300 chars per project (EN) / 280 (DE).
   Use a number ONLY when the catalog or base resume supplies one (rule 2 above). A bullet without a number
   is fine; a fabricated number is a FAIL.
2. Experience entries: keep all employers from the base resume (FYTA, ZALF, Our Greenery GmbH and the RAWE programme),
   most recent first. 3-5 bullets for substantial roles (FYTA, ZALF, Our Greenery), 1-2 bullets for RAWE.
   Pick the most JD-relevant bullets from the catalog/base resume; each bullet <= 140 chars.
3. Technical skills: JD-relevant only (anti-stuffing). Prioritize JD-required -> core experience tools -> adjacent strengths.
   Group into 4-6 categories with 4-7 skills each (e.g. Plant Science & Cultivation, Laboratory & Analytical,
   Quality & Food Safety, Data & Software, Research & Collaboration, Certifications & Training).
4. Project tools/methods: 3-5 most JD-relevant per project.
5. Project names: SHORTEN to under 50 chars. Drop subtitles after colons.
   BAD: "Master's Thesis: Antihyperglycemic Potential of Costus pictus (Insulin Plant)"
   GOOD: "Master's Thesis: Costus pictus Phytochemistry"
6. Section order (US Style): Summary -> Technical Skills -> Projects -> Professional Experience -> Education -> Languages
   (US style: projects are a SEPARATE top-level `projects:` section in the YAML)
7. Section order (German Style): Summary -> Professional Experience -> Education -> Technical Skills -> Languages
   (German style: NO separate `projects:` section. The Master's thesis becomes its own professional_experience entry
   "Humboldt-Universität zu Berlin" / "Master's Thesis Researcher" with plain bullets, placed in date order.
   Do NOT use project_bullets and do NOT include a top-level `projects:` key in German style YAML.)
8. LENGTH — MINIMUM 1.5 PAGES (NON-NEGOTIABLE), MAXIMUM 2 PAGES (A4). Aim for about 1.7 pages.
   A resume under 1.5 pages is rejected automatically and sent back to you. Reach the length with REAL content
   from the base resume and catalog, never padding or invented facts:
   - every employer in the base resume, 4-5 bullets each for FYTA, ZALF, Our Greenery and 2-3 for RAWE;
   - every project that fits the JD, 3 bullets each;
   - 5-6 technical_skills categories with 6-8 genuine skills each;
   - an `details` list (2-4 short lines) under each education entry: thesis topic, relevant modules
     (names and grades exactly as in the base resume), GPA, exchange credits;
   - bullets close to their length limit (<=140 chars) but concrete, never padded.
   Never exceed 2 pages and never shrink fonts or margins.
9. Anti-hallucination: only projects from selected_projects.yaml, metrics from catalog key_metrics.
10. Use 2-5 projects. The candidate has few projects, so include every one that fits the JD.
11. Education stays complete: M.Sc. (expected 05/2027), Erasmus exchange (BOKU Vienna, 03/2025), B.Sc. (11/2020).
    In-progress degrees use exactly "expected 05/2027" (German: "voraussichtlich 05/2027"), never "present".
12. Languages: English (C2), German (A2) unless the base resume says otherwise.
13. Education `details` (optional list of strings per education entry) may only restate facts from the base resume.

# DYNAMIC TAILORING TO THE JOB DESCRIPTION (EVERY RUN)

Do not reuse the base resume verbatim. Re-derive everything from THIS JD (Job_Description.yaml and ATS_Report.yaml):
1. Separate must-have from nice-to-have requirements. Rank every catalog project and every experience bullet by
   how directly it proves a must-have, then order projects and bullets by that rank (best first).
2. Summary: position the candidate for THIS role (use the JD's own role wording where truthful: working student,
   intern, quality assurance, research assistant, hydroponics technician...).
3. Technical skills: name and order the categories after the JD's own wording; JD-required skills the candidate
   genuinely has come first; use the JD's exact term when it matches a real skill (e.g. "Qualitätssicherung",
   "food safety standards"). Genuine skills the JD does not mention move to the end, they are not deleted
   (the length minimum still applies).
4. Bullets: rewrite with the JD's vocabulary where it is truthful; give more bullets and more detail to the
   experience that best matches the JD, fewer to the rest (never below the minimums in rule 2 of this section).
5. Archetype: follow role_archetype from ATS_Report.yaml, blend in a second archetype when the JD mixes
   (e.g. lab work plus quality control).
6. German style section order (German CV convention: reverse-chronological, 2 pages at most): ALWAYS write a top-level
   `section_order` key. Student / working-student / intern / Praktikum / Werkstudent JDs ->
   [summary, education, professional_experience, technical_skills, spoken_languages]
   (a student's current studies lead). All other JDs ->
   [summary, professional_experience, education, technical_skills, spoken_languages].
7. Language: write everything in the language selected by the user, not the JD's language.

# SCORE-BOOST MEASURES (always active)

{score_boost_doc}

# COVER LETTER RULES

1. Match target JD language exactly.
2. Geschäftsbrief layout: Sender -> Recipient -> Date -> Subject -> Salutation -> Body -> Closing.
3. English: max 4 paragraphs, 250-320 words. German: max 4 paragraphs, 180-240 words.
4. Ground every claim in SPECIFIC facts from project_info (methods, systems, instruments, tasks). Don't paraphrase the JD — show your work.
   BAD: "I bring experience in plant research and quality control."
   GOOD: "At ZALF I measured root hair and root architecture in ImageJ for the RhizoTraits project and prepared soil samples for 15N isotope analysis."
5. No resume rehash — cover letter carries info the resume does not. Focus on HOW you did things, not WHAT.
6. Paragraph structure:
   - P1: Hook — link a specific JD requirement to a specific experience. State what you'd do in the first 90 days.
   - P2: Deep dive experience/project 1 — specific methods, specific decisions.
   - P3: Deep dive experience/project 2 — different angle.
   - P4: Languages (English C2, German A2), availability only as far as the base resume states it, closing motivation.
7. No raw URLs in prose.
8. If Referral/LinkedIn Connection, mention weak_tie_contact in paragraph 1.
9. German conventions: real umlauts (not ae/oe/ue), "Mit freundlichen Grüßen" without comma,
    date "City, DD.MM.YYYY" numeric, sender "city, Deutschland".
10. Subject uses exact job title from Job_Description.yaml.

# STEP 2 DOC (full reference)

{step2_doc}

# STEP 3 DOC (full reference)

{step3_doc}
{golden_section}"""


SYSTEM_PROMPT = _load_system_prompt()


# ─── Claude Code Call ────────────────────────────────────────────────────────

_NOT_LOGGED_IN_HELP = (
    "Claude Code is not signed in. One-time fix (pick one):\n"
    '  1. "{cli}" auth login            (opens the browser; uses your Claude subscription)\n'
    '  2. "{cli}" setup-token           then set CLAUDE_CODE_OAUTH_TOKEN to the printed token\n'
    "  3. set ANTHROPIC_API_KEY to an Anthropic API key\n"
    "Then re-run the pipeline."
)


def call_harness(prompt: str, system: str = None, progress_pos: int = 0) -> str:
    """Return the assistant text from one isolated Claude Code print-mode call.

    Uses the claude.exe bundled with the Claude Desktop app. Tools, skills, MCP servers
    and session persistence are all disabled: this is a pure text-in/text-out call.
    Prompt and system prompt go through files/stdin so the Windows 32K command-line
    limit never applies.
    """
    system = system or SYSTEM_PROMPT
    cli = config.find_claude_cli()
    if not cli:
        raise RuntimeError(
            "claude.exe not found. Install/open the Claude Desktop app, or set "
            "LLM_CV_CLAUDE_CLI to the full path of claude.exe.")

    model = os.getenv("LLM_CV_MODEL", "").strip()
    effort = os.getenv("LLM_CV_EFFORT", "").strip()
    label = f"Claude Code{' (' + model + ')' if model else ''}"

    pbar = tqdm(
        total=1, unit="req",
        desc=f"  ↳ {label}",
        file=sys.stderr,
        leave=False,
        position=progress_pos,
        bar_format="{desc} |{bar}| {elapsed} {postfix}",
    )

    stop_event = threading.Event()

    def _tick():
        while not stop_event.wait(0.5):
            pbar.refresh()

    ticker = threading.Thread(target=_tick, daemon=True)
    ticker.start()

    start = time.time()
    try:
        with tempfile.TemporaryDirectory(prefix="llm-cv-claude-") as workspace:
            system_path = Path(workspace) / "system.txt"
            system_path.write_text(system, encoding="utf-8")
            cmd = [
                cli, "-p", "--output-format", "json",
                "--no-session-persistence",
                "--tools", "",
                "--disable-slash-commands",
                "--strict-mcp-config",
                "--system-prompt-file", str(system_path),
            ]
            if model:
                cmd += ["--model", model]
            if effort:
                cmd += ["--effort", effort]
            env = dict(os.environ, PYTHONUTF8="1")
            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,          # prompt via stdin (file-sized prompts are fine)
                    cwd=workspace,         # empty folder: no project CLAUDE.md / settings picked up
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=API_TIMEOUT,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(
                    f"Claude Code call exceeded {API_TIMEOUT}s (raise LLM_CV_API_TIMEOUT).")

        stdout = (result.stdout or "").strip()
        try:
            payload = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {}
        text = payload.get("result", "") if isinstance(payload, dict) else ""

        if result.returncode != 0 or payload.get("is_error"):
            detail = text or (result.stderr or "").strip() or stdout[:500]
            if "not logged in" in detail.lower() or "/login" in detail.lower():
                raise RuntimeError(_NOT_LOGGED_IN_HELP.format(cli=cli))
            raise RuntimeError(f"Claude Code call failed (exit {result.returncode}): {detail[:800]}")
        if not text.strip():
            raise RuntimeError("Claude Code returned an empty response")

        pbar.update(1)
        models = ", ".join((payload.get("modelUsage") or {}).keys()) or "default model"
        cost = payload.get("total_cost_usd")
        cost_s = f" ~${cost:.3f}" if isinstance(cost, (int, float)) and cost else ""
        print(f"[claude] {time.time() - start:.1f}s — {models}{cost_s}", file=sys.stderr)
        return text
    finally:
        stop_event.set()
        ticker.join(timeout=1)
        pbar.close()


def windows_safe_name(name: str, max_len: int = 60) -> str:
    """Strip characters Windows forbids in file names and keep paths short (260-char limit)."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return cleaned[:max_len].rstrip(" .") or "Unknown"


def validate_yaml(yaml_text: str) -> bool:
    """Validate YAML in-process (works on Windows; no /dev/stdin)."""
    import yaml
    try:
        yaml.safe_load(yaml_text)
        return True
    except Exception:
        return False


def write_yaml_file(path: Path, yaml_text: str) -> bool:
    """Write YAML to file and validate it."""
    path.write_text(yaml_text, encoding="utf-8")
    if validate_yaml(yaml_text):
        print(f"[ok] Wrote {path.name} ({len(yaml_text)} bytes, valid YAML)", file=sys.stderr)
        return True
    else:
        print(f"[warn] Wrote {path.name} but YAML validation failed", file=sys.stderr)
        return False


# ─── Prompt Builders (variable suffix only — system prompt is static) ────────

def build_step1_prompt(jd_text: str, render_mode: str, resume_style: str,
                       app_source: str, language: str, weak_tie: str = "") -> str:
    """Build the Step 1 variable suffix: ATS analysis + JD archival + project ranking."""

    catalog = read_file(SKILL_DIR / "okf" / "project_catalog_condensed.yaml")
    archetype = detect_archetype(jd_text)
    base_resume = get_base_resume(language, archetype)

    loc_match = re.search(r'(?:location|ort|standort|city)[:\s]+([^\n,]+)', jd_text, re.IGNORECASE)
    job_location = loc_match.group(1).strip() if loc_match else ""
    nearest_city = get_nearest_city(job_location) if job_location else "Berlin, Germany"

    return f"""# TASK: ATS Analysis, JD Archival & Project Ranking

Execute Step 1 of the llm-cv pipeline. Analyze the JD, score the base resume, rank projects, and output THREE files.

## Configuration
- render_mode: {render_mode}
- resume_style: {resume_style}
- application_source: "{app_source}"
- language: "{language}"
- weak_tie_contact: "{weak_tie}"
- closest_candidate_location: "{nearest_city}"

## Input: Job Description
{jd_text}

## Input: Base Resume (archetype: {archetype})
{base_resume}

## Input: Project Catalog (condensed — no bullets)
{catalog}

## Instructions

1. Detect role archetype from JD (Plant Research & Experiments, Quality Control & Food Safety, Hydroponics & Controlled-Environment Agriculture).
2. Score base resume against JD using 4-category ATS matrix (25pts each, 100 total):
   - keywords_and_terminology, experience_relevance, technical_skills, soft_skills_and_language
3. Extract skill_gaps: EVERY must-have skill, tool, method, standard or certification the JD names (e.g. GMP, HACCP, SAP, statistical software, a language level) that the base resume and catalog do not evidence. Be thorough: the user decides afterwards which gaps to add. Use an empty list only if the JD truly asks for nothing the candidate lacks.
4. Build improvement_blueprint (bullet density audit, project swap directive, keyword inventory, tech skills tuning, quantified outcomes).
5. Archive JD into clean YAML sections (overview, requirements, responsibilities, stack).
6. Rank up to 6 projects from catalog (rank all if fewer than 6) by: technology overlap, transferable skills, business-problem match, archetype fit, complexity, reframing potential.
7. Write project_info.md with all 6 ranked projects.

## Output Format

Output THREE YAML/Markdown blocks, each wrapped in code fences with a clear header:

### FILE 1: ATS_Report.yaml
```yaml
type: ats_report
company: "[Company Name]"
position: "[Job Position Title]"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
language: "{language}"
closest_candidate_location: "{nearest_city}"
ats_vendor: "[Workday/Personio/SAP SuccessFactors/Greenhouse/Lever/Taleo/Unknown]"
application_source: "{app_source}"
weak_tie_contact: {('null' if not weak_tie else f'"{weak_tie}"')}
role_archetype:
  primary: "[Archetype]"
  archetype_rationale: "[One sentence]"
ats_score_matrix:
  keywords_and_terminology: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  experience_relevance: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  technical_skills: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  soft_skills_and_language: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
  total_score: 0
formatting_quality:
  verdict: "Excellent"
  notes: ""
  suggestions: []
core_score_detractors: []
skill_gaps: []
placement_breakdown:
  keywords: []
improvement_blueprint:
  target_language_confirmation: "{language}"
  bullet_point_density_audit: []
  project_swap_directive:
    remove_projects: []
    add_projects: []
    volume_constraint_check: "3 projects selected"
  keyword_inventory:
    hard_skills: []
    methodologies: []
    domain_terms: []
  technical_skills_tuning:
    add: []
    remove: []
  quantified_outcomes: []
  ats_threshold_calibration:
    meets_target: false
    score_gate_verdict: "REVIEW"
    remedy_suggestions: []
```

### FILE 2: Job_Description.yaml
```yaml
type: job_description
company: "[Company Name]"
position: "[Job Position Title]"
location: "[Job Location]"
sections:
  - title: "Core Role Overview & Context"
    content: "[Overview paragraph]"
  - title: "Target Profile Requirements"
    bullets: ["[Requirement]"]
  - title: "Primary Responsibilities"
    bullets: ["[Responsibility]"]
  - title: "Tech Stack & Tooling"
    bullets: ["[Tool/Skill]"]
```

### FILE 3: project_info.md
```markdown
# Tailored Project Portfolio

# [Project Title]
[Description from catalog]
Problem: [business_problem]
Metrics: [key_metrics — cite verbatim]
Tech: [technologies]
Archetypes: [archetypes]
Repo: [repo_url]
[First 2 bullets from catalog]
<!-- LLM Rank: [rank], Reason: [one sentence] -->

Repeat for every ranked project.
```

## OUTPUT NOW
Output all three files. Do NOT ask questions. Do NOT explain. Just output the three code blocks."""


def build_step2_prompt(app_dir: Path, render_mode: str, resume_style: str,
                       language: str, stuffing: str, user_skills: str,
                       score_boost: str, initial_score: int) -> str:
    """Build the Step 2 variable suffix: Resume writer + ATS rescoring."""

    ats_report = read_file(app_dir / "ATS_Report.yaml")
    selected_projects = read_file(app_dir / "selected_projects.yaml")
    job_desc = read_file(app_dir / "Job_Description.yaml")

    archetype = "Plant Research & Experiments"
    arch_match = re.search(r'primary:\s*"?([^"\n]+)"?', ats_report)
    if arch_match:
        archetype = arch_match.group(1).strip()

    lang_dir = "english" if language == "English" else "german"
    base_resume = get_base_resume(language, archetype)

    keyword_stuffing = "false"
    if stuffing in ("all", "selective"):
        keyword_stuffing = "true"

    # Build the schema section based on style
    if resume_style == "german":
        schema_section = f"""
## Resume.yaml Schema (German Style — NO top-level projects: section)
type: resume
language: "{language}"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
resume_variation: "Balanced"
section_order: ["summary", "[education or professional_experience first, see DYNAMIC TAILORING rule 6]", "...", "technical_skills", "spoken_languages"]
keyword_stuffing: {keyword_stuffing}
user_directed_skills: [{('' if not user_skills else f'"{user_skills}"')}]
contact_info:
  name: "{CANDIDATE_NAME_UPPER}"
  location: "[from ATS_Report closest_candidate_location]"
  phone: "{config.CANDIDATE_PHONE}"
  email: "{config.CANDIDATE_EMAIL}"
  linkedin: "{CANDIDATE_LINKEDIN_SHORT}"
summary: "[2 lines, <=200 chars EN / <=170 DE, no tool names]"
technical_skills:
  - category: "[Category 1, named after the JD]"
    skills: ["[6-8 skills]"]
  - category: "[Category 2]"
    skills: ["[6-8 skills]"]
  - category: "[Category 3]"
    skills: ["[6-8 skills]"]
  - category: "[Category 4]"
    skills: ["[6-8 skills]"]
  - category: "[Category 5]"
    skills: ["[6-8 skills]"]
  - category: "[Category 6]"
    skills: ["[6-8 skills]"]
professional_experience:
  - company: "FYTA GmbH"
    location: "Berlin"
    date: "07/2026 – present"
    title: "Working Student, Plant Experiments and Product Development"
    bullets: ["[4-5 bullets from base resume/catalog, <=140 chars each]"]
  - company: "Humboldt-Universität zu Berlin"
    location: "Berlin"
    date: "07/2025 – present"
    title: "Master's Thesis Researcher"
    bullets: ["[4-5 bullets from the thesis catalog entry, <=140 chars each]"]
  - company: "Leibniz Centre for Agricultural Landscape Research (ZALF)"
    location: "Müncheberg"
    date: "06/2024 – 09/2024"
    title: "Research Assistant"
    bullets: ["[4-5 bullets, <=140 chars each]"]
  - company: "Our Greenery GmbH"
    location: "Berlin"
    date: "08/2023 – 02/2024"
    title: "Hydroponics Specialist (Internship)"
    bullets: ["[4-5 bullets, <=140 chars each]"]
education:
  - degree: "[Degree]"
    university: "[University]"
    date: "[MM/YYYY or 'expected MM/YYYY']"
    details: ["[2-4 short lines from the base resume: thesis topic, relevant modules + grades, GPA]"]
languages: ["[Language (Level)]"]
"""
    else:
        schema_section = f"""
## Resume.yaml Schema (US Style — projects as separate top-level section)
type: resume
language: "{language}"
render_mode: "{render_mode}"
resume_style: "{resume_style}"
resume_variation: "Balanced"
keyword_stuffing: {keyword_stuffing}
user_directed_skills: [{('' if not user_skills else f'"{user_skills}"')}]
contact_info:
  name: "{CANDIDATE_NAME_UPPER}"
  location: "[from ATS_Report closest_candidate_location]"
  phone: "{config.CANDIDATE_PHONE}"
  email: "{config.CANDIDATE_EMAIL}"
  linkedin: "{CANDIDATE_LINKEDIN_SHORT}"
summary: "[2 lines, <=200 chars EN / <=170 DE, no tool names]"
technical_skills:
  - category: "[Category 1, named after the JD]"
    skills: ["[6-8 skills]"]
  - category: "[Category 2]"
    skills: ["[6-8 skills]"]
  - category: "[Category 3]"
    skills: ["[6-8 skills]"]
  - category: "[Category 4]"
    skills: ["[6-8 skills]"]
  - category: "[Category 5]"
    skills: ["[6-8 skills]"]
  - category: "[Category 6]"
    skills: ["[6-8 skills]"]
projects:
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[Bullet 1: outcome + metric, 60-80 chars]"
      - "[Bullet 2: outcome + metric, 60-80 chars]"
      - "[Bullet 3: outcome + metric, 60-80 chars]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[Project Name under 50 chars]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
  - name: "[5th project — add ONLY if 4 projects leave empty space]"
    repo_url: "[from selected_projects.yaml]"
    tools: ["[3-5 JD-relevant tools]"]
    bullets:
      - "[3 bullets per project]"
      - "[3 bullets per project]"
      - "[3 bullets per project]"
professional_experience:
  - company: "[Company, verbatim from base resume]"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title, verbatim from base resume]"
    bullets: ["[4-5 JD-relevant bullets from base resume/catalog, <=140 chars each; 2-3 for RAWE]"]
  # one entry per employer in the base resume: FYTA, ZALF, Our Greenery GmbH, RAWE programme
education:
  - degree: "[Degree]"
    university: "[University]"
    date: "[MM/YYYY or 'expected MM/YYYY']"
    details: ["[2-4 short lines from the base resume: thesis topic, relevant modules + grades, GPA]"]
languages: ["[Language (Level)]"]
"""

    return f"""# TASK: Resume Rewrite & ATS Rescoring

Write a tailored Resume.yaml for this job application.

## Configuration
- render_mode: {render_mode}
- resume_style: {resume_style}
- language: "{language}"
- keyword_stuffing: {keyword_stuffing}
- user_directed_skills: "{user_skills}"
- score_boost_mode: {score_boost}
- initial_ats_score: {initial_score}

## Input: ATS Report (from Step 1)
{ats_report}

## Input: Selected Projects (ranked projects with full bullets)
{selected_projects}

## Input: Job Description (archived)
{job_desc}

## Input: Base Resume (archetype: {archetype})
{base_resume}

{schema_section}

## Post-Rewrite ATS Rescoring (MANDATORY)
After writing Resume.yaml, also output a post_rewrite_ats_score block:
- Re-run 4-category ATS matrix on the final resume
- Calculate score_delta (post - pre)
- Set score_gate_verdict (PROCEED if >=85, HOLD if <85)
- If score_boost is active, use the itemized scoring rubric (Measure 4) from the system prompt

## post_rewrite_ats_score (append to ATS_Report.yaml)
```yaml
post_rewrite_ats_score:
  ats_score_matrix:
    keywords_and_terminology: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    experience_relevance: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    technical_skills: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    soft_skills_and_language: {{ max_score: 25, current_score: 0, evaluation_criteria: "..." }}
    total_score: 0
  score_delta: 0
  formatting_quality:
    verdict: "Excellent"
    notes: ""
    suggestions: []
  score_gate_verdict: "PROCEED"
  remaining_gaps: []
```

## OUTPUT NOW

Output TWO code blocks:

### FILE 1: Resume.yaml
```yaml
[full Resume.yaml content]
```

### FILE 2: post_rewrite_ats_score block (to append to ATS_Report.yaml)
```yaml
[post_rewrite_ats_score block only — will be appended to existing ATS_Report.yaml]
```

Do NOT ask questions. Do NOT explain. Just output the two code blocks."""


def build_step3_prompt(app_dir: Path, render_mode: str, language: str) -> str:
    """Build the Step 3 variable suffix: Cover letter writer."""

    ats_report = read_file(app_dir / "ATS_Report.yaml")
    job_desc = read_file(app_dir / "Job_Description.yaml")
    project_info = read_file(app_dir / "project_info.md")

    return f"""# TASK: Cover Letter Generation

Write a formal cover letter (Cover_Letter.yaml) grounded in project metrics.

## Configuration
- render_mode: {render_mode}
- language: "{language}"

## Input: ATS Report
{ats_report}

## Input: Job Description
{job_desc}

## Input: Project Info (ranked projects with metrics)
{project_info}

## Cover_Letter.yaml Schema
```yaml
type: cover_letter
render_mode: "{render_mode}"
language: "{language}"
sender:
  name: "{CANDIDATE_NAME_UPPER}"
  address: "[closest_candidate_location from ATS_Report]"
  phone: "{config.CANDIDATE_PHONE}"
  email: "{config.CANDIDATE_EMAIL}"
recipient:
  company: "[Company Name]"
  department: "Hiring Team"
  address: "[Company Address from JD, or company name + city]"
date: "[Closest City], [Date]"
subject: "Bewerbung als [Title] / Application for [Title]"
salutation: "Sehr geehrte Damen und Herren, / Dear Hiring Team,"
paragraphs:
  - "[P1: Hook linking portfolio to role]"
  - "[P2: Deep dive project 1 with metrics]"
  - "[P3: Deep dive project 2 with metrics]"
  - "[P4: languages (English C2, German A2), availability only if stated in base resume, closing motivation]"
closing: "Mit freundlichen Grüßen, / Sincerely,"
signature_image: "okf/BHAGYA_LEKSHMI_signature.png"
```

## OUTPUT NOW

Output ONE code block:

### FILE: Cover_Letter.yaml
```yaml
[full Cover_Letter.yaml content]
```

Do NOT ask questions. Do NOT explain. Just output the code block."""


def _build_length_fix_prompt(app_dir: Path, error_msg: str, language: str, resume_yaml: str) -> str:
    """Prompt for a resume that is under 1.5 pages (SHORT) or over 2 pages (LONG)."""
    ats_report = read_file(app_dir / "ATS_Report.yaml")
    job_desc = read_file(app_dir / "Job_Description.yaml")
    selected = read_file(app_dir / "selected_projects.yaml")
    archetype = "Plant Research & Experiments"
    m = re.search(r'primary:\s*"?([^"\n]+)"?', ats_report)
    if m:
        archetype = m.group(1).strip()
    base_resume = get_base_resume(language, archetype)
    style_m = re.search(r'^resume_style:\s*"?(\w+)"?', resume_yaml, re.MULTILINE)
    style = style_m.group(1) if style_m else "us"

    if error_msg.startswith("LENGTH_SHORT"):
        task = f"""The resume is TOO SHORT. {error_msg}
The minimum is 1.5 pages (NON-NEGOTIABLE); the target is about 1.7 pages and the maximum 2 pages.
Add REAL, JD-relevant content from the base resume, the catalog and selected projects until it is clearly long enough:
1. Every employer from the base resume, 4-5 bullets each (RAWE 2-3), each bullet close to 140 chars and concrete.
2. Every project that fits the JD, 3 bullets each (project summaries stay <= 300 chars in total).
3. 5-6 technical_skills categories with 6-8 genuine skills each, named and ordered after the JD.
4. A `details` list (2-4 short lines) under every education entry, using only facts from the base resume
   (thesis topic, relevant modules with their grades, GPA, exchange credits).
5. A fuller summary (use the whole character limit).
Never invent facts, numbers, employers, tools or certifications. Never pad with filler sentences."""
    else:
        task = f"""The resume is TOO LONG. {error_msg}
The maximum is 2 pages and the minimum 1.5 pages. Trim only the LEAST JD-relevant content (lowest-ranked project,
extra bullets of the least relevant employer, surplus skills) until the resume is about 1.8 pages.
Do not go below 1.5 pages. Do not change fonts or margins."""

    return f"""# TASK: Fix Resume Length ({style} style, language: {language})

{task}

## Job Description (archived)
{job_desc}

## ATS Report
{ats_report}

## Selected Projects
{selected}

## Base Resume
{base_resume}

## Current Resume.yaml
{resume_yaml}

## Rules
- Keep the schema, `resume_style`, `section_order` (if present), contact info, employer names, dates and titles unchanged.
- Keep every YAML field name exactly as in the current file (`details` is allowed under education entries).
- Facts only from the inputs above. Stop-slop rules still apply.

## OUTPUT NOW
Output the full corrected Resume.yaml in a single code block:
```yaml
[corrected Resume.yaml]
```"""


def build_fix_prompt(app_dir: Path, error_msg: str, language: str) -> str:
    """Build a fix prompt for parseability failures."""

    resume_yaml = read_file(app_dir / "Resume.yaml")

    fix_instructions = ""
    if "summary" in error_msg.lower() and "char" in error_msg.lower():
        cur_match = re.search(r'[Ss]ummary:?\s*(\d+)\s*chars?\s*\(limit:?\s*(\d+)\)', error_msg)
        if cur_match:
            current, limit = int(cur_match.group(1)), int(cur_match.group(2))
            fix_instructions = f"""
## SPECIFIC FIX REQUIRED
The summary is {current} chars but the limit is {limit} chars. You MUST trim it by at least {current - limit + 5} chars.
Rewrite the summary to be under {limit} chars. Remove adjectives, condense phrasing, keep the core message.
Count the characters carefully before outputting. The summary must be <= {limit} characters."""

    if "project" in error_msg.lower() and "char" in error_msg.lower():
        proj_match = re.search(r'(\d+)\s*chars?\s*\(limit:?\s*(\d+)\)', error_msg)
        if proj_match:
            current, limit = int(proj_match.group(1)), int(proj_match.group(2))
            fix_instructions = f"""
## SPECIFIC FIX REQUIRED
A project summary is {current} chars but the limit is {limit} chars. Trim it by at least {current - limit + 5} chars.
Shorten bullet text while keeping metrics and technologies. Count carefully."""

    if "yaml_to_pdf" in error_msg.lower() or "tex-only" in error_msg.lower():
        fix_instructions = """
## SPECIFIC FIX REQUIRED
The YAML-to-LaTeX renderer failed. This usually means a schema mismatch.
Check that:
1. For German style: NO top-level projects section; the thesis is a professional_experience entry with plain bullets
2. For US style: projects are a separate top-level section
3. All required fields are present (contact_info, summary, technical_skills, professional_experience, education, languages)
4. No unquoted special characters in YAML values"""

    if error_msg.startswith("LENGTH_"):
        return _build_length_fix_prompt(app_dir, error_msg, language, resume_yaml)

    return f"""# TASK: Fix Resume YAML

The resume YAML failed a compilation check. Fix the issue and output the corrected YAML.

## Error
{error_msg}
{fix_instructions}

## Current Resume.yaml
{resume_yaml}

## Rules
- Fix ONLY the reported issue. Do NOT rewrite the entire resume.
- Keep all project names, metrics, and structure the same.
- If the issue is a keyword miss, de-parenthesize skill strings or remove special characters.
- If the issue is char count overflow, trim text to fit the limit. Count characters carefully.
- If the issue is a schema error, fix the YAML structure to match the expected format.
- Never change fonts or LaTeX preamble.

## OUTPUT NOW
Output the corrected Resume.yaml in a single code block:
```yaml
[corrected Resume.yaml]
```"""


# ─── Step Execution ──────────────────────────────────────────────────────────

def run_step1(args):
    """Execute Step 1: ATS analysis + JD archival + project ranking."""
    progress_pos = getattr(args, 'progress_pos', 0)

    jd_text = read_file(Path(args.jd_file)) if args.jd_file else args.jd_text
    if not jd_text:
        print("ERROR: No JD text provided", file=sys.stderr)
        sys.exit(1)

    with tqdm(total=4, desc="Step 1: ATS Analysis", file=sys.stderr,
              unit="step", position=progress_pos,
              bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}") as pbar:
        pbar.set_postfix_str("Building prompt")
        prompt = build_step1_prompt(
            jd_text=jd_text,
            render_mode=args.render,
            resume_style=args.style,
            app_source=args.source,
            language=args.language,
            weak_tie=args.weak_tie or "",
        )
        pbar.update(1)

        pbar.set_postfix_str("Calling harness")
        content = call_harness(prompt, progress_pos=progress_pos + 1)
        pbar.update(1)

        pbar.set_postfix_str("Parsing response")

        yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
        md_blocks = re.findall(r'```(?:markdown|md)?\s*\n(.*?)```', content, re.DOTALL)

        if not yaml_blocks:
            print("ERROR: No YAML blocks found in response", file=sys.stderr)
            print(f"Response preview: {content[:500]}", file=sys.stderr)
            sys.exit(1)

        ats_yaml = yaml_blocks[0].strip()

        company = ""
        position = ""
        company_match = re.search(r'^company:\s*"?([^"\n]+)"?\s*$', ats_yaml, re.MULTILINE)
        position_match = re.search(r'^position:\s*"?([^"\n]+)"?\s*$', ats_yaml, re.MULTILINE)
        if company_match:
            company = company_match.group(1).strip()
        if position_match:
            position = position_match.group(1).strip()

        if not company or not position:
            print("ERROR: Could not extract company/position from ATS_Report.yaml", file=sys.stderr)
            sys.exit(1)

        safe_company = windows_safe_name(company)
        safe_position = windows_safe_name(position)
        app_dir = APPLICATIONS_DIR / f"{safe_company} — {safe_position}"
        app_dir.mkdir(parents=True, exist_ok=True)
        pbar.update(1)

        pbar.set_postfix_str("Writing files")
        write_yaml_file(app_dir / "ATS_Report.yaml", ats_yaml)

        if len(yaml_blocks) >= 2:
            write_yaml_file(app_dir / "Job_Description.yaml", yaml_blocks[1].strip())

        project_info_content = ""
        for block in md_blocks:
            if "Tailored Project Portfolio" in block or "LLM Rank" in block:
                project_info_content = block.strip()
                break

        if not project_info_content:
            md_match = re.search(r'# Tailored Project Portfolio.*?(?=```|$)', content, re.DOTALL)
            if md_match:
                project_info_content = md_match.group(0).strip()

        if project_info_content:
            (app_dir / "project_info.md").write_text(project_info_content, encoding="utf-8")
            print(f"[ok] Wrote project_info.md ({len(project_info_content)} bytes)", file=sys.stderr)
        else:
            print("[warn] project_info.md not found in response", file=sys.stderr)

        pbar.update(1)

    print(str(app_dir))
    return 0


def run_step2(args):
    """Execute Step 2: Resume writer + ATS rescoring."""
    progress_pos = getattr(args, 'progress_pos', 0)

    app_dir = Path(args.app_dir)
    if not app_dir.exists():
        print(f"ERROR: App dir not found: {app_dir}", file=sys.stderr)
        sys.exit(1)

    with tqdm(total=4, desc="Step 2: Resume Writer", file=sys.stderr,
              unit="step", position=progress_pos,
              bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}") as pbar:
        pbar.set_postfix_str("Building prompt")
        prompt = build_step2_prompt(
            app_dir=app_dir,
            render_mode=args.render,
            resume_style=args.style,
            language=args.language,
            stuffing=args.stuffing,
            user_skills=args.user_skills or "",
            score_boost=args.score_boost,
            initial_score=int(args.initial_score or 0),
        )
        pbar.update(1)

        pbar.set_postfix_str("Calling harness")
        content = call_harness(prompt, progress_pos=progress_pos + 1)
        pbar.update(1)

        pbar.set_postfix_str("Parsing response")

        yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)

        if not yaml_blocks:
            print("ERROR: No YAML blocks found in response", file=sys.stderr)
            print(f"Response preview: {content[:500]}", file=sys.stderr)
            sys.exit(1)
        pbar.update(1)

        pbar.set_postfix_str("Writing files")
        write_yaml_file(app_dir / "Resume.yaml", yaml_blocks[0].strip())

        if len(yaml_blocks) >= 2:
            post_score_yaml = yaml_blocks[1].strip()
            ats_path = app_dir / "ATS_Report.yaml"
            existing = read_file(ats_path)
            if existing and "post_rewrite_ats_score" not in existing:
                appended = existing.rstrip() + "\n\n" + post_score_yaml + "\n"
                write_yaml_file(ats_path, appended)
            elif existing and "post_rewrite_ats_score" in existing:
                pattern = r'post_rewrite_ats_score:.*$'
                replaced = re.sub(pattern, post_score_yaml, existing, flags=re.DOTALL)
                write_yaml_file(ats_path, replaced)
        pbar.update(1)

    print("STEP 2 COMPLETE")
    return 0


def run_step3(args):
    """Execute Step 3: Cover letter writer."""
    progress_pos = getattr(args, 'progress_pos', 0)

    app_dir = Path(args.app_dir)
    if not app_dir.exists():
        print(f"ERROR: App dir not found: {app_dir}", file=sys.stderr)
        sys.exit(1)

    with tqdm(total=3, desc="Step 3: Cover Letter", file=sys.stderr,
              unit="step", position=progress_pos,
              bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}") as pbar:
        pbar.set_postfix_str("Building prompt")
        prompt = build_step3_prompt(
            app_dir=app_dir,
            render_mode=args.render,
            language=args.language,
        )
        pbar.update(1)

        pbar.set_postfix_str("Calling harness")
        content = call_harness(prompt, progress_pos=progress_pos + 1)
        pbar.update(1)

        pbar.set_postfix_str("Writing file")

        yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)

        if not yaml_blocks:
            print("ERROR: No YAML blocks found in response", file=sys.stderr)
            print(f"Response preview: {content[:500]}", file=sys.stderr)
            sys.exit(1)

        write_yaml_file(app_dir / "Cover_Letter.yaml", yaml_blocks[0].strip())
        pbar.update(1)

    print("STEP 3 COMPLETE")
    return 0


def run_fix(args):
    """Execute a fix pass on Resume.yaml."""
    progress_pos = getattr(args, 'progress_pos', 0)

    app_dir = Path(args.app_dir)

    with tqdm(total=3, desc="Fix: Resume YAML", file=sys.stderr,
              unit="step", position=progress_pos,
              bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}] {postfix}") as pbar:
        pbar.set_postfix_str("Building prompt")
        prompt = build_fix_prompt(app_dir, args.error, args.language)
        pbar.update(1)

        pbar.set_postfix_str("Calling harness")
        content = call_harness(prompt, progress_pos=progress_pos + 1)
        pbar.update(1)

        pbar.set_postfix_str("Writing file")

        yaml_blocks = re.findall(r'```ya?ml\s*\n(.*?)```', content, re.DOTALL)
        if yaml_blocks:
            write_yaml_file(app_dir / "Resume.yaml", yaml_blocks[0].strip())
            print("FIX COMPLETE")
        else:
            print("ERROR: No YAML in fix response", file=sys.stderr)
            sys.exit(1)
        pbar.update(1)

    return 0


# ─── URL Fetch ──────────────────────────────────────────────────────────────

def fetch_jd_from_url(url: str, scraper: str = "tinyfish") -> str:
    """Fetch with one explicit scraper; the launcher handles backup selection."""
    import hashlib
    import shutil
    tinyfish_exe = None
    if scraper == "tinyfish":
        tinyfish_exe = shutil.which("tinyfish") or shutil.which(
            "tinyfish", path=os.path.join(os.environ.get("APPDATA", ""), "npm"))
        if not tinyfish_exe:
            print("[fetch] tinyfish CLI is not installed on this machine; using Jina Reader instead",
                  file=sys.stderr)
            scraper = "jina"
    cache_dir = SKILL_DIR / "okf" / ".jd_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(url.encode()).hexdigest()
    cache_path = cache_dir / f"{scraper}-{url_hash}.txt"

    if cache_path.exists():
        import time as _time
        age = _time.time() - cache_path.stat().st_mtime
        if age < 7 * 86400:
            cached = cache_path.read_text(encoding="utf-8")
            if len(cached) > 200:
                print(f"[fetch] Cache hit ({len(cached)} bytes, {age/3600:.0f}h old)", file=sys.stderr)
                return cached

    print(f"[fetch] Fetching via {scraper}: {url}", file=sys.stderr)
    try:
        if scraper == "tinyfish":
            result = subprocess.run(
                [tinyfish_exe, "fetch", "content", "get", "--format", "markdown", url],
                capture_output=True, text=True, timeout=API_TIMEOUT, check=True,
            )
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")
            documents = json.loads(result.stdout).get("results", [])
            content = documents[0].get("text", "") if documents else ""
        elif scraper == "jina":
            req = urllib.request.Request(f"https://r.jina.ai/{url}", headers={
                "Authorization": f"Bearer {os.getenv('JINA_API_KEY', '')}",
            } if os.getenv("JINA_API_KEY") else {})
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
        else:
            raise ValueError(f"Unknown scraper: {scraper}")
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError) as error:
        print(f"[fetch] {scraper} failed: {error}", file=sys.stderr)
        return ""

    content = content.strip()
    if len(content) < 200:
        print(f"[fetch] Content too short ({len(content)} bytes)", file=sys.stderr)
        return ""

    cache_path.write_text(content, encoding="utf-8")
    print(f"[fetch] Fetched {len(content)} bytes, cached at {cache_path.name}", file=sys.stderr)
    return content


def run_fetch(args):
    """Fetch JD from URL and print to stdout."""
    content = fetch_jd_from_url(args.url, args.scraper)
    if content:
        print(content)
        return 0
    else:
        print("FETCH_FAILED", file=sys.stderr)
        return 1


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="llm-cv harness pipeline")
    subparsers = parser.add_subparsers(dest="step", required=True)

    # Step 1
    p1 = subparsers.add_parser("step1", help="ATS analysis + JD archival + project ranking")
    p1.add_argument("--jd-file", help="Path to JD text file")
    p1.add_argument("--jd-text", help="JD text directly")
    p1.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p1.add_argument("--style", default="us", choices=["us", "german"])
    p1.add_argument("--source", default="Cold Apply")
    p1.add_argument("--language", default="English", choices=["English", "German"])
    p1.add_argument("--weak-tie", default="")

    # Step 2
    p2 = subparsers.add_parser("step2", help="Resume writer + ATS rescoring")
    p2.add_argument("--app-dir", required=True, help="Application folder path")
    p2.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p2.add_argument("--style", default="us", choices=["us", "german"])
    p2.add_argument("--language", default="English", choices=["English", "German"])
    p2.add_argument("--stuffing", default="none", choices=["none", "all", "selective"])
    p2.add_argument("--user-skills", default="")
    p2.add_argument("--score-boost", default="false", choices=["true", "false"])
    p2.add_argument("--initial-score", default="0")
    p2.add_argument("--progress-pos", type=int, default=0, help="tqdm bar position for parallel display")

    # Step 3
    p3 = subparsers.add_parser("step3", help="Cover letter writer")
    p3.add_argument("--app-dir", required=True, help="Application folder path")
    p3.add_argument("--render", default="latex", choices=["latex", "reportfallback"])
    p3.add_argument("--language", default="English", choices=["English", "German"])
    p3.add_argument("--progress-pos", type=int, default=0, help="tqdm bar position for parallel display")

    # Fetch
    pfetch = subparsers.add_parser("fetch", help="Fetch JD via TinyFish (Jina only as an explicit backup)")
    pfetch.add_argument("--url", required=True, help="Job posting URL")
    pfetch.add_argument("--scraper", choices=["tinyfish", "jina"], default="tinyfish")

    # Fix
    pf = subparsers.add_parser("fix", help="Fix Resume.yaml after parseability failure")
    pf.add_argument("--app-dir", required=True, help="Application folder path")
    pf.add_argument("--error", required=True, help="Error message from parseability audit")
    pf.add_argument("--language", default="English", choices=["English", "German"])

    args = parser.parse_args()

    runners = {"step1": run_step1, "step2": run_step2, "step3": run_step3,
               "fetch": run_fetch, "fix": run_fix}
    try:
        sys.exit(runners[args.step](args))
    except RuntimeError as error:
        # Expected failures (not signed in, claude.exe missing, timeout): short message, no traceback.
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
