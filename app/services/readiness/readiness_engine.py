"""v2 Readiness dimension calculators (Issue #86).

Computes M, C, P, G from SignalEvent-like objects. Uses scoring_constants
for base scores, caps, and decay. No magic numbers.

Reference: docs/v2-spec.md §4.3.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol

from app.services.readiness.scoring_constants import (
    BASE_SCORES_COMPLEXITY,
    BASE_SCORES_LEADERSHIP_GAP,
    BASE_SCORES_MOMENTUM,
    BASE_SCORES_PRESSURE,
    CAP_DIMENSION_MAX,
    CAP_FOUNDER_URGENCY,
    CAP_JOBS_COMPLEXITY,
    CAP_JOBS_MOMENTUM,
    COMPOSITE_WEIGHTS,
    QUIET_SIGNAL_AMPLIFIED_BASE,
    QUIET_SIGNAL_LOOKBACK_DAYS,
    decay_complexity,
    decay_momentum,
    decay_pressure,
    from_pack,
)

if TYPE_CHECKING:
    from app.packs.loader import Pack

# Leadership gap suppressors (v2-spec §4.3, §4.4)
SUPPRESS_CTO_HIRED_60_DAYS: int = 70
SUPPRESS_CTO_HIRED_180_DAYS: int = 50

DEFAULT_CONFIDENCE: float = 0.7

# Momentum: 120 days
WINDOW_MOMENTUM_DAYS: int = 120
# Complexity: 400 days (decay 366+ uses 0.4)
WINDOW_COMPLEXITY_DAYS: int = 400
# Pressure: 365 days (decay extends to 121+ with 0.2)
WINDOW_PRESSURE_DAYS: int = 365
# Leadership: 120 days for positive, 180 for cto_hired
WINDOW_LEADERSHIP_POSITIVE_DAYS: int = 120
WINDOW_LEADERSHIP_CTO_HIRED_DAYS: int = 180

# Job types for subscore caps
MOMENTUM_JOB_TYPES: frozenset[str] = frozenset({"job_posted_engineering", "job_posted_infra"})
COMPLEXITY_JOB_TYPES: frozenset[str] = frozenset({"job_posted_infra"})
PRESSURE_FOUNDER_URGENCY_TYPES: frozenset[str] = frozenset({"founder_urgency_language"})


class _EventLike(Protocol):
    """Minimal interface for event-like objects."""

    event_type: str
    event_time: datetime
    confidence: float | None


def _days_since(event_time: datetime, as_of: date) -> int:
    """Return days from event_time to as_of (non-negative)."""
    ev_date = (
        event_time.date()
        if hasattr(event_time, "date")
        else date(event_time.year, event_time.month, event_time.day)
    )
    delta = as_of - ev_date
    return max(0, delta.days)


def _get_confidence(ev: _EventLike) -> float:
    """Return event confidence or default."""
    c = ev.confidence
    if c is None:
        return DEFAULT_CONFIDENCE
    return max(0.0, min(1.0, float(c)))


def _has_funding_in_window(
    events: list[Any],
    as_of: date,
    window_days: int | None = None,
    _cfg: dict | None = None,
) -> bool:
    """Return True if any funding_raised event exists within window (Issue #113)."""
    if window_days is None:
        window_days = (_cfg or {}).get("quiet_signal_lookback_days", QUIET_SIGNAL_LOOKBACK_DAYS)
    for ev in events:
        if getattr(ev, "event_type", None) != "funding_raised":
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        if _days_since(ev_time, as_of) <= window_days:
            return True
    return False


def _get_effective_base(
    etype: str, dimension: str, has_funding: bool, _cfg: dict | None = None
) -> int | None:
    """Return base score for event type in dimension (Issue #113).

    When has_funding is False and etype is a quiet signal, returns amplified base.
    Otherwise returns None (caller uses normal BASE_SCORES_* lookup).
    """
    if has_funding:
        return None
    amplified = (_cfg or {}).get("quiet_signal_amplified_base") or QUIET_SIGNAL_AMPLIFIED_BASE
    amp = amplified.get(etype)
    if amp is None:
        return None
    return amp.get(dimension)


def _cfg_base(cfg: dict | None, key: str, default: dict) -> dict:
    """Return config value or default."""
    if not cfg:
        return default
    return cfg.get(key, default)


def compute_momentum(events: list[Any], as_of: date, _cfg: dict | None = None) -> int:
    """Compute Momentum (M) 0..100 from events (v2-spec §4.3).

    Window: 120 days. Jobs subscore cap 30. Total cap 100.
    Quiet signal amplification (Issue #113): job_posted_infra uses higher base when no funding.
    """
    bs = _cfg_base(_cfg, "base_scores_momentum", BASE_SCORES_MOMENTUM)
    cap_jobs = (_cfg or {}).get("cap_jobs_momentum", CAP_JOBS_MOMENTUM)
    cap_dim = (_cfg or {}).get("cap_dimension_max", CAP_DIMENSION_MAX)
    has_funding = _has_funding_in_window(events, as_of, _cfg=_cfg)
    jobs_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in bs:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_MOMENTUM_DAYS:
            continue
        base = _get_effective_base(etype, "M", has_funding, _cfg) or bs[etype]
        decay = decay_momentum(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in MOMENTUM_JOB_TYPES:
            jobs_sum += contrib
        else:
            other_sum += contrib

    jobs_capped = min(jobs_sum, cap_jobs)
    total = jobs_capped + other_sum
    return int(round(max(0, min(total, cap_dim))))


def compute_complexity(events: list[Any], as_of: date, _cfg: dict | None = None) -> int:
    """Compute Complexity (C) 0..100 from events (v2-spec §4.3).

    Window: 365 days. job_posted_infra cap 20.
    Quiet signal amplification (Issue #113): job_posted_infra, compliance_mentioned,
    api_launched use higher base when no funding.
    """
    bs = _cfg_base(_cfg, "base_scores_complexity", BASE_SCORES_COMPLEXITY)
    cap_jobs = (_cfg or {}).get("cap_jobs_complexity", CAP_JOBS_COMPLEXITY)
    cap_dim = (_cfg or {}).get("cap_dimension_max", CAP_DIMENSION_MAX)
    has_funding = _has_funding_in_window(events, as_of, _cfg=_cfg)
    job_infra_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in bs:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_COMPLEXITY_DAYS:
            continue
        base = _get_effective_base(etype, "C", has_funding, _cfg) or bs[etype]
        decay = decay_complexity(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in COMPLEXITY_JOB_TYPES:
            job_infra_sum += contrib
        else:
            other_sum += contrib

    job_infra_capped = min(job_infra_sum, cap_jobs)
    total = job_infra_capped + other_sum
    return int(round(max(0, min(total, cap_dim))))


def compute_pressure(events: list[Any], as_of: date, _cfg: dict | None = None) -> int:
    """Compute Pressure (P) 0..100 from events (v2-spec §4.3).

    Window: 120 days. founder_urgency_language cap 30.
    """
    bs = _cfg_base(_cfg, "base_scores_pressure", BASE_SCORES_PRESSURE)
    cap_founder = (_cfg or {}).get("cap_founder_urgency", CAP_FOUNDER_URGENCY)
    cap_dim = (_cfg or {}).get("cap_dimension_max", CAP_DIMENSION_MAX)
    founder_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in bs:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_PRESSURE_DAYS:
            continue
        base = bs[etype]
        decay = decay_pressure(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in PRESSURE_FOUNDER_URGENCY_TYPES:
            founder_sum += contrib
        else:
            other_sum += contrib

    founder_capped = min(founder_sum, cap_founder)
    total = founder_capped + other_sum
    return int(round(max(0, min(total, cap_dim))))


def compute_leadership_gap(events: list[Any], as_of: date, _cfg: dict | None = None) -> int:
    """Compute Leadership Gap (G) 0..100 from events (v2-spec §4.3, §4.4).

    State-based. cto_hired suppresses: 60d → -70, 180d → -50.
    """
    raw_g = 0.0
    cto_hired_days: int | None = None
    bs = _cfg_base(_cfg, "base_scores_leadership_gap", BASE_SCORES_LEADERSHIP_GAP)
    cap_dim = (_cfg or {}).get("cap_dimension_max", CAP_DIMENSION_MAX)
    suppress_60 = (_cfg or {}).get("suppress_cto_hired_60_days", SUPPRESS_CTO_HIRED_60_DAYS)
    suppress_180 = (_cfg or {}).get("suppress_cto_hired_180_days", SUPPRESS_CTO_HIRED_180_DAYS)

    for ev in events:
        etype = getattr(ev, "event_type", None)
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)

        if etype == "cto_hired":
            if days <= WINDOW_LEADERSHIP_CTO_HIRED_DAYS:
                if cto_hired_days is None or days < cto_hired_days:
                    cto_hired_days = days
            continue

        if etype not in bs:
            continue

        if etype in ("cto_role_posted", "fractional_request", "advisor_request"):
            if days > WINDOW_LEADERSHIP_POSITIVE_DAYS:
                continue
        elif etype == "no_cto_detected":
            if days > 365:  # 365 days per spec
                continue
        else:
            continue

        base = bs[etype]
        # State-based: no decay; spec does not mention confidence for G
        raw_g += base

    g = int(round(max(0, min(raw_g, cap_dim))))

    if cto_hired_days is not None:
        if cto_hired_days <= 60:
            g = max(0, g - suppress_60)
        else:
            g = max(0, g - suppress_180)

    return g


def compute_composite(M: int, C: int, P: int, G: int, _cfg: dict | None = None) -> int:
    """Compute composite readiness R from dimensions (v2-spec §4.1).

    R = round(0.30*M + 0.30*C + 0.25*P + 0.15*G), clamped 0..100.
    """
    cw = (_cfg or {}).get("composite_weights", COMPOSITE_WEIGHTS)
    cap_dim = (_cfg or {}).get("cap_dimension_max", CAP_DIMENSION_MAX)
    raw = (
        cw.get("M", COMPOSITE_WEIGHTS["M"]) * M
        + cw.get("C", COMPOSITE_WEIGHTS["C"]) * C
        + cw.get("P", COMPOSITE_WEIGHTS["P"]) * P
        + cw.get("G", COMPOSITE_WEIGHTS["G"]) * G
    )
    return int(round(max(0, min(raw, cap_dim))))


def apply_global_suppressors(
    M: int, C: int, P: int, G: int, company_status: str | None = None
) -> tuple[int, int, int, int, list[str]]:
    """Apply global suppressors (v2-spec §4.4).

    If company_status in (acquired, dead): zero all dimensions.
    Returns (M, C, P, G, suppressors_applied).
    """
    if company_status and company_status.strip().lower() in ("acquired", "dead"):
        return (0, 0, 0, 0, ["company_status_suppressed"])
    return (M, C, P, G, [])


def _event_contribution_to_dimension(
    ev: Any,
    etype: str,
    days: int,
    dimension: str,
    has_funding: bool = True,
    _cfg: dict | None = None,
) -> float:
    """Compute single event's contribution to a dimension (base * decay * confidence).

    Issue #113: quiet signals use amplified base when has_funding is False.
    """
    conf = _get_confidence(ev)
    bs_m = _cfg_base(_cfg, "base_scores_momentum", BASE_SCORES_MOMENTUM)
    bs_c = _cfg_base(_cfg, "base_scores_complexity", BASE_SCORES_COMPLEXITY)
    bs_p = _cfg_base(_cfg, "base_scores_pressure", BASE_SCORES_PRESSURE)
    bs_g = _cfg_base(_cfg, "base_scores_leadership_gap", BASE_SCORES_LEADERSHIP_GAP)
    if dimension == "M" and etype in bs_m:
        base = _get_effective_base(etype, "M", has_funding, _cfg) or bs_m[etype]
        return base * decay_momentum(days) * conf
    if dimension == "C" and etype in bs_c:
        base = _get_effective_base(etype, "C", has_funding, _cfg) or bs_c[etype]
        return base * decay_complexity(days) * conf
    if dimension == "P" and etype in bs_p:
        base = bs_p[etype]
        return base * decay_pressure(days) * conf
    if dimension == "G" and etype in bs_g and etype != "cto_hired":
        base = bs_g[etype]
        return base  # state-based, no decay
    return 0.0


def compute_event_contributions(
    events: list[Any], as_of: date, limit: int = 8, _cfg: dict | None = None
) -> list[dict[str, Any]]:
    """Compute per-event contribution points for top_events (v2-spec §4.5).

    Each event's contribution is the sum of its contributions across dimensions.
    Returns up to limit items, sorted by contribution desc.
    Issue #113: uses has_funding for quiet signal amplification in contribution_points.
    """
    has_funding = _has_funding_in_window(events, as_of, _cfg=_cfg)
    scored: list[tuple[float, Any]] = []

    for ev in events:
        etype = getattr(ev, "event_type", None)
        ev_time = getattr(ev, "event_time", None)
        if etype is None or ev_time is None:
            continue
        days = _days_since(ev_time, as_of)

        total = 0.0
        for dim in ("M", "C", "P", "G"):
            total += _event_contribution_to_dimension(
                ev, etype, days, dim, has_funding=has_funding, _cfg=_cfg
            )

        if total > 0:
            scored.append((total, ev))

    scored.sort(key=lambda x: -x[0])

    result: list[dict[str, Any]] = []
    for contrib, ev in scored[:limit]:
        ev_time = getattr(ev, "event_time", None)
        event_time_iso = ev_time.isoformat() if ev_time and hasattr(ev_time, "isoformat") else ""
        result.append(
            {
                "event_type": getattr(ev, "event_type", ""),
                "event_time": event_time_iso,
                "source": getattr(ev, "source", "") or "",
                "url": getattr(ev, "url", "") or "",
                "contribution_points": round(contrib, 1),
                "confidence": _get_confidence(ev),
            }
        )
    return result


def build_explain_payload(
    M: int,
    C: int,
    P: int,
    G: int,
    R: int,
    top_events: list[dict[str, Any]],
    suppressors_applied: list[str],
    quiet_signal_amplification_applied: list[str] | None = None,
    _cfg: dict | None = None,
) -> dict[str, Any]:
    """Build explain JSON payload (v2-spec §4.5).

    Issue #113: quiet_signal_amplification_applied lists event types that received
    amplified base when company had no funding in lookback window.
    """
    cw = (_cfg or {}).get("composite_weights", COMPOSITE_WEIGHTS)
    payload: dict[str, Any] = {
        "weights": dict(cw),
        "dimensions": {"M": M, "C": C, "P": P, "G": G, "R": R},
        "top_events": top_events,
        "suppressors_applied": suppressors_applied,
    }
    if quiet_signal_amplification_applied:
        payload["quiet_signal_amplification_applied"] = quiet_signal_amplification_applied
    return payload


def compute_readiness(
    events: list[Any],
    as_of: date,
    company_status: str | None = None,
    top_events_limit: int = 8,
    pack: Pack | None = None,
) -> dict[str, Any]:
    """Compute M, C, P, G, composite, and explain payload (Issue #87).

    Returns dict suitable for ReadinessSnapshot: momentum, complexity, pressure,
    leadership_gap, composite, explain.
    Issue #113: quiet signal amplification applied when no funding in lookback.
    When pack is provided, uses pack scoring config; otherwise uses default constants.
    """
    _cfg: dict | None = None
    if pack is not None:
        _cfg = from_pack(pack.scoring)

    M = compute_momentum(events, as_of, _cfg=_cfg)
    C = compute_complexity(events, as_of, _cfg=_cfg)
    P = compute_pressure(events, as_of, _cfg=_cfg)
    G = compute_leadership_gap(events, as_of, _cfg=_cfg)

    M, C, P, G, suppressors_applied = apply_global_suppressors(M, C, P, G, company_status)

    R = compute_composite(M, C, P, G, _cfg=_cfg)

    top_events = compute_event_contributions(events, as_of, limit=top_events_limit, _cfg=_cfg)

    has_funding = _has_funding_in_window(events, as_of, _cfg=_cfg)
    quiet_base = (_cfg or {}).get("quiet_signal_amplified_base", QUIET_SIGNAL_AMPLIFIED_BASE)
    event_types_present = {getattr(ev, "event_type", "") for ev in events}
    quiet_amplified = [t for t in quiet_base if t in event_types_present] if not has_funding else []

    explain = build_explain_payload(
        M, C, P, G, R, top_events, suppressors_applied, quiet_amplified, _cfg=_cfg
    )

    return {
        "momentum": M,
        "complexity": C,
        "pressure": P,
        "leadership_gap": G,
        "composite": R,
        "explain": explain,
    }
