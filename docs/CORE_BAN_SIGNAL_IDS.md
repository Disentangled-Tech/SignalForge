# CORE_BAN_SIGNAL_IDS — Runtime Signal-Level Suppression

**Location:** `app/services/esl/esl_decision.py`  
**Related:** ADR-006 (Core-Enforced Hard Ethical Bans), Issue #175, #148 (Sensitivity System)

## Purpose

`CORE_BAN_SIGNAL_IDS` is a frozenset of signal IDs that **always** trigger `suppress` in the ESL decision gate, regardless of pack policy. Pack config cannot override this; it is enforced before any pack-level rules (blocked_signals, prohibited_combinations, etc.).

Core hard bans exist for two categories only:

1. **Protected attributes** — Signals that infer or expose legally or ethically protected characteristics (e.g. demographic, health, neurodivergence). These must never be inferred, stored, or surfaced; core ban ensures no pack can allow them.
2. **Distress-exploitation patterns** — Signals that indicate acute distress or vulnerability where any outreach would be exploitative (e.g. crisis, imminent harm). Pack-level downgrade or tone constraints are not sufficient; the entity must not be recommended for outreach at all.

This complements ADR-006 pack-level bans: packs cannot set `allow_*` keys to loosen core restrictions. Do **not** use `CORE_BAN_SIGNAL_IDS` for pack-specific business rules (e.g. "no financial_distress for bookkeeping"); use pack `blocked_signals` or `downgrade_rules` instead.

## Criteria for Adding Signal IDs

A signal ID belongs in `CORE_BAN_SIGNAL_IDS` **only if** all of the following hold:

- **Protected-attribute or distress-exploitation:** The signal implies (a) a protected attribute that must never be inferred/surfaced, or (b) a distress-exploitation case where any outreach is prohibited (not just constrained).
- **Cross-pack:** The prohibition should apply to **every** pack; no pack may legitimately allow the signal with safeguards.
- **Signal-level:** The prohibition is best expressed as "this signal ID always → suppress," not as a combination (use pack `prohibited_combinations` for combinations) or as a downgrade (use pack `downgrade_rules` or `sensitivity_mapping`).

If a signal is pack-specific (e.g. "block financial_distress for bookkeeping but allow with constraints elsewhere"), do **not** add it to `CORE_BAN_SIGNAL_IDS`; add it to the pack's `blocked_signals` or use `sensitivity_mapping` + downgrade rules instead.

## Current State

- **Phase 1:** `CORE_BAN_SIGNAL_IDS` is empty (`frozenset()`).
- No signals currently trigger core-ban suppression at runtime.
- Pack-level validation (`validate_esl_policy_against_core_bans`) remains the primary enforcement for core ethical bans.

## How to Extend

When adding a new core-banned signal:

1. **Define the signal** in the pack taxonomy (e.g. `distress_mentioned`, `bankruptcy_filed`) if it is pack-specific, or in a shared taxonomy if cross-pack.

2. **Add to `CORE_BAN_SIGNAL_IDS`** in `app/services/esl/esl_decision.py`:

   ```python
   CORE_BAN_SIGNAL_IDS: frozenset[str] = frozenset({
       "distress_mentioned",
       "bankruptcy_filed",
       # Add signal IDs here
   })
   ```

3. **Ensure pack taxonomy includes the signal** so that:
   - Derivers can emit it (if applicable)
   - Schema validation accepts it in blocked_signals/prohibited_combinations
   - SignalInstance records can reference it

4. **Document** the signal and rationale (e.g. in this doc or an ADR amendment).

5. **Test** that entities with the signal receive `esl_decision="suppress"` and `reason_code="core_ban"`.

## Constraints

- **Do not** add signals that packs may legitimately use with additional safeguards (e.g. distress with tone constraints). Use pack-level `blocked_signals`, `downgrade_rules`, or `sensitivity_mapping` instead.
- **Do** add only signals that meet the criteria above (protected attributes or distress-exploitation, cross-pack, signal-level).
- Changes require maintainer review; this is a security/ethics boundary.
