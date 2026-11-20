# llm-cv (Windows + Claude Desktop)

Resume + cover-letter pipeline for Bhagya Lekshmi Vikraman Nair. Full agent playbook: `SKILL.md`.

## When the user says "llm-cv" with a job description (text, file or URL)

Follow `SKILL.md` §"Trigger Action". The pipeline NEVER guesses options. You MUST:

1. **Ask the four First Action questions in ONE `AskUserQuestion` call** before running anything:
   - Render mode: `LaTeX` or `ReportFallback`
   - Resume layout: `US Style` or `German Style` (offer both; show each section order)
   - Application source: `Cold Apply` / `Referral` / `LinkedIn Connection` / `Direct` (ask for the contact if Referral or LinkedIn)
   - Language: `English` or `German`
2. Run **stage 1**: `bash run_pipeline.sh <jd flags> --render .. --style .. --source .. --language .. --stage 1`
3. Read `SKILL_GAPS` from the output and **ask the skill-gap question with `AskUserQuestion`**: `No stuffing` / `Add all` / `Selective` (and which skills when Selective).
4. Run **stage 2**: `bash run_pipeline.sh --stage 2 --app-dir "<APP_DIR>" --render .. --style .. --language .. --stuffing none|all|selective [--user-skills ".."] --score-boost yes --force`

The launcher refuses to run without these answers when there is no terminal.

## Non-negotiable rules

- **The resume must be at least 1.5 pages** (maximum 2). `run_pipeline.sh` measures it (`lib/length_check.py`), asks the model to add real content, then falls back to layout levels, and exits non-zero if the minimum is not met. Never send or present a resume that failed this check.
- Never invent facts, numbers, employers, visa status or a GitHub link. Only use `okf/` data.
- Section order: US = Summary, Technical Skills, Projects, Professional Experience, Education, Spoken Languages. German = Summary, then Professional Experience/Education (education first for student/Werkstudent JDs; the model sets `section_order`), Technical Skills, Languages.
- Do not edit pipeline scripts during a run (see SKILL.md Read-Only Guardrail).
