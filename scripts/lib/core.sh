#!/bin/bash
# core.sh - Shared Core functionality for bulk data pipeline
# Handles configuration, preflight checks, and database operations

# Source UI components
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$SCRIPT_DIR/lib/ui.sh"

