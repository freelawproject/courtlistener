#!/bin/bash
set -e

# 003-bulk-data-export.sh - Export data from tables in parallel

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Ensure logging.sh is properly sourced
if [[ ! -f "$SCRIPT_DIR/lib/logging.sh" ]]; then
    echo "ERROR: logging.sh not found at $SCRIPT_DIR/lib/logging.sh"
    exit 1
fi
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

PHASE_START_TIME=$(date +%s)

log_section "PHASE 3: BULK DATA EXPORT"

# Parse command line arguments
parse_args() {
    for arg in "$@"; do
        case $arg in
            --db-host=*) DB_HOST="${arg#*=}" ;;
            --db-user=*) DB_USER="${arg#*=}" ;;
            --db-password=*) DB_PASSWORD="${arg#*=}" ;;
            --pipeline-date=*) PIPELINE_DATE="${arg#*=}" ;;
            --output-dir=*) OUTPUT_DIR="${arg#*=}" ;;
            --temp-dir=*) TEMP_DIR="${arg#*=}" ;;
            --workers=*) WORKERS="${arg#*=}" ;;
            *) log "ERROR" "Unknown argument: $arg"; exit 1 ;;
        esac
    done

    # Validate required arguments
    if [[ -z "$DB_HOST" ]] || [[ -z "$DB_USER" ]] || [[ -z "$DB_PASSWORD" ]] || [[ -z "$PIPELINE_DATE" ]] || [[ -z "$TEMP_DIR" ]]; then
        log "ERROR" "Missing required arguments. Usage: $0 --db-host=HOST --db-user=USER --db-password=PASS --pipeline-date=DATE --temp-dir=DIR [--output-dir=DIR]"
        exit 1
    fi

    # Validate metadata file exists and is readable
    if [[ ! -f "$TEMP_DIR/bulk_tables_metadata.txt" ]]; then
        log "ERROR" "Table metadata file not found at $TEMP_DIR/bulk_tables_metadata.txt"
        exit 1
    elif [[ ! -r "$TEMP_DIR/bulk_tables_metadata.txt" ]]; then
        log "ERROR" "Table metadata file not readable at $TEMP_DIR/bulk_tables_metadata.txt"
        exit 1
    fi
}

parse_args "$@"

# --- Data Export ---
export PGPASSWORD="$DB_PASSWORD"

# Source logging functions for subshells
SCRIPT_DIR_ABS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SCRIPT_DIR_ABS


export_table() {
    local table_name=$1
    local filename=$2
    local output_path="$3"
    local compression_threads=$4

    # Source logging for subshell
    source "$SCRIPT_DIR_ABS/lib/logging.sh"

    local start_time
    start_time=$(date +%s)

    # Validate table name is not empty
    if [[ -z "$table_name" ]]; then
        log "ERROR" "Empty table name received for export"
        return 1
    fi

    log "INFO" "Exporting table: $table_name to $filename"

    local base_filename="${filename%.csv}"

    # Use COPY TO for CSV export
    PGPASSWORD="$DB_PASSWORD" psql \
        --host "$DB_HOST" \
        --username "$DB_USER" \
        --dbname courtlistener \
        --command "\\COPY public.\"$table_name\" TO STDOUT WITH (FORMAT csv, HEADER, ENCODING 'utf8', ESCAPE '\\');" \
    | lbzip2 -n "$compression_threads" > "$output_path/$base_filename.csv.bz2"

    if [[ $? -ne 0 ]]; then
        log "ERROR" "Failed to export table: $table_name"
        return 1
    fi

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log "SUCCESS" "Exported table: $table_name in ${duration}s"
}

export -f export_table
export DB_HOST DB_USER DB_PASSWORD SCRIPT_DIR_ABS EXPORT_DIR

# Determine output location
if [[ -n "$OUTPUT_DIR" ]]; then
    EXPORT_DIR="$OUTPUT_DIR"
else
    EXPORT_DIR="$TEMP_DIR/export"
fi

# Export all necessary variables for parallel subshells
export EXPORT_DIR DB_HOST DB_USER DB_PASSWORD SCRIPT_DIR_ABS

# Validate output directory is writable and not root
if [[ "$EXPORT_DIR" == "/" ]] || [[ "$EXPORT_DIR" == "/root" ]] || [[ "$EXPORT_DIR" == "/home" ]]; then
    log "ERROR" "Refusing to write to system directory: $EXPORT_DIR"
    exit 1
fi

if [[ ! -w "$(dirname "$EXPORT_DIR")" ]]; then
    log "ERROR" "Cannot write to directory: $EXPORT_DIR"
    exit 1
fi

mkdir -p "$EXPORT_DIR"

# Read table metadata into an array, sort by size (ascending)
mapfile -t table_lines < <(sort -t'|' -k4 -n "$TEMP_DIR/bulk_tables_metadata.txt")

# Calculate conservative parallelization to avoid over-subscription
CORES=$(nproc --all 2>/dev/null || echo 4)

# Use workers from command line if provided, otherwise calculate conservative default
if [[ -n "$WORKERS" ]]; then
    PARALLEL_WORKERS="$WORKERS"
else
    # Use n_cores * 0.25 GNU parallel workers
    PARALLEL_WORKERS=$(echo "$CORES * 0.25" | bc -l)
    PARALLEL_WORKERS=$(printf "%.0f" "$PARALLEL_WORKERS")
    if (( PARALLEL_WORKERS < 1 )); then PARALLEL_WORKERS=1; fi
fi

LBZIP2_THREADS="$CORES"

log "INFO" "Conservative core allocation:"
log "INFO" "  Total cores: $CORES"
log "INFO" "  Parallel workers: $PARALLEL_WORKERS"
log "INFO" "  lbzip2 threads per worker: $LBZIP2_THREADS"
log "INFO" "  Total table count: ${#table_lines[@]}"

# Create a single export worker function
export_worker() {
    local line="$1"
    local table_name=$(echo "$line" | cut -d'|' -f1)
    local filename=$(echo "$line" | cut -d'|' -f3)

    # Debug output
    log "DEBUG" "Processing table: $table_name, filename: $filename"

    export_table "$table_name" "$filename" "$EXPORT_DIR" "$LBZIP2_THREADS"
}
export -f export_worker
export LBZIP2_THREADS

# Process all tables in size order (rabbits first, elephants last)
log "INFO" "Processing all tables in size order (smallest to largest)"
if [[ ${#table_lines[@]} -gt 0 ]]; then
    printf "%s\n" "${table_lines[@]}" | parallel --line-buffer --jobs "$PARALLEL_WORKERS" export_worker {}
else
    log "INFO" "No tables to process"
fi
log "SUCCESS" "Finished processing all tables at $(date)"

# If not using a local output dir, upload to S3
if [[ -z "$OUTPUT_DIR" ]]; then
    log "INFO" "Uploading to S3..."
    aws s3 sync "$EXPORT_DIR" "s3://com-courtlistener-storage/bulk-data/" --exclude "*" --include "*.csv.bz2"
    log "SUCCESS" "All data uploaded to S3."
fi

# --- Completion ---
PHASE_END_TIME=$(date +%s)
PHASE_DURATION=$((PHASE_END_TIME - PHASE_START_TIME))
minutes=$((PHASE_DURATION / 60))
seconds=$((PHASE_DURATION % 60))

log "SUCCESS" "PHASE 3 COMPLETE: BULK DATA EXPORT"
printf "%-25s %s\n" "Execution time:" "${minutes}m ${seconds}s"