"""Scoring engine — deterministic CTO-need score from analysis results."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from app.models.app_settings import AppSettings
from app.models.company import Company

if TYPE_CHECKING:
    from app.packs.loader import Pack

logger = logging.getLogger(__name__)

# ── Default signal weights ──────────────────────────────────────────
# Each key maps to a pain-signal boolean in the analysis output.
# Value = points added when the signal is *true*.
DEFAULT_SIGNAL_WEIGHTS: dict[str, int] = {
    "hiring_engineers": 15,
    "switching_from_agency": 10,
    "adding_enterprise_features": 15,
    "compliance_security_pressure": 25,
    "product_delivery_issues": 20,
    "architecture_scaling_risk": 15,
    "founder_overload": 10,
}

# ── Stage bonuses ───────────────────────────────────────────────────
STAGE_BONUSES: dict[str, int] = {
    "scaling_team": 20,
    "enterprise_transition": 30,
    "struggling_execution": 30,
}

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


def _normalize_signals(
    signals: dict[str, Any],
    known_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Map legacy signal keys to canonical keys (Issue #64).

    known_keys: set of valid signal keys (default: DEFAULT_SIGNAL_WEIGHTS).
    Used when pack provides different weights (Issue #189, Plan Step 1.5).
    """
    known = known_keys or set(DEFAULT_SIGNAL_WEIGHTS)
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
) -> int:
    """Return a 0-100 CTO-need score from pain signals and stage.

    Parameters
    ----------
    pain_signals:
        Dict from ``AnalysisRecord.pain_signals_json``.  Accepts either the
        nested ``{"signals": {key: {"value": bool, ...}, ...}}`` format or a
        flat ``{key: {"value": bool, ...}, ...}`` format.
    stage:
        Company lifecycle stage string (e.g. ``"scaling_team"``).
    custom_weights:
        If provided, overrides defaults for matching keys only (Issue #64).
    pack:
        Optional Pack. When provided, uses pack.scoring pain_signal_weights and
        stage_bonuses (Issue #189, Plan Step 1.5). When None, uses defaults.
    """
    if not isinstance(pain_signals, dict):
        return 0

    # Base weights from pack or defaults (Issue #189, Plan Step 1.5)
    if pack is not None and isinstance(pack.scoring, dict):
        sc = pack.scoring
        weights = dict(sc.get("pain_signal_weights") or DEFAULT_SIGNAL_WEIGHTS)
        stage_bonuses = dict(sc.get("stage_bonuses") or STAGE_BONUSES)
    else:
        weights = dict(DEFAULT_SIGNAL_WEIGHTS)
        stage_bonuses = dict(STAGE_BONUSES)

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


def get_custom_weights(db: Session) -> dict[str, int] | None:
    """Load custom scoring weights from AppSettings.

    Returns ``None`` when the ``scoring_weights`` key is absent or the stored
    value is not valid JSON. Legacy keys are mapped to canonical keys (Issue #64).
    """
    row = db.query(AppSettings).filter(AppSettings.key == "scoring_weights").first()
    if row is None or row.value is None:
        return None
    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, dict):
            canonical: dict[str, int] = {}
            for k, v in parsed.items():
                ck = _LEGACY_SIGNAL_KEY_MAP.get(k, k)
                if ck in DEFAULT_SIGNAL_WEIGHTS:
                    canonical[ck] = int(round(float(v))) if isinstance(v, (int, float)) else 0
            return canonical if canonical else None
        return None
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid JSON in scoring_weights AppSettings row")
        return None


def get_display_scores_for_companies(db: Session, company_ids: list[int]) -> dict[int, int]:
    """Compute display scores from latest analysis for each company.

    Returns a dict mapping company_id -> score. Only includes companies that
    have at least one analysis. Uses the same weights as score_company
    (custom weights from Settings when set, pack config when available else defaults).
    """
    if not company_ids:
        return {}

    from app.services.pack_resolver import get_default_pack_id, resolve_pack

    custom_weights = get_custom_weights(db)
    pack_id = get_default_pack_id(db)
    pack = resolve_pack(db, pack_id) if pack_id else None
    analyses = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id.in_(company_ids))
        .order_by(AnalysisRecord.created_at.desc())
        .all()
    )
    latest_by_company: dict[int, AnalysisRecord] = {}
    for a in analyses:
        if a.company_id not in latest_by_company:
            latest_by_company[a.company_id] = a

    result: dict[int, int] = {}
    for cid, analysis in latest_by_company.items():
        pain_signals = (
            analysis.pain_signals_json if isinstance(analysis.pain_signals_json, dict) else {}
        )
        score = calculate_score(
            pain_signals=pain_signals,
            stage=analysis.stage or "",
            custom_weights=custom_weights,
            pack=pack,
        )
        result[cid] = score
    return result


def score_company(db: Session, company_id: int, analysis: AnalysisRecord) -> int:
    """Score a company from its latest analysis and persist the result.

    1. Loads optional custom weights from AppSettings.
    2. Resolves active pack when available (Issue #189, Plan Step 1.5).
    3. Computes the deterministic score.
    4. Updates ``company.cto_need_score`` and ``company.current_stage``.
    5. Commits and returns the score.
    """
    from app.services.pack_resolver import get_default_pack_id, resolve_pack

    custom_weights = get_custom_weights(db)
    pack_id = get_default_pack_id(db)
    pack = resolve_pack(db, pack_id) if pack_id else None
    pain_signals = (
        analysis.pain_signals_json if isinstance(analysis.pain_signals_json, dict) else {}
    )
    score = calculate_score(
        pain_signals=pain_signals,
        stage=analysis.stage or "",
        custom_weights=custom_weights,
        pack=pack,
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
