# Outreach Critic Rules

The draft must:

- Avoid phrases:
  - "I noticed you..."
  - "I saw that you..."
  - "After your recent funding..."
  - "You're hiring..."
- Avoid urgency language:
  - ASAP
  - urgent
  - before it's too late
  - quickly
- Contain only one CTA
- Include opt-out language
- Use short paragraphs (max 2–3 lines)
- Avoid shame framing

If violations detected:
- Rewrite once
- If still failing → mark as Manual Review Required

## Source of truth: recommendation tier order

The canonical order of recommendation tiers (Observe Only → … → Direct Strategic Outreach) is defined in `app/services/ore/critic.py` as `RECOMMENDATION_ORDER`. The ESL gate filter (`app/services/esl/esl_gate_filter.py`) must import and use this constant for tone capping; do not duplicate the list elsewhere.

## Shame framing: core + pack override (additive)

Shame framing is enforced in two layers:
- **Core:** A fixed list of shame patterns in the critic is always applied (e.g. "falling behind", "you must", "you're struggling").
- **Pack:** Playbooks may add extra phrases via `forbidden_phrases`; packs cannot remove or override core shame patterns.
