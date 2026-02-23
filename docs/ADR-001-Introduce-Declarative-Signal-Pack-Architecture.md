📘 ADR-001

Title: Introduce Declarative Signal Pack Architecture

Status: Accepted
Date: 2026-02-23

⸻

Context

SignalForge V1/V2 included domain-specific logic for fractional CTO targeting embedded in core systems:
	•	Signal derivation logic
	•	Scoring weights
	•	ESL policies
	•	Outreach templates
	•	UI labels

V3 requires:
	•	Multi-industry support
	•	Decoupling domain intelligence from core
	•	Controlled extensibility
	•	Ethical consistency across industries

⸻

Decision

SignalForge will adopt a Declarative Signal Pack Architecture.

A Signal Pack is a configuration bundle containing:
	•	pack.json (manifest)
	•	taxonomy.yaml
	•	derivers.yaml
	•	scoring.yaml
	•	esl_policy.yaml
	•	playbooks/

Core will:
	•	Load packs at runtime
	•	Validate schemas
	•	Execute pack rules
	•	Remain domain-agnostic

Packs will not contain executable code in V3.

⸻

Consequences

Positive
	•	Enables industry portability
	•	Prevents domain logic creep
	•	Allows controlled beta expansion
	•	Preserves ESL authority
	•	Supports future pack marketplace

Negative
	•	Increases configuration complexity
	•	Requires strong validation tooling
	•	Requires pack versioning discipline

⸻

Alternatives Considered
	1.	Plugin architecture with arbitrary code → Rejected (security risk).
	2.	Keep fractional CTO core logic and layer others on top → Rejected (technical debt growth).
	3.	Hard-fork product per industry → Rejected (unscalable).

⸻

⸻

📘 ADR-002

Title: Pack Version Pinning Per Workspace

Status: Accepted
Date: 2026-02-23

⸻

Context

As packs evolve:
	•	Scoring weights may change
	•	ESL policies may change
	•	Signals may be added or deprecated

Uncontrolled pack updates could:
	•	Re-score historical leads
	•	Change outreach tone unexpectedly
	•	Create inconsistent behavior across workspaces

⸻

Decision

Each workspace must:
	•	Reference a specific pack_id + version
	•	Not automatically upgrade to new versions
	•	Explicitly opt-in to upgrades

Historical signals remain tied to the pack version that generated them.

⸻

Consequences

Positive
	•	Predictable behavior
	•	Safer rollouts
	•	Easier debugging
	•	Clear audit trail

Negative
	•	Must maintain backward compatibility for old pack versions
	•	Slightly more DB complexity

⸻

Alternatives Considered
	1.	Global pack version → Rejected (breaks tenant isolation).
	2.	Auto-upgrade packs → Rejected (uncontrolled behavior shifts).

⸻

⸻

📘 ADR-003

Title: No Automatic Reprocessing on Pack Switch

Status: Accepted
Date: 2026-02-23

⸻

Context

Switching packs could theoretically:
	•	Re-run derivation on historical observations
	•	Recompute all lead scores
	•	Trigger large compute spikes

Automatic reprocessing introduces:
	•	Performance risk
	•	Unexpected lead resurfacing
	•	Confusing user experience

⸻

Decision

Switching active pack will:
	•	Apply only to new observations going forward
	•	Not reprocess historical data automatically

Optional manual reprocessing may be introduced later with limits.

⸻

Consequences

Positive
	•	Predictable performance
	•	Avoids runaway compute
	•	Clear semantic behavior

Negative
	•	Historical data may not align perfectly with new pack logic
	•	Manual reprocess tooling required later

⸻

⸻

📘 ADR-004

Title: Lead Feed Projection for Performance

Status: Accepted
Date: 2026-02-23

⸻

Context

Lead rendering requires joining:
	•	SignalInstances
	•	Scores
	•	ESL decisions
	•	Outreach status

At scale, this can create heavy read-time computation.

⸻

Decision

Introduce a materialized Lead Feed Projection per:
	•	workspace_id
	•	pack_id

Projection includes:
	•	entity_id
	•	composite_score
	•	top_reasons
	•	esl_decision
	•	last_seen
	•	outreach_status_summary

Projection updated incrementally on:
	•	New SignalInstance
	•	Score recalculation
	•	ESL decision change
	•	Outreach event

⸻

Consequences

Positive
	•	Fast UI load times
	•	Stable sorting
	•	Reduced N+1 queries

Negative
	•	More write-time complexity
	•	Requires event-driven update discipline

⸻

⸻

📘 ADR-005

Title: Structured LLM Inputs Only (No Raw Observations)

Status: Accepted
Date: 2026-02-23

⸻

Context

Observations may contain:
	•	Prompt injection attempts
	•	Manipulative phrasing
	•	Sensitive content

Passing raw text to LLM risks:
	•	Prompt injection
	•	Policy violation
	•	Hallucinated assumptions

⸻

Decision

LLM draft generation will receive:
	•	signal_id
	•	explainability_template
	•	dates
	•	structured entity facts

Raw observation text will not be passed unless:
	•	Sanitized
	•	Quoted as evidence
	•	Marked untrusted

Critic layer must validate final draft.

⸻

Consequences

Positive
	•	Strong protection against prompt injection
	•	More deterministic outreach
	•	Lower hallucination risk

Negative
	•	Slightly less “rich” drafts
	•	Requires careful structured prompt design

⸻

⸻

📘 ADR-006

Title: Core-Enforced Hard Ethical Bans

Status: Accepted
Date: 2026-02-23

⸻

Context

Packs can define ESL policies, but allowing full flexibility risks:
	•	Protected attribute targeting
	•	Distress exploitation
	•	Unethical behavior by industry pack

⸻

Decision

Core will enforce non-overridable bans:
	•	Protected attribute inference
	•	Bankruptcy/tax lien exploitation (unless explicitly permitted in future with strict review)
	•	Targeting vulnerability states
	•	High-sensitivity distress surfacing

Pack ESL policies can only further restrict behavior, not loosen core bans.

⸻

Consequences

Positive
	•	Preserves brand integrity
	•	Reduces legal exposure
	•	Prevents pack-level abuse

Negative
	•	Limits extreme vertical customization
	•	Requires governance for future changes

⸻

⸻

📘 ADR-007

Title: One Active Pack Per Workspace (V3 Constraint)

Status: Accepted
Date: 2026-02-23

⸻

Context

Supporting multiple active packs per workspace:
	•	Increases query complexity
	•	Complicates scoring
	•	Multiplies performance overhead
	•	Introduces UX ambiguity

⸻

Decision

In V3:
	•	Each workspace may have exactly one active pack.
	•	Multi-pack support may be considered post-V3.

⸻

Consequences

Positive
	•	Simplifies queries
	•	Reduces performance risk
	•	Cleaner mental model
	•	Easier beta validation

Negative
	•	Limits advanced users
	•	Delays multi-industry stacking use case

⸻

⸻

📘 ADR-008

Title: Safe Regex + Deriver Execution Limits

Status: Accepted
Date: 2026-02-23

⸻

Context

Derivers rely on text pattern matching.

Regex misuse can cause:
	•	Catastrophic backtracking
	•	CPU exhaustion
	•	DoS conditions

⸻

Decision

Deriver engine must:
	•	Precompile regex at pack load
	•	Enforce maximum pattern length
	•	Enforce execution timeouts
	•	Limit advanced regex features if necessary

Per-workspace per-hour derivation quotas must exist.

⸻

Consequences

Positive
	•	Prevents DoS via config
	•	Protects multi-tenant stability

Negative
	•	Slightly limits expressive power of derivers

⸻

⸻

📘 ADR-009

Title: SignalInstances Are Pack-Scoped

Status: Accepted
Date: 2026-02-23

⸻

Context

Same Observation could produce different Signals under different packs.

Example:
	•	CTO pack → “security posture shift”
	•	Bookkeeping pack → irrelevant

Signals must not bleed across packs.

⸻

Decision

SignalInstances will include:
	•	pack_id
	•	signal_id
	•	entity_id
	•	timestamps
	•	strength/confidence

No cross-pack reuse of SignalInstances.

⸻

Consequences

Positive
	•	Clean isolation
	•	No semantic ambiguity
	•	Supports pack versioning

Negative
	•	Increased storage footprint
	•	More rows in DB

⸻

⸻

🧠 Strategic Outcome of ADR Set

With these decisions:
	•	Core becomes stable signal engine.
	•	Packs become safely swappable intelligence layers.
	•	Multi-tenant isolation is preserved.
	•	Scaling constraints are controlled.
	•	Ethical guardrails remain non-negotiable.
	•	Performance risks are addressed proactively.

⸻