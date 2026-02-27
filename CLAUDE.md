# SignalForge — Claude Code Guide

## Project Overview

SignalForge is a single-user intelligence assistant that monitors startup companies and identifies when founders are likely to need technical leadership help.

**Pipeline:** companies → signals → analysis → scoring → briefing → outreach draft

**Core scoring concepts:**
- **TRS (Technical Readiness Score):** Measures how ready/complex a company's tech situation is across four dimensions: Momentum (M), Complexity (C), Pressure (P), Leadership Gap (G)
- **ESL (Engagement Suitability Layer):** Modulates outreach timing — protects stressed founders, enforces cooldowns. Formula: `ESL = BE × SM × CM × AM`
- **ORE (Outreach Recommendation Engine):** Generates human-readable recommendation kits; never auto-sends
- **OutreachScore = TRS × ESL**

---

## Tech Stack

- **Language:** Python 3.11+
- **Web framework:** FastAPI + Uvicorn (dev) / Gunicorn (prod)
- **Database:** PostgreSQL, SQLAlchemy 2.x ORM, Alembic migrations, psycopg3
- **Validation:** Pydantic 2.x
- **Templates:** Jinja2 (server-rendered, no SPA)
- **LLM:** Provider-agnostic abstraction (`app/llm/`), defaults to OpenAI
- **HTTP client:** httpx (async)
- **HTML parsing:** BeautifulSoup4
- **Config:** PyYAML, python-dotenv

---

## Development Setup

```bash
./scripts/setup.sh --dev --start   # Full setup: venv, deps, migrations, server
```

Or manually:

```bash
make install                        # Create .venv, install deps
source .venv/bin/activate
cp .env.example .env                # Then fill in values
createdb signalforge_dev
alembic upgrade head
make dev                            # Start dev server (auto-reload)
```

Server runs at `http://localhost:8000`.

### Key Environment Variables

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/signalforge_dev
SECRET_KEY=...
INTERNAL_JOB_TOKEN=...
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_MODEL_REASONING=gpt-4o
```

---

## Common Commands

```bash
make dev                            # Start dev server
make test                           # Run all tests
make lint                           # Run ruff linter
make migrate                        # Create new Alembic migration
make upgrade                        # Apply migrations
make signals-daily                  # Run full daily pipeline (ingest → derive → score)
make create-company COMPANY_NAME="Acme"
make diagnose-scan COMPANY_ID=N
```

---

## Testing

```bash
pytest tests/ -v                            # All tests
pytest tests/ --cov=app --cov-report=html   # With coverage
pytest tests/test_core_derivers.py -v       # Single file
pytest tests/ -k "test_readiness" -v        # By keyword
pytest tests/ -m "not integration" -v       # Skip integration tests
pytest tests/ -p no:xdist                   # Serial (avoids DB lock issues)
```

- Tests use a `signalforge_test` database (auto-created, isolated per test via transaction rollback)
- `conftest.py` provides `db` (SessionLocal) and `client` (TestClient) fixtures
- Uses `pytest-asyncio` with `asyncio_mode="auto"`
- Markers: `@pytest.mark.integration`, `@pytest.mark.serial`
- Follow TDD: write tests first (`rules/TDD_rules.md`)

---

## Linting & Formatting

```bash
ruff check app tests                # Lint
ruff format app tests               # Format in-place
mypy app/                           # Type check
```

Config in `pyproject.toml`. Line length: 100. Target: Python 3.11. Enabled rules: E, F, I, UP, B, C4.

---

## Architecture

### Layers (bottom → top)

1. **Evidence** — Raw citations (web pages, snippets, external data)
2. **Core Events** — Structured facts (`SignalEvent` rows from adapters)
3. **Core Signals** — Derived signals (`SignalInstance`, core taxonomy signal IDs)
4. **Scoring / ESL** — Pack-weighted interpretation (`ReadinessSnapshot`, `EngagementSnapshot`)
5. **Outreach** — Prompt-driven recommendation kits (ORE output)

### Core vs Pack Responsibilities

- **Core** (`app/core_taxonomy/`, `app/core_derivers/`): canonical `signal_id` taxonomy, derivers. Deterministic, pack-agnostic. Derives signals from events.
- **Packs** (`/packs/{pack_name}/`): scoring weights, ESL rubric, playbooks, prompts. Pack-specific interpretation. **Not executed at runtime** — only schema-validated.
- Runtime derive stage uses **core derivers only**.

### Pack System

- **v1 schema**: Full config (taxonomy, scoring, ESL, derivers, playbooks) — `packs/fractional_cto_v1/`
- **v2 schema**: Minimal (scoring, ESL, playbooks, prompt_bundles); relies on core taxonomy + core derivers — `packs/example_v2/`
- Pack loader: `app/packs/loader.py`
- Validation CI: `.github/workflows/pack-validation.yml`

### Signal Derivation Types

- **Passthrough:** `event_type` → `signal_id` (1:1 mapping)
- **Pattern:** Regex on title/summary → `signal_id` (text matching, max 500 chars per ADR-008)
- Evidence tracked via `SignalInstance.evidence_event_ids` (JSONB list of source `SignalEvent` IDs)

### TRS Dimensions

| Dim | Name | Examples |
|-----|------|---------|
| M | Momentum | Funding raised, hiring surge, product launches |
| C | Complexity | APIs, AI features, enterprise requirements |
| P | Pressure | Enterprise customers, regulatory deadlines |
| G | Leadership Gap | CTO role posted, no CTO detected, fractional requests |

### ESL Components

- **BE (Base Engageability)** = TRS / 100
- **SM (Stability Modifier)** = 1 − (weights × stress indices); high stress → lower outreach
- **CM (Cadence Modifier)** = cooldown after recent outreach
- **AM (Alignment Modifier)** = founder mission alignment
- **Cap:** If SM < 0.7 → recommendation capped at "Soft Value Share" (protects stressed founders)

### Recommendation Categories

Observe Only → Soft Value Share → Low-Pressure Intro → Standard Outreach → Direct Strategic Outreach

---

## Key Directories

```
app/
├── api/            # Route handlers (one file per endpoint group)
├── models/         # SQLAlchemy ORM (one model per file)
├── schemas/        # Pydantic schemas (CompanyRead, CompanyCreate, scout EvidenceBundle, etc.)
├── services/       # Business logic (readiness/, esl/, ore/, ingestion/, etc.)
├── ingestion/      # Data adapters (crunchbase, producthunt, github, etc.)
├── scout/          # LLM Discovery Scout — source allowlist/denylist, evidence-only (no ingest/event writes)
├── core_derivers/  # Core signal derivation engine + YAML config
├── core_taxonomy/  # Canonical signal_id taxonomy
├── packs/          # Pack loader and schema validation
├── prompts/        # LLM prompt templates (versioned by filename)
├── templates/      # Jinja2 HTML templates
├── llm/            # LLM provider abstraction
└── db/             # SQLAlchemy engine, session factory

packs/              # Pack configuration directories
alembic/            # Database migrations
tests/              # Pytest test suite (~100 files)
scripts/            # CLI utilities
rules/              # ADRs, TDD rules, design docs
docs/               # Comprehensive documentation
```

---

## Database Patterns

- **Upsert by unique constraint** (e.g., `(company_id, as_of)` for `ReadinessSnapshot`)
- **Timestamps:** UTC-aware columns everywhere
- **JSONB:** Flexible payloads (explain, raw LLM responses, `evidence_event_ids`)
- **Cascade strategies:** SET NULL or CASCADE depending on entity relationship
- **Idempotency:** All pipeline stages designed to be safe to re-run

---

## API Patterns

- **Internal endpoints:** `/internal/run_*` — require `X-Internal-Token` header
- **Public endpoints:** `/api/*` — user-facing operations
- **Views:** `/` routes — server-rendered HTML via Jinja2

---

## Naming Conventions

| Item | Convention | Example |
|------|------------|---------|
| DB tables | snake_case | `readiness_snapshots` |
| ORM models | PascalCase | `ReadinessSnapshot` |
| Pydantic schemas | PascalCase + suffix | `CompanyRead`, `CompanyCreate` |
| Functions | snake_case | `compute_readiness` |
| Constants | UPPER_SNAKE_CASE | `BASE_SCORES_MOMENTUM` |

---

## Ethical Design Guardrails

- **No automatic outreach** — human always reviews before anything is sent
- **No neurodivergence inference** — never infer or store neurodivergent status
- **No urgency exploitation** — ESL brakes on stressed founders
- **Cooldown enforcement** — Cadence Modifier prevents harassment
- **Bias auditing** — monthly bias check for demographic skew
- **Explainability** — all scores include detailed reasoning

---

## Key Documentation

| File | Purpose |
|------|---------|
| `README.md` | Project overview and quick start |
| `docs/GLOSSARY.md` | Acronyms (TRS, ESL, ORE, SM, BE, CM, AM, etc.) |
| `docs/pipeline.md` | Pipeline stages with API endpoints; Scout as separate flow |
| `docs/discovery_scout.md` | LLM Discovery Scout (Evidence-Only): inputs, output schema, no entity writes |
| `docs/deriver-engine.md` | Deriver types, validation, evidence tracking |
| `docs/v2PRD.md` | v2 product requirements |
| `docs/signal-models.md` | Database schema and relationships |
| `rules/TDD_rules.md` | TDD guidelines |
| `rules/ADR-*.md` | Architecture Decision Records (1–9) |
| `rules/CORE_VS_PACK_RESPONSIBILITIES.md` | Core vs Pack boundary |
