# Parameterized Outreach Template Library (Issue #118)

## Purpose

The template library provides a centralized, parameterized store of outreach message templates for the Outreach Recommendation Engine (ORE). Templates are keyed by **outreach type** and **channel** (DM, Email). They use a fixed set of placeholders so that drafts can be filled consistently without hard-coded signals or surveillance language. The library supports:

- Consistent fallback drafts when the critic rejects an LLM-generated draft
- Future use for template-only or hybrid draft modes (out of scope for initial implementation)
- A single place to enforce critic-aligned rules in template content

Templates are **config/content only** — no database tables. Pack overrides (e.g. per-pack template files or playbook keys) are deferred to a later phase.

---

## Placeholder Contract

All templates in the library **must** use the following placeholders. Resolution substitutes these with concrete values (e.g. founder name, company name, chosen pattern frame from the playbook).

| Placeholder       | Description |
|-------------------|-------------|
| `{founder_name}`  | Founder or primary contact name |
| `{company_name}`  | Company name |
| `{pattern_frame}` | Generic pattern frame (e.g. “When a team’s pace picks up…”) — never event-specific |
| `{value_asset}`   | Lightweight offer (e.g. “2-page Tech Inflection Checklist”) |
| `{cta}`           | Single consent-based call-to-action (e.g. “Want me to send that checklist?”) |

**Opt-out:** Every template **must** include a clear opt-out line. This may be fixed text (e.g. “No worries if now isn’t the time.”) or a placeholder such as `{opt_out}` if the resolution layer supports it. The contract is: the **resolved** message must contain explicit opt-out language; templates are written to satisfy this.

---

## Outreach Types and Channels

- **Outreach types:** Soft Value Share, Low-Pressure Intro, Standard Outreach, Direct Strategic Outreach (aligned with ESL recommendation types; Observe Only has no message template).
- **Channels:** DM (e.g. LinkedIn), Email.

The library holds one template per (outreach_type, channel) pair — e.g. `soft_value_share_dm`, `soft_value_share_email`, through `direct_strategic_outreach_email`.

---

## Template Rules (Critic-Aligned)

Templates must be written so that **any** resolved instance (with valid placeholder values) can pass the ORE critic. See [critic_rules.md](critic_rules.md) and `app/services/ore/critic.py`.

1. **No surveillance language**  
   No “I noticed you…”, “I saw that you…”, “After your recent funding…”, “You’re hiring…”, or any reference to specific signals/events. Use only generic pattern frames (e.g. “When teams scale…”).

2. **No urgency language**  
   No “ASAP”, “urgent”, “before it’s too late”, “quickly”, or similar.

3. **Single CTA**  
   One clear, consent-based ask (e.g. “Want me to send X?”, “Open to a 15-min chat?”). No multiple CTAs.

4. **Opt-out line**  
   Resolved message must include explicit opt-out (e.g. “No worries if now isn’t the time.”).

5. **Short paragraphs**  
   Max 2–3 lines per paragraph; ND-friendly formatting.

6. **No shame framing**  
   No “falling behind”, “must”, “should” in a pressuring sense.

7. **Pack forbidden_phrases**  
   At resolution time, the critic still applies pack-level `forbidden_phrases`. Template **content** should avoid any phrase that is commonly forbidden; manual check per acceptance criteria ensures no conflict with active pack rules.

---

## How Templates Map to Critic Rules

- **Manual check (DoD):** Each template in the library is reviewed so that when placeholders are filled with typical values, the resulting text passes `check_critic` (surveillance, urgency, CTA count, opt-out, short paragraphs). No surveillance or event-specific text is allowed in the template body.
- **Runtime:** When a resolved template is used (e.g. as fallback), the pipeline runs the same critic on the resolved draft; the template is written so that this passes for valid inputs.
- **Suppressed signals / forbidden_phrases:** The critic may still run with `forbidden_phrases` and suppressed-signal phrase checks. Template text does not reference specific signals, so it will not trigger those; any pack-specific forbidden phrase must not appear in the template (manual review).

---

## Reference

- **ORE design:** [Outreach-Recommendation-Engine-ORE-design-spec.md](Outreach-Recommendation-Engine-ORE-design-spec.md) — “Parameterized template library” section and Message Template Library.
- **Critic rules:** [critic_rules.md](critic_rules.md), `app/services/ore/critic.py`.
- **Issue:** #118 (Parameterized Outreach Template Library).
