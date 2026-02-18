# SignalForge v2 — Cursor-Ready Implementation Spec
## Feature: Readiness Scoring Engine + “Emerging Companies to Watch”

Owner: SignalForge  
Version: v2 (implementation spec)  
Status: Ready for build

---

## 0) Scope (What we are building now)

### In-scope
- Ingest company “events” (signals) from source adapters (start with 2–3 sources)
- Normalize + dedupe companies
- Compute 4-dimension readiness score (0–100) with time decay + suppressors
- Store score snapshots + deltas
- Daily Briefing: “Emerging Companies to Watch” section (top N)
- Watchlist add/remove
- Alerts when score jumps (optional, minimal)

### Out-of-scope (defer)
- Full ML model training
- Heavy scraping / LinkedIn scraping if it violates ToS or requires complicated auth
- Complex dashboard charts (we’ll store data now so charts are easy later)
- Multi-tenant billing/roles (assume single-user or simple auth)

---

## 1) Architecture Overview

### Services / Modules
1. **Ingestion**
   - `source_adapters/*` produce raw events
   - `event_normalizer` converts raw -> canonical `SignalEvent`
2. **Entity Resolution**
   - `company_resolver` maps events to a canonical `Company` record
3. **Scoring**
   - `readiness_engine` computes:
     - Momentum (M)
     - Complexity (C)
     - Pressure (P)
     - Leadership Gap (G)
     - Composite R
     - Suppressors
     - Deltas
4. **Delivery**
   - `briefing_builder` queries top companies and generates the section
   - `watchlist_service` manages watchlist + last_seen + reasons
   - `alert_service` checks for large deltas and emits notifications (email/slack/app)

### Processing Mode
- Start as **scheduled batch** (e.g., hourly ingest + nightly scoring)
- Move to event-driven later if needed

---

## 2) Data Model (DB Schema)

Assume Postgres.

### 2.1 `companies`
- `id` (uuid, pk)
- `name` (text)
- `domain` (text, unique nullable)  // example.com
- `website_url` (text nullable)
- `linkedin_url` (text nullable)
- `crunchbase_url` (text nullable)
- `status` (text default 'active') // active|acquired|dead|unknown
- `created_at` (timestamptz)
- `updated_at` (timestamptz)

Indexes:
- unique index on `domain` (where domain is not null)
- trigram index on `name` for fuzzy matching (optional)

### 2.2 `company_aliases`
Tracks alternate names/domains for dedupe.
- `id` (uuid, pk)
- `company_id` (uuid, fk companies.id)
- `alias_type` (text) // name|domain|url|social
- `alias_value` (text)
- `created_at` (timestamptz)

Index:
- unique (`alias_type`, `alias_value`)

### 2.3 `signal_events`
Canonical normalized events.
- `id` (uuid, pk)
- `company_id` (uuid fk nullable until resolved)
- `source` (text) // e.g., crunchbase|producthunt|rss|manual
- `source_event_id` (text nullable) // id from upstream if present
- `event_type` (text) // see taxonomy below
- `event_time` (timestamptz) // when it happened
- `ingested_at` (timestamptz)
- `title` (text nullable)
- `summary` (text nullable)
- `url` (text nullable)
- `raw` (jsonb) // upstream payload (for audits)
- `confidence` (float default 0.7) // 0..1

Indexes:
- (`company_id`, `event_time` desc)
- (`event_type`, `event_time` desc)
- unique (`source`, `source_event_id`) where source_event_id is not null

### 2.4 `readiness_snapshots`
Stores computed scores over time.
- `id` (uuid, pk)
- `company_id` (uuid, fk)
- `as_of` (date) // daily snapshot date
- `momentum` (int) // 0..100
- `complexity` (int) // 0..100
- `pressure` (int) // 0..100
- `leadership_gap` (int) // 0..100
- `composite` (int) // 0..100
- `explain` (jsonb) // structured explanation + top contributing events
- `computed_at` (timestamptz)

Indexes:
- unique (`company_id`, `as_of`)
- (`as_of`, `composite` desc)

### 2.5 `watchlist`
- `id` (uuid, pk)
- `company_id` (uuid, fk)
- `added_at` (timestamptz)
- `added_reason` (text nullable) // user note
- `is_active` (bool default true)

Index:
- unique (`company_id`) where is_active = true

### 2.6 `alerts`
- `id` (uuid, pk)
- `company_id` (uuid, fk)
- `alert_type` (text) // readiness_jump|ctohire|new_signal
- `payload` (jsonb)
- `created_at` (timestamptz)
- `sent_at` (timestamptz nullable)
- `status` (text default 'pending') // pending|sent|failed

---

## 3) Signal Taxonomy (Event Types)

Implement as string constants (enum-like). Keep small now; expand later.

### Momentum-related
- `funding_raised`
- `job_posted_engineering`
- `job_posted_infra`
- `headcount_growth`
- `launch_major`

### Complexity-related
- `api_launched`
- `ai_feature_launched`
- `enterprise_feature`
- `compliance_mentioned`

### Pressure-related
- `enterprise_customer`
- `regulatory_deadline`
- `founder_urgency_language`
- `revenue_milestone`

### Leadership Gap-related
- `cto_role_posted`
- `no_cto_detected`
- `fractional_request`
- `advisor_request`
- `cto_hired` (suppressor)

---

## 4) Readiness Scoring Engine (Deterministic)

### 4.1 Composite Formula
R = round(0.30M + 0.30C + 0.25P + 0.15G)
Clamp 0..100

### 4.2 Time Decay Helpers

#### Momentum decay (fast)
Weight by event recency (days since event):
- 0–30 days: 1.0
- 31–60: 0.7
- 61–90: 0.4
- 91+: 0.0

#### Pressure decay (medium)
- 0–30: 1.0
- 31–60: 0.85
- 61–120: 0.6
- 121+: 0.2 (cap this, never fully zero unless very old)

#### Complexity decay (slow)
- Complexity is cumulative with a slow decay:
  - 0–90: 1.0
  - 91–180: 0.8
  - 181–365: 0.6
  - 366+: 0.4

#### Leadership Gap decay (contextual)
- Gap is based on current state; events should “set” a state rather than decay.
- Example: `cto_hired` within 180 days should suppress.

### 4.3 Dimension Scoring (M, C, P, G)

#### M: Momentum (0..100)
Inputs (each event contributes points * decay * confidence):
- `funding_raised`: base 35
- `job_posted_engineering`: base 10 each (cap from jobs at 30)
- `headcount_growth`: base 20
- `launch_major`: base 15

Algorithm:
1. Fetch events in last 120 days for M types
2. `sum = Σ (base[event_type] * decay_m(days) * confidence)`
3. Apply caps:
   - jobs subscore cap 30
   - total sum cap 100
4. Convert to int: `M = clamp(round(sum), 0, 100)`

#### C: Complexity (0..100)
Base points (slower decay):
- `api_launched`: 25
- `ai_feature_launched`: 25
- `enterprise_feature`: 20
- `compliance_mentioned`: 15
- `job_posted_infra`: 10 (cap 20)

Algorithm:
1. Fetch events in last 365 days for C types
2. `sum = Σ (base * decay_c(days) * confidence)`
3. Cap at 100
4. `C = clamp(round(sum), 0, 100)`

#### P: Pressure (0..100)
Base points:
- `enterprise_customer`: 25
- `regulatory_deadline`: 30
- `founder_urgency_language`: 15 (cap 30)
- `revenue_milestone`: 15
- `funding_raised`: 20 (yes, funding also adds pressure, but lower than momentum)

Algorithm similar to Momentum but with `decay_p`.

#### G: Leadership Gap (0..100)
This is state-based with suppressors.

Inputs:
- “No CTO” state (inferred)
- CTO role posted
- Fractional/advisor request
- CTO hired (suppresses)

Base scoring:
- If `cto_hired` in last 180 days: `G = max(G - 50, 0)` and set `gap_closed = true`
- Else:
  - If `cto_role_posted` in last 120 days: +70
  - If `fractional_request` or `advisor_request` in last 120 days: +60
  - If `no_cto_detected` in last 365 days: +40
Cap 100

Implementation detail:
- Prefer highest-confidence “leadership state” signal among the above.
- If both `cto_role_posted` and `no_cto_detected`, treat as reinforcing (but still cap at 100).

### 4.4 Suppressors (Global)
Apply after computing dimensions:
- If company status = `acquired` or `dead`: set `R = 0` and mark suppressed
- If `cto_hired` within 60 days: `G = max(G - 70, 0)` and recompute R
- If “VP Eng / Head of Eng hired” signal exists (future): reduce G by 30

### 4.5 Explainability Payload (`readiness_snapshots.explain`)
Store:
- `weights`: {M:0.30, C:0.30, P:0.25, G:0.15}
- `dimensions`: {M,C,P,G,R}
- `top_events`: array of up to 8 items:
  - {event_type, event_time, source, url, contribution_points, confidence}
- `suppressors_applied`: array strings
- `notes`: short text for debugging (optional)

---

## 5) Implementation Modules (Suggested Files)

Assume TypeScript (Node) or Python. Use whichever the repo already uses.
Below is language-agnostic folder guidance.

### 5.1 Core
- `src/domain/signals/eventTypes.ts`
- `src/domain/signals/decay.ts`
- `src/domain/readiness/readinessEngine.ts`
- `src/domain/readiness/scoringTables.ts`
- `src/domain/companies/resolution.ts`
- `src/services/briefing/briefingBuilder.ts`
- `src/services/watchlist/watchlistService.ts`

### 5.2 Ingestion
- `src/ingestion/adapters/crunchbase.ts` (or placeholder)
- `src/ingestion/adapters/producthunt.ts`
- `src/ingestion/normalize.ts`

### 5.3 Jobs
- `src/jobs/ingestHourly.ts`
- `src/jobs/scoreNightly.ts`
- `src/jobs/alertScanDaily.ts`

---

## 6) Key Functions (Pseudo-code)

### 6.1 `computeReadiness(companyId, asOfDate)`
events = getSignalEvents(companyId, window=365d)

M = computeMomentum(events, asOfDate)
C = computeComplexity(events, asOfDate)
P = computePressure(events, asOfDate)
G = computeLeadershipGap(events, asOfDate)

[R, suppressors] = applySuppressors(company, events, M,C,P,G)
explain = buildExplainPayload(events, M,C,P,G,R,suppressors, asOfDate)

saveSnapshot(companyId, asOfDate, M,C,P,G,R, explain)
return {M,C,P,G,R, explain}

### 6.2 `computeMomentum(events)`
- filter by M event types
- for each event:
  - days = diff(asOf, event_time)
  - contrib = base[type] * decay_m(days) * confidence
  - if type is job_posted_engineering -> track in jobs bucket
- apply caps
- return int score

(Repeat patterns for C and P using their decay.)

### 6.3 `buildDailyBriefing(asOfDate)`
top = query readiness_snapshots where as_of=asOfDate
and composite >= threshold (default 60)
order by composite desc
limit 10

for each:
hydrate company + top explain events
produce briefing card:
- name, website, founder (if known), score, key signals
- why_it_matters (LLM optional later; for now template)
return section markdown/json

### 6.4 `scoreDelta(companyId, asOfDate)`
today = getSnapshot(companyId, asOfDate)
prev  = getSnapshot(companyId, asOfDate - 1 day)
delta = today.composite - prev.composite (or 0 if none)
store delta in explain or compute on read

---

## 7) API Endpoints (Minimal)

### Companies
- `GET /api/companies/:id`
- `GET /api/companies/:id/readiness?range=30d`

### Watchlist
- `POST /api/watchlist {company_id, reason?}`
- `DELETE /api/watchlist/:company_id`
- `GET /api/watchlist`

### Briefing
- `GET /api/briefing/daily?date=YYYY-MM-DD`

### Admin / Debug (optional)
- `POST /api/admin/score-company {company_id, as_of}`
- `GET /api/admin/company-events/:company_id`

---

## 8) UI Requirements (Minimal)

### Daily Briefing Section: “Emerging Companies to Watch”
For each company card:
- Company name + website link
- Readiness score (big number)
- Dimension mini-breakdown: M/C/P/G (small)
- Top 3 signals (from explain.top_events mapped to human labels)
- Button: “Add to Watchlist”
- Optional: “Why it matters” (template)

### Watchlist View
- List of companies
- Latest composite score
- 7-day delta (computed client-side from snapshots)
- “Remove” button

---

## 9) Source Adapters (MVP)

Pick 2–3 easy, compliant sources. Implement as adapters that return a list of raw events.

### Adapter Contract
`fetchEvents(since: datetime) -> RawEvent[]`

RawEvent fields:
- `company_name`
- `domain` or `website_url` or `company_profile_url`
- `event_type_candidate` (string)
- `event_time`
- `title`
- `summary`
- `url`
- `source_event_id`
- `raw_payload`

Then normalize:
`RawEvent -> SignalEvent + company resolution`

### MVP Suggestions
- Funding feed (structured): Crunchbase alternative or any accessible funding RSS/aggregator you already use
- Product launches: Product Hunt
- Jobs feed: a compliant job board API or RSS

(Do not hard-build LinkedIn scraping.)

---

## 10) Entity Resolution (Company Dedupe)

### Strategy (MVP)
Order of matching:
1. domain exact match
2. normalized website_url host match
3. linkedin_url match
4. fuzzy name match (only if no domain)

When creating a new company:
- store name + best URL + domain if extractable
- create alias records for name + domain + known URLs

### Normalization helpers
- `normalizeName`: lowercase, remove inc/llc/ltd, punctuation, extra spaces
- `extractDomain`: from url (strip www)

---

## 11) Testing Plan

### Unit Tests
- decay functions (exact day boundaries)
- computeMomentum caps + decay
- computeComplexity slow decay
- pressure scoring includes funding
- leadership gap suppressors (cto_hired)
- composite rounding + clamping

### Integration Tests
- ingest -> normalize -> resolve -> create events
- scoreNightly writes snapshots
- briefing endpoint returns expected top companies

### Golden Fixtures
Create a `fixtures/companies/*.json` with synthetic event timelines:
- Seed raise + hiring spike + no CTO
- AI launch + SOC2 mention + enterprise customer
- CTO hired recently (suppressed)

---

## 12) Jobs & Scheduling

### `ingestHourly`
- run adapters with `since = now - 24h` (or last cursor)
- normalize events
- resolve companies
- upsert events (dedupe by source_event_id)

### `scoreNightly`
- as_of = today (local)
- score all companies with any events in last 365 days OR on watchlist
- write snapshots

### `alertScanDaily` (optional)
- compare latest vs previous snapshot
- if delta >= 15 => create alert record

---

## 13) Configuration

### Defaults
- `READINESS_THRESHOLD = 60`
- `ALERT_DELTA_THRESHOLD = 15`
- Weights: M 0.30 / C 0.30 / P 0.25 / G 0.15

### Scoring Tables
Keep in a single config file:
- base points per event_type
- caps for job buckets
- decay breakpoints

---

## 14) Acceptance Criteria (Build Complete When…)

1. Ingest creates normalized `signal_events` tied to `companies`
2. Nightly scoring writes `readiness_snapshots` with explain payload
3. Daily briefing endpoint returns top 10 companies (>=60) sorted
4. UI shows section with add-to-watchlist working
5. Watchlist view shows latest score and is stable across refresh
6. Unit tests cover core scoring logic + suppressors + decay boundaries

---

## 15) Implementation Order (Recommended)

1) Create schema + migrations  
2) Implement event taxonomy + decay functions + scoring tables  
3) Implement readinessEngine + snapshot writer  
4) Build company resolver + aliases  
5) Implement 1 adapter end-to-end (prove pipeline)  
6) Add 2nd adapter  
7) Build briefing endpoint + UI section  
8) Add watchlist endpoints + UI  
9) Add alert scan (optional)

---

## 16) “Human Labels” Mapping for UI

Map event types to display strings:
- funding_raised -> “New funding”
- job_posted_engineering -> “Engineering hiring”
- job_posted_infra -> “Infra/DevOps hiring”
- api_launched -> “API launch”
- ai_feature_launched -> “AI feature launch”
- enterprise_customer -> “Enterprise customer”
- compliance_mentioned -> “Compliance pressure”
- cto_role_posted -> “CTO search”
- fractional_request -> “Fractional help requested”
- cto_hired -> “CTO hired” (suppressor)

---

## 17) Notes for Future (Don’t build now)

- Founder language classifier can generate:
  - founder_urgency_language events with confidence score
- “Readiness velocity” as a first-class metric:
  - store 7d and 30d deltas for faster querying
- Outreach draft generation per company card

---

