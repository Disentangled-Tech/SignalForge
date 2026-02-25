"""Scoring engine — deterministic CTO-need score from analysis results.

Phase 2 (CTO Pack Extraction): All weights and stage bonuses come from pack config.
No hardcoded fallbacks. When pack is None, resolves default pack from db or
loads fractional_cto_v1 from filesystem for backward compatibility.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from app.models.app_settings import AppSettings
from app.models.company import Company
from app.packs.interfaces import PackScoringInterface, adapt_pack_for_scoring

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# Legacy keys from pre-schema-change analyses (Issue #64)
# recent_funding = capital received (scaling needs); switching_from_agency = agency→in-house transition
_LEGACY_SIGNAL_KEY_MAP: dict[str, str] = {
    "hiring_technical_roles": "hiring_engineers",
    "recent_funding": "architecture_scaling_risk",
    "product_launch": "adding_enterprise_features",
    "technical_debt_indicators": "architecture_scaling_risk",
    "scaling_challenges": "architecture_scaling_risk",
    "leadership_changes": "founder_overload",
    "compliance_needs": "compliance_security_pressure",
}


def _get_signal_value(entry: dict) -> Any:
    """Return the boolean value; supports legacy 'detected' key (Issue #64)."""
    v = entry.get("value")
    if v is not None:
        return v
    return entry.get("detected")


def _get_pack_or_default(db: Session | None = None) -> Pack | None:
    """Resolve pack: from db if available, else load fractional_cto_v1 from filesystem.

    Phase 2: No hardcoded fallbacks. Used when pack is None.
    """
    from app.services.pack_resolver import get_default_pack

    return get_default_pack(db)


def _get_weights_from_pack(pack_interface: PackScoringInterface) -> tuple[dict[str, int], dict[str, int]]:
    """Extract pain_signal_weights and stage_bonuses from pack interface (Phase 1)."""
    weights = pack_interface.get_pain_signal_weights()
    stage_bonuses = pack_interface.get_stage_bonuses()
    return weights, stage_bonuses


def _normalize_signals(
    signals: dict[str, Any],
    known_keys: set[str],
) -> dict[str, Any]:
    """Map legacy signal keys to canonical keys (Issue #64).

    known_keys: set of valid signal keys from pack pain_signal_weights (Phase 2).
    """
    known = known_keys
    canonical: dict[str, Any] = {}
    for k, v in signals.items():
        canonical_key = _LEGACY_SIGNAL_KEY_MAP.get(k, k)
        if canonical_key in known:
            if canonical_key not in canonical:
                canonical[canonical_key] = v
            elif isinstance(v, dict) and _is_signal_true(_get_signal_value(v)):
                canonical[canonical_key] = v  # prefer true when merging
        elif k in known:
            canonical[k] = v
    return canonical


def _is_signal_true(val: Any) -> bool:
    """Return True if value indicates a positive pain signal.

    LLMs may return boolean True, string "true"/"True"/"yes", or int 1.
    """
    if val is True:
        return True
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1")
    if isinstance(val, (int, float)):
        return val == 1 or val == 1.0
    return False


def _sample_for_log(pain_signals: dict[str, Any] | None) -> dict:
    """Extract a small sample of pain signals for debug logging."""
    if not pain_signals:
        return {}
    signals = pain_signals.get("signals", pain_signals)
    if not isinstance(signals, dict):
        return {}
    return dict(list(signals.items())[:2])


def calculate_score(
    pain_signals: dict[str, Any],
    stage: str,
    custom_weights: dict[str, int] | dict[str, float] | None = None,
    pack: Pack | None = None,
    db: Session | None = None,
) -> int:
    """Return a 0-100 CTO-need score from pain signals and stage.

    Phase 2: All weights come from pack. No hardcoded fallbacks. When pack is
    None, resolves default pack from db or loads fractional_cto_v1 from
    filesystem. Returns 0 when no pack available.

    Parameters
    ----------
    pain_signals:
        Dict from ``AnalysisRecord.pain_signals_json``.  Accepts either the
        nested ``{"signals": {key: {"value": bool, ...}, ...}}`` format or a
        flat ``{key: {"value": bool, ...}, ...}`` format.
    stage:
        Company lifecycle stage string (e.g. ``"scaling_team"``).
    custom_weights:
        If provided, overrides pack weights for matching keys only (Issue #64).
    pack:
        Pack with pain_signal_weights and stage_bonuses. When None, resolved
        from db or filesystem.
    db:
        Optional session for resolving default pack when pack is None.
    """
    if not isinstance(pain_signals, dict):
        return 0

    effective_pack = pack if pack is not None else _get_pack_or_default(db)
    if effective_pack is None:
        return 0

    pack_interface = adapt_pack_for_scoring(effective_pack)
    weights, stage_bonuses = _get_weights_from_pack(pack_interface)
    if not weights:
        return 0

    # Merge custom weights with base so we always use canonical keys (Issue #64)
    if custom_weights is not None:
        weights = {k: custom_weights.get(k, v) for k, v in weights.items()}

    # Normalise: accept nested {"signals": {...}} or flat dict
    signals: dict[str, Any] = pain_signals.get("signals", pain_signals)
    if not isinstance(signals, dict):
        return 0

    # Map legacy keys to canonical (Issue #64)
    signals = _normalize_signals(signals, known_keys=set(weights))

    score = 0
    for key, weight in weights.items():
        entry = signals.get(key)
        if isinstance(entry, dict):
            val = _get_signal_value(entry)
            if _is_signal_true(val):
                score += weight
        elif _is_signal_true(entry):
            score += weight

    # Stage bonus
    stage_str = (stage or "").strip().lower()
    score += stage_bonuses.get(stage_str, 0)

    result = max(0, min(score, 100))
    if result == 0 and signals:
        logger.debug(
            "calculate_score=0: stage=%r signals_sample=%s",
            stage,
            dict(list(signals.items())[:3]),
        )
    return int(round(result))


def get_known_pain_signal_keys(db: Session | None = None) -> set[str]:
    """Return known pain signal keys from default pack (Phase 2).

    Used by scan_orchestrator for change detection and by get_custom_weights
    for validation. When no pack available, returns empty set.
    """
    pack = _get_pack_or_default(db)
    if pack is None:
        return set()
    pack_interface = adapt_pack_for_scoring(pack)
    weights, _ = _get_weights_from_pack(pack_interface)
    return set(weights)


def get_custom_weights(db: Session) -> dict[str, int] | None:
    """Load custom scoring weights from AppSettings.

    Returns ``None`` when the ``scoring_weights`` key is absent, the stored
    value is not valid JSON, or no pack is available for validation.
    Legacy keys are mapped to canonical keys (Issue #64).
    Phase 2: Validates keys against pack pain_signal_weights only.
    """
    pack = _get_pack_or_default(db)
    if pack is None:
        return None
    weights_dict = (pack.scoring or {}).get("pain_signal_weights") or {}
    known_keys = set(weights_dict)

    row = db.query(AppSettings).filter(AppSettings.key == "scoring_weights").first()
    if row is None or row.value is None:
        return None
    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, dict):
            canonical: dict[str, int] = {}
            for k, v in parsed.items():
                ck = _LEGACY_SIGNAL_KEY_MAP.get(k, k)
                if ck in known_keys:
                    canonical[ck] = int(round(float(v))) if isinstance(v, (int, float)) else 0
            return canonical if canonical else None
        return None
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid JSON in scoring_weights AppSettings row")
        return None


def get_display_scores_for_companies(
    db: Session,
    company_ids: list[int],
    workspace_id: str | None = None,
) -> dict[int, int]:
    """Resolve display scores for companies (pack-scoped, Phase 2/3).

    Uses batched ReadinessSnapshot + Company lookup to avoid N+1 queries.
    Returns dict company_id -> score; omits companies with no score.
    When workspace_id provided (Phase 3), pack resolved from workspace's active pack.
    """
    from app.services.score_resolver import get_company_scores_batch

    return get_company_scores_batch(db, company_ids, workspace_id=workspace_id)


def score_company(
    db: Session,
    company_id: int,
    analysis: AnalysisRecord,
    pack: Pack | None = None,
) -> int:
    """Score a company from its latest analysis and persist the result.

    1. Loads optional custom weights from AppSettings.
    2. Uses pack when provided; otherwise resolves from db (Issue #189, Plan Step 2.3).
    3. Computes the deterministic score.
    4. Updates ``company.cto_need_score`` and ``company.current_stage``.
    5. Commits and returns the score.
    """
    from app.services.pack_resolver import get_default_pack_id, resolve_pack

    custom_weights = get_custom_weights(db)
    effective_pack = pack if pack is not None else (
        resolve_pack(db, pid) if (pid := get_default_pack_id(db)) else None
    )
    pain_signals = (
        analysis.pain_signals_json if isinstance(analysis.pain_signals_json, dict) else {}
    )
    score = calculate_score(
        pain_signals=pain_signals,
        stage=analysis.stage or "",
        custom_weights=custom_weights,
        pack=effective_pack,
        db=db,
    )

    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        logger.error("score_company: company_id=%s not found", company_id)
        return score

    company.cto_need_score = score
    company.current_stage = analysis.stage
    db.commit()

    if score == 0 and (pain_signals or analysis.stage):
        logger.info(
            "score_company: company_id=%s score=0 stage=%r pain_signals_keys=%s sample=%s",
            company_id,
            analysis.stage,
            list(pain_signals.keys()),
            _sample_for_log(pain_signals),
        )
    return score
