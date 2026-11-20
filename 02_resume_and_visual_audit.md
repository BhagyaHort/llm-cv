# Pipeline Step 2: Resume Rewrite & Visual Layout Audit

> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles". Only write to the application folder: `Resume.yaml`, `Resume.tex` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.tex` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.tex`, `Layout_Audit_Report.yaml`, `Parseability_Report.yaml`, `Parseability_Report.pdf`.

## Objective
Generate a tailored resume (`Resume.yaml`) from Step 1's `ATS_Report.yaml`, audit layout, self-correct, and re-score ATS.

## Inputs
- **Base Resume:** `okf/base_files/english/resume.md` or `okf/base_files/german/resume_de.md` (per `language` key in `ATS_Report.yaml`)
- **Project Portfolio:** `project_info.md` in the company folder (from Step 1 LLM ranking). In wrapper mode, also read `selected_projects.yaml` (full bullets for only the 6 ranked projects, ~7KB) instead of the full 49KB catalog.
- **ATS Report:** `ATS_Report.yaml` from the company folder — read `render_mode`, `resume_style`, `language`, `skill_gaps`, `improvement_blueprint`, `role_archetype`, `closest_candidate_location` from here. Use archived `Job_Description.yaml` for JD references — do not re-paste raw JD.

## First Action: Keyword Stuffing Decision

Present `skill_gaps` from `ATS_Report.yaml` and ask one question via `ask`:

- **Q1** "Step 1 found these skill gaps: [list]. How do you want to handle them?" — Header: "Keyword stuffing"
  - `Add all` — Add every `skill_gaps` skill to technical skills (user directive, anti-hallucination waived per SKILL.md §3)
  - `No stuffing` — Only add skills candidate genuinely knows (catalog/base resume)
  - `Selective` — User specifies which skills to add
- **Q2** (only if Selective) "Which skills to add?" — Header: "Skills to add" — free text

Store in `Resume.yaml`:
```yaml
keyword_stuffing: true    # true if Add all or Selective, false if No stuffing
user_directed_skills: []  # populated only if Selective
```

## 1. Document Rewrite & Project Selection
> **Score-Boost Gate:** Read `ats_score_matrix.total_score` from `ATS_Report.yaml`. If < 85 AND `score_boost_mode: true` (user opted in via wrapper script), apply the Score-Boost measures from `prompts/score_boost.md` during this rewrite. Measures 1-3 (student framing, JD phrase weaving, adjacent skills) apply here in §1. Measure 4 (itemized scoring rubric) applies in §5. If score ≥ 85 or `score_boost_mode: false`, skip all Score-Boost measures.

- **Archetype alignment:** Bias project order/phrasing toward archetype from Step 1.
- **Skill gap closure:** Apply per `keyword_stuffing` decision:
  - `Add all`: Add all `skill_gaps` to technical skills (user directive).
  - `Selective`: Add only `user_directed_skills` + genuine skills from `skill_gaps`.
  - `No stuffing`: Add only genuine skills (catalog/base resume). Note real gaps without fabricating.
- **Technical skills selection (ANTI-STUFFING):** Include only skills the candidate genuinely knows that are relevant to this JD. Do NOT list every technology from every project. Prioritize: (1) JD-required skills the candidate has, (2) core tools from selected projects, (3) adjacent skills that strengthen the profile. Omit irrelevant technologies even if known. A focused, credible skills block reads better than an exhaustive inventory that looks like ATS keyword stuffing.
- **Project tools:** List only the 3-5 most JD-relevant tools used in that project, not every technology from the catalog entry. Irrelevant tools dilute the signal.
- **Language:** Translate fully to user-selected language (not auto-detected). Set `language` key in `Resume.yaml`.
- **Location:** Read `closest_candidate_location` from `ATS_Report.yaml`, set as `contact_info.location`.
- **Employment dates:** Copy exactly from base resume. Never generalize or omit.
- **Project URLs:** Copy `repo_url` verbatim from `Repo:` line in `project_info.md`. If empty, omit `[GitHub]` link.
- **Resume variation:** Set `resume_variation` in `Resume.yaml`:
  - `Balanced` (default): 3 projects, 4 experience bullets
  - `Project-Heavy`: 4 projects with verbose descriptions, simplified skills
  - `Skills-Heavy`: 3 projects, expanded technical skills
- **Section order:**
  - **US Style** (`resume_style: us`): Summary → Technical Skills → Projects → Professional Experience → Education → Spoken Languages
  - **German Style** (`resume_style: german`): Summary → Professional Experience → Education → Technical Skills → Spoken Languages

> **ANTI-HALLUCINATION — Project Sourcing:** Every project must come from `project_info.md` (sourced from `okf/project_catalog.yaml`). No inventing/splitting/merging. `name` must match `project_info.md` exactly. `repo_url` verbatim from `Repo:` line. Metrics from catalog `key_metrics` only — reframe for JD context, never invent.

### German Style — Master's Thesis Entry
Projects are NOT a separate section in German style. The Master's thesis becomes its own experience entry (as in the candidate's own resume), with plain bullets (no `project_bullets`):
```yaml
- company: "Humboldt-Universität zu Berlin"
  location: "Berlin"
  date: "07/2025 – present"
  title: "Master's Thesis Researcher"
  bullets:
    - "[Thesis bullet from the catalog entry, <=140 chars]"
```
- Dates and titles come from the base resume and are immutable. List entries most recent first.
- Use 3-5 thesis bullets. The seminar paper may appear as one extra bullet when the JD values literature review or food-safety knowledge.
- Never use `project_bullets` and never add a top-level `projects:` key in German style.

### Score-Boost Measures (apply only if Score-Boost Gate is active)

See `prompts/score_boost.md` for full detail. Summary:

- **Student Framing (Measure 1):** If the JD is an intern/Werkstudent/student role AND the candidate is currently enrolled (education entry with date "present"), lead the summary with "M.Sc. student in [field] and [archetype], ..." instead of a bare title. Still exactly 2 lines, ≤200 chars EN / ≤170 DE, no tool names.
- **Exact JD Phrase Weaving (Measure 2):** Scan `Job_Description.yaml` for distinctive verb phrases (e.g. "plant experiments", "quality assessments", "nutrient and pH management"). Weave at least 1 exact phrase into truthful bullet prose. The phrase must be genuinely matched by the candidate's work (no capability fabrication). Put it in the most relevant experience bullet (<=140 chars).
- **Real Adjacent Skills (Measure 3):** If the JD asks for tools or methods the base resume already contains in a category the current JD-anchored skills block dropped (for example ImageJ, Excel Pivot Tables, isotope analysis, pH/EC measurement), re-add that category as its own Technical Skills row. Replace weak-signal filler instead of growing the block: total length must stay within 2 pages.

> **Anti-Hallucination:** Measures 1-3 enhance framing and surface real adjacent skills. No fabricating capabilities, metrics, or experience. Exact JD phrase weaving requires the phrase to be genuinely matched by candidate work.

## 2. Structural & Layout Constraints

Required length: **at least 1.5 pages (NON-NEGOTIABLE) and at most 2 pages (A4)**; aim for about 1.7. `lib/length_check.py` measures the compiled PDF (enforced threshold 1.55 = 1.5 + measurement margin) and the launcher rejects anything shorter or longer. Never shrink fonts or margins to fit.

| Element | English | German |
|---------|---------|--------|
| Summary | 2 lines, ≤200 chars | 2 lines, ≤170 chars |
| Project summary | 3 bullets, 180-300 chars total | 3 bullets, 160-280 chars total |
| Experience bullets | ≤140 chars, up to 2 lines each | same |
| FYTA / ZALF / Our Greenery bullets | 4-5 each | 4-5 each |
| RAWE bullets | 2-3 | 2-3 |
| Education `details` | 2-4 lines per entry | same |
| Project name+tools | ≤120 chars | ≤120 chars |

- **Filenames:** English → `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf`/`.tex`. German → `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.pdf`/`.tex`.
- **Summary:** No tool-listing (tools go in Technical Skills). Positioning statement: who you are + what you do + outcome. Lead with the M.Sc. student framing when the JD is a working-student/intern role. Never claim experience, certifications or a work permit that is not in the base resume.
- **Projects:** Select the relevant ones from `project_info.md` (the candidate has few, so use every project that fits the JD). Format: `name --- summary` (single paragraph, renderer joins bullets into prose; no `[GitHub]` link because `repo_url` is empty). Name/em-dashes excluded from char count. Write exactly 3 bullets per project, 180-300 chars total (160-280 German). Each bullet: one concrete outcome. No padding, no tech-listing (tools go in the `tools` field and Technical Skills section).
- **Render mode:** `latex` (default) or `reportfallback`. ReportFallback skips §4 and Steps B/C — single compile produces final PDF.
- **Section Rule Separation (HARD):** Never reduce `\titlespacing` after-sep below 4pt (`\titlespacing{\section}{0pt}{6pt}{4pt}` is the renderer default). A smaller gap makes the `\titlerule` visually merge with the first content line under every section header. If the document overflows 2 pages, trim content, never the after-sep.

## 2.5 Length Directive (minimum 1.5 pages, maximum 2)

The launcher checks the page count after compiling (`lib/length_check.py`):

- **< 1.5 pages (SHORT):** add REAL content: all four experience entries with 4-5 bullets (RAWE 2-3), every relevant project, 5-6 skills categories with 6-8 skills, `details` lines under each education entry (thesis, modules + grades, GPA), a full-length summary. If two model passes are not enough the launcher raises the layout level (`layout_boost` 1-4: margins, spacing, 12pt) until the minimum is met.
- **> 2 pages (LONG):** trim the weakest content first (lowest-ranked project, then surplus bullets of the least relevant employer, then the least JD-relevant skills). Never reduce fonts/margins.
- **1.5-2 pages:** done. Do not pad.

> **ANTI-HALLUCINATION — Length:** Projects from `project_info.md` only. Skills from `skill_gaps` (if `keyword_stuffing: false`, only genuine skills). Never invent projects, skills, metrics or experience to reach a page count.

## 3. Visual Layout Audit & Stop-Slop Checks

- Apply **Stop-Slop** per SKILL.md §"Stop-Slop".
- **Tools-Line Deduplication:** No bullet that just names a header tool. Reinforcement allowed only with added action/outcome. Keep tools lines to 3-5 JD-aligned entries.
- **Orphan Punctuation:** Verify no orphan periods, double periods, spaces before punctuation. Run `--check-tex` and scan PDF.
- **Length (MANDATORY):** (a) 1.5 to 2 pages (never fewer, never 3), (b) no empty section, (c) no internal gap >2 empty lines, (d) no section header orphaned at the bottom of a page. Report as `page_fill_density` in `Layout_Audit_Report.yaml`.
- **Self-Correction:** If violations, immediately adjust text parameters. v2 only if >3 bullets changed or entire section restructured.
- Write findings to `Layout_Audit_Report.yaml`.

## 4. LaTeX Project Format Polish (Post-Processing)

Renderer produces `name --- [GitHub] --- summary` directly from YAML bullets. Optional prose refinement on generated `.tex`:

1. No bullet points — renderer already joins into prose. Don't reintroduce `\begin{itemize}`.
2. No separate "Tools:" line — weave tools into description prose.
3. Keep `name --- [GitHub] --- summary` structure. Name/separators/link excluded from char count.
4. Quantification: use a metric only if the catalog `key_metrics`/bullets or the base resume contain one (verbatim or reframed). If none exists, write a concrete qualitative outcome. Never fabricate a number.
5. Length: 180-300 chars total (160-280 German), up to 4 rendered lines.
6. Keyword preservation: all tools/technologies from YAML bullets must appear in prose.
7. Active voice. No adverbs ending in `-ly`. No em-dashes except `---` separators.

## 5. Post-Rewrite ATS Rescoring

- Re-run 4-category ATS matrix (25pts each, 100 total) on final polished resume.
- Re-issue `formatting_quality` verdict. Calculate `score_delta`.
- Update `post_rewrite_ats_score` block in existing `ATS_Report.yaml` (do NOT overwrite pre-rewrite section).
- Surface score delta to user. ATS_Report.pdf recompile happens in Step C.
- **Score-Boost Measure 4 (Itemized Scoring Rubric — mandatory when Score-Boost is active):** Score each of the 4 categories against an explicit enumerated list of JD term groups, not impressions. Write the matched/unmatched item lists inside `evaluation_criteria`. Unmatched terms carry a parenthetical reason: "(excluded by user)" if the user excluded them, "(not in candidate's evidence)" otherwise; mirror that phrasing in `remaining_gaps`. Every score point must trace to a string present in `Resume.yaml` or a documented fact. Do not inflate: the category ceiling is real JD-stack coverage. Target ≥88 only if the itemized rubric genuinely supports it. See `prompts/score_boost.md` for full detail.

## 6. Resume Parseability Audit (Mandatory Post-Compilation)

Run after final resume PDF is compiled:
```bash
cd "$APPLICATIONS_DIR/[Company Name] — [Job Role]/"
"$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf" "Resume.yaml"
# German: substitute "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.pdf"
```

**Checks:** Unicode integrity (zero replacement glyphs), keyword recovery (100% from YAML), section headers (6 US / 5 German), contact info (5/5), text structure.

**Pass:** All checks pass. **Auto-recovery:** If fail, script re-compiles with ReportFallback renderer and re-audits. Use `--no-recovery` to debug manually.

> **FONT RULE:** Keyword misses are YAML wording problems, NOT font problems. Fix by de-parenthesizing, splitting strings, removing special characters. NEVER patch `.tex` preamble fonts (see SKILL.md §Font Rule).

## 7. Post-Generation Anti-Hallucination Validation (MANDATORY)

After writing `Resume.yaml`, before final compilation:
```bash
"$VENV_PYTHON" -c "
import yaml
with open('okf/project_catalog.yaml') as f:
    catalog = {p['title'] for p in yaml.safe_load(f)['projects']}
with open('Resume.yaml') as f:
    resume = yaml.safe_load(f)
names = [p['name'] for p in resume.get('projects', [])]
for exp in resume.get('professional_experience', []):
    names += [pb['name'] for pb in exp.get('project_bullets', [])]  # unused in this profile
for n in names:
    print(f'  [{\"OK\" if n in catalog else \"HALLUCINATED\"}] {n}')
"
```
Resume project names are shortened versions of catalog titles. Every shortened name must clearly map to exactly one catalog entry; if it does not, replace it with a real catalog project.

## Optional: Add One More Project

1. Read `project_info.md` — pick next-ranked project not already in resume. If user names a specific project, use it (must exist in catalog).
2. Write single-paragraph: `name --- summary` (180-300 chars / 160-280 German, 4 lines max).
3. Insert: US style → `projects` list. German style → thesis/seminar content goes into the Humboldt thesis experience entry bullets.
4. Recompile + re-run parseability audit. Must stay within 2 pages.

## Output Schemas

### A. `Layout_Audit_Report.yaml`
```yaml
type: layout_audit_report
eye_test_diagnostics:
  page_fill_density: { status: "Pass/Fail", feedback: "1.5 to 2 pages (never fewer, never 3), no empty sections or orphaned headers." }
  page_boundary_splits: { status: "Pass/Fail", feedback: "..." }
  summary_cognitive_load: { status: "Pass/Fail", feedback: "..." }
  skills_block_density: { status: "Pass/Fail", feedback: "..." }
  bullet_wrap_and_line_length: { status: "Pass/Fail", feedback: "..." }
  section_layout_balance: { status: "Pass/Fail", feedback: "..." }
  education_and_project_inline_formatting: { status: "Pass/Fail", feedback: "..." }
  stop_slop_and_ai_writing_tells: { status: "Pass/Fail", feedback: "..." }
  tools_line_deduplication: { status: "Pass/Fail", feedback: "..." }
direct_visual_refactoring_actions: []
optimized_v2_generated: false
```

### B. `Resume.yaml`
```yaml
type: resume
language: "English/German"
render_mode: "latex"  # latex | reportfallback
resume_variation: "Balanced"  # Balanced | Project-Heavy | Skills-Heavy
keyword_stuffing: false
user_directed_skills: []
contact_info:
  name: "BHAGYA LEKSHMI VIKRAMAN NAIR"
  location: "[closest_candidate_location from ATS_Report.yaml]"
  phone: "+49 176 87731064"
  email: "bhagyanair224@gmail.com"
  linkedin: "linkedin.com/in/bhagyalekshmi224"
summary: "[2 lines, <=200 chars (<=170 German), no tool names]"
technical_skills:
  - category: "[Category]"
    skills: ["[Skill]"]
projects:
  - name: "[Project Name]"
    repo_url: "[from project_info.md]"
    tools: ["[Tool]"]  # 3-5 most JD-relevant, used for parseability audit
    bullets: ["[Outcome bullet]"]  # exactly 3, joined into prose (180-300 chars EN / 160-280 DE)
professional_experience:
  - company: "[Company]"
    location: "[City]"
    date: "[MM/YYYY – MM/YYYY]"
    title: "[Title]"
    bullets: ["[<=140 chars]"]
education:
  - degree: "[Degree]"
    university: "[University]"
    date: "[MM/YYYY or 'expected MM/YYYY']"
languages: ["[Language (Level)]"]
```

### C. `post_rewrite_ats_score` (added to existing ATS_Report.yaml)
```yaml
post_rewrite_ats_score:
  ats_score_matrix:
    keywords_and_terminology: { max_score: 25, current_score: 0, evaluation_criteria: "" }
    experience_relevance:      { max_score: 25, current_score: 0, evaluation_criteria: "" }
    technical_skills:          { max_score: 25, current_score: 0, evaluation_criteria: "" }
    soft_skills_and_language:  { max_score: 25, current_score: 0, evaluation_criteria: "" }
    total_score: 0
  score_delta: 0
  formatting_quality:
    verdict: "Excellent"  # Excellent | Good | Average | Bad
    notes: ""
    suggestions: []
  score_gate_verdict: "PROCEED/HOLD"
  remaining_gaps: []
```

## Compilation Commands (reference only — handled by bash in wrapper mode)

> In wrapper mode, `run_pipeline.sh` handles all compilation after the session ends. Agents write YAML only. The commands below are for single-session mode or manual debugging.

### LaTeX Mode (Steps A–E)
```bash
cd "$APPLICATIONS_DIR/[Company Name] — [Job Role]/"

# Step A: Generate .tex source (no PDF yet)
"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf" --tex-only
# German: substitute "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.pdf"

# Step B: Prose refinement + char count check
"$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" --check-tex "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.tex"

# Step C: Final compilation (double pdflatex) + photo stamp + ATS report recompile
pdflatex -interaction=nonstopmode "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.tex"
pdflatex -interaction=nonstopmode "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.tex"

"$VENV_PYTHON" "$SCRIPT_DIR/stamp_photo.py" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf" "Resume.yaml"

"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"

# Step D: Parseability audit
"$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf" "Resume.yaml"

# Step E: AI watermark check (mandatory — exit 1 = marks found, investigate before proceeding)
"$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Resume.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf"
```

### ReportFallback Mode (single compile + audit — NO photo stamping)
```bash
cd "$APPLICATIONS_DIR/[Company Name] — [Job Role]/"
"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf"
"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf"
"$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf" "Resume.yaml"
"$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Resume.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf"
```

> **NO PHOTO STAMPING in ReportFallback mode.** `stamp_photo.py` is LaTeX-only. ReportFallback resumes must never have a photo overlaid — neither via `stamp_photo.py` nor any other method. The `resume.py` dispatcher already guards this (`mode == 'latex'` check), but do NOT invoke `stamp_photo.py` manually either.

---
### INPUTS FOR PROCESSING
Load from company folder (Step 1 outputs). Do not re-paste:
- `ATS_Report.yaml` — improvement blueprint and role archetype
- `project_info.md` — tailored project list

---
**Next:** Proceed to Step 3 — read `03_cover_letter.md`.
