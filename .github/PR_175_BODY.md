# ESL Pack Policy Binding — Phases 1–4 (Closes #175)

Implements the Engagement Suitability Layer (ESL) decision gate with pack policy binding per [Issue #175](https://github.com/Disentangled-Tech/SignalForge/issues/175).

## Summary

- **Phase 1:** Extend esl_policy schema (blocked_signals, sensitivity_mapping, prohibited_combinations, downgrade_rules); create `evaluate_esl_decision`; fractional_cto_v1 parity
- **Phase 2:** Integrate ESL decision into engagement snapshot writer; store in explain
- **Phase 3:** Briefing/ORE filter suppressed entities; apply tone constraints for allow_with_constraints
- **Phase 4:** Dedicated columns (esl_decision, esl_reason_code, sensitivity_level); migration backfill; JobRun audit

## Key Changes

### Schema (`app/packs/schemas.py`)
- Validate `blocked_signals`, `sensitivity_mapping`, `prohibited_combinations`, `downgrade_rules` when present
- All entries must reference taxonomy signal_ids

### ESL Decision (`app/services/esl/esl_decision.py`)
- `evaluate_esl_decision(signal_ids, pack)` → allow | allow_with_constraints | suppress
- Logic: core bans → blocked_signals → prohibited_combinations → downgrade_rules → sensitivity → allow
- `CORE_BAN_SIGNAL_IDS` (empty for Phase 1; see `docs/CORE_BAN_SIGNAL_IDS.md` for extension)

### Pack (`packs/fractional_cto_v1/esl_policy.yaml`)
- `blocked_signals: []`, `prohibited_combinations: []` for parity

### Documentation
- `docs/CORE_BAN_SIGNAL_IDS.md` — extension guidance for core-banned signals

## Verification

- [x] Fractional CTO behavior unchanged (parity tests pass)
- [x] All tests pass with `pytest tests/ -v -W error`
- [x] Ruff clean on modified files
- [x] Maintainer review: Safe to merge

## References

- Plan: `.cursor/plans/esl_pack_policy_binding_12b81103.plan.md`
- Issue: #175
