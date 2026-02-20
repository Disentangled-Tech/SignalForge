#!/bin/bash
# =============================================================================
# SignalForge — Trigger Monthly Bias Audit (Issue #112)
# =============================================================================
# Calls the internal bias audit endpoint to analyze surfaced companies.
#
# Usage:
#   ./scripts/run_bias_audit.sh
#   ./scripts/run_bias_audit.sh 2026-02-01  # optional: report month
#
# Crontab entry (1st of month at 09:00):
#   0 9 1 * * /path/to/signalforge/scripts/run_bias_audit.sh >> /var/log/signalforge/bias_audit.log 2>&1
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
MONTH="${1:-}"

echo "[$(date -Iseconds)] Starting bias audit..."
if [[ -n "$MONTH" ]]; then
    URL="${BASE_URL}/internal/run_bias_audit?month=${MONTH}"
else
    URL="${BASE_URL}/internal/run_bias_audit"
fi

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "$URL" \
    -H "X-Internal-Token: ${INTERNAL_JOB_TOKEN}" \
    -H "Content-Type: application/json")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [[ "$HTTP_CODE" -ge 200 ]] && [[ "$HTTP_CODE" -lt 300 ]]; then
    echo "[$(date -Iseconds)] Bias audit completed successfully (HTTP $HTTP_CODE)"
    echo "$BODY"
else
    echo "[$(date -Iseconds)] ERROR: Bias audit failed (HTTP $HTTP_CODE)"
    echo "$BODY"
    exit 1
fi
