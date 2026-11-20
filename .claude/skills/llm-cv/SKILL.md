---
name: llm-cv
description: Run the llm-cv resume + cover letter pipeline for a job description. Use when the user says "llm-cv" with a JD (text, file path or URL). Always asks the four First Action questions (render mode, US or German layout, application source, language) and the skill-gap question with AskUserQuestion before generating.
---

# llm-cv launcher

Read and follow `SKILL.md` and `CLAUDE.md` in the project root. Short version:

1. One `AskUserQuestion` call with the four questions: render mode (LaTeX / ReportFallback), resume layout (US Style / German Style), application source (Cold Apply / Referral / LinkedIn Connection / Direct), language (English / German).
2. `bash run_pipeline.sh ... --stage 1` with those answers.
3. `AskUserQuestion` for the skill gaps printed as `SKILL_GAPS:` (No stuffing / Add all / Selective).
4. `bash run_pipeline.sh --stage 2 --app-dir "<APP_DIR>" ... --stuffing ... --force`.

The resume must be 1.5 to 2 pages; the launcher enforces it and exits non-zero otherwise. Never skip the questions or guess answers.
