# llm-cv (Windows + Claude Desktop)

ATS-optimised resume and cover-letter tailoring pipeline for **Bhagya Lekshmi Vikraman Nair**. Give it a job description (text, file or URL) and it produces a tailored resume and cover letter as PDFs, an archived JD, and an ATS score report. The resume uses the Jake Ryan-style LaTeX layout in LM Roman 10 with this section order: Summary, Technical Skills, Projects, Professional Experience, Education, Spoken Languages (1.5 to 2 pages, enforced).

Ported from a Linux / oh-my-pi setup to Windows with the Claude Desktop app.

## Always asked, never guessed

When you say "llm-cv" with a JD, the agent asks four questions in one AskUserQuestion call (render mode LaTeX/ReportFallback, layout US/German, application source, language English/German), runs stage 1, then asks the skill-gap question (No stuffing / Add all / Selective), then runs stage 2. `run_pipeline.sh` refuses to continue without these answers when there is no terminal. Instructions for Claude live in `CLAUDE.md` and `.claude/skills/llm-cv/SKILL.md`.

Section order: **US** = Summary, Technical Skills, Projects, Professional Experience, Education, Spoken Languages. **German** (Lebenslauf: reverse-chronological, 2 pages max) = Summary, Experience, Education, Skills, Languages; for student/working-student/intern JDs the model puts Education first.

Every run is tailored to the JD (project and bullet order, summary, skill-category names, German section order). The resume is **at least 1.5 pages** (non-negotiable, max 2).

## How it works (token-saving design)

`run_pipeline.sh` (run under Git Bash) is the launcher. The model is called only **3 times** (+ optional fix calls); each call only writes YAML. Everything else is plain code:

```
run_pipeline.sh
  Stage 1  Step 1 model call: ATS score + JD archive + project ranking
           [bash] compile ATS_Report.pdf / Job_Description.pdf, extract selected projects
  Stage 2  Step 2 model call: resume YAML + ATS re-score          (parallel)
           Step 3 model call: cover letter YAML                    (parallel)
           [bash] compile resume (pdflatex x2) + cover letter, parseability + watermark checks,
                  fix loop, optional Obsidian sync, YYYY/MM/DD folder sort, tracker CSV
```

Model calls use the `claude.exe` bundled with the Claude Desktop app (print mode, tools off). The model never touches your files; it returns YAML that Python validates and writes.

## One-time setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

This creates `.venv`, installs `requirements.txt`, builds the LM Roman 10 TTFs into `okf/fonts/` (converted from the OpenType files in your MiKTeX install by `install_fonts.py`), and checks for Git Bash, MiKTeX and `claude.exe`.

Then sign in once so the pipeline's model calls work (the Desktop app's own login is not shared with the bundled CLI):

```powershell
& "<path printed by setup_windows.ps1>" auth login
```

Alternatives: set `ANTHROPIC_API_KEY`, or run `claude setup-token` and set `CLAUDE_CODE_OAUTH_TOKEN`.

Requirements: Windows 10/11, Python 3.10+, Git for Windows (Git Bash), MiKTeX (packages install automatically on first use), Claude Desktop.

## Running

```bash
# Git Bash (or the Claude Desktop Bash tool), from this folder
bash run_pipeline.sh --file jd.txt                 # interactive menus
bash run_pipeline.sh --url "https://..."           # fetch the JD (TinyFish if installed, else Jina Reader)

# Non-interactive, two stages (what an agent uses)
bash run_pipeline.sh --file jd.txt --render latex --style us --source "Cold Apply" --language English --stage 1
bash run_pipeline.sh --stage 2 --app-dir "<APP_DIR printed by stage 1>" --render latex --style us \
    --language English --stuffing none --score-boost yes --force
```

From PowerShell or cmd use `.\run_pipeline.cmd` with the same arguments.

| Flag | Meaning |
|------|---------|
| `--file / --url / "text"` | JD source |
| `--render latex\|reportfallback` | MiKTeX LaTeX (default) or ReportLab |
| `--style us\|german` | US order (projects section) or German order (thesis as an experience entry) |
| `--language English\|German` | output language (loads `okf/base_files/<language>/`) |
| `--source` | `Cold Apply`, `Referral`, `LinkedIn Connection`, `Direct` |
| `--stage 1\|2`, `--app-dir` | split run (stage 2 needs the stage 1 folder) |
| `--stuffing none\|all\|selective`, `--user-skills` | keyword-gap handling |
| `--force` | skip the duplicate-application prompt |

Outputs land in `Applications/YYYY/MM/DD/<Company> — <Role>/` (git-ignored).

Optional environment variables: `LLM_CV_MODEL`, `LLM_CV_EFFORT` (model choice), `LLM_CV_API_TIMEOUT`, `LLM_CV_APPLICATIONS_DIR`, `LLM_CV_VAULT_DIR` (Obsidian sync only runs if this folder exists), `LLM_CV_CLAUDE_CLI`, `LLM_CV_CRITICAL_TERMS`.

## Your profile data (`okf/`)

| Path | Purpose |
|------|---------|
| `okf/base_files/english/resume*.md`, `german/resume_de.md` | base CVs (plain + 3 role variants) the model rewrites from |
| `okf/project_catalog.yaml` / `_condensed.yaml` | projects and experience the model may use (condensed one is regenerated with `extract_projects.py --condensed`) |
| `okf/skill_mappings.yaml`, `project_mappings.yaml` | name normalisation for the Obsidian sync |
| `okf/raw/` | your source documents; `okf/convert_raw.py` converts them to Markdown with markitdown |
| `okf/fonts/` | generated LM Roman 10 TTFs |
| `okf/BHAGYA_LEKSHMI_foto.jpg`, `..._signature.png` | optional headshot / signature (not present yet) |
| `okf/golden/Resume.yaml`, `Cover_Letter.yaml` | optional "golden" examples added to the system prompt when present |

Anti-hallucination rules: the model may only use catalog/base-resume facts and numbers; no invented metrics, visa status or GitHub link.

## Role archetypes

`api_pipeline.detect_archetype()` picks one from the JD: **Plant Research & Experiments**, **Quality Control & Food Safety**, **Hydroponics & Controlled-Environment Agriculture**, and loads the matching `resume_*.md`.

## Checks that run after generation

LaTeX char-count check, PDF parseability audit (keywords must survive text extraction; auto-fallback to ReportLab), AI-watermark scan, duplicate-application check, length governor (resume must be 1.5 to 2 pages: model adds real content, then layout levels, else the run fails), applications tracker CSV.

## Tests

```bash
.venv/Scripts/python.exe tests/test_utils.py
.venv/Scripts/python.exe tests/test_llm_search.py          # catalog checks + offline ranking
.venv/Scripts/python.exe tests/test_llm_search.py --llm    # also calls Claude Code (needs sign-in)
```

More detail: `SKILL.md` (agent playbook), `docs/ARCHITECTURE.md`, step docs `00`-`03`, `99_completion_checklist.md`.
