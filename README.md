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

   If migrations are not applied, some features (e.g. company delete) may return 500 due to schema mismatch (e.g. `outreach_recommendations` columns added in Issue #123).

6. **Start the server**

   ```bash
   make dev
   ```

   If you run the app in the same terminal after `pytest`, it may inherit `DATABASE_URL=signalforge_test`. Use a fresh shell or `unset DATABASE_URL` before starting the app to ensure you connect to `signalforge_dev`.

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

**Event-driven pipeline** (ingest → derive → score → update_lead_feed): see [docs/pipeline.md](docs/pipeline.md). Changing a workspace's active pack only reloads analysis config (no re-derive or re-ingest); see [Pack selection](docs/pipeline.md#pack-selection) and [GLOSSARY](docs/GLOSSARY.md).

## Documentation

### User-facing

| Doc | Description |
| --- | --- |
| [docs/USER_ONBOARDING.md](docs/USER_ONBOARDING.md) | Quick start: login, add/import companies, briefing, record outreach |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Full user guide: onboarding, concepts, task-based tutorials |

### Technical

| Doc | Description |
| --- | --- |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Glossary of acronyms (ESL, ORE, TRS, ADR, etc.) |
| [docs/pipeline.md](docs/pipeline.md) | Pipeline stages (ingest, derive, score, update_lead_feed) and API behavior |
| [docs/deriver-engine.md](docs/deriver-engine.md) | Deriver engine: passthrough and pattern derivers, evidence, logging |
| [docs/adapter-interface.md](docs/adapter-interface.md) | Ingestion adapter contract and RawEvent schema |

## License

NONE

## Architecture Overview — Ethical Inflection Intelligence System (v2)

🔗 PART 1 — Dependency Graph (Execution Order + Blocking)

Below is the realistic build order, including which issues block others.

I’ll use the updated epic structure:
	•	EPIC A — TRS Foundation
	•	EPIC B — Engagement Suitability Layer
	•	EPIC C — Outreach Governance
	•	EPIC D — Safeguards & Bias Monitoring
	•	EPIC E — Calibration

⸻

🧱 Phase 1 — TRS Foundation (Must Exist First)

A1 — TRS Snapshot Pipeline

Blocks: B3, C1, C3, D3

You cannot compute ESL without TRS snapshots.

⸻

🧠 Phase 2 — ESL Foundation

B1 — ESL Schema

Blocks: B2, B3, C1, C2

Tables required:
	•	engagement_snapshots
	•	outreach_history
	•	alignment metadata

⸻

B2 — ESL Core Engine

Blocks: B3, C1, D1

You must compute ESL before integrating into jobs or enforcing caps.

⸻

B3 — Integrate ESL Into Nightly Job

Blocks: C1, C3, D2

Now OutreachScore exists.

⸻

🛡 Phase 3 — Governance Layer

C1 — Weekly Outreach Review Endpoint

Blocks: none
Depends on: B3

⸻

C2 — Cooldown Enforcement

Depends on: B1
Independent of C1

⸻

C3 — Modify Daily Briefing

Depends on: B3
Should follow C1 for ranking logic consistency

⸻

🧭 Phase 4 — Safeguards

D1 — Stability Cap Enforcement

Depends on: B2

⸻

D2 — Monthly Bias Audit Job

Depends on: B3
Needs OutreachScore output.

⸻

D3 — Quiet Signal Amplification

Depends on: A1
Should occur before serious calibration.

⸻

📈 Phase 5 — Calibration

E1 — Track Outreach Outcomes

Depends on: C2
Optional for first release.

⸻

🗺 Visual Flow (Condensed)

A1 → B1 → B2 → B3 → C1 → C3
             ↓
             D1
B1 → C2
B3 → D2
A1 → D3
C2 → E1


⸻

🔄 Recommended Implementation Order (Practical)
	1.	A1 — Finalize TRS snapshot stability
	2.	B1 — Add ESL schema
	3.	B2 — Implement ESL engine
	4.	D1 — Stability cap enforcement (small addition to ESL)
	5.	B3 — Integrate ESL into nightly job
	6.	C1 — Weekly review endpoint
	7.	C2 — Cooldown enforcement
	8.	C3 — Modify daily briefing
	9.	D3 — Quiet signal amplification
	10.	D2 — Bias audit job
	11.	E1 — Outreach outcome tracking

⸻

This order keeps:
	•	Core logic stable before API changes
	•	Safeguards integrated before public surface
	•	No half-ethical state

⸻

📌 PART 2 — GitHub-Ready Architecture Overview Issue

Below is a fully formatted issue you can paste into GitHub and pin.

⸻

📌 ISSUE TITLE:

Architecture Overview — Ethical Inflection Intelligence System (v2)

⸻

Purpose

SignalForge v2 is not just a readiness detection engine.

It is a layered Ethical Inflection Intelligence System designed to:
	•	Detect technical inflection points
	•	Protect founder autonomy
	•	Support neurodivergent founders
	•	Prevent urgency exploitation
	•	Maintain sustainable deal flow without hustle

This document defines the system architecture and guiding principles.

⸻

🧱 System Layers

⸻

Layer 1 — Signal Ingestion

Collects structured events:
	•	Funding
	•	Hiring
	•	Product launches
	•	Compliance signals
	•	Founder communication signals

Stores normalized events in signal_events.

⸻

Layer 2 — Technical Readiness Score (TRS)

Computes likelihood of technical inflection.

Dimensions:
	•	Momentum
	•	Complexity
	•	Pressure
	•	Leadership Gap

Outputs:
	•	readiness_snapshots
	•	TRS (0–100)
	•	Explain payload

TRS answers:

Is this company entering a technical inflection window?

TRS does NOT trigger outreach.

⸻

Layer 3 — Engagement Suitability Layer (ESL)

Modulates outreach intensity.

Components:
	•	BaseEngageability
	•	StabilityModifier
	•	Stress Volatility Index
	•	Sustained Pressure Index
	•	Communication Stability Index
	•	CadenceModifier
	•	AlignmentModifier

Formula:

ESL = BE × SM × CM × AM
OutreachScore = TRS × ESL

ESL answers:

Is this a healthy moment to engage, and how?

Key rule:
High pressure reduces engagement intensity.

ESL is a braking system, not an accelerator.

⸻

Layer 4 — Outreach Governance

Enforces:
	•	Cooldown periods
	•	Weekly outreach limits
	•	Human-in-the-loop review
	•	No automatic outreach
	•	Stability caps on escalation

The system never auto-contacts founders.

⸻

Layer 5 — Safeguards & Bias Monitoring

Includes:
	•	Quiet signal amplification
	•	Monthly bias audit
	•	Stability caps
	•	Alignment weighting

SignalForge does not:
	•	Infer neurodivergence
	•	Classify psychological traits
	•	Exploit distress spikes
	•	Over-optimize for VC-backed founders

⸻

🎯 Outreach Recommendation Categories

Based on ESL:
	•	Observe Only
	•	Soft Value Share
	•	Low-Pressure Intro
	•	Standard Outreach
	•	Direct Strategic Outreach

If StabilityModifier < 0.7:
→ Recommendation capped at Soft Value Share.

⸻

🛡 Ethical Guardrails
	1.	No automatic outreach.
	2.	No inference of neurodivergence.
	3.	No urgency exploitation.
	4.	Cooldown enforced.
	5.	Bias audit runs monthly.
	6.	All scores fully explainable.

⸻

🧠 Design Philosophy

SignalForge exists to:

Support founders at architectural inflection points with clarity and care — not to extract opportunity from stress.

The Engagement Suitability Layer ensures:
	•	Vulnerable founders are protected.
	•	Neurodivergent founders are respected.
	•	Outreach intensity matches environmental stability.
	•	Deal flow remains sustainable and aligned.

⸻

📈 Success Criteria

SignalForge v2 is successful when:
	•	Outreach feels well-timed.
	•	Founder feedback reflects “good timing.”
	•	Manual sourcing effort drops significantly.
	•	Pipeline remains steady without pressure.
	•	Bias skew is monitored and controlled.

⸻

🚫 Non-Goals

SignalForge does NOT:
	•	Auto-send outreach
	•	Scrape private data
	•	Predict psychological state
	•	Rank founders by vulnerability
	•	Replace human judgment

⸻

🔄 Implementation Order
	1.	TRS Foundation
	2.	ESL Engine
	3.	Nightly Integration
	4.	Weekly Review Endpoint
	5.	Cooldown Enforcement
	6.	Bias Monitoring
	7.	Calibration

⸻

🧭 Final Intent

SignalForge v2 is designed to be:

A timing intelligence instrument
A founder-respecting system
A neurodivergent-aware architecture
A sustainable dealflow engine

Not a lead scraper.

⸻
