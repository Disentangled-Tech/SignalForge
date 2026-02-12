#!/usr/bin/env bash
# SignalForge project setup and validation script
# Run from project root before development or running the app.
# Usage: ./scripts/setup.sh [--dev] [--start]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

log_ok()    { echo -e "${GREEN}✓${NC} $1"; }
log_warn()  { echo -e "${YELLOW}⚠${NC} $1"; WARNINGS=$((WARNINGS + 1)); }
log_fail()  { echo -e "${RED}✗${NC} $1"; ERRORS=$((ERRORS + 1)); }
log_info()  { echo -e "  $1"; }

# Parse flags
MODE_DEV=false
START_SERVER=false
for arg in "$@"; do
  case $arg in
    --dev)   MODE_DEV=true ;;
    --start) START_SERVER=true ;;
    --help|-h)
      echo "SignalForge setup script"
      echo ""
      echo "Usage: ./scripts/setup.sh [options]"
      echo ""
      echo "Options:"
      echo "  --dev     Development mode: also run migrations"
      echo "  --start   Start the dev server after setup"
      echo "  --help    Show this help"
      exit 0
      ;;
  esac
done

echo "======================================================================"
echo "  SignalForge — Validating environment"
echo "======================================================================"
echo ""

# Load .env early for PostgreSQL connection params
PG_HOST="${PGHOST:-localhost}"
PG_PORT="${PGPORT:-5432}"
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$PROJECT_ROOT/.env"
  set +a
  [[ -n "$PGHOST" ]] && PG_HOST="$PGHOST"
  [[ -n "$PGPORT" ]] && PG_PORT="$PGPORT"
  # Parse port from DATABASE_URL if present (postgresql://user:pass@host:port/db)
  if [[ -n "$DATABASE_URL" ]]; then
    parsed_port=$(echo "$DATABASE_URL" | sed -n 's|.*@[^:]*:\([0-9]*\)/.*|\1|p')
    [[ -n "$parsed_port" ]] && PG_PORT="$parsed_port"
    parsed_host=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):[0-9]*/.*|\1|p')
    [[ -n "$parsed_host" ]] && PG_HOST="$parsed_host"
  fi
fi

# ---------------------------------------------------------------------------
# 1. Python 3.11+
# ---------------------------------------------------------------------------
check_python() {
  if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0")
    MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    if [[ "$MAJOR" -ge 3 ]] && [[ "$MINOR" -ge 11 ]]; then
      log_ok "Python $PYTHON_VERSION (>= 3.11)"
    else
      log_fail "Python 3.11+ required (found $PYTHON_VERSION)"
    fi
  else
    log_fail "Python 3 not found. Install with: brew install python@3.11"
  fi
}

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
check_venv() {
  if [[ -d "$PROJECT_ROOT/.venv" ]]; then
    log_ok "Virtual environment (.venv) exists"
    VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
    VENV_PIP="$PROJECT_ROOT/.venv/bin/pip"
    return 0
  else
    log_warn "Virtual environment not found"
    log_info "Run: make install"
    log_info "  or: python3 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 3. Dependencies (alembic, uvicorn, etc.)
# ---------------------------------------------------------------------------
check_deps() {
  if [[ -n "$VENV_PIP" ]] && [[ -x "$VENV_PIP" ]]; then
    if "$VENV_PIP" show alembic &>/dev/null && \
       "$VENV_PIP" show uvicorn &>/dev/null && \
       "$VENV_PIP" show fastapi &>/dev/null; then
      log_ok "Required packages installed (alembic, uvicorn, fastapi)"
    else
      log_fail "Missing dependencies. Run: .venv/bin/pip install -e \".[dev]\""
    fi
  else
    log_warn "Skipping dependency check (no venv)"
  fi
}

# ---------------------------------------------------------------------------
# 4. .env file
# ---------------------------------------------------------------------------
check_env() {
  if [[ -f "$PROJECT_ROOT/.env" ]]; then
    log_ok ".env file exists"
  elif [[ -f "$PROJECT_ROOT/.env.example" ]]; then
    log_warn ".env not found"
    cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
    log_ok "Created .env from .env.example"
    log_info "Edit .env with DATABASE_URL, SECRET_KEY, etc."
  else
    log_fail ".env.example not found"
  fi
}

# ---------------------------------------------------------------------------
# 5. PostgreSQL
# ---------------------------------------------------------------------------
check_postgres() {
  if ! command -v pg_isready &>/dev/null; then
    log_fail "pg_isready not found. Install PostgreSQL: brew install postgresql"
    return 1
  fi

  # Try TCP first (host:port from .env or default localhost:5432)
  if pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null; then
    log_ok "PostgreSQL is running (${PG_HOST}:${PG_PORT})"
    return 0
  fi

  # Try default connection (Unix socket / env); often works when TCP fails w/ Homebrew
  if pg_isready -q 2>/dev/null; then
    log_ok "PostgreSQL is running (default connection)"
    return 0
  fi

  # PostgreSQL not reachable — try to start/restart it
  log_warn "PostgreSQL not reachable at ${PG_HOST}:${PG_PORT}"

  if [[ "$(uname)" == "Darwin" ]]; then
    if command -v brew &>/dev/null; then
      for svc in postgresql@16 postgresql@15 postgresql@14 postgresql; do
        if brew services list 2>/dev/null | grep -q "$svc"; then
          # Use restart if service exists — often fixes "already started" but stuck
          log_info "Restarting PostgreSQL: brew services restart $svc"
          if brew services restart "$svc" 2>/dev/null; then
            sleep 4
            if pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null || pg_isready -q 2>/dev/null; then
              log_ok "PostgreSQL started"
              return 0
            fi
          fi
        fi
      done
    fi
    log_info "If PostgreSQL still fails: brew services restart postgresql@16"
    log_info "Or remove stale PID: rm -f $(brew --prefix 2>/dev/null)/var/postgresql@*/postmaster.pid"
  elif [[ "$(uname)" == "Linux" ]]; then
    if command -v systemctl &>/dev/null; then
      for svc in postgresql postgresql-16 postgresql-15 postgresql-14; do
        if systemctl list-units --type=service --all 2>/dev/null | grep -q "$svc"; then
          log_info "Starting PostgreSQL: sudo systemctl start $svc"
          if sudo systemctl start "$svc" 2>/dev/null; then
            sleep 4
            if pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null; then
              log_ok "PostgreSQL started"
              return 0
            fi
          fi
        fi
      done
    fi
    log_info "Start PostgreSQL manually: sudo systemctl start postgresql"
  fi

  log_fail "PostgreSQL must be running. Install: brew install postgresql"
  return 1
}

# ---------------------------------------------------------------------------
# 6. Database exists
# ---------------------------------------------------------------------------
check_database() {
  # Load .env to get DATABASE_URL if available
  if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
  fi

  DB_NAME="${PGDATABASE:-signalforge_dev}"
  if [[ -n "$DATABASE_URL" ]]; then
    # Extract db name from postgresql://user:pass@host:port/dbname
    parse_db=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^/?]*\).*|\1|p')
    [[ -n "$parse_db" ]] && DB_NAME="$parse_db"
  fi

  if ! command -v psql &>/dev/null && ! command -v createdb &>/dev/null; then
    log_warn "psql/createdb not found — cannot verify database"
    return 1
  fi

  # Try to list databases (works with current user or postgres)
  if psql -h "$PG_HOST" -p "$PG_PORT" -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    log_ok "Database '$DB_NAME' exists"
    return 0
  fi
  if psql -h "$PG_HOST" -p "$PG_PORT" -U postgres -lqt 2>/dev/null | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    log_ok "Database '$DB_NAME' exists"
    return 0
  fi

  # Database doesn't exist — try to create it
  log_warn "Database '$DB_NAME' not found"
  if command -v createdb &>/dev/null; then
    if createdb -h "$PG_HOST" -p "$PG_PORT" "$DB_NAME" 2>/dev/null; then
      log_ok "Created database '$DB_NAME'"
      return 0
    fi
    if createdb -h "$PG_HOST" -p "$PG_PORT" -U postgres "$DB_NAME" 2>/dev/null; then
      log_ok "Created database '$DB_NAME'"
      return 0
    fi
  fi
  log_info "Create manually: createdb $DB_NAME"
  return 1
}

# ---------------------------------------------------------------------------
# 7. Alembic migrations (dev mode)
# ---------------------------------------------------------------------------
run_migrations() {
  if [[ "$MODE_DEV" != "true" ]]; then
    return 0
  fi
  if [[ -x "$PROJECT_ROOT/.venv/bin/alembic" ]]; then
    log_info "Running migrations: alembic upgrade head"
    if (cd "$PROJECT_ROOT" && .venv/bin/alembic -c alembic.ini upgrade head 2>/dev/null); then
      log_ok "Migrations up to date"
    else
      log_fail "Migration failed. Check alembic.ini and DATABASE_URL"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Run all checks
# ---------------------------------------------------------------------------
check_python
check_venv
check_deps
check_env
check_postgres
check_database
run_migrations

echo ""
echo "----------------------------------------------------------------------"

if [[ $ERRORS -gt 0 ]]; then
  echo -e "${RED}Setup incomplete: $ERRORS error(s)${NC}"
  [[ $WARNINGS -gt 0 ]] && echo -e "${YELLOW}$WARNINGS warning(s)${NC}"
  echo ""
  echo "Fix the errors above, then run this script again."
  exit 1
fi

if [[ $WARNINGS -gt 0 ]]; then
  echo -e "${YELLOW}Setup OK with $WARNINGS warning(s)${NC}"
else
  echo -e "${GREEN}All checks passed. Ready to work.${NC}"
fi

echo ""

if [[ "$START_SERVER" == "true" ]]; then
  echo "Starting development server..."
  exec "$PROJECT_ROOT/.venv/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000
else
  echo "Next steps:"
  echo "  source .venv/bin/activate"
  echo "  make dev          # Start development server"
  echo "  make test        # Run tests"
  echo ""
  echo "Or run with --start to start the server after setup:"
  echo "  ./scripts/setup.sh --dev --start"
fi
