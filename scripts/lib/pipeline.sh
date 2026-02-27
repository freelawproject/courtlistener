#!/bin/bash
# pipeline.sh - Pipeline execution orchestration
# Manages phase execution, timing, and error handling

# Source dependencies
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/logging.sh"

# Execute pipeline phases
run_pipeline() {
    local workers="$1"
    local skip_phases="$2"

    show_section "PIPELINE EXECUTION"

    # Build phase commands
    local phase_cmds=()
    local phase_labels=()

    if [[ ! "$skip_phases" =~ "schema" ]]; then
        phase_cmds+=("$SCRIPT_DIR/001-export-schema.sh --db-host=$DB_HOST --db-user=$DB_USER --db-password=$DB_PASSWORD --pipeline-date=$PIPELINE_DATE --output-dir=$OUTPUT_DIR --temp-dir=$TEMP_DIR")
        phase_labels+=("Schema Export")
    fi

    if [[ ! "$skip_phases" =~ "import-gen" ]]; then
        phase_cmds+=("$SCRIPT_DIR/002-generate-import-script.sh --db-host=$DB_HOST --db-user=$DB_USER --db-password=$DB_PASSWORD --pipeline-date=$PIPELINE_DATE --output-dir=$OUTPUT_DIR --temp-dir=$TEMP_DIR --bulk-dir=$OUTPUT_DIR")
        phase_labels+=("Import Script Generation")
    fi

    if [[ ! "$skip_phases" =~ "export" ]]; then
        phase_cmds+=("$SCRIPT_DIR/003-bulk-data-export.sh --db-host=$DB_HOST --db-user=$DB_USER --db-password=$DB_PASSWORD --pipeline-date=$PIPELINE_DATE --output-dir=$OUTPUT_DIR --temp-dir=$TEMP_DIR --workers=$workers")
        phase_labels+=("Bulk Data Export")
    fi

    if [[ ${#phase_cmds[@]} -eq 0 ]]; then
        log "WARN" "All phases skipped. Nothing to do."
        return 0
    fi

    # Execute phases
    local phase_num=1
    local total_phases=${#phase_cmds[@]}
    local start_time=$(date +%s)

    for i in "${!phase_cmds[@]}"; do
        local cmd="${phase_cmds[$i]}"
        local label="${phase_labels[$i]}"

        log "INFO" "[$phase_num/$total_phases] Starting: $label"
        local phase_start_time=$(date +%s)

        if $cmd; then
            local phase_end_time=$(date +%s)
            local phase_duration=$((phase_end_time - phase_start_time))
            show_success "$label" "$phase_duration"
        else
            show_error "Phase failed: $label"
            log "ERROR" "Command: $cmd"
            return 1
        fi

        phase_num=$((phase_num + 1))
    done

    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    show_completion "$total_duration"

    echo "$total_duration"
    return 0
}

