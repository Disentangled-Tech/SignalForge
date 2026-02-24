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

⸻

1) Outreach Types and What They Mean

Observe Only

When:
 • cooldown active
 • instability high
 • low confidence or low alignment

Output:
 • No message draft
 • “watch trigger”: what signal would move them to Soft Value Share

⸻

Soft Value Share (default for instability/high pressure)

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
