# Completion Checklist

After all 3 steps complete, verify:
- [ ] `ATS_Report.yaml` exists in the company folder with pre and post rewrite scores, including `closest_candidate_location`, `application_source`, and `weak_tie_contact` (if applicable)
- [ ] `ATS_Report.pdf` is generated and `post_rewrite_ats_score` block is populated
- [ ] `ATS_Report.yaml` contains a non-scored `formatting_quality` verdict (pre- and post-rewrite) with `suggestions` populated only if verdict is `Average` or `Bad`
- [ ] `Job_Description.yaml` (with `location` key) & `Job_Description.pdf` are generated
- [ ] `project_info.md` (tailored project list) is generated in the company folder
- [ ] `Resume.yaml` & `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.pdf` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.pdf` are generated with the tailored closest location
- [ ] `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Resume.tex` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Lebenslauf.tex` & `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.tex` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Anschreiben.tex` are preserved in the folder
- [ ] `Layout_Audit_Report.yaml` is generated with all eye-test diagnostics at Pass status
- [ ] `Parseability_Report.yaml` & `Parseability_Report.pdf` are generated with overall status PASS (100% keyword recovery, all section headers detected, 5/5 contact fields, no unicode corruptions)
- [ ] `check_watermarks.py` run on Resume.yaml + resume PDF — exit 0 (clean, no AI watermarks/C2PA/provenance marks)
- [ ] `Cover_Letter.yaml` & `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Cover_Letter.pdf` / `BHAGYA_LEKSHMI_VIKRAMAN_NAIR_Anschreiben.pdf` are generated with the tailored closest location in the sender address and date fields
- [ ] `check_watermarks.py` run on Cover_Letter.yaml + cover letter PDF — exit 0 (clean, no AI watermarks/C2PA/provenance marks)
- [ ] Professional Experience bullets are single-line, <= 105 chars (per 02 §Layout Constraints)
- [ ] Projects in `name --- summary` format (no GitHub link), summary <= 300 chars (<= 280 German) (per 02 §Layout Constraints)
- [ ] Summary is exactly 2 lines, <= 200 chars (<= 170 German) (per 02 §Layout Constraints) — STRICT, no compromise
- [ ] Resume is 1.5 to 2 pages (NON-NEGOTIABLE minimum 1.5, never 3), verified by `lib/length_check.py` (`Length - OK` in the summary box), no empty sections, no orphaned section headers (per 02 §2.5)
- [ ] Resume font is Latin Modern Roman 10 (lmodern) — never patched to Helvetica or any other font (per SKILL §Font Rule)
- [ ] Cover letter fits one page, 250–320 words (180–240 German) (per 03 §Structure)
- [ ] All files match the language selected by the user in the First Action (not auto-detected from JD) and comply with the Stop-Slop guidelines
- [ ] `Resume.yaml` contains `keyword_stuffing` and `user_directed_skills` fields reflecting the user's Step 2 First Action choice
- [ ] If `keyword_stuffing: true`, all `skill_gaps` (or user-specified skills) were added to the technical skills section as directed
- [ ] All projects in `project_info.md` and `Resume.yaml` match catalog titles in `okf/project_catalog.yaml` exactly (Step 1 Post-Ranking Validation and Step 2 Post-Generation Anti-Hallucination Validation both PASS — zero hallucinated projects)
- [ ] All metrics in resume and cover letter are sourced from catalog bullets or base resume (no fabricated numbers)
- [ ] All `repo_url` values are copied verbatim from the catalog (no bare profile URLs or constructed URLs)
- [ ] `sync_to_obsidian.py` has synced the application to the Obsidian vault (check `<vault>/Job Search/` for notes)
- [ ] `sync_to_obsidian.py --sort` has moved the folder into `$APPLICATIONS_DIR/YYYY/MM/DD/[Company Name] — [Job Role]/`
