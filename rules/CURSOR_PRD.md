SignalForge — Cursor Engineering PRD

Purpose:
SignalForge is a single-user intelligence assistant that monitors startup companies and identifies when a founder is likely to need technical leadership help.
The system collects public signals, analyzes operational stage and risks using an LLM, scores urgency, and produces a daily briefing with suggested outreach.

This is not a CRM, not a lead scraper, and not a marketing automation platform.

The product’s value comes from reasoning and timing.

The three most important outputs
	1.	Correct company stage classification
	2.	Clear explanation of “why now”
	3.	A believable human outreach draft

If a feature does not improve those outcomes, do not build it.

⸻

Core Workflow

The system must always operate as a deterministic pipeline:

companies → signals → analysis → scoring → briefing → outreach draft

No background autonomous behavior is allowed.

The system never contacts external founders automatically.

⸻

Architectural Rules

LLM Usage

The LLM is a reasoning component only.

The LLM may:
	•	classify stage
	•	interpret operational signals
	•	generate explanations
	•	draft outreach

The LLM may NOT:
	•	schedule jobs
	•	access the database
	•	make decisions about actions
	•	initiate communication
	•	control workflow

All orchestration must be Python code.

⸻

Single User Constraint

Version 1 supports exactly one operator.

Do not implement:
	•	organizations
	•	roles
	•	permissions
	•	team accounts
	•	multi-tenant architecture

Authentication exists only to prevent public access.

⸻

Simplicity Rule

Prioritize:
	•	readability
	•	debuggability
	•	explicit logic
	•	logs

Avoid:
	•	agent frameworks
	•	message queues
	•	microservices
	•	complex async orchestration

One developer should understand the entire system by reading the code.

⸻

Required Technology Stack

Component	Requirement
Backend	Python 3.11+
Framework	FastAPI
ORM	SQLAlchemy 2.x
Migrations	Alembic
Database	PostgreSQL
Scheduler	Cloudways cron calling internal endpoints
Templates	Jinja2 server-rendered pages
LLM	provider abstraction module

Explicitly forbidden in V1
	•	React frameworks
	•	LangChain
	•	vector databases
	•	Redis
	•	Celery
	•	Kafka
	•	Docker orchestration
	•	WebSockets

⸻

System Behavior

Company Scan

When scanning a company:
	1.	Fetch homepage HTML
	2.	Attempt common paths:
	•	/blog
	•	/news
	•	/careers
	•	/jobs
	3.	Extract readable text
	4.	Deduplicate using content hash
	5.	Store SignalRecord

Failures must not stop the run.

⸻

Analysis Pipeline

After signals exist, the system performs structured analysis:
	1.	Stage classification
	2.	Pain signal detection
	3.	Explanation generation
	4.	Outreach draft generation

Each step must produce structured JSON.

If JSON parsing fails:
	•	retry once
	•	if still invalid, mark analysis failed for that company

⸻

Scoring

Scoring must be deterministic Python logic.

Inputs:
	•	stage
	•	detected signals

Output:
	•	integer score (0–100)

The LLM never assigns scores.

The latest score updates companies.cto_need_score.

⸻

Daily Briefing

Once per day:
	1.	Select companies with activity in the last 14 days
	2.	Sort by score descending
	3.	Select top 5
	4.	Generate briefing entries
	5.	Store briefing
	6.	Optionally email to operator

The system must never automatically message founders.

⸻

Required Web Pages

Login

Password authentication only.

Companies List

Shows:
	•	company name
	•	score
	•	last scan time

Company Detail

Shows:
	•	stored signals
	•	analysis output
	•	outreach draft
	•	rescan button

Daily Briefing

Shows:
	•	ranked recommendations
	•	explanations
	•	outreach drafts

Settings

Editable:
	•	operator profile (markdown)
	•	scoring weights
	•	email settings
	•	briefing time

⸻

Data Handling

Allowed Data
	•	public website text
	•	company metadata
	•	user notes

Not Allowed
	•	private social platform scraping
	•	personal email harvesting
	•	unauthorized data collection

⸻

Prompt Handling

All prompts must live in:

/app/prompts/

Rules:
	•	never hardcode prompts in Python
	•	prompts must be versioned by filename
	•	prompts must be editable without code changes

⸻

Safety Rules for Outreach

The outreach draft must:
	•	be under 140 words
	•	not fabricate experience
	•	not invent clients
	•	not claim credentials not in operator profile
	•	avoid marketing language
	•	read like a thoughtful peer

If violation detected:
	•	regenerate once

⸻

Internal Job Endpoints

Cloudways cron will call:

POST /internal/run_scan
POST /internal/run_briefing
POST /internal/run_score

Requirements:
	•	require secret token header
	•	create JobRun record
	•	never crash server
	•	return JSON status

⸻

Logging Requirements

Log:
	•	job start/finish
	•	number of companies processed
	•	LLM failures
	•	analysis failures
	•	email success/failure

Logs must be human readable.

⸻

Error Handling

Rules:
	•	one company failure cannot stop a run
	•	record company, step, and error message
	•	store in job_runs table

⸻

Definition of Done

The system is complete when:
	1.	User adds ≥25 companies
	2.	Scan runs automatically
	3.	A daily briefing appears
	4.	Outreach drafts read human
	5.	System runs 7 consecutive days without manual intervention

⸻

Out of Scope (Do Not Build)
	•	automated founder emailing
	•	LinkedIn automation
	•	CRM pipeline features
	•	analytics dashboards
	•	lead scraping engines
	•	AI decision-making agents
	•	vector search memory

⸻

Guidance to the Coding Assistant

When uncertain, choose the simplest implementation that preserves clarity.

This is an operational intelligence tool, not a SaaS platform.

Prefer correctness and reliability over features.

Only add features that improve:
	•	classification accuracy
	•	reasoning clarity
	•	outreach credibility

⸻
