# Implementation Plan: GitHub Issue #2 — Database Connectivity

**Issue**: Configure SQLAlchemy 2.x engine, session dependency, and test DB connection at startup  
**Acceptance Criteria**: App fails fast if DB unreachable; `/health` confirms DB connectivity

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| SQLAlchemy engine | Partial — basic `create_engine` exists | `app/db/session.py` |
| Session dependency | Exists — `get_db()` generator | `app/db/session.py` |
| Startup DB test | **Missing** | — |
| Health endpoint | Basic — no DB check | `app/main.py` |
| Fail-fast on startup | **Missing** | — |

---

## Implementation Tasks

### 1. Configure SQLAlchemy 2.x Engine

**Goal**: Ensure engine is properly configured for SQLAlchemy 2.x with production-ready settings.

**File**: `app/db/session.py`

**Changes**:
- Keep `pool_pre_ping=True` (already present) — validates connections before use
- Add explicit pool configuration:
  - `pool_size` — default 5
  - `max_overflow` — default 10
  - `pool_timeout` — optional, for connection acquisition
- Add `future=True` if using legacy `create_engine` (SQLAlchemy 2.x uses this by default in 2.0+)
- Ensure `Base` uses `DeclarativeBase` (SQLAlchemy 2.0 style) — current `declarative_base()` is deprecated in favor of `DeclarativeBase`
- Optionally add `connect_args` for PostgreSQL-specific options (e.g., `connect_timeout`)

**Reference**: [SQLAlchemy 2.0 Engine Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html)

---

### 2. Session Dependency

**Goal**: Ensure `get_db` is the canonical FastAPI dependency for database sessions.

**File**: `app/db/session.py`

**Changes**:
- Keep existing `get_db()` — already correct
- Export `get_db` from `app/db/__init__.py` for clean imports
- Document usage: `Depends(get_db)` in route handlers

**File**: `app/db/__init__.py`

**Changes**:
```python
from app.db.session import Base, get_db, SessionLocal, engine

__all__ = ["Base", "get_db", "SessionLocal", "engine"]
```

**Usage example** (for future routes):
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db import get_db

@app.get("/something")
def route(db: Session = Depends(get_db)):
    ...
```

---

### 3. Test DB Connection at Startup

**Goal**: App fails fast if database is unreachable — do not start serving if DB is down.

**File**: `app/db/session.py`

**Add function**:
```python
from sqlalchemy import text

def check_db_connection() -> None:
    """
    Verify database connectivity. Raises if unreachable.
    Call during application startup.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
```

**File**: `app/main.py`

**Changes**:
- Import `check_db_connection` from `app.db.session`
- In `lifespan` startup phase:
  - Call `check_db_connection()` before yielding
  - If it raises, lifespan fails → FastAPI does not start serving
  - Log success/failure

**Lifespan flow**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SignalForge starting")
    try:
        check_db_connection()
        logger.info("Database connection verified")
    except Exception as e:
        logger.critical("Database unreachable: %s", e)
        raise  # Fail fast — do not start
    yield
    ...
```

**Note**: `check_db_connection` must use synchronous `engine.connect()`; FastAPI lifespan supports sync code. For async-compatible approach, consider `asyncio.to_thread()` if needed.

---

### 4. Update `/health` to Confirm DB Connectivity

**Goal**: `/health` returns DB status so load balancers and operators can verify full stack health.

**File**: `app/main.py`

**Changes**:
- Add a `Depends(get_db)` or inline health check that executes `SELECT 1` via DB
- Return JSON:
  - `status`: `"ok"` if DB reachable, `"degraded"` or `"unhealthy"` if not
  - `version`: app version
  - `database`: `"connected"` or `"disconnected"`

**Options**:
- **Option A**: Inject `get_db` into health route — if DB fails, dependency raises → 500
- **Option B**: Use `engine.connect()` directly in health handler — catch exceptions, return 503 with `database: "disconnected"`

**Recommendation**: Option B — health should return 200 with `database: "connected"` when healthy, and 503 with `database: "disconnected"` when DB is down. This allows load balancers to distinguish "app up, DB down" from "app down".

**Response shape**:
```python
{
    "status": "ok",
    "version": "0.1.0",
    "database": "connected"
}
```

On DB failure:
```python
{
    "status": "unhealthy",
    "version": "0.1.0",
    "database": "disconnected"
}
```
HTTP status: 503

---

## Test Strategy (TDD)

### Unit / Integration Tests

**File**: `tests/test_health.py`

- [ ] `test_health_returns_ok_when_db_connected` — 200, `status: "ok"`, `database: "connected"`
- [ ] `test_health_returns_503_when_db_unreachable` — mock/patch engine to raise, assert 503 and `database: "disconnected"`

**File**: `tests/test_db_startup.py` (new)

- [ ] `test_app_fails_to_start_when_db_unreachable` — override `check_db_connection` or DATABASE_URL to invalid value, assert `TestClient` or app startup raises

**File**: `tests/conftest.py`

- [ ] `client` fixture — ensure DB is reachable (or use `pytest-docker` / SQLite for isolated tests)
- [ ] Add `client_no_db` fixture — app configured with unreachable DB for fail-fast tests (may require lazy engine creation)

---

## Implementation Order

1. **Create `check_db_connection()`** — `app/db/session.py`
2. **Add startup check in lifespan** — `app/main.py` (fail fast)
3. **Update `/health`** — add DB check, return `database` field
4. **Upgrade SQLAlchemy engine config** — pool settings, `DeclarativeBase` if desired
5. **Export `get_db`** — `app/db/__init__.py`
6. **Write tests** — TDD: tests first, then implement; or adjust tests to match new behavior

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| DB down at startup | App raises, never serves; Uvicorn exits non-zero |
| DB down after startup | `/health` returns 503, `database: "disconnected"` |
| DB slow at startup | `check_db_connection` should timeout; consider `connect_args={"connect_timeout": 5}` |
| Invalid DATABASE_URL | Startup fails when `check_db_connection` raises |

---

## Security & Privacy Notes

- No credentials in logs — log only "Database unreachable" or generic message, not connection strings
- `pool_pre_ping` helps prevent stale connections from leaking
- Health endpoint should not expose internal details (e.g., full error messages) in production

---

## Files to Modify

| File | Action |
|------|--------|
| `app/db/session.py` | Add `check_db_connection`, enhance engine config |
| `app/db/__init__.py` | Export `get_db`, `engine` |
| `app/main.py` | Lifespan startup check, update `/health` |
| `tests/test_health.py` | Update for new health response schema |
| `tests/test_db_startup.py` | New file — fail-fast tests |

---

## Additional Details the Issue Glosses Over

Recommendations for gaps and considerations beyond the bare acceptance criteria:

### 1. Connection Timeout

The issue does not specify how long to wait for DB before failing. Without a timeout, a misconfigured or unreachable host can hang indefinitely.

**Recommendation**: Add `connect_timeout` via `connect_args` in the engine (e.g., 5–10 seconds). Consider making it configurable via `DB_CONNECT_TIMEOUT` env var.

---

### 2. Startup Retries

Should the app retry the DB connection a few times before failing? In containerized or orchestrated environments, the DB may start a few seconds after the app.

**Recommendation**: For V1, fail immediately (simplicity rule). If operational experience shows flaky startup, add a short retry loop (e.g., 3 attempts, 2s apart) as a follow-up.

---

### 3. Liveness vs Readiness

The issue mentions only `/health`. Orchestrators (k8s, Cloud Run) often distinguish:

- **Liveness** — Is the process alive? (simple ping)
- **Readiness** — Is the app ready to serve traffic? (includes DB)

**Recommendation**: Use a single `/health` that includes DB check (readiness). If you later need a cheap liveness probe, add `/health/live` that returns 200 without a DB query.

---

### 4. Graceful Shutdown

The issue does not mention closing the connection pool on shutdown.

**Recommendation**: In lifespan shutdown phase, call `engine.dispose()` to cleanly close connections. Prevents connection leaks and helps DB resources.

---

### 5. Test Harness Impact

Fail-fast at startup means importing `app.main` or creating `TestClient(app)` will trigger the DB check. If the test DB is unreachable, all tests fail at import.

**Recommendation**: Either:
- Require a real Postgres test DB (e.g., via `make test-db` or CI) and document it, or
- Use lazy engine creation (e.g., `get_engine()` that builds on first use) so tests can patch `DATABASE_URL` before engine creation, or
- Add a `SKIP_DB_CHECK` env var for tests only (acceptable if strictly test-scoped and never in production)

---

### 6. Migration State

The issue does not ask whether startup should verify schema/migrations.

**Recommendation**: For V1, do not add migration checks at startup. Keep startup focused on connectivity. Run migrations separately (e.g., `alembic upgrade head` before `uvicorn`). If a table is missing, the first query will fail with a clear error.

---

### 7. PostgreSQL SSL

Production Postgres often requires `sslmode=require` or `sslmode=verify-full`.

**Recommendation**: Document that `DATABASE_URL` can include `?sslmode=require`. Consider `DB_SSL_MODE` env var if you want to append it without exposing full URLs in config.

---

### 8. Health Endpoint Dependencies

If health uses `Depends(get_db)`, it acquires a session from the pool. If health uses `engine.connect()` directly, it creates a new connection. Both validate reachability; `engine.connect()` is slightly more isolated.

**Recommendation**: Use `engine.connect()` directly in the health handler (as in Option B). Avoids session overhead and keeps health logic simple.

---

### 9. Logging on Failure

What to log when DB is unreachable: full exception, message only, or nothing?

**Recommendation**: Log `logger.critical("Database unreachable: %s", e)` with the exception message only. Never log `DATABASE_URL` or credentials. Consider redacting host/port in production if it reveals topology.

---

### 10. Environment-Specific Behavior

Should local dev be allowed to start without a DB (e.g., for frontend-only work)?

**Recommendation**: Keep fail-fast everywhere for consistency. Developers can run Postgres via Docker or `brew services`. Document `docker-compose up -d postgres` or equivalent in README.

---

## Acceptance Criteria Checklist

- [ ] **App fails fast if DB unreachable** — startup raises, app does not serve
- [ ] **`/health` confirms DB connectivity** — returns `database: "connected"` when healthy, 503 when not
