# Outreach Recommendation Engine (ORE) — Design Spec

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

B) Strategy Selector

Chooses:
 • Channel (DM vs email)
 • Length (short by default)
 • CTA type (consent-based)
 • Value asset type (checklist, pattern note, 2-question diagnostic)

C) Draft Generator + Critic

Generate draft → run through critic checks → revise once.

Critic checks:
 • Surveillance language?
 • Urgency pressure?
 • Too many asks?
 • Clear opt-out?
 • Plain language?
 • ND-friendly formatting?

Pack playbooks may define **forbidden_phrases** (a list of strings). The critic applies these in addition to the core rules above: any draft containing a forbidden phrase (case-insensitive) fails the critic and the pipeline substitutes a compliant fallback when possible. See playbook YAML (e.g. playbooks/ore_outreach.yaml) and app/services/ore/critic.py.

Pack-driven playbooks and sensitivity (Issue #176)

ORE is pack-driven: the active pack supplies the playbook (e.g. playbooks/ore_outreach.yaml), including pattern_frames, value_assets, ctas, optional opening_templates, value_statements, forbidden_phrases, and tone. The critic applies pack forbidden_phrases in addition to core rules. Sensitivity gating is prompt-only: tone_constraint (e.g. "Soft Value Share") and playbook tone definitions are passed as TONE_INSTRUCTION so the LLM stays within the allowed tier; sensitivity_level is never sent to the LLM. See docs/playbook-draft-engine.md for YAML shape, loader, and data flow.

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
