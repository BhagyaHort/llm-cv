# Pipeline Step 3: Cover Letter Generation & Compilation

> **Rules:** Follow SKILL.md §"Read-Only Guardrail", §"Agent Execution Rules", §"YAML Safety Rules", §"Anti-Hallucination Principles". Only write to the application folder: `Cover_Letter.yaml`, `Cover_Letter.tex` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.tex`, `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.pdf` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Anschreiben.pdf`.

## Objective
Generate a formal cover letter (`Cover_Letter.yaml`) grounded in project metrics, conforming to German Geschäftsbrief layout, and compile to PDF.

> **Wrapper mode:** Session 3 runs as a separate Claude Code call launched by bash, in parallel with Session 2 (resume writer). The agent reads `ATS_Report.yaml`, `Job_Description.yaml`, and `project_info.md` from disk and writes `Cover_Letter.yaml`. No subagent spawning — bash handles the parallelism.

## Inputs
- `ATS_Report.yaml` from company folder — read `render_mode`, `language`, `closest_candidate_location`, `application_source`, `weak_tie_contact`, `role_archetype` from here
- `Job_Description.yaml` from company folder (Step 1 output)
- `project_info.md` from company folder (Step 1 LLM ranking)

## 1. Structure & Layout
- Match target JD language exactly.
- **Geschäftsbrief layout:** Sender block (name, address=`closest_candidate_location` from ATS_Report.yaml, phone, email) → Recipient block (company, hiring team, address) → Date (right-aligned, closest city + date) → Subject (bold, single line) → Salutation → Body → Closing.
- **English:** Max 4 paragraphs, 250–320 words total (single A4 page).
- **German:** Max 4 paragraphs, 180–240 words total (reduced 10–20 words/paragraph to avoid A4 overflow).

> **ANTI-HALLUCINATION — Recipient:** `recipient.company` from `Job_Description.yaml`. `recipient.address` from JD text only — if no street address, use company name + city. Subject uses exact job title from `Job_Description.yaml`.

## 2. Narrative Rules & Stop-Slop
- Apply **Stop-Slop** per SKILL.md §"Stop-Slop".
- Ground every tech skill in metrics from portfolio/ATS report. No AI fluff ("passionate", "thrilled").
- **No Resume Rehash:** Cover letter carries info the resume does not — "why this company" grounded in JD mission/product, and concrete first-90-days framing. Reference at most one project's headline metric per paragraph as supporting evidence.
- **Always integrate:** Language skills (English C2, German A2) and, only if the base resume states it, availability. Never claim a GitHub portfolio, a visa/work-permit status or German studies beyond what the base resume says.
- **Archetype-conditional:** Lean on the JD archetype: Plant Research & Experiments → thesis/ZALF/FYTA methods; Quality Control & Food Safety → Our Greenery food-safety work, seminar research on contaminants; Hydroponics & CEA → Our Greenery hydroponics, light-regime thesis work.
- **No raw URLs in prose:** Do not paste URLs. Do not mention GitHub (the candidate has none).
- **Application source:** If `Referral`/`LinkedIn Connection`, mention `weak_tie_contact` in paragraph 1.

> **ANTI-HALLUCINATION — Metrics & Projects:** All metrics from `project_info.md` or `okf/project_catalog.yaml`. No fabrication. Project names must match catalog titles exactly. If no metric exists, reference qualitative outcome.

## Output Schema

### `Cover_Letter.yaml`
```yaml
type: cover_letter
render_mode: "latex"  # latex | reportfallback
sender:
  name: BHAGYA LEKSHMI VIKRAMAN NAIR
  address: "[closest_candidate_location from ATS_Report.yaml]"
  phone: "[from config.py CANDIDATE_PHONE]"
  email: "[from config.py CANDIDATE_EMAIL]"
recipient:
  company: "[Company Name]"
  department: "Hiring Team"
  address: "[Company Address from JD]"
date: "[Closest City], [Date]"
subject: "Bewerbung als [Title] / Application for [Title]"
salutation: "Sehr geehrte Damen und Herren, / Dear Hiring Team,"
paragraphs:
  - "[P1: Hook linking portfolio to role]"
  - "[P2: Deep dive project 1 with metrics]"
  - "[P3: Deep dive project 2 with metrics]"
  - "[P4: languages (English C2, German A2), availability only if stated in base resume, closing motivation]"
closing: "Mit freundlichen Grüßen, / Sincerely,"
signature_image: "okf/BHAGYA_LEKSHMI_signature.png"  # optional — path to signature PNG (transparent bg). Omit/leave empty to use typed name only.
```

## Compilation (reference only — handled by bash in wrapper mode)

> In wrapper mode, `run_pipeline.sh` handles compilation and Obsidian sync after the session ends. Agents write YAML only. The commands below are for single-session mode or manual debugging.

```bash
cd "$APPLICATIONS_DIR/[Company Name] — [Job Role]/"

# English
"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Cover_Letter.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.pdf"

# German
"$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Cover_Letter.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Anschreiben.pdf"

# AI watermark check (mandatory)
"$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Cover_Letter.yaml" "BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.pdf"
```
Renderer reads `render_mode` — `latex` (default) or `reportfallback`. Both produce same Geschäftsbrief layout.

## Post-Pipeline: Obsidian Sync (handled by bash in wrapper mode)
```bash
"$VENV_PYTHON" "$SCRIPT_DIR/sync_to_obsidian.py" "$APPLICATIONS_DIR/[Company Name] — [Job Role]" --sort
```
`--sort` moves folder into YYYY/MM/DD tree. `--verbose` for per-note progress. `--full` for complete vault rebuild (periodic reconciliation). Standalone sorter: `organize_applications.py "[folder]"`.

---
### ATTACHMENTS FOR PROCESSING
- Load `Job_Description.yaml` from company folder — do not re-paste raw JD.
- Load `ATS_Report.yaml` from company folder — do not re-paste.
- Load `project_info.md` from company folder.

---
**Next:** Pipeline complete. Read `99_completion_checklist.md` to verify all outputs.
