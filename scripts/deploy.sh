#!/bin/bash
# =============================================================================
# SignalForge — Production Deployment Script
# =============================================================================
# Usage: ./scripts/deploy.sh
#
# This script:
#   1. Checks .env exists
#   2. Installs/updates Python dependencies
#   3. Runs database migrations
#   4. Prints instructions for starting/restarting Gunicorn
#
# --- Crontab Setup ---
# Add these entries with: crontab -e
#
#   # Daily signal scan at 06:00
#   0 6 * * * /path/to/signalforge/scripts/run_scan.sh >> /var/log/signalforge/scan.log 2>&1
#
#   # Daily briefing generation at 08:00
#   0 8 * * * /path/to/signalforge/scripts/run_briefing.sh >> /var/log/signalforge/briefing.log 2>&1
#
# Make sure to:
#   - Replace /path/to/signalforge with the actual project path
#   - Create the log directory: sudo mkdir -p /var/log/signalforge && sudo chown $USER /var/log/signalforge
#   - Ensure scripts are executable: chmod +x scripts/*.sh
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "======================================================================"
echo "  SignalForge — Deploying"
echo "======================================================================"
echo ""

# 1. Check .env exists
if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    echo -e "${RED}ERROR: .env file not found.${NC}"
    echo "Copy .env.example and configure:"
    echo "  cp .env.example .env"
    echo "  # Edit .env with production values"
    exit 1
fi
echo -e "${GREEN}✓${NC} .env file found"

# 2. Check virtual environment
if [[ ! -d "$PROJECT_ROOT/.venv" ]]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv "$PROJECT_ROOT/.venv"
fi
echo -e "${GREEN}✓${NC} Virtual environment ready"

# 3. Install/update dependencies
echo ""
echo "Installing dependencies..."
"$PROJECT_ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$PROJECT_ROOT/.venv/bin/pip" install --quiet -r "$PROJECT_ROOT/requirements.txt"
echo -e "${GREEN}✓${NC} Dependencies installed"

# 4. Run database migrations
echo ""
echo "Running database migrations..."
"$PROJECT_ROOT/.venv/bin/alembic" -c "$PROJECT_ROOT/alembic.ini" upgrade head
echo -e "${GREEN}✓${NC} Database migrations complete"

# 5. Create log directory if it doesn't exist
if [[ ! -d /var/log/signalforge ]]; then
    echo ""
    echo -e "${YELLOW}Note: /var/log/signalforge does not exist.${NC}"
    echo "Create it for cron logging:"
    echo "  sudo mkdir -p /var/log/signalforge && sudo chown \$USER /var/log/signalforge"
fi

# 6. Print start/restart instructions
echo ""
echo "======================================================================"
echo -e "${GREEN}  Deployment complete!${NC}"
echo "======================================================================"
echo ""
echo "To start Gunicorn:"
echo "  cd $PROJECT_ROOT"
echo "  .venv/bin/gunicorn app.main:app -c gunicorn.conf.py --daemon"
echo ""
echo "To restart Gunicorn (if already running):"
echo "  pkill -HUP -f 'gunicorn.*app.main:app' || true"
echo "  # Or stop and start:"
echo "  pkill -f 'gunicorn.*app.main:app' && sleep 2"
echo "  .venv/bin/gunicorn app.main:app -c gunicorn.conf.py --daemon"
echo ""
echo "To check status:"
echo "  curl -s http://localhost:8000/health | python3 -m json.tool"
echo ""

