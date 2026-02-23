# Deprecation Path for Hardcoded Constants (Issue #172, Phase 4)

After Phase 2 (CTO Pack Extraction), pack config is the single source of truth. The following constants remain only as fallbacks when `pack=None` (e.g. pack load failure, ingest before pack resolution).

## Deprecated / Fallback-Only Constants

| Constant | Location | Deprecation | Preferred Source |
|----------|----------|-------------|-------------------|
| `SIGNAL_EVENT_TYPES` | `app/ingestion/event_types.py` | Deprecated when pack always available | `pack.taxonomy.signal_ids` |
| `SVI_EVENT_TYPES` | `app/services/esl/esl_constants.py` | Fallback-only | `pack.esl_policy.svi_event_types` |

## Usage

- **Normalization**: `normalize._is_valid_event_type_for_pack` uses pack taxonomy when pack provided; else `event_types.is_valid_event_type` (SIGNAL_EVENT_TYPES).
- **ESL SVI**: `esl_engine.compute_svi` uses `pack.esl_policy.svi_event_types` when pack provided; else `SVI_EVENT_TYPES`.

## Removal

No removal planned. These constants provide resilience when pack load fails or pack is unavailable. Removing them would require guaranteeing pack is always available at runtime.
