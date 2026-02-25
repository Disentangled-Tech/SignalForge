# SignalForge Glossary

A reference for acronyms and abbreviations used throughout the project.

## Domain-Specific (SignalForge)

| Acronym | Full Form | Description |
|---------|-----------|-------------|
| **ADR** | Architecture Decision Record | Documented design decisions (e.g., ADR-001 through ADR-009). See [docs/ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md](ADR-001-Introduce-Declarative-Signal-Pack-Architecture.md). |
| **AM** | Alignment Modifier | ESL component; adjusts score based on founder mission alignment and fit. |
| **BE** | Base Engageability | ESL component; BE = TRS / 100, clamped to 0–1. |
| **CM** | Cadence Modifier | ESL component; reduces score when within cooldown after recent outreach. |
| **CSI** | Communication Stability Index | Stability dimension; large gaps between events reduce CSI. |
| **CTA** | Call to Action | The primary ask in an outreach message (e.g., "Want me to send that checklist?"). ORE enforces a single CTA per draft. |
| **CTO** | Chief Technology Officer | Primary target persona; fractional CTO serving early-stage founders. |
| **ESL** | Engagement Suitability Layer | Layer that modulates outreach intensity. ESL = BE × SM × CM × AM. Protects founder autonomy and reduces pressure-based outreach. |
| **ND** | Neurodivergent | Design consideration for outreach; ND-friendly messaging avoids shame language, urgency pressure, and surveillance phrasing. |
| **ORE** | Outreach Recommendation Engine | Produces outreach kits: recommendation type, channel, draft variants, why-this-works notes, and safeguards. See [docs/Outreach-Recommendation-Engine-ORE-design-spec.md](Outreach-Recommendation-Engine-ORE-design-spec.md). |
| **PRD** | Product Requirements Document | Product specification; see [docs/v2PRD.md](v2PRD.md) and [rules/CURSOR_PRD.md](../rules/CURSOR_PRD.md). |
| **SM** | Stability Modifier | ESL component; SM = 1 - (w_svi×SVI + w_spi×SPI + w_csi×(1-CSI)). High stress reduces SM. |
| **SPI** | Sustained Pressure Index | Stability dimension; high when pressure exceeds threshold for sustained days. |
| **SVI** | Stress Volatility Index | Stability dimension; measures recent urgency/stress events (e.g., founder_urgency_language). |
| **TDD** | Test-Driven Development | Development practice; write tests first, then implement. See [rules/TDD_rules.md](../rules/TDD_rules.md). |
| **TRS** | Technical Readiness Score | 0–100 score measuring likelihood of technical inflection. Dimensions: Momentum, Complexity, Pressure, Leadership Gap. |

## Technical

| Acronym | Full Form | Description |
|---------|-----------|-------------|
| **API** | Application Programming Interface | HTTP endpoints for programmatic access (e.g., `/internal/run_score`, `/api/companies`). |
| **CRUD** | Create, Read, Update, Delete | Standard data operations. |
| **CSV** | Comma-Separated Values | File format for bulk company import. |
| **DB** | Database | PostgreSQL database (e.g., `signalforge_dev`, `signalforge_test`). |
| **DoS** | Denial of Service | Security concern; ADR-008 addresses regex-based DoS via pattern length and execution timeouts. |
| **FK** | Foreign Key | Database referential constraint (e.g., `company_id` FK to `companies.id`). |
| **HTML** | HyperText Markup Language | Server-rendered pages via Jinja2 templates. |
| **HTTP** | Hypertext Transfer Protocol | Protocol for API and web requests. |
| **JSON** | JavaScript Object Notation | Data interchange format; used for API bodies, pack config, and stored payloads. |
| **JSONB** | JSON Binary | PostgreSQL JSON type with indexing; used for `raw`, `explain`, `top_signal_ids`, etc. |
| **LLM** | Large Language Model | AI model for draft generation and analysis; provider abstraction in `app/llm/`. |
| **ORM** | Object-Relational Mapping | SQLAlchemy models mapping Python objects to database tables. |
| **PR** | Pull Request | GitHub code review workflow. |
| **CI/CD** | Continuous Integration / Continuous Deployment | Automated build and deployment; internal endpoints may be triggered from CI/CD. |
| **UI** | User Interface | Server-rendered views (briefing, companies, settings). |
| **URL** | Uniform Resource Locator | Web address; validated for `website_url`, `founder_linkedin_url`, etc. |
| **UUID** | Universally Unique Identifier | Identifier format for workspaces, packs, and entities. |

## Business / Roles

| Acronym | Full Form | Description |
|---------|-----------|-------------|
| **B2B** | Business-to-Business | Product category for personalization (e.g., marketplace, B2B). |
| **CEO** | Chief Executive Officer | Founder role for personalization. |
| **COO** | Chief Operating Officer | Founder role for personalization. |
| **DM** | Direct Message | Outreach channel (e.g., LinkedIn DM vs email). |

## ADR Quick Reference

| ADR | Title |
|-----|-------|
| ADR-001 | Introduce Declarative Signal Pack Architecture |
| ADR-002 | Pack Version Pinning Per Workspace |
| ADR-003 | No Automatic Reprocessing on Pack Switch |
| ADR-004 | Lead Feed Projection for Performance |
| ADR-005 | Structured LLM Inputs Only (No Raw Observations) |
| ADR-006 | Core-Enforced Hard Ethical Bans |
| ADR-007 | One Active Pack Per Workspace (V3 Constraint) |
| ADR-008 | Safe Regex + Deriver Execution Limits |
| ADR-009 | SignalInstances Are Pack-Scoped |
