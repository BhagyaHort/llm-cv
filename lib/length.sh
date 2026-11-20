#!/bin/bash
###############################################################################
# lib/length.sh — resume length governor (NON-NEGOTIABLE: 1.5 to 2 pages)
#
# Sourced by run_pipeline.sh after lib/compile.sh. Provides:
#   ensure_resume_length <app_dir> <language> <render_mode>
#
# After the resume PDF compiles it is measured (lib/length_check.py):
#   SHORT (< 1.5 pages): up to 2 model passes ask Claude to add REAL content from the base
#                        resume/catalog (api_pipeline.py fix, LENGTH_SHORT). If it is still short,
#                        deterministic layout levels 1-4 are applied (layout_boost in Resume.yaml:
#                        wider margins, line spacing, bullet gaps, 12pt) until the minimum is met.
#   LONG  (> 2 pages)  : first relax any layout boost, then up to 3 model passes trim the least
#                        relevant content (LENGTH_LONG).
# Sets RESUME_LENGTH_STATUS (OK|FAIL) and RESUME_LENGTH_INFO for the final summary.
#
# Depends on: VENV_PYTHON, SCRIPT_DIR, LLM_TMP, RESUME_PDF, log/ok/warn, api(), compile_resume().
###############################################################################

RESUME_LENGTH_STATUS=""
RESUME_LENGTH_INFO=""
MAX_LENGTH_MODEL_FIXES_SHORT=2
MAX_LENGTH_MODEL_FIXES_LONG=3

_measure_resume_length() {
    local pdf="$1" rc=0
    "$VENV_PYTHON" "$SCRIPT_DIR/lib/length_check.py" "$pdf" > "$LLM_TMP/llm-cv-length.txt" 2>"$LLM_TMP/llm-cv-length.err" || rc=$?
    RESUME_LENGTH_INFO="$(tr -d '\r' < "$LLM_TMP/llm-cv-length.txt")"
    return $rc
}

ensure_resume_length() {
    local app_dir="$1" language="$2" render_mode="$3"
    local pdf="$app_dir/$RESUME_PDF"
    local model_fixes=0 boost=0 rc=0 err_msg=""
    RESUME_LENGTH_STATUS="FAIL"

    if [[ ! -f "$pdf" ]]; then
        warn "No resume PDF to measure: $pdf"
        return 1
    fi

    local guard=0
    while [[ $guard -lt 12 ]]; do
        guard=$((guard + 1))
        rc=0
        _measure_resume_length "$pdf" || rc=$?
        log "Resume length: $RESUME_LENGTH_INFO (layout_boost=$boost)"

        if [[ $rc -eq 0 ]]; then
            RESUME_LENGTH_STATUS="OK"
            ok "Resume length OK (>= 1.5 pages, <= 2 pages)"
            return 0
        fi

        if [[ $rc -eq 3 ]]; then
            # SHORT
            if [[ $boost -eq 0 && $model_fixes -lt $MAX_LENGTH_MODEL_FIXES_SHORT ]]; then
                model_fixes=$((model_fixes + 1))
                err_msg="LENGTH_SHORT: measured $RESUME_LENGTH_INFO; minimum is 1.5 pages"
                log "Resume is under 1.5 pages: asking Claude to add real content (pass $model_fixes/$MAX_LENGTH_MODEL_FIXES_SHORT)..."
                api fix --app-dir "$app_dir" --error "$err_msg" --language "$language" \
                    > "$LLM_TMP/llm-cv-lenfix-$guard.log" 2>&1 || warn "length fix call failed (see $LLM_TMP/llm-cv-lenfix-$guard.log)"
            elif [[ $boost -lt 4 ]]; then
                boost=$((boost + 1))
                log "Still short after model passes: applying layout level $boost"
                "$VENV_PYTHON" "$SCRIPT_DIR/lib/set_boost.py" "$app_dir/Resume.yaml" "$boost" > /dev/null
            else
                warn "Resume is still under 1.5 pages at the maximum layout level."
                return 1
            fi
        else
            # LONG (rc=4)
            if [[ $boost -gt 0 ]]; then
                boost=$((boost - 1))
                log "Over 2 pages with layout level: relaxing to level $boost"
                "$VENV_PYTHON" "$SCRIPT_DIR/lib/set_boost.py" "$app_dir/Resume.yaml" "$boost" > /dev/null
            elif [[ $model_fixes -lt $MAX_LENGTH_MODEL_FIXES_LONG ]]; then
                model_fixes=$((model_fixes + 1))
                err_msg="LENGTH_LONG: measured $RESUME_LENGTH_INFO; maximum is 2 pages"
                log "Resume is over 2 pages: asking Claude to trim (pass $model_fixes/$MAX_LENGTH_MODEL_FIXES_LONG)..."
                api fix --app-dir "$app_dir" --error "$err_msg" --language "$language" \
                    > "$LLM_TMP/llm-cv-lenfix-$guard.log" 2>&1 || warn "length fix call failed (see $LLM_TMP/llm-cv-lenfix-$guard.log)"
            else
                warn "Resume is still over 2 pages after trimming."
                return 1
            fi
        fi

        if ! compile_resume "$app_dir" "$language" "$render_mode"; then
            warn "Recompile failed during length adjustment: $COMPILE_ERROR"
            return 1
        fi
    done
    warn "Length governor gave up after $guard rounds."
    return 1
}
