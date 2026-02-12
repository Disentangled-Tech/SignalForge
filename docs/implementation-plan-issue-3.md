# Implementation Plan: GitHub Issue #3 — Alembic Migrations

**Issue**: [Alembic migrations](https://github.com/Disentangled-Tech/SignalForge/issues/3)  
**Tasks**: Initialize Alembic, Wire to models Base, Create first empty migration  
**Acceptance Criteria**: `alembic upgrade head` works; Tables created successfully

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Alembic initialization | Done | `alembic/`, `alembic.ini` |
| env.py + Base wiring | Partial — uses `Base.metadata` only | `alembic/env.py` |
| Model imports in env | **Missing** — commented out | `alembic/env.py` |
| SQLAlchemy models | **Empty** — no models defined | `app/models/` |
| First migration | Exists but empty (no tables) | `alembic/versions/001_initial.py` |

---

## Gap Analysis

1. **Alembic is initialized** — `alembic.ini`, `alembic/env.py`, `alembic/versions/001_initial.py` exist.
2. **Base is wired** — `target_metadata = Base.metadata` in env.py.
3. **Models are not imported** — `# from app.models import Company, SignalRecord, JobRun, etc.` is commented; `app.models` is empty.
4. **001_initial.py creates no tables** — `upgrade()` and `downgrade()` use `pass`.

To satisfy "Tables created successfully", we must define models and create a migration that creates those tables.

---

## Implementation Tasks

### 1. Define Core SQLAlchemy Models

**Goal**: Create minimal models required for the pipeline and internal job endpoints.

**File**: `app/models/__init__.py` → refactor into separate modules or single file.

**Recommended minimal schema** (aligned with PRD and pipeline):

| Model | Purpose |
|-------|---------|
| `Company` | Companies user adds; link for signals, analysis, briefing |
| `SignalRecord` | Scraped content from company sites; deduplicated by content hash |
| `JobRun` | Records for internal job endpoints (`/internal/scan`, `/internal/briefing`) |

**Company** (minimal fields for V1):

- `id` (PK)
- `name`, `website_url`, `founder_name`, `notes` (nullable)
- `cto_need_score` (int, nullable)
- `created_at`, `updated_at`
- `last_scan_at` (nullable)

**SignalRecord**:

- `id` (PK)
- `company_id` (FK)
- `source_url`, `content_hash`, `content_text`
- `created_at`

**JobRun**:

- `id` (PK)
- `job_type` (e.g. `"scan"`, `"briefing"`)
- `status` (e.g. `"running"`, `"success"`, `"failure"`)
- `started_at`, `finished_at` (nullable)
- `companies_processed` (int, nullable)
- `error_message` (nullable)

**Reference**: CURSOR_PRD.md pipeline, `job_runs` table, stage/pain/outreach rules.

---

### 2. Wire Models to Alembic

**Goal**: Ensure Alembic sees all model metadata for autogenerate and migrations.

**File**: `alembic/env.py`

**Changes**:

```python
# Import models so Alembic can detect them
from app.models import Company, SignalRecord, JobRun  # noqa: F401

target_metadata = Base.metadata
```

Ensure models inherit from `Base` and are imported before `target_metadata` is used.

---

### 3. Create Migration with Tables

**Goal**: Replace empty 001 migration with one that creates the core tables.

**Options**:

- **Option A**: Replace `001_initial.py` — edit upgrade/downgrade to `op.create_table` / `op.drop_table`.
- **Option B**: Add `002_create_core_tables.py` — keep 001 as placeholder, add new migration.

**Recommendation**: Option B — keeps migration history clean; 001 stays as "initial" placeholder; 002 creates tables.

**File**: `alembic/versions/002_create_core_tables.py` (autogenerate or manual)

**Migration content** (manual approach):

- `upgrade()`: `op.create_table` for `companies`, `signal_records`, `job_runs` with correct columns and FKs.
- `downgrade()`: `op.drop_table` in reverse order (respect FK dependencies).

**Autogenerate approach**:

```bash
alembic revision --autogenerate -m "create core tables"
```

Then review and fix any issues (e.g. indexes, constraints).

---

### 4. Verify `alembic upgrade head` Works

**Goal**: Migrations run successfully and tables exist.

**Steps**:

1. `alembic upgrade head` — no errors.
2. `alembic downgrade base` — no errors.
3. `alembic upgrade head` — idempotent.
4. Inspect DB: `\dt` in psql or `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';`

---

## Test Strategy (TDD)

### Unit / Integration Tests

**File**: `tests/test_migrations.py` (new)

- [ ] `test_alembic_upgrade_head_succeeds` — run `alembic upgrade head` in subprocess; assert exit 0.
- [ ] `test_tables_exist_after_migration` — after upgrade, query `information_schema.tables` or use SQLAlchemy `inspector.get_table_names()`.
- [ ] `test_alembic_downgrade_base_succeeds` — run `alembic downgrade base`; assert exit 0.
- [ ] `test_downgrade_removes_tables` — after downgrade, assert core tables are gone.

**File**: `tests/test_models.py` (new)

- [ ] `test_company_model_creation` — create Company instance; assert attributes.
- [ ] `test_signal_record_model_creation` — create SignalRecord with company_id; assert FK.
- [ ] `test_job_run_model_creation` — create JobRun; assert attributes.

**Conftest**:

- Use test DB (`signalforge_test`) for migration tests; ensure clean state (e.g. `alembic downgrade base` before upgrade in test).

---

## Implementation Order

1. **Define models** — `app/models/company.py`, `signal_record.py`, `job_run.py` (or single `app/models/__init__.py`).
2. **Wire models in env.py** — import models in `alembic/env.py`.
3. **Autogenerate migration** — `alembic revision --autogenerate -m "create core tables"`.
4. **Review and fix migration** — ensure correct types, FKs, indexes.
5. **Write tests** — migration tests, model tests.
6. **Verify** — `alembic upgrade head`, `alembic downgrade base` locally.

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Migrations run on clean DB | Tables created |
| Migrations run on DB with existing tables | Idempotent or clear conflict (e.g. duplicate migration) |
| Downgrade from head | Tables dropped |
| psycopg driver in URL | env.py uses `settings.database_url`; ensure `postgresql+psycopg://` in test env |

---

## Security & Privacy Notes

- No credentials in migration files.
- No PII in migration script content.
- Use parameterized / safe identifiers; avoid user input in raw SQL.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `app/models/company.py` | Create — Company model |
| `app/models/signal_record.py` | Create — SignalRecord model |
| `app/models/job_run.py` | Create — JobRun model |
| `app/models/__init__.py` | Update — export models |
| `alembic/env.py` | Update — import models |
| `alembic/versions/002_create_core_tables.py` | Create — migration |
| `tests/test_migrations.py` | Create — migration tests |
| `tests/test_models.py` | Create — model tests |

---

## Acceptance Criteria Checklist

- [x] `alembic upgrade head` works
- [x] Tables created successfully (`companies`, `signal_records`, `job_runs`)
- [x] `alembic downgrade base` works
- [x] Tests pass
