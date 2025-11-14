#!/bin/bash
set -e

# 002-generate-import-script.sh - Generate the bulk import script
# Creates import script with inconsistency detection and split schema loading
# The generated import script is ALWAYS output directly to $BULK_DIR as $BULK_DIR/load-bulk-data-$PIPELINE_DATE.sh.
# Both generator and consumer scripts MUST reference the import script at this location for consistency.

# Get script directory and source libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

PHASE_START_TIME=$(date +%s)

log_section "PHASE 2: IMPORT SCRIPT GENERATION"

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
            --bulk-dir=*) BULK_DIR="${arg#*=}" ;;
            *) log "ERROR" "Unknown argument: $arg"; exit 1 ;;
        esac
    done

    # Validate required arguments
    local missing_args=()
    local present_args=()
    [[ -z "$DB_HOST" ]] && missing_args+=("DB_HOST") || present_args+=("DB_HOST=$DB_HOST")
    [[ -z "$DB_USER" ]] && missing_args+=("DB_USER") || present_args+=("DB_USER=$DB_USER")
    [[ -z "$DB_PASSWORD" ]] && missing_args+=("DB_PASSWORD") || present_args+=("DB_PASSWORD=<set>")
    [[ -z "$PIPELINE_DATE" ]] && missing_args+=("PIPELINE_DATE") || present_args+=("PIPELINE_DATE=$PIPELINE_DATE")
    [[ -z "$TEMP_DIR" ]] && missing_args+=("TEMP_DIR") || present_args+=("TEMP_DIR=$TEMP_DIR")
    [[ -z "$BULK_DIR" ]] && missing_args+=("BULK_DIR") || present_args+=("BULK_DIR=$BULK_DIR")

    if (( ${#missing_args[@]} > 0 )); then
        log "ERROR" "Argument values present:"
        for arg in "${present_args[@]}"; do
            log "ERROR" "  $arg"
        done
        log "ERROR" "Missing required arguments: ${missing_args[*]}"
        log "ERROR" "Usage: $0 --db-host=HOST --db-user=USER --db-password=PASS --pipeline-date=DATE --temp-dir=DIR --bulk-dir=DIR [--output-dir=DIR]"
        exit 1
    fi

    if [[ ! -f "$TEMP_DIR/bulk_tables_metadata.txt" ]]; then
        log "ERROR" "Table metadata file not found at $TEMP_DIR/bulk_tables_metadata.txt"
        exit 1
    fi
}

parse_args "$@"

# Determine output location
SCRIPT_OUTPUT_DIR="$BULK_DIR"
mkdir -p "$SCRIPT_OUTPUT_DIR"

import_script_name="load-bulk-data-$PIPELINE_DATE.sh"
import_script_path="$SCRIPT_OUTPUT_DIR/$import_script_name"

log "INFO" "Generating import script: $import_script_name"
log "INFO" "Import script will be output directly to \$BULK_DIR: $BULK_DIR (resolved as $SCRIPT_OUTPUT_DIR)"

# --- Template rendering and table definition generation ---
### Template processing utilities (moved from template_utils.sh)

# Process a template file by substituting variables using jq
# Usage: process_template template_file output_file variable1=value1 variable2=value2 ...
process_template() {
    local template_file="$1"
    local output_file="$2"
    shift 2

    if [[ ! -f "$template_file" ]]; then
        log "ERROR" "Template file not found: $template_file"
        return 1
    fi

    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        log "ERROR" "jq is required for template processing but not found"
        return 1
    fi

    # Build a JSON object with all variables
    local json_vars="{}"
    for var_assignment in "$@"; do
        if [[ "$var_assignment" =~ ^([^=]+)=(.*)$ ]]; then
            local var_name="${BASH_REMATCH[1]}"
            local var_value="${BASH_REMATCH[2]}"
            # Use jq to safely add the variable to the JSON object
            json_vars=$(echo "$json_vars" | jq --arg key "$var_name" --arg value "$var_value" '. + {($key): $value}')
        else
            log "WARN" "Invalid variable assignment format: $var_assignment"
        fi
    done

    # Process the template using jq for robust string replacement
    local template_content
    template_content=$(cat "$template_file")

    # Use jq to replace all {{VARIABLE}} patterns with actual values
    echo "$json_vars" | jq -r --arg template "$template_content" '
        . as $vars |
        $template |
        reduce ($vars | keys_unsorted[]) as $key (.;
            gsub("{{" + $key + "}}"; $vars[$key])
        )
    ' > "$output_file"
}

# Generate table definitions for the template
# Usage: generate_table_definitions metadata_file
generate_table_definitions() {
    local metadata_file="$1"

    if [[ ! -f "$metadata_file" ]]; then
        log "ERROR" "Metadata file not found: $metadata_file"
        return 1
    fi

    while IFS='|' read -r table_name csv_filename _; do
        # Only use the first two fields, ignore extras
        # Make filenames date-agnostic by replacing {{DATE}} with wildcard pattern
        date_agnostic_filename=$(echo "$csv_filename" | sed "s/{{DATE}}/????-??-??/g")
        echo "  \"$table_name|$date_agnostic_filename\""
    done < "$metadata_file"
}

# Validate template variables are properly substituted
# Usage: validate_template_processing output_file
validate_template_processing() {
    local output_file="$1"

    local remaining_vars=$(grep -o '{{[^}]*}}' "$output_file" 2>/dev/null || true)

    if [[ -n "$remaining_vars" ]]; then
        log "WARN" "Unsubstituted template variables found in $output_file:"
        log "WARN" "$remaining_vars"
        return 1
    fi

    return 0
}

# Set template and output paths
TEMPLATE_PATH="$SCRIPT_DIR/templates/bulk-import-script.template.sh"


TABLE_DEFINITIONS=$(generate_table_definitions "$TEMP_DIR/bulk_tables_import.txt")

# Set schema file names (adjust as needed)
PRE_DATA_SCHEMA="schema-pre-data-$PIPELINE_DATE.sql"
POST_DATA_SCHEMA="schema-post-data-$PIPELINE_DATE.sql"

# Render the template
process_template "$TEMPLATE_PATH" "$import_script_path" \
    PIPELINE_DATE="$PIPELINE_DATE" \
    PRE_DATA_SCHEMA="$PRE_DATA_SCHEMA" \
    POST_DATA_SCHEMA="$POST_DATA_SCHEMA" \
    TABLE_DEFINITIONS="$TABLE_DEFINITIONS"

chmod +x "$import_script_path"

# Optionally validate
validate_template_processing "$import_script_path" || log "WARN" "Some template variables were not replaced."

log "SUCCESS" "Import script generated at: $import_script_path (located in \$BULK_DIR for downstream consumption)"
