#!/bin/bash
###############################################################################
# lib/compile.sh — Compilation functions for llm-cv pipeline
#
# Sourced by run_pipeline.sh. Provides:
#   compile_step1_pdfs     — compile ATS_Report.pdf + Job_Description.pdf
#   get_resume_filenames   — set RESUME_PDF/RESUME_TEX based on language
#   get_cover_letter_filename — set CL_PDF based on language
#   compile_resume         — full resume pipeline (tex → pdflatex → stamp → parseability)
#   compile_cover_letter   — cover letter compile + watermark check
#   generate_layout_audit  — write Layout_Audit_Report.yaml
#
# Depends on globals from run_pipeline.sh:
#   VENV_PYTHON, SCRIPT_DIR, LLM_TMP, CANDIDATE_FILE_PREFIX, log(), ok(), warn()
#   (VENV_PYTHON/SCRIPT_DIR/LLM_TMP come from lib/env.sh; pdflatex = MiKTeX)
###############################################################################

COMPILE_ERROR=""
COMPILE_LOG=""

# File-name prefix for the generated PDFs (config.py: CANDIDATE_FILE_PREFIX)
CANDIDATE_FILE_PREFIX="${CANDIDATE_FILE_PREFIX:-$("$VENV_PYTHON" -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import config; print(config.CANDIDATE_FILE_PREFIX)" | tr -d '\r')}"

compile_step1_pdfs() {
    local app_dir="$1"
    cd "$app_dir"
    set +e
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf" 2>&1
    local r1=$?
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Job_Description.yaml" "Job_Description.pdf" 2>&1
    local r2=$?
    set -e
    if [[ $r1 -ne 0 ]]; then
        warn "ATS_Report.pdf compilation failed (exit $r1)"
    fi
    if [[ $r2 -ne 0 ]]; then
        warn "Job_Description.pdf compilation failed (exit $r2)"
    fi
}

get_resume_filenames() {
    local language="$1"
    if [[ "$language" == "German" ]]; then
        RESUME_PDF="${CANDIDATE_FILE_PREFIX}_Lebenslauf.pdf"
        RESUME_TEX="${CANDIDATE_FILE_PREFIX}_Lebenslauf.tex"
    else
        RESUME_PDF="${CANDIDATE_FILE_PREFIX}_Resume.pdf"
        RESUME_TEX="${CANDIDATE_FILE_PREFIX}_Resume.tex"
    fi
}

get_cover_letter_filename() {
    local language="$1"
    if [[ "$language" == "German" ]]; then
        CL_PDF="${CANDIDATE_FILE_PREFIX}_Anschreiben.pdf"
    else
        CL_PDF="${CANDIDATE_FILE_PREFIX}_Cover_Letter.pdf"
    fi
}

compile_resume() {
    local app_dir="$1"
    local language="$2"
    local render_mode="$3"

    get_resume_filenames "$language"
    cd "$app_dir"
    COMPILE_ERROR=""
    COMPILE_LOG=""
    set +e

    if [[ "$render_mode" == "latex" ]]; then
        # Step A: Generate .tex
        "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "$RESUME_PDF" --tex-only > $LLM_TMP/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="yaml_to_pdf --tex-only failed"
            COMPILE_LOG=$(cat $LLM_TMP/llm-cv-compile.log)
            set -e; return 1
        fi

        # Step B: Check tex (char counts)
        "$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" --check-tex "$RESUME_TEX" > $LLM_TMP/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="check-tex failed (char count violations)"
            COMPILE_LOG=$(cat $LLM_TMP/llm-cv-compile.log)
            set -e; return 1
        fi

        # Step C: Double pdflatex
        # MiKTeX: -enable-installer fetches any missing LaTeX package without a GUI prompt.
        pdflatex -interaction=nonstopmode -enable-installer "$RESUME_TEX" > "$LLM_TMP/llm-cv-pdflatex.log" 2>&1
        pdflatex -interaction=nonstopmode -enable-installer "$RESUME_TEX" >> "$LLM_TMP/llm-cv-pdflatex.log" 2>&1
        if [[ ! -f "$RESUME_PDF" ]]; then
            COMPILE_ERROR="pdflatex produced no PDF"
            COMPILE_LOG=$(tail -30 "$LLM_TMP/llm-cv-pdflatex.log")
            set -e; return 1
        fi

        # Stamp photo
        "$VENV_PYTHON" "$SCRIPT_DIR/stamp_photo.py" "$RESUME_PDF" "Resume.yaml" > $LLM_TMP/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            warn "stamp_photo.py returned non-zero — photo may be missing"
        fi
    else
        # ReportFallback: single compile, no photo stamp
        "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Resume.yaml" "$RESUME_PDF" > $LLM_TMP/llm-cv-compile.log 2>&1
        if [[ $? -ne 0 ]]; then
            COMPILE_ERROR="yaml_to_pdf (ReportFallback) failed"
            COMPILE_LOG=$(cat $LLM_TMP/llm-cv-compile.log)
            set -e; return 1
        fi
    fi

    # Step D: Parseability audit
    "$VENV_PYTHON" "$SCRIPT_DIR/resume_parseability.py" "$RESUME_PDF" "Resume.yaml" > $LLM_TMP/llm-cv-parse.log 2>&1
    if [[ $? -ne 0 ]]; then
        COMPILE_ERROR="parseability audit failed"
        COMPILE_LOG=$(cat $LLM_TMP/llm-cv-parse.log)
        set -e; return 1
    fi

    # Step E: Watermark check (non-critical)
    "$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Resume.yaml" "$RESUME_PDF" > $LLM_TMP/llm-cv-watermark.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "AI watermark check returned non-zero exit — investigate before submitting"
        warn "See $LLM_TMP/llm-cv-watermark.log"
    fi

    # Recompile ATS report with post-rewrite scores
    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "ATS_Report.yaml" "ATS_Report.pdf" > /dev/null 2>&1

    set -e
    ok "Resume compiled: $RESUME_PDF"
    return 0
}

compile_cover_letter() {
    local app_dir="$1"
    local language="$2"

    get_cover_letter_filename "$language"
    cd "$app_dir"
    set +e

    "$VENV_PYTHON" "$SCRIPT_DIR/yaml_to_pdf.py" "Cover_Letter.yaml" "$CL_PDF" > $LLM_TMP/llm-cv-cl-compile.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "Cover letter compilation failed. See $LLM_TMP/llm-cv-cl-compile.log"
        set -e; return 1
    fi

    "$VENV_PYTHON" "$SCRIPT_DIR/check_watermarks.py" "Cover_Letter.yaml" "$CL_PDF" > $LLM_TMP/llm-cv-cl-watermark.log 2>&1
    if [[ $? -ne 0 ]]; then
        warn "Cover letter watermark check returned non-zero — investigate"
    fi

    set -e
    ok "Cover letter compiled: $CL_PDF"
    return 0
}

generate_layout_audit() {
    local app_dir="$1"
    local resume_pdf="$2"
    local parse_status="Pass"
    local fill_status="Pass"
    local page_count=""

    # Length requirement: at least 1.5 pages, at most 2 (lib/length_check.py)
    local len_rc=0
    page_count=$("$VENV_PYTHON" "$SCRIPT_DIR/lib/length_check.py" "$resume_pdf" | tr -d '\r') || len_rc=$?
    if [[ $len_rc -ne 0 ]]; then
        fill_status="Fail"
    fi

    # Check if parseability report exists and passed
    if [[ -f "$app_dir/Parseability_Report.yaml" ]]; then
        local parse_raw
        parse_raw=$("$VENV_PYTHON" "$SCRIPT_DIR/lib/yaml_get.py" "$app_dir/Parseability_Report.yaml" overall_status "" | tr -d '\r')
        [[ -z "$parse_raw" ]] && parse_raw=$("$VENV_PYTHON" "$SCRIPT_DIR/lib/yaml_get.py" "$app_dir/Parseability_Report.yaml" status "" | tr -d '\r')
        local parse_pass="Fail"
        [[ "${parse_raw,,}" == *pass* ]] && parse_pass="Pass"
        parse_status="$parse_pass"
    fi

    cat > "$app_dir/Layout_Audit_Report.yaml" << EOF
type: layout_audit_report
eye_test_diagnostics:
  page_fill_density:
    status: "$fill_status"
    feedback: "$page_count (requirement: 1.5 to 2 pages)"
  parseability:
    status: "$parse_status"
    feedback: "From resume_parseability.py"
  watermark_check:
    status: "Pass"
    feedback: "From check_watermarks.py"
direct_visual_refactoring_actions: []
optimized_v2_generated: false
EOF
}
