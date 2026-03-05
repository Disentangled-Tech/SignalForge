# Outreach Critic Rules

The draft must:

- **Surveillance / source-revealing:** Avoid phrases such as "I noticed you...", "I saw that you...", "After your recent funding...", "You're hiring..."
- **Urgency:** No ASAP, urgent, before it's too late, quickly
- **Single CTA:** Contain only one call-to-action
- **Opt-out:** Include opt-out language (e.g. "No worries if now isn't the time")
- **Format:** Short paragraphs (max 2–3 lines)
- **Shame framing:** Avoid shame framing (enforced via core list + pack forbidden_phrases; see below)

**Pack-aware checks (Issue #120):** When the ORE pipeline passes optional context, the critic also enforces:

- **Pack forbidden_phrases:** Any phrase in the playbook's `forbidden_phrases` list (case-insensitive) fails the critic. Packs may add shaming or domain-specific phrases here; they are additive to the core list.
- **Suppressed-signal mention:** Draft must not contain reference phrases for signals that are core-banned or pack-blocked (or in prohibited_combinations). The pipeline passes the set of entity signal IDs that must not be referenced; the critic uses a core phrase map (`app/services/ore/suppressed_signal_phrases`) to detect mentions. See [CORE_BAN_SIGNAL_IDS.md](CORE_BAN_SIGNAL_IDS.md) for core bans and critic behavior.
- **Tone tier:** When `tone_constraint` is set (e.g. "Soft Value Share"), the draft must not contain phrases that imply a higher recommendation tier.

If violations detected:

- Pipeline may try fallback draft or template once
- If still failing → store draft for manual review, set strategy_notes with violation summary, and log violation_type, pack_id, signal_id (when applicable)

## Source of truth: recommendation tier order

The canonical order of recommendation tiers (Observe Only → … → Direct Strategic Outreach) is defined in `app/services/ore/critic.py` as `RECOMMENDATION_ORDER`. The ESL gate filter (`app/services/esl/esl_gate_filter.py`) must import and use this constant for tone capping; do not duplicate the list elsewhere.

## Shame framing: core + pack override (additive)

Shame framing is enforced in two layers:
- **Core:** A fixed list of shame patterns in the critic is always applied (e.g. "falling behind", "you must", "you're struggling").
- **Pack:** Playbooks may add extra phrases via `forbidden_phrases`; packs cannot remove or override core shame patterns.
