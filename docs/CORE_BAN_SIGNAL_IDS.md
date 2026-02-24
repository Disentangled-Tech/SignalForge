# CORE_BAN_SIGNAL_IDS — Runtime Signal-Level Suppression

**Location:** `app/services/esl/esl_decision.py`  
**Related:** ADR-006 (Core-Enforced Hard Ethical Bans), Issue #175

## Purpose

`CORE_BAN_SIGNAL_IDS` is a frozenset of signal IDs that **always** trigger `suppress` in the ESL decision gate, regardless of pack policy. Pack config cannot override this; it is enforced before any pack-level rules (blocked_signals, prohibited_combinations, etc.).

This complements ADR-006 pack-level bans: packs cannot set `allow_*` keys to loosen core restrictions. `CORE_BAN_SIGNAL_IDS` adds a **signal-level** runtime check for signals that imply protected attributes, distress, or other ethically prohibited content.

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

- **Do not** add signals that packs may legitimately use with additional safeguards (e.g. distress with tone constraints). Use pack-level `blocked_signals` or `downgrade_rules` instead.
- **Do** add signals that imply content packs must never surface (protected attributes, exploitation, high-sensitivity distress).
- Changes require maintainer review; this is a security/ethics boundary.
