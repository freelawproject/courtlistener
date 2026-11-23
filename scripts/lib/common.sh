#!/bin/bash
# common.sh - Shared utilities for bulk data pipeline
# Centralizes common functions and logic used across multiple scripts

# Source logging library
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logging.sh"

# Validate required environment variables
validate_env_vars() {
    local required_vars=("$@")
    local errors=()
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            errors+=("$var environment variable not set")
        fi
    done
    if [[ ${#errors[@]} -gt 0 ]]; then
        for error in "${errors[@]}"; do
            log "ERROR" "$error"
        done
        return 1
    fi
    return 0
}

# Check for required binaries
check_binaries() {
    local binaries=("$@")
    local missing_binaries=()
    for binary in "${binaries[@]}"; do
        if ! command -v "$binary" &> /dev/null; then
            missing_binaries+=("$binary")
        fi
    done
    if [[ ${#missing_binaries[@]} -gt 0 ]]; then
        log "ERROR" "Missing binaries: ${missing_binaries[*]}"
        return 1
    fi
    return 0
}

# Check for GNU parallel (non-fatal)
check_gnu_parallel() {
    if ! command -v parallel &> /dev/null; then
        log "WARN" "GNU parallel not found (performance will be reduced)"
        return 1
    fi
    return 0
}

# Check output directory or S3
check_output() {
    local output_dir="$1"
    if [[ -n "$output_dir" ]]; then
        if ! mkdir -p "$output_dir" 2>/dev/null || [[ ! -w "$output_dir" ]]; then
            log "ERROR" "Cannot create/write: $output_dir"
            return 1
        fi
    else
        local s3_issues=()
        if ! command -v aws &> /dev/null; then s3_issues+=("AWS CLI"); fi
        if [[ -z "$AWS_ACCESS_KEY_ID" ]] || [[ -z "$AWS_SECRET_ACCESS_KEY" ]]; then
            s3_issues+=("AWS credentials")
        fi
        if [[ ${#s3_issues[@]} -gt 0 ]]; then
            log "ERROR" "Missing S3 requirements: ${s3_issues[*]}"
            return 1
        fi
    fi
    return 0
}

# Test database connection
test_db_connection() {
    local db_host="$1"
    local db_user="$2"
    local db_password="$3"
    export PGPASSWORD="$db_password"
    if ! psql --host "$db_host" --username "$db_user" --dbname courtlistener --command "SELECT 1;" >/dev/null 2>&1; then
        log "ERROR" "Cannot connect to database"
        return 1
    fi
    return 0
}

# Calculate worker count
calculate_workers() {
    local workers="$1"
    if [[ "$workers" == "-1" ]]; then
        local cores=$(nproc --all 2>/dev/null || echo 4)
        workers=$(( cores * 8 / 10 ))
        if (( workers < 1 )); then workers=1; fi
    fi
    echo "$workers"
}

# Setup directories
setup_directories() {
    local output_dir="$1"
    local temp_dir_var="$2"
    if [[ -n "$output_dir" ]]; then
        eval "$temp_dir_var=\"$output_dir/tmp\""
    else
        eval "$temp_dir_var=\"/var/tmp/courtlistener-bulk-\$\$\""
    fi
    mkdir -p "${!temp_dir_var}"
    if [[ ! -d "${!temp_dir_var}" ]] || [[ ! -w "${!temp_dir_var}" ]]; then
        log "ERROR" "Cannot create or write to temp directory: ${!temp_dir_var}"
        return 1
    fi
    return 0
}

# Upload to S3
upload_to_s3() {
    local source_dir="$1"
    local s3_dest="$2"
    local pattern="$3"
    log "INFO" "Uploading to S3..."
    aws s3 sync "$source_dir" "$s3_dest" --exclude "*" --include "$pattern"
    log "SUCCESS" "All data uploaded to S3."
}

# Get PostgreSQL version
get_pg_version() {
    local db_host="$1"
    local db_user="$2"
    local db_password="$3"
    export PGPASSWORD="$db_password"
    psql --host "$db_host" --username "$db_user" --dbname courtlistener \
        --tuples-only --no-align --command "SHOW server_version;" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1
}

# Get pg_dump version
get_pg_dump_version() {
    pg_dump --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1
}

# Compare PostgreSQL versions
compare_pg_versions() {
    local client_version="$1"
    local server_version="$2"
    local client_major=$(echo "$client_version" | cut -d. -f1)
    local client_minor=$(echo "$client_version" | cut -d. -f2)
    local server_major=$(echo "$server_version" | cut -d. -f1)
    local server_minor=$(echo "$server_version" | cut -d. -f2)

    if (( client_major < server_major )) || \
       (( client_major == server_major && client_minor < server_minor )); then
        log "WARN" "Client version is older than server version. This may cause compatibility issues."
        return 1
    fi
    return 0
}

# Count tables in database
count_tables() {
    local db_host="$1"
    local db_user="$2"
    local db_password="$3"
    export PGPASSWORD="$db_password"
    psql --host "$db_host" --username "$db_user" --dbname courtlistener \
        --tuples-only --no-align \
        --command "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "unknown"
}