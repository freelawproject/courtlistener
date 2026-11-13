#!/bin/bash
set -e

# 001-export-schema.sh - Export split schema files (pre-data and post-data)
# This implements the PLAN.md requirement to split schema into two parts

# Get script directory and source logging library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/lib" && pwd)/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# Parse arguments
DB_HOST=""
DB_USER=""
DB_PASSWORD=""
PIPELINE_DATE=""
OUTPUT_DIR=""
TEMP_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-host=*) DB_HOST="${1#*=}" ;;
        --db-user=*) DB_USER="${1#*=}" ;;
        --db-password=*) DB_PASSWORD="${1#*=}" ;;
        --pipeline-date=*) PIPELINE_DATE="${1#*=}" ;;
        --output-dir=*) OUTPUT_DIR="${1#*=}" ;;
        --temp-dir=*) TEMP_DIR="${1#*=}" ;;
        *) log "ERROR" "Unknown argument: $1"; exit 1 ;;
    esac
    shift
done

# Validate required arguments
validate_env_vars "DB_HOST" "DB_USER" "DB_PASSWORD" "PIPELINE_DATE" || exit 1

PHASE_START_TIME=$(date +%s)

log_section "PHASE 1: SCHEMA EXPORT"

# Determine output location
if [[ -n "$OUTPUT_DIR" ]]; then
    EXPORT_DIR="$OUTPUT_DIR"
else
    EXPORT_DIR="$TEMP_DIR/schema-export"
    mkdir -p "$EXPORT_DIR"
fi

log "INFO" "Schema export configuration:"
log "INFO" "  Database: $DB_HOST"
log "INFO" "  Export to: $EXPORT_DIR"
log "INFO" "  Date: $PIPELINE_DATE"

# Check pg_dump availability and version
if ! command -v pg_dump &> /dev/null; then
    log "ERROR" "pg_dump not found. Install postgresql-client package."
    exit 1
fi

export PGPASSWORD="$DB_PASSWORD"

CLIENT_VERSION=$(get_pg_dump_version)
SERVER_VERSION=$(get_pg_version "$DB_HOST" "$DB_USER" "$DB_PASSWORD")

log "INFO" "Version compatibility check:"
log "INFO" "  Client (pg_dump): $CLIENT_VERSION"
log "INFO" "  Server: $SERVER_VERSION"

# Check version compatibility
if [[ -n "$CLIENT_VERSION" ]] && [[ -n "$SERVER_VERSION" ]]; then
    compare_pg_versions "$CLIENT_VERSION" "$SERVER_VERSION"
else
    log "WARN" "Could not determine version compatibility"
fi

# Define filenames
schema_pre_filename="schema-pre-data-$PIPELINE_DATE.sql"
schema_post_filename="schema-post-data-$PIPELINE_DATE.sql"

# Export pre-data schema (tables, types, sequences - no constraints/indexes)
log "INFO" "Exporting pre-data schema (tables, types, sequences)..."

if [[ -n "$OUTPUT_DIR" ]]; then
    pg_dump \
        --host "$DB_HOST" \
        --username "$DB_USER" \
        --dbname courtlistener \
        --schema-only \
        --section=pre-data \
        --no-owner \
        --no-privileges \
        --file "$OUTPUT_DIR/$schema_pre_filename"
    log "SUCCESS" "Pre-data schema exported to: $OUTPUT_DIR/$schema_pre_filename"
else
    pg_dump \
        --host "$DB_HOST" \
        --username "$DB_USER" \
        --dbname courtlistener \
        --schema-only \
        --section=pre-data \
        --no-owner \
        --no-privileges \
        --file "$EXPORT_DIR/$schema_pre_filename"

    log "INFO" "Uploading to S3..."
    upload_to_s3 "$EXPORT_DIR" "s3://com-courtlistener-storage/bulk-data/" "*.sql"
    log "SUCCESS" "Pre-data schema uploaded: s3://com-courtlistener-storage/bulk-data/$schema_pre_filename"
fi

# Export post-data schema (constraints, indexes, triggers)
log "INFO" "Exporting post-data schema (constraints, indexes, triggers)..."

if [[ -n "$OUTPUT_DIR" ]]; then
    pg_dump \
        --host "$DB_HOST" \
        --username "$DB_USER" \
        --dbname courtlistener \
        --schema-only \
        --section=post-data \
        --no-owner \
        --no-privileges \
        --file "$OUTPUT_DIR/$schema_post_filename"
    log "SUCCESS" "Post-data schema exported to: $OUTPUT_DIR/$schema_post_filename"
else
    pg_dump \
        --host "$DB_HOST" \
        --username "$DB_USER" \
        --dbname courtlistener \
        --schema-only \
        --section=post-data \
        --no-owner \
        --no-privileges \
        --file "$EXPORT_DIR/$schema_post_filename"

    log "INFO" "Uploading to S3..."
    upload_to_s3 "$EXPORT_DIR" "s3://com-courtlistener-storage/bulk-data/" "*.sql"
    log "SUCCESS" "Post-data schema uploaded: s3://com-courtlistener-storage/bulk-data/$schema_post_filename"
fi

# Count tables for summary
table_count=$(count_tables "$DB_HOST" "$DB_USER" "$DB_PASSWORD")

# Calculate and show timing
PHASE_END_TIME=$(date +%s)
PHASE_DURATION=$((PHASE_END_TIME - PHASE_START_TIME))
minutes=$((PHASE_DURATION / 60))
seconds=$((PHASE_DURATION % 60))

log "SUCCESS" "PHASE 1 COMPLETE: SCHEMA EXPORT"
log "INFO" "Export Summary:"
log "INFO" "  Pre-data schema: $schema_pre_filename"
log "INFO" "  Post-data schema: $schema_post_filename"
log "INFO" "  Tables exported: $table_count"
log "INFO" "  Execution time: ${minutes}m ${seconds}s"

# Cleanup temp directory if used
if [[ -z "$OUTPUT_DIR" ]] && [[ -d "$EXPORT_DIR" ]]; then
    rm -rf "$EXPORT_DIR"
fi
