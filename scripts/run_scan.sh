#!/bin/bash
# =============================================================================
# SignalForge — Trigger Daily Signal Scan
# =============================================================================
# Calls the internal scan endpoint to collect signals for all companies.
#
# Usage:
#   ./scripts/run_scan.sh
#
# Crontab entry (daily at 06:00):
#   0 6 * * * /path/to/signalforge/scripts/run_scan.sh >> /var/log/signalforge/scan.log 2>&1
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load token from .env if not already in environment
if [[ -z "$INTERNAL_JOB_TOKEN" ]] && [[ -f "$PROJECT_ROOT/.env" ]]; then
    INTERNAL_JOB_TOKEN=$(grep -E '^INTERNAL_JOB_TOKEN=' "$PROJECT_ROOT/.env" | cut -d'=' -f2-)
fi

if [[ -z "$INTERNAL_JOB_TOKEN" ]]; then
    echo "[$(date -Iseconds)] ERROR: INTERNAL_JOB_TOKEN not set. Check .env or environment."
    exit 1
fi

BASE_URL="${SIGNALFORGE_URL:-http://localhost:8000}"

echo "[$(date -Iseconds)] Starting signal scan..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "${BASE_URL}/internal/run_scan" \
    -H "X-Internal-Token: ${INTERNAL_JOB_TOKEN}" \
    -H "Content-Type: application/json")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [[ "$HTTP_CODE" -ge 200 ]] && [[ "$HTTP_CODE" -lt 300 ]]; then
    echo "[$(date -Iseconds)] Scan completed successfully (HTTP $HTTP_CODE)"
    echo "$BODY"
else
    echo "[$(date -Iseconds)] ERROR: Scan failed (HTTP $HTTP_CODE)"
    echo "$BODY"
    exit 1
fi

