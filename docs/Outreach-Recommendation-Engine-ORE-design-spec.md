# Outreach Recommendation Engine (ORE) — Design Spec

ORE is **pack-driven** (Issue #121): all outreach wording and strategy come from pack/playbook. There is no "Founder" or other domain-specific recipient wording unless the pack defines **taxonomy.recipient_label**. Explainability text can come from pack taxonomy or playbook **explainability_snippet_template**. Structured logs include **pack_id** and **playbook_id** for every recommendation (no PII). See [playbook-draft-engine.md](playbook-draft-engine.md) for YAML shape, pattern frame selection by dominant TRS dimension, and logging fields.

---

1) What the Outreach Engine Produces

For each company surfaced in Weekly Review, ORE outputs a compact “outreach kit”:

 1. Recommended Outreach Type
 • Observe Only
 • Soft Value Share
 • Low-Pressure Intro
 • Standard Outreach
 • Direct Strategic Outreach
(Already derived from ESL; ORE respects caps.)
 2. Channel Suggestion (optional)
 • LinkedIn DM
 • Email
 • Comment → DM later
 • Warm intro request
 • “Save for later” (observe)
 3. Message Draft (primary artifact)
 • 2–4 variants (short / medium, DM vs email)
 • 150–600 characters for DM, 120–180 words for email
 4. Why This Works (for you, not the founder)
 • 2–3 bullets, plain language
 • references categories of signals, not specifics
 5. Offer & CTA Recommendation
 • Always consent-based
 • ND-friendly options: “want a quick checklist?” / “want me to send a 1-pager?” / “would it help to compare notes?”
 6. Red Flags / Safeguards Triggered
 • “High pressure detected → Soft Value Share only”
 • “Cooldown active → Do not contact”
 • “Low alignment → deprioritize”

⸻

1) Inputs and Data Contract

**ESL context (compute_esl_from_context).** The pipeline loads ESL from DB via `compute_esl_from_context(db, company_id, as_of, pack_id, core_pack_id)`. The return shape is documented in the implementation plan (Issue #122, §1.1.1) and typed as `EslContextResult` in `app/services/esl/engagement_snapshot_writer.py`. Keys include `esl_composite`, `recommendation_type`, `explain` (with `tone_constraint`, `esl_decision`, etc.), and **signal_ids** (M1, Issue #120): the entity’s signal set for the pack (or core pack when `core_pack_id` is set), used by the pack-aware critic. Consumers must not rely on undocumented keys.

Required Inputs
 • Company: name, website, short description (if known)
 • Founder: name, role, contact options (if known)
 • TRS: total + top contributing categories (not raw events)
 • ESL: score, recommendation, stability flags, cadence flags
 • Alignment: manual flags, notes (optional)
 • History: last outreach date/outcome (from outreach_history)
 • Your offer: default entry point (e.g., “90-min Tech Coaching / Roadmap”)

Optional Inputs (nice-to-have)
 • Recent public messaging themes (blog headlines, product tagline)
 • “Tone preferences” you set (more direct vs more gentle)

Strict Prohibition (hard rule)

ORE must never mention:
 • “I saw you posted X roles”
 • “I noticed you raised X”
 • “I noticed you said SOC2”
 • Any signal source explicitly

Instead it can reference general patterns:
 • “Teams often hit a complexity step-change when product and hiring accelerate.”

⸻

1) System Architecture

ORE has 3 layers:

A) Policy Gate (Safety + Ethics)

Checks before generation:
 • Cooldown active? → output “Observe Only” + explanation (no draft)
 • Stability cap triggered (SM < 0.7)? → max recommendation = Soft Value Share
 • Low alignment? → require manual confirmation tag “OK to contact”
 • High pressure + leadership gap combo? → force “soft” framing and no time pressure CTA

B) Strategy Selector (Deterministic — Issue #117)

Strategy selection is **deterministic**: no LLM, no network, no DB. The selector runs after the policy gate and uses only gate output, TRS dominant dimension, alignment, and playbook data.

**Inputs:**
 • **recommendation_type** — From the policy gate (e.g. Observe Only, Soft Value Share, Low-Pressure Intro, Standard Outreach, Direct Strategic Outreach).
 • **TRS dominant dimension** — The dimension with the highest score among M/C/P/G (momentum, complexity, pressure, leadership_gap), with a fixed tie-break order. Sourced from ReadinessSnapshot.
 • **alignment_high** — Alignment flag from ESL context (reserved for future channel/CTA rules).
 • **playbook** — Normalized ORE playbook (pattern_frames, value_assets, ctas; optional channels, soft_ctas).
 • **stability_cap_triggered** — When true, the selector must choose a softer CTA (see below).

**Outputs:**
 • **channel** — e.g. "LinkedIn DM" (default when playbook has no `channels` list or only one option).
 • **cta_type** — One of the playbook’s consent-based CTAs; when stability cap is triggered, a softer CTA is chosen (from playbook `soft_ctas` if present, else first CTA).
 • **value_asset** — One of the playbook’s value assets (e.g. by recommendation_type; Soft Value Share may prefer first or “checklist” type).
 • **pattern_frame** — Framing text keyed by dominant dimension (e.g. momentum, complexity, pressure, leadership_gap) with fallback (e.g. momentum then complexity). Pressure-dominant uses stabilization framing when the playbook defines it.

**Stability cap → softer CTA:** When the stability cap is triggered (e.g. SM < 0.7), the policy gate already caps recommendation at Soft Value Share. The selector additionally chooses a softer CTA: if the playbook defines optional **soft_ctas**, one of those is used; otherwise the first CTA from **ctas** is used. This keeps outreach consent-based and low-pressure for stressed founders.

**Pack vs core:** The playbook supplies the options (pattern_frames, value_assets, ctas, optional channels, soft_ctas); TRS dimensions come from core (ReadinessSnapshot). See ADR-013 and playbook-draft-engine.md.

C) Draft Generator + Critic (pack-aware safety layer, Issue #120)

Generate draft → run through critic checks → revise once (or use fallback). The critic is **pack-aware**: it receives context (pack_id, suppressed_signal_ids, tone_constraint, forbidden_phrases, allowed_signal_labels) so drafts never violate ESL hard bans or pack constraints.

**Pack-aware critic checks:**
 • **Core rules (always):** Surveillance language, urgency pressure, single CTA, opt-out language, short paragraphs, shame framing (core phrase list; see docs/critic_rules.md).
 • **Pack forbidden_phrases:** Playbook list applied case-insensitive; any match fails the critic.
 • **Suppressed-signal mention:** Draft must not reference phrases associated with signals that are core-banned or pack-blocked (or in prohibited_combinations). The pipeline passes the set of entity signal IDs that must not be referenced; the critic uses a core phrase map (suppressed_signal_phrases) to detect mentions. Violations are logged with violation_type, pack_id, signal_id.
 • **Tone tier:** When tone_constraint is set (e.g. "Soft Value Share"), the draft must not contain phrases that imply a higher tier (e.g. "book a call" when only Soft Value Share is allowed).
 • **Unsupported claims (optional/future):** When allowed_signal_labels is provided, drafts should not reference signals outside that set; full enforcement can be staged later.

**Block/regenerate behavior:** If the critic fails, the pipeline (1) tries the template fallback; (2) if fallback also fails, stores the original draft and sets strategy_notes with a "Manual Review" message and violation summary. No automatic send; human always reviews before outreach.

**Logging:** On critic failure, the pipeline logs each violation with structured fields: violation_type, pack_id, signal_id (when applicable), company_id. See app/services/ore/ore_pipeline._log_critic_violations and CriticResult.violation_details.

Pack-driven playbooks and sensitivity (Issue #176)

ORE is pack-driven: the active pack supplies the playbook (e.g. playbooks/ore_outreach.yaml), including pattern_frames, value_assets, ctas, optional opening_templates, value_statements, forbidden_phrases, and tone. The critic applies pack forbidden_phrases in addition to core rules. Sensitivity gating is prompt-only: tone_constraint (e.g. "Soft Value Share") and playbook tone definitions are passed as TONE_INSTRUCTION so the LLM stays within the allowed tier; sensitivity_level is never sent to the LLM. Optional **enable_ore_polish** (Issue #119) defaults to false for backward compatibility; when true, ORE runs an LLM polish step before the critic and falls back to the original draft if the polished draft fails. See docs/playbook-draft-engine.md for YAML shape, loader, and data flow.

**Optional LLM polishing (hybrid mode, Issue #119)**

When a playbook sets **enable_ore_polish** to true, ORE runs an optional polishing step after draft generation and before the critic. Polishing runs only in this hybrid path; the critic runs after polishing. If the polished draft fails the critic, ORE falls back to the **original** draft and re-runs the critic on it; only if the original also fails does the pipeline use the template fallback. Constraints for the polisher: preserve explainability and pack tone; do not add new claims, urgency, or speculation; do not reference events or signals outside the allowed framing list (suppressed refs remain excluded). ESL hard bans and pack forbidden phrases cannot be bypassed; the critic still applies to the chosen draft.

⸻

1) Outreach Types and What They Mean

Observe Only

When:
 • cooldown active
 • sensitivity high or stability cap triggered
 • low confidence or low alignment

Output:
 • No message draft
 • “watch trigger”: what signal would move them to Soft Value Share

⸻

Soft Value Share (default for high sensitivity / stability cap / high pressure)

Goal: give something useful with zero obligation.

Characteristics:
 • 3–6 sentences
 • One small resource or insight
 • CTA: “Want me to send it?” (Yes/no)

Examples of value assets:
 • “tech inflection checklist”
 • “early warning signs of scaling pain”
 • “architecture stabilization mini-audit prompts”

⸻

Low-Pressure Intro

Goal: open a relationship, not sell.

Characteristics:
 • brief intro + pattern + offer a tiny next step
 • CTA: “Open to a quick compare-notes?”

⸻

Standard Outreach

Goal: propose a short call tied to a problem frame.

Characteristics:
 • 6–10 sentences
 • CTA includes 2 options (15 min or “I can send a 1-pager”)

⸻

Direct Strategic Outreach

Rare. Only when:
 • high TRS
 • high stability
 • no cooldown
 • high alignment

Characteristics:
 • specific positioning
 • direct ask
 • still consent-based and not urgent

⸻

1) Neurodivergent-Aware Message Rules

These are not “special treatment.” They’re just good outreach, optimized for clarity and autonomy.

Format Rules
 • Short paragraphs (1–2 sentences)
 • Bullets when listing
 • One clear ask max
 • Explicit permission to ignore
 • No “quick question” ambiguity

Tone Rules
 • No shame language (“falling behind”, “must”, “should”)
 • No urgency pressure (“ASAP”, “soon”, “before it’s too late”)
 • No implied surveillance
 • Offer choices: “A or B”

Autonomy Rules
 • Include opt-out line: “No worries if now isn’t the time.”
 • Avoid “calendar links” by default (those feel pushy for many ND folks)
 • Prefer: “Want me to send X?” or “Open to a 15-min chat?”

⸻

1) Message Template Library (Parameterized)

The canonical placeholder contract, template rules, and critic alignment for the parameterized template library are documented in [outreach-template-library.md](outreach-template-library.md) (Issue #118). The following summarizes the slot names used in the design; the doc defines the full set (`founder_name`, `company_name`, `pattern_frame`, `value_asset`, `cta`) and rules (no surveillance, short paragraphs, opt-out, single CTA).

Store templates by outreach type + channel.

Each template has slots:
 • {name}
 • {company}
 • {pattern_frame} (generic)
 • {value_asset}
 • {cta}

**Pack override prompts (ore_outreach_v1):** If a pack overrides the base `ore_outreach_v1` template (e.g. in a v2 pack’s `prompts/` directory), that template **must** include **{{TONE_INSTRUCTION}}** and all other app placeholders (**NAME**, **COMPANY**, **PATTERN_FRAME**, **VALUE_ASSET**, **CTA**, **EXPLAINABILITY_SNIPPET**, **TOP_SIGNALS**, **TONE_INSTRUCTION**). The loader requires all placeholders to be supplied; omitting them will cause draft generation to fail. When no explainability context is available, the pipeline passes empty string and empty list respectively; when no tone constraint is set, **TONE_INSTRUCTION** is passed as empty string.

**Tone gating (M5):** Tone gating is prompt-only: an additive instruction (e.g. maximum outreach tier and tier-specific wording from the playbook) is passed as **TONE_INSTRUCTION** so the LLM stays within the allowed tone. It does not change policy gate, critic, or ESL logic. **sensitivity_level** is never sent to the LLM; only the derived **tone_constraint** (e.g. "Soft Value Share") and playbook **tone** text are used for the prompt. Tier-specific wording should be defined in the playbook's `tone` (string or dict per recommendation_type); see playbooks/ore_outreach.yaml.

Pattern Frames (safe, non-invasive)

Pick one based on dominant TRS dimension(s), but never cite events.
 • Momentum-led: “When a team’s pace picks up, tech decisions that worked earlier can start costing more.”
 • Complexity-led: “When products add integrations/AI/enterprise asks, systems often need a stabilization pass.”
 • Pressure-led (gentle): “When timelines get tighter, it helps to reduce decision load and get a clean plan.”
 • Leadership gap-led: “When there isn’t a dedicated technical owner yet, teams often benefit from a short-term systems guide.”

Value Assets (lightweight)
 • “2-page Tech Inflection Checklist”
 • “30-minute ‘what’s breaking next’ map”
 • “5 questions to reduce tech chaos”

CTAs (consent-based)
 • “Want me to send that checklist?”
 • “Open to a 15-min compare-notes call?”
 • “If helpful, I can share a one-page approach—want it?”

⸻

1) Ranking and Personalization (Minimal but Powerful)

ORE should personalize without creeping people out.

Personalization sources:
 • company tagline / mission statement
 • product category (B2B, marketplace, etc.)
 • founder role (CEO, COO)

Avoid:
 • referencing their post content
 • referencing exact hiring

Optional setting for you:
 • preferred channel: email-first vs LinkedIn-first
 • desired weekly outreach count
 • default outreach type floor/ceiling

⸻

1) Outputs and Persistence

Store in DB (or generated on-demand):

outreach_recommendations
 • company_id
 • as_of
 • recommendation_type
 • channel
 • draft_variants (json)
 • strategy_notes (json)
 • safeguards_triggered (json)
 • created_at

**strategy_notes shape (Issue #117 M4):** The pipeline sets `strategy_notes` from the Strategy Selector so each recommendation records the chosen strategy for audit and debugging. The object always includes: `channel`, `cta_type`, `value_asset`, `pattern_frame`. When the draft fails the critic and is stored for manual review, the pipeline also adds a `message` key with a short summary of the critic result (e.g. violation types). Consumers should treat `strategy_notes` as an opaque JSON object; the four selector keys are stable for query/display; `message` is optional and only present on critic failure.

This enables:
 • reviewing later
 • comparing what worked
 • outcome tracking

⸻

1) Success Metrics (for the Outreach Engine)

Quality metrics (not just conversion):
 • % of outreach that gets a reply (any)
 • % of replies that say “good timing”
 • low follow-up requirement (fewer messages to get clarity)
 • low “creepy” responses (aim: ~0)

Energy metrics:
 • time from review → send < 10 minutes for weekly batch
 • 3–5 outreach items/week max by default

⸻

1) Implementation Plan (High-level)

 1. Add policy gate function (cooldown/stability cap)
 2. Build strategy selector (channel + CTA + value asset)
 3. Implement template library + slot filling
 4. Add critic pass (regex + rubric + LLM rewrite if needed)
 5. Persist recommendations
 6. Add API: GET /api/outreach/recommendations?week=...
 7. Add outcome capture integration (ties to outreach_history)

---

## Per-company recommendation API (Issue #122)

**Endpoint:** `GET /api/outreach/recommendation/{company_id}`

Returns the ORE recommendation kit for a single company: recommended playbook ID, draft variants, rationale, sensitivity tag, and core recommendation fields (recommendation_type, outreach_score, safeguards_triggered). Pack-scoped; all copy and recommendation types come from pack/playbook/ESL (no domain assumptions in the endpoint).

**Query parameters:**

| Parameter      | Type   | Required | Description |
|----------------|--------|----------|-------------|
| `as_of`        | date   | No       | Snapshot date (YYYY-MM-DD). Default: latest available snapshot date, or today if none. |
| `pack_id`      | UUID   | No       | Pack to use. Default: workspace active pack or app default when omitted. |
| `workspace_id` | string | No       | Workspace for pack resolution when `pack_id` omitted. When multi_workspace_enabled, defaults to default workspace if omitted. |

**Response:** JSON matching `OutreachRecommendationResponse`: `company_id`, `as_of`, `recommended_playbook_id`, `drafts`, `rationale`, `sensitivity_tag`, `recommendation_type`, `outreach_score`, `safeguards_triggered`, etc.

**404 conditions:** Company not found; or no ReadinessSnapshot for (company_id, as_of, resolved pack) — i.e. no recommendation available.

**Auth:** Same as weekly review: session auth required (`require_auth`). When multi_workspace_enabled, workspace access is enforced and effective workspace is used for pack resolution when `pack_id` is omitted.
