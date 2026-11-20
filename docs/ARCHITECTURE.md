# LLM-CV (Windows port) Architecture

## Overview

> **Windows port:** this copy runs on Windows with the Claude Desktop app. `run_pipeline.sh` runs under Git Bash (`lib/env.sh` handles paths, venv, MiKTeX, temp folder); model calls go through the `claude.exe` bundled with Claude Desktop (auto-discovered by `config.find_claude_cli()`), PDFs are built with MiKTeX `pdflatex` (LM Roman 10 via `lmodern`) or the ReportLab fallback (LM Roman 10 TTFs built by `install_fonts.py`).

LLM-CV is an ATS-optimized resume and cover letter generation pipeline. A 2-stage bash orchestrator (`run_pipeline.sh`) makes 3 isolated Claude Code model calls via `api_pipeline.py`. Each uses the harness's configured default model, authentication, and reasoning settings, with a shared system prompt containing step docs, golden examples, and constraints.

### Design Philosophy

- **Agent is a launcher, not a worker:** Ask 4 configuration questions, pass the original URL via `--url` (TinyFish fetches inside the pipeline), then run two stages with one `ask` between for keyword stuffing. Only extraction failures trigger launcher-managed Firecrawl then Jina backups.
- **Harness model selection:** No pipeline model/provider override. Claude Code handles provider authentication and chooses its configured default model.
- **Shared system prompt:** The same prompt is supplied through `--system-prompt`; caching and token limits depend on the harness provider.
- **2-stage split:** Keyword stuffing asked AFTER Step 1 when skill gaps are known. Stage 1 prints APP_DIR, SKILL_GAPS, ATS_SCORE. Agent reads these, asks user, launches stage 2.
- **LLM judgment over algorithmic matching:** The LLM ranker correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and understands domain relevance — all without synonyms, allowlists, or transferable skills definitions.
- **Condensed catalog for ranking, extracted subset for writing:** Step 1 reads a 21KB condensed catalog (no bullets) for ranking. Bash then extracts full bullet data for only the 6 ranked projects into a 7KB `selected_projects.yaml` for Step 2.
- **Minimal dependencies:** Only `pyyaml`, `reportlab`, `pypdf` — no vector databases, embedding models, or ML frameworks.

---

## Pipeline Flow

### Direct API Architecture (DEFAULT — always use the wrapper)

```
User says "llm-cv" + JD (URL, file, or pasted text)
    │
    ├── [if URL] Pass --url; pipeline fetches via TinyFish (backups only on failure)
    ├── Agent asks 4 questions via ask (render mode, style, source, language)
    │
    ├── Stage 1: run_pipeline.sh --stage 1 --url "<posting URL>" ...
    │       │
    │       ├── Step 1 model call (Claude Code default model)
    │       │     reads: 10.5K system prompt + condensed catalog (21KB) + base resume + JD
    │       │     writes: ATS_Report.yaml, Job_Description.yaml, project_info.md
    │       │     token usage and caching depend on the harness model/provider
    │       │
    │       ├── [bash] Compile Step 1 PDFs (ATS_Report.pdf, Job_Description.pdf)
    │       ├── [bash] extract_projects.py → selected_projects.yaml (7KB)
    │       └── Prints: APP_DIR, SKILL_GAPS, ATS_SCORE to stdout
    │
    ├── Agent reads SKILL_GAPS, asks user about keyword stuffing via ask
    │
    └── Stage 2: run_pipeline.sh --stage 2 --app-dir ... --stuffing ... --force
            │
            ├── Step 2 model call (resume writer + ATS rescoring)                ┐
            │     reads: 10.5K system prompt + selected_projects.yaml (7KB)         │ parallel
            │            + ATS_Report.yaml + JD + base resume                       │
            │     writes: Resume.yaml, appends post_rewrite_ats_score               │
            │     model/provider selected by Claude Code                                  │
            │                                                                       │
            ├── Step 3 model call (cover letter writer)                          ┘
            │     reads: 10.5K system prompt + ATS_Report.yaml + JD + project_info
            │     writes: Cover_Letter.yaml
            │     model/provider selected by Claude Code
            │
            ├── [bash] wait for both model calls
            ├── [bash] Compile resume: yaml_to_pdf --tex-only → check-tex → pdflatex x2 → stamp_photo → parseability → watermark
            ├── [bash] Compile cover letter: yaml_to_pdf → watermark
            ├── [bash] Fix loop: if parseability fails, call api_pipeline.py fix (max 2 attempts)
            ├── [bash] Recompile ATS_Report.pdf with post-rewrite scores
            ├── [bash] Generate Layout_Audit_Report.yaml
            ├── [bash] Obsidian sync + sort
            │
            └── Print summary block (company, position, folder, delta, resume status)
```

### Inter-step contract

`ATS_Report.yaml` is the contract between steps:

| Field | Written by | Read by |
|:---|:---|:---|
| `render_mode` | Step 1 API | Step 2 API, bash (compilation) |
| `resume_style` | Step 1 API | Step 2 API, bash (compilation) |
| `language` | Step 1 API | Step 2 API, Step 3 API, bash (compilation) |
| `application_source` | Step 1 API | Step 3 API, Obsidian sync |
| `skill_gaps` | Step 1 API | Bash (stuffing decision), Step 2 API |
| `improvement_blueprint` | Step 1 API | Step 2 API |
| `role_archetype` | Step 1 API | Step 2 API, bash (base resume selection) |
| `closest_candidate_location` | Step 1 API | Step 2 API, Step 3 API |
| `post_rewrite_ats_score` | Step 2 API | Bash (summary output) |

Keyword stuffing and score-boost decisions are passed as CLI flags to stage 2, not persisted to disk.

### Parallelism

Bash launches Steps 2 and 3 in parallel using `&` and `wait`:

```bash
$API_PY step2 --app-dir "$APP_DIR" ... --progress-pos 0 \
    > /tmp/llm-cv-step2.log 2> >(tee -a /tmp/llm-cv-step2.log >&2) &
STEP2_PID=$!
$API_PY step3 --app-dir "$APP_DIR" ... --progress-pos 2 \
    > /tmp/llm-cv-step3.log 2> >(tee -a /tmp/llm-cv-step3.log >&2) &
STEP3_PID=$!

wait "$STEP2_PID"
wait "$STEP3_PID"
```

### 2-Stage CLI flags

| Flag | Stage | Purpose |
|:---|:---|:---|
| `--stage 1` | 1 | Run Step 1 only, print APP_DIR/SKILL_GAPS/ATS_SCORE, exit |
| `--stage 2` | 2 | Run Steps 2+3 + compilation + sync |
| `--app-dir` | 2 | Application folder path (from stage 1 output) |
| `--file` / `--url` | 1 | JD source |
| `--render` | 1, 2 | Render mode (latex/reportfallback) |
| `--style` | 1, 2 | Resume style (us/german) |
| `--source` | 1 | Application source |
| `--language` | 1, 2 | Language |
| `--stuffing` | 2 | Keyword stuffing (none/all/selective) |
| `--user-skills` | 2 | Skills to add (Selective) |
| `--score-boost` | 2 | Always yes |
| `--force` | 2 | Skip duplicate check interactive prompt |

---

## Shared System Prompt Architecture

### System prompt composition (~10.8K tokens)

```
SYSTEM_PRClaude CodeT = _load_system_prompt()
    ├── Role description (expert ATS resume optimization system)
    ├── Anti-hallucination principles (6 rules)
    ├── Resume constraints (12 non-negotiable rules)
    ├── German style independent entry format
    ├── Score-boost measures (from prompts/score_boost.md)
    ├── Cover letter rules (10 rules)
    ├── Step 2 doc (full 02_resume_and_visual_audit.md)
    ├── Step 3 doc (full 03_cover_letter.md)
    ├── Golden example: John Deere resume (few-shot anchor)
    └── Golden example: John Deere cover letter (few-shot anchor)
```

### Harness behavior

`call_harness()` launches `claude -p --output-format json` (tools, skills, MCP and session persistence disabled; optional `LLM_CV_MODEL` / `LLM_CV_EFFORT`). Each call uses a unique temporary workspace and prompt file, disables session persistence, tools, extensions, skills, and rules, and extracts text from the final assistant `message_end` event. Errors, aborted/truncated responses, and missing text fail the step. The actual provider/model is logged to stderr.

The prompt goes through stdin and the system prompt through `--system-prompt-file`, so the Windows 32K command-line limit never applies. Inheriting an open non-TTY stdin otherwise makes Claude Code wait in `readPipedInput` before model selection. The elapsed-time bar measures the complete invocation, including model generation.

Claude Code manages authentication, reasoning, token limits, and caching. Costs and cache hit rates from the former Qwen/OpenRouter backend are not guarantees for the configured harness model. `LLM_CV_API_TIMEOUT` remains the call deadline in seconds (default 300); `LLM_CV_MODEL` is no longer used.

### Variable user message

Each step's `build_stepN_prompt()` constructs a variable suffix containing only:
- JD text, ATS report, selected projects, base resume (step-specific inputs)
- Task instructions and output format
- Schema template (German or US, with fill directives)

No guardrails or constraints in the user message — those are in the static system prompt.

---

## Token Optimization

### Architecture-level savings

| Technique | What it does | Impact |
|:---|:---|:---|
| **Harness calls** | 3 isolated Claude Code invocations, one per generation step | Default harness model/authentication; no pipeline-specific provider |
| **Shared system prompt** | Identical instructions supplied to each invocation | Provider-managed caching |
| **2-stage split** | Stuffing asked post-Step-1 with real gaps | Better stuffing decisions, no blind guessing |
| **Bash compilation** | PDF compilation, parseability, watermark, sync in bash (0 tokens) | ~1M tokens saved vs agent-handled compilation |
| **Condensed catalog** | Step 1 reads 21KB catalog (no bullets) instead of 49KB | ~28KB context saved |
| **Selected projects extraction** | Step 2 reads 7KB (6 projects with bullets) instead of 49KB | ~42KB context saved |

### Token consumption

| Mode | Per run | Cost | API calls | Time |
|:---|:---|:---|:---|:---|
| Single-session (old) | ~8M | $0.13 | ~63 | 25 min |
| Wrapper v2 (Claude Code sessions) | ~2M | $0.04 | ~29 | 10 min |
| Harness default (current) | Model-dependent | Provider-dependent | 3 + fix | Model-dependent |

---

## Length Directive

Required length is **1.5 to 2 A4 pages** (non-negotiable minimum 1.5; `lib/length_check.py` enforces 1.55 with a measurement margin; never 3). `lib/length.sh` runs the governor: 2 model passes add real content, then deterministic `layout_boost` levels 1-4. Fonts and margins are never shrunk to force a fit. Fill by adding real content (an extra project, extra bullets, an extra skills row), never padding or longer prose. Numbers appear only where the catalog or base resume supplies them; the candidate's few metrics are never invented.

---

## Project Catalog

`okf/project_catalog.yaml` — single source of truth. 15 projects, each with:

| Field | Type | Description |
|:---|:---|:---|
| `title` | string | Project title |
| `description` | string | One-line project description |
| `business_problem` | string | Business problem solved |
| `key_metrics` | string | Quantified metrics (authoritative — cite verbatim, never invent) |
| `transferable_skills` | list | Skills that transfer across domains |
| `technologies` | string | Comma-separated tech list |
| `archetypes` | list | Role archetypes this project fits |
| `repo_url` | string | GitHub URL (empty string if none) |
| `bullets` | list (8-10) | Detailed project bullets with metrics |
| `keywords` | list | Search/matching keywords |

### Condensed catalog

`okf/project_catalog_condensed.yaml` — same 15 projects without the `bullets` field (21KB vs 49KB). Generated by `extract_projects.py --condensed`. Step 1 reads this for ranking.

### Selected projects extraction

After Step 1 ranks the top 6 projects, `extract_projects.py --from-project-info` reads `project_info.md` (written by Step 1 API), matches titles against the full catalog, and extracts full bullet data for only those 6 projects into `selected_projects.yaml` (~7KB). Step 2 reads this instead of the 49KB full catalog.

---

## File Inventory

### Pipeline Scripts

| `api_pipeline.py` | Claude Code model calls. Shared system prompt, 3 step builders, fix loop, URL fetch. tqdm progress bars on model calls and step phases. |
|:---|:---|
| `run_pipeline.sh` | 2-stage bash orchestrator (615 lines). Arg parsing, stage routing, Step 1 launch, stuffing decision, Steps 2+3 parallel launch, fix loop, sync, summary. |
| `lib/compile.sh` | Compilation functions (199 lines). Sourced by run_pipeline.sh. |
| `extract_projects.py` | Condensed catalog generation + selected projects extraction (3 modes) |
| `config.py` | Location lookup, candidate info, `SKILL_DIR` constant |
| `yaml_to_pdf.py` | PDF compilation entry point (routes YAML to renderers) |
| `check_watermarks.py` | AI watermark/provenance check (3 layers: Unicode, C2PA, metadata). tqdm on directory scan. |
| `stamp_photo.py` | Candidate photo stamping onto LaTeX-mode resume PDFs |
| `obsidian_sync_core.py` | Obsidian sync core logic. tqdm on full-sync folder parsing loop. |
| `organize_applications.py` | Application folder organization (date tree sort) |
| `obsidian_folder_sort.py` | Folder sorting logic |
| `sync_to_obsidian.py` | Obsidian sync entry point |
| `track_outcomes.py` | Application outcome tracking |
| `okf_diversity_audit.py` | Weekly diversity audit (standalone) |

### Renderers (14 files in `renderers/`)

| File | Role |
|:---|:---|
| `__init__.py` | Package init |
| `utils.py` | Shared utilities (`escape_latex`, color constants, `run_pdflatex`, font registration) |
| `resume_common.py` | Shared resume helpers (`HEADERS`, `get_resume_language`, `get_photo_path`, `stamp_photo_on_pdf`) |
| `resume.py` | Resume renderer dispatcher (reads `render_mode` + `resume_style`) |
| `resume_latex_us.py` | Resume LaTeX renderer (US style) |
| `resume_reportfallback_us.py` | Resume ReportLab renderer (US style) |
| `resume_latex_german.py` | Resume LaTeX renderer (German style, Lebenslauf section order) |
| `resume_reportfallback_german.py` | Resume ReportLab renderer (German style) |
| `cover_letter.py` | Cover letter renderer dispatcher |
| `cover_letter_latex.py` | Cover letter LaTeX renderer |
| `cover_letter_reportfallback.py` | Cover letter ReportLab renderer |
| `job_description.py` | Job description renderer (ReportLab) |
| `ats_report.py` | ATS report renderer (ReportLab) |
| `parseability_report.py` | Parseability report renderer (ReportLab) |

### Data Files

| File | Role |
|:---|:---|
| `okf/project_catalog.yaml` | 15-project catalog (49KB, source of truth with bullets) |
| `okf/project_catalog_condensed.yaml` | 15 projects without bullets (21KB, Step 1 input) |
| `okf/base_files/english/` | 5 English base resumes (4 archetype + 1 generic) |
| `okf/base_files/german/` | 1 German base resume (covers all archetypes) |
| `okf/project_mappings.yaml` | Obsidian sync project name mappings |
| `okf/skill_mappings.yaml` | Obsidian sync skill mappings (includes ITIL V3 Foundation, Project Management) |
| `okf/.jd_cache/` | JD URL cache (7-day TTL, sha1-keyed) |
| `okf/.location_cache.json` | Cached location lookups |

---

## Design Decisions

### Why model calls

The pipeline must use Claude Code's configured default model and authentication rather than pinning a provider-specific model. Each step remains an isolated structured generation request: Python builds prompts, Claude Code returns assistant text, Python writes YAML, and bash compiles PDFs. No application-generation tool loop is needed.

### Why 2-stage split

Keyword stuffing asked blind upfront often adds irrelevant skills. Asking after Step 1 shows the actual skill gaps from the ATS analysis, so the user makes an informed decision. Stage 1 prints `SKILL_GAPS` to stdout; the agent reads them and presents them in the stuffing `ask`.

### Why a shared system prompt

The system prompt is the same for all 3 steps, keeping constraints and examples consistent. Claude Code supplies it to the selected provider; provider caching behavior is not hardcoded in the pipeline.

### Why one primary JD scraper

TinyFish is the sole default URL fetcher, invoked by `api_pipeline.py fetch`; the agent does not pre-scrape or load multiple scraping skills. Firecrawl MCP is the first backup and explicit `fetch --scraper jina` is the last, both managed sequentially by the launcher after extraction failure. Successful backup text is saved to a unique temporary file and Stage 1 reruns with `--file`. The shell pipeline itself fails on TinyFish errors because mounted MCP tools are available to the launcher, not directly to bash. Cache names include the scraper to avoid reusing legacy Jina/direct-fetch results as TinyFish output. No scraper guarantees access to every posting; all failures end in a request for pasted JD text.

### Why condensed catalog + extraction

Step 1 needs project metadata for ranking but not the 8-10 bullets per project. The condensed catalog (21KB vs 49KB) saves ~28KB of context in Step 1. After ranking, `extract_projects.py` pulls full bullet data for only the 6 ranked projects (7KB), so Step 2 gets exactly what it needs without loading all 15 projects' bullets.

### Why LLM ranking over algorithmic search

Tested against 10 real JDs, the LLM ranker won or tied on 10/10 and was never beaten by the algorithm. It correctly distinguishes AI roles from DE roles, prioritizes Power BI projects for BI roles, and handles synonyms/transferable skills natively.

### Photo path resolution

`get_photo_path()` in `renderers/resume_common.py` resolves relative photo paths against `SKILL_DIR` from `config.py`, not the current working directory. Critical because `stamp_photo.py` runs from the application folder.

### Font rule

LaTeX mode renders in Latin Modern Roman 10 (`lmodern`). The `.tex` preamble must never be patched to change fonts. A keyword miss in the parseability audit means the YAML wording is unrecoverable in the PDF text layer — fix by adjusting YAML wording, not by swapping fonts.

---

## What Was Removed (vs. okf-cv)

| Component | Why |
|:---|:---|
| `okf_portfolio_search.py` | OKF phrase matching — replaced by LLM judgment |
| `zvec_hybrid_search.py` | Zvec embeddings + score fusion — replaced by LLM |
| `embedding_server.py` | SentenceTransformer TCP daemon — no embeddings needed |
| `okf_lint.py` | Frontmatter linter — no frontmatter (catalog YAML is source) |
| `okf_learn.py` | Self-learning keyword enrichment — no keyword matching to enrich |
| `okf_utils.py` | Shared utils (tokenize, stopwords) — only used by deleted files |
| `okf/zvec_db/` | Vector database — no embeddings |
| `sentence-transformers`, `zvec` deps | No embeddings or vector search |

---

## Diversity Audit

Run: `.venv/Scripts/python.exe okf_diversity_audit.py`
