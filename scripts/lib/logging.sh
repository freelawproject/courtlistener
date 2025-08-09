#!/bin/bash
# logging.sh - Professional, non-blocking logging and UI for bulk data pipeline
# Provides consistent, clean output suitable for logs and interactive use

# Color codes (optional, can be disabled for pure professional output)
if [[ -z "$NO_COLOR" ]]; then
    declare -A COLORS=(
        ["reset"]="\033[0m"
        ["bold"]="\033[1m"
        ["dim"]="\033[2m"
        ["red"]="\033[31m"
        ["green"]="\033[32m"
        ["yellow"]="\033[33m"
        ["blue"]="\033[34m"
        ["magenta"]="\033[35m"
        ["cyan"]="\033[36m"
        ["gray"]="\033[90m"
    )
else
    declare -A COLORS=(
        ["reset"]=""
        ["bold"]=""
        ["dim"]=""
        ["red"]=""
        ["green"]=""
        ["yellow"]=""
        ["blue"]=""
        ["magenta"]=""
        ["cyan"]=""
        ["gray"]=""
    )
fi

# Log levels
declare -A LOG_LEVELS=(
    ["DEBUG"]=0
    ["INFO"]=1
    ["SUCCESS"]=2
    ["WARN"]=3
    ["ERROR"]=4
    ["FATAL"]=5
)

# Default log level
CURRENT_LOG_LEVEL=${LOG_LEVEL:-"INFO"}

# Log with timestamp, level, and message
log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")

    # Only log if level is >= current log level
    if [[ ${LOG_LEVELS[$level]} -ge ${LOG_LEVELS[$CURRENT_LOG_LEVEL]} ]]; then
        case "$level" in
            DEBUG)
                echo -e "${COLORS[gray]}${timestamp} [DEBUG] ${message}${COLORS[reset]}" >&2
                ;;
            INFO)
                echo -e "${COLORS[blue]}${timestamp} [INFO]  ${message}${COLORS[reset]}"
                ;;
            SUCCESS)
                echo -e "${COLORS[green]}${timestamp} [SUCCESS] ${message}${COLORS[reset]}"
                ;;
            WARN)
                echo -e "${COLORS[yellow]}${timestamp} [WARN]  ${message}${COLORS[reset]}" >&2
                ;;
            ERROR)
                echo -e "${COLORS[red]}${timestamp} [ERROR] ${message}${COLORS[reset]}" >&2
                ;;
            FATAL)
                echo -e "${COLORS[red]}${timestamp} [FATAL] ${message}${COLORS[reset]}" >&2
                ;;
            *)
                echo -e "${timestamp} [$level] $message"
                ;;
        esac
    fi
}

# Section header
log_section() {
    local title="$1"
    log "INFO" "=== $title ==="
}

# Progress indicator (non-blocking)
log_progress() {
    local current="$1"
    local total="$2"
    local label="$3"
    local progress=$((current * 100 / total))
    log "INFO" "Progress: $progress% ($current/$total) - $label"
}

# Success message with duration
log_success() {
    local label="$1"
    local duration="$2"
    log "SUCCESS" "Completed: $label ($duration s)"
}

# Error message
log_error() {
    local message="$1"
    log "ERROR" "$message"
}

# Fatal error and exit
fatal() {
    local message="$1"
    log "FATAL" "FATAL: $message"
    exit 1
}

# Show completion banner
log_completion() {
    local total_duration="$1"
    local hours=$((total_duration / 3600))
    local minutes=$(((total_duration % 3600) / 60))
    local seconds=$((total_duration % 60))
    log "SUCCESS" "Pipeline completed in ${hours}h ${minutes}m ${seconds}s"
}

# Show configuration
log_config() {
    local workers="$1"
    local script_dir="$2"
    local output_dir="$3"
    local skip_phases="$4"
    local threshold_gb="$5"
    local threshold_rows="$6"
    local pipeline_date="$7"

    log "INFO" "CONFIGURATION:"
    log "INFO" "  Workers: $workers"
    log "INFO" "  Script directory: $script_dir"
    log "INFO" "  Output: ${output_dir:-S3 (com-courtlistener-storage/bulk-data)}"
    log "INFO" "  Skip phases: ${skip_phases:-none}"
    log "INFO" "  Large table thresholds: ${threshold_gb}GB or ${threshold_rows} rows"
    log "INFO" "  Pipeline date: $pipeline_date"
}

# Show help
log_help() {
    log "INFO" "DESCRIPTION:"
    log "INFO" "  CSV-driven bulk data export pipeline with dynamic schema introspection"
    log "INFO" ""
    log "INFO" "USAGE:"
    log "INFO" "  $0 [options]"
    log "INFO" ""
    log "INFO" "OPTIONS:"
    log "INFO" "  --workers=N                    Number of parallel workers (default: 1, -1 = auto-detect)"
    log "INFO" "  --output-dir=PATH              Output to local directory instead of S3"
    log "INFO" "  --skip-export                  Skip data export phase"
    log "INFO" "  --skip-schema                  Skip schema export phase"
    log "INFO" "  --skip-import-gen              Skip import script generation phase"
    log "INFO" "  --large-table-size-threshold=N Large table size threshold in GB (default: 4)"
    log "INFO" "  --large-table-rows-threshold=N Large table row count threshold (default: 1000000)"
    log "INFO" "  --help                         Show this help message"
    log "INFO" ""
    log "INFO" "ENVIRONMENT VARIABLES REQUIRED:"
    log "INFO" "  DB_HOST              Database host"
    log "INFO" "  DB_USER              Database username"
    log "INFO" "  DB_PASSWORD          Database password"
    log "INFO" ""
    log "INFO" "EXAMPLES:"
    log "INFO" "  $0 --workers=-1 --output-dir=/tmp/bulk-data    # Local output"
    log "INFO" "  $0 --workers=4                                 # S3 output"
    log "INFO" ""
    log "INFO" "GENERATED FILES:"
    log "INFO" "  • Table data: *.csv.bz2 files"
    log "INFO" "  • Pre-data schema: schema-pre-data-YYYY-MM-DD.sql"
    log "INFO" "  • Post-data schema: schema-post-data-YYYY-MM-DD.sql"
    log "INFO" "  • Import script: load-bulk-data-YYYY-MM-DD.sh"
    log "INFO" ""
    log "INFO" "IMPORT GUIDE (Local):"
    log "INFO" "  1. Set environment variables:"
    log "INFO" "     export BULK_DIR=/path/to/output"
    log "INFO" "     export BULK_DB_HOST=your_target_host"
    log "INFO" "     export BULK_DB_USER=your_target_user"
    log "INFO" "     export BULK_DB_PASSWORD=your_target_password"
    log "INFO" "  2. Run: bash load-bulk-data-YYYY-MM-DD.sh --workers=-1"
    log "INFO" ""
    log "INFO" "IMPORT GUIDE (S3):"
    log "INFO" "  1. Download all files from S3 to a directory"
    log "INFO" "  2. Follow the same steps as Local import"
}

# UI functions (previously in ui.sh)
# Show pipeline header
show_header() {
    log_section "CourtListener Bulk Data Export - Pipeline v2.0"
}

# Show section header
show_section() {
    local title="$1"
    log_section "$title"
}

# Show configuration table
show_config() {
    local workers="$1"
    local script_dir="$2"
    local output_dir="$3"
    local skip_phases="$4"
    local threshold_gb="$5"
    local threshold_rows="$6"
    local pipeline_date="$7"

    log_config "$workers" "$script_dir" "$output_dir" "$skip_phases" "$threshold_gb" "$threshold_rows" "$pipeline_date"
}

# Show progress with logging
show_progress() {
    local current="$1"
    local total="$2"
    local label="$3"
    log_progress "$current" "$total" "$label"
}

# Show success message
show_success() {
    local label="$1"
    local duration="$2"
    log_success "$label" "$duration"
}

# Show error message
show_error() {
    local message="$1"
    log_error "$message"
}

# Show completion banner
show_completion() {
    local total_duration="$1"
    log_completion "$total_duration"
}

# Show usage help
show_help() {
    log_help
}