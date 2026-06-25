#!/bin/bash
# bulk-data-pipeline.sh - Master orchestration script
# Streamlined CSV-driven bulk data export pipeline

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/pipeline.sh"

# Configuration defaults
TABLES_CONFIG="$SCRIPT_DIR/bulk_tables.csv"

# Parse command line arguments
parse_args() {
    WORKERS=1
    SKIP_PHASES=""
    OUTPUT_DIR=""
    for arg in "$@"; do
        case $arg in
            --workers=*) WORKERS="${arg#*=}" ;;
            --output-dir=*) OUTPUT_DIR="${arg#*=}" ;;
            --skip-export) SKIP_PHASES="$SKIP_PHASES export" ;;
            --skip-schema) SKIP_PHASES="$SKIP_PHASES schema" ;;
            --skip-import-gen) SKIP_PHASES="$SKIP_PHASES import-gen" ;;
            --large-table-size-threshold=*) LARGE_TABLE_SIZE_THRESHOLD_GB="${arg#*=}" ;;
            --large-table-rows-threshold=*) LARGE_TABLE_ROWS_THRESHOLD="${arg#*=}" ;;
            --help) show_help; exit 0 ;;
        esac
    done
    # Auto-detect workers if requested
    if [[ "$WORKERS" == "-1" ]]; then
        CORES=$(nproc --all 2>/dev/null || echo 4)
        WORKERS=$(( CORES * 8 / 10 ))
        if (( WORKERS < 1 )); then WORKERS=1; fi
    fi
}

# Cleanup function
cleanup() {
    log "INFO" "Cleaning up temporary files..."
    if [[ -n "$TEMP_DIR" && "$TEMP_DIR" != "/" && "$TEMP_DIR" != "/tmp" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
set -e

# Run preflight checks
run_preflight_checks() {
    log_section "PREFLIGHT CHECKS"

    local errors=()

    # Environment variables
    log "INFO" "Checking environment variables..."
    validate_env_vars "DB_HOST" "DB_USER" "DB_PASSWORD" || errors+=("Environment variables not set")

    # Required binaries
    log "INFO" "Checking required binaries..."
    check_binaries "psql" "pg_dump" "lbzip2" "bc" "jq" || errors+=("Required binaries missing")

    # GNU parallel
    log "INFO" "Checking GNU parallel..."
    check_gnu_parallel

    # Output directory or S3
    check_output "$OUTPUT_DIR" || errors+=("Output directory/S3 not accessible")

    # Test database connection
    log "INFO" "Testing database connection..."
    test_db_connection "$DB_HOST" "$DB_USER" "$DB_PASSWORD" || errors+=("Cannot connect to database")

    if [[ ${#errors[@]} -gt 0 ]]; then
        log "FATAL" "Preflight checks failed"
        for error in "${errors[@]}"; do
            log "ERROR" "  • $error"
        done
        exit 1
    fi
    log "SUCCESS" "All preflight checks passed"
}

# Setup directories and environment
setup_environment() {
    PIPELINE_DATE="$(date -I)"
    setup_directories "$OUTPUT_DIR" "TEMP_DIR" || exit 1
    export DB_HOST DB_USER DB_PASSWORD OUTPUT_DIR PIPELINE_DATE TEMP_DIR
    export LARGE_TABLE_SIZE_THRESHOLD_GB LARGE_TABLE_ROWS_THRESHOLD
}

generate_table_metadata() {
    log_section "SCHEMA INTROSPECTION"

    log "INFO" "Generating table metadata from CSV config: $TABLES_CONFIG"
    if [[ ! -f "$TABLES_CONFIG" ]]; then
        log "ERROR" "Table configuration file not found: $TABLES_CONFIG"
        exit 1
    fi
    rm -f "$TEMP_DIR/bulk_tables_metadata.txt"
    rm -f "$TEMP_DIR/bulk_tables_import.txt"
    local total=$(($(wc -l < "$TABLES_CONFIG") - 1)) # minus header

    export DB_HOST DB_USER DB_PASSWORD PIPELINE_DATE TEMP_DIR LARGE_TABLE_SIZE_THRESHOLD_GB LARGE_TABLE_ROWS_THRESHOLD

    table_metadata_worker() {
        table="$1"
        filename="$2"
        idx="$3"
        total="$4"
        echo "Processing table $idx/$total: $table" >&2
        filename="${filename//\{\{DATE\}\}/$PIPELINE_DATE}"
        table_exists=$(PGPASSWORD="$DB_PASSWORD" psql \
            --host "$DB_HOST" --username "$DB_USER" --dbname courtlistener \
            --tuples-only --no-align \
            --command "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '$table';" 2>/dev/null)
        if [[ -z "$table_exists" ]]; then
            echo "  ERROR: Table '$table' from CSV does not exist in the database" >&2
            return
        fi
        size_bytes=$(PGPASSWORD="$DB_PASSWORD" psql \
            --host "$DB_HOST" --username "$DB_USER" --dbname courtlistener \
            --tuples-only --no-align \
            --command "SELECT pg_total_relation_size('public.\"$table\"');" 2>/dev/null)
        # Output both formats for downstream compatibility
        echo "$table|$filename" >> "$TEMP_DIR/bulk_tables_import.txt"
        echo "$table|$filename|$size_bytes" >> "$TEMP_DIR/bulk_tables_metadata.txt"
    }

    export -f table_metadata_worker

    # Prepare input for parallel: table, filename, idx, total
    tail -n +2 "$TABLES_CONFIG" | awk -F',' -v total="$total" '{print $1"\t"$2}' | \
        awk -v total="$total" -v OFS='\t' '{print $1, $2, NR, total}' | \
        parallel --bar --colsep '\t' --jobs "$WORKERS" table_metadata_worker {1} {2} {3} {4} > /dev/null

    local total_tables=$(wc -l < "$TEMP_DIR/bulk_tables_metadata.txt")
    log "SUCCESS" "Table metadata generated: $TEMP_DIR/bulk_tables_metadata.txt"
    log "INFO" "Found $total_tables tables with information"

    if [[ $total_tables -eq 0 ]]; then
        log "ERROR" "No table metadata was generated. Check database connection and table names."
        exit 1
    fi
}

# Main execution flow
main() {
    # Initialize
    local start_time=$(date +%s)
    show_header

    # Parse arguments and setup
    parse_args "$@"
    run_preflight_checks
    setup_environment

    # Show configuration
    show_config "$WORKERS" "$SCRIPT_DIR" "$OUTPUT_DIR" "$SKIP_PHASES" \
        "$LARGE_TABLE_SIZE_THRESHOLD_GB" "$LARGE_TABLE_ROWS_THRESHOLD" "$PIPELINE_DATE"

    log "INFO" "Using temp directory: $TEMP_DIR"

    # Setup cleanup
    trap cleanup EXIT  # Enables cleanup of temp files on script exit

    # Generate metadata and run pipeline
    generate_table_metadata
    local total_duration
    total_duration=$(run_pipeline "$WORKERS" "$SKIP_PHASES")
    log "DEBUG" "run_pipeline returned: '$total_duration'"
    if ! [[ "$total_duration" =~ ^[0-9]+$ ]]; then
        log "ERROR" "run_pipeline did not return a numeric duration: '$total_duration'"
        total_duration=0
    fi

    # Show final instructions (now in log_help)
    log_help

    local hours=$((total_duration / 3600))
    local minutes=$(((total_duration % 3600) / 60))
    local seconds=$((total_duration % 60))
    log "SUCCESS" "Pipeline completed in ${hours}h ${minutes}m ${seconds}s!"
}

# Run main with all arguments
main "$@"
