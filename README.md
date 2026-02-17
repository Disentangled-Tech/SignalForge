# SignalForge

Single-user intelligence assistant that monitors startup companies and identifies when a founder is likely to need technical leadership help.

**Pipeline:** companies → signals → analysis → scoring → briefing → outreach draft

## Tech Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x + Alembic
- PostgreSQL
- Jinja2 templates
- LLM provider abstraction

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL (installed via Homebrew on macOS)

### Quick Start

Run the setup script before working on the project (development or running the app):

```bash
./scripts/setup.sh
```

This validates and, when possible, starts:

- Python 3.11+
- Virtual environment (`.venv`)
- Dependencies (alembic, uvicorn, fastapi)
- `.env` file (creates from `.env.example` if missing)
- PostgreSQL (attempts to start via `brew services` if not running)
- Database `signalforge_dev` (creates if missing)

**Options:**

```bash
./scripts/setup.sh --dev     # Also run migrations
./scripts/setup.sh --start  # Start dev server after setup
./scripts/setup.sh --dev --start  # Migrations + start server
```

### Manual Setup

1. **Clone and enter the project**

   ```bash
   cd SignalForge
   ```

2. **Create virtual environment and install**

   ```bash
   make install
   source .venv/bin/activate
   ```

3. **Configure environment**

   ```bash
   cp .env.example .env
   # Edit .env with your DATABASE_URL, SECRET_KEY, etc.
   ```

4. **Create database**

   ```bash
   createdb signalforge_dev
   ```

5. **Run migrations**

   ```bash
   alembic upgrade head
   ```

6. **Start the server**

   ```bash
   make dev
   ```

7. **Run tests**

   ```bash
   pytest tests/ -v
   ```

## Project Structure

```
app/
├── main.py          # FastAPI app entry
├── config.py        # Configuration from env
├── prompts/         # All LLM prompts (versioned by filename)
├── api/             # API routes
├── models/          # SQLAlchemy models
├── schemas/         # Pydantic schemas
├── services/        # Business logic
├── llm/             # LLM provider abstraction
├── db/              # Database session
└── templates/       # Jinja2 templates
alembic/             # Database migrations
tests/
```

## Internal Job Endpoints

Cloudways cron will call:

- `POST /internal/run_scan`
- `POST /internal/run_briefing`

Both require the `X-Internal-Token` header matching `INTERNAL_JOB_TOKEN`.

## License

MIT
