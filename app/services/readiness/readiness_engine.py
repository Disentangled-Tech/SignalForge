"""v2 Readiness dimension calculators (Issue #86).

Computes M, C, P, G from SignalEvent-like objects. Uses scoring_constants
for base scores, caps, and decay. No magic numbers.

Reference: docs/v2-spec.md §4.3.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Protocol

from app.services.readiness.scoring_constants import (
    BASE_SCORES_COMPLEXITY,
    BASE_SCORES_LEADERSHIP_GAP,
    BASE_SCORES_MOMENTUM,
    BASE_SCORES_PRESSURE,
    CAP_DIMENSION_MAX,
    CAP_FOUNDER_URGENCY,
    CAP_JOBS_COMPLEXITY,
    CAP_JOBS_MOMENTUM,
    decay_complexity,
    decay_momentum,
    decay_pressure,
)

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
MOMENTUM_JOB_TYPES: frozenset[str] = frozenset(
    {"job_posted_engineering", "job_posted_infra"}
)
COMPLEXITY_JOB_TYPES: frozenset[str] = frozenset({"job_posted_infra"})
PRESSURE_FOUNDER_URGENCY_TYPES: frozenset[str] = frozenset(
    {"founder_urgency_language"}
)


class _EventLike(Protocol):
    """Minimal interface for event-like objects."""

    event_type: str
    event_time: datetime
    confidence: float | None


def _days_since(event_time: datetime, as_of: date) -> int:
    """Return days from event_time to as_of (non-negative)."""
    ev_date = event_time.date() if hasattr(event_time, "date") else date(event_time.year, event_time.month, event_time.day)
    delta = as_of - ev_date
    return max(0, delta.days)


def _get_confidence(ev: _EventLike) -> float:
    """Return event confidence or default."""
    c = ev.confidence
    if c is None:
        return DEFAULT_CONFIDENCE
    return max(0.0, min(1.0, float(c)))


def compute_momentum(events: list[Any], as_of: date) -> int:
    """Compute Momentum (M) 0..100 from events (v2-spec §4.3).

    Window: 120 days. Jobs subscore cap 30. Total cap 100.
    """
    jobs_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in BASE_SCORES_MOMENTUM:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_MOMENTUM_DAYS:
            continue
        base = BASE_SCORES_MOMENTUM[etype]
        decay = decay_momentum(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in MOMENTUM_JOB_TYPES:
            jobs_sum += contrib
        else:
            other_sum += contrib

    jobs_capped = min(jobs_sum, CAP_JOBS_MOMENTUM)
    total = jobs_capped + other_sum
    return int(round(max(0, min(total, CAP_DIMENSION_MAX))))


def compute_complexity(events: list[Any], as_of: date) -> int:
    """Compute Complexity (C) 0..100 from events (v2-spec §4.3).

    Window: 365 days. job_posted_infra cap 20.
    """
    job_infra_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in BASE_SCORES_COMPLEXITY:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_COMPLEXITY_DAYS:
            continue
        base = BASE_SCORES_COMPLEXITY[etype]
        decay = decay_complexity(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in COMPLEXITY_JOB_TYPES:
            job_infra_sum += contrib
        else:
            other_sum += contrib

    job_infra_capped = min(job_infra_sum, CAP_JOBS_COMPLEXITY)
    total = job_infra_capped + other_sum
    return int(round(max(0, min(total, CAP_DIMENSION_MAX))))


def compute_pressure(events: list[Any], as_of: date) -> int:
    """Compute Pressure (P) 0..100 from events (v2-spec §4.3).

    Window: 120 days. founder_urgency_language cap 30.
    """
    founder_sum = 0.0
    other_sum = 0.0

    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in BASE_SCORES_PRESSURE:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        days = _days_since(ev_time, as_of)
        if days > WINDOW_PRESSURE_DAYS:
            continue
        base = BASE_SCORES_PRESSURE[etype]
        decay = decay_pressure(days)
        conf = _get_confidence(ev)
        contrib = base * decay * conf
        if etype in PRESSURE_FOUNDER_URGENCY_TYPES:
            founder_sum += contrib
        else:
            other_sum += contrib

    founder_capped = min(founder_sum, CAP_FOUNDER_URGENCY)
    total = founder_capped + other_sum
    return int(round(max(0, min(total, CAP_DIMENSION_MAX))))


def compute_leadership_gap(events: list[Any], as_of: date) -> int:
    """Compute Leadership Gap (G) 0..100 from events (v2-spec §4.3, §4.4).

    State-based. cto_hired suppresses: 60d → -70, 180d → -50.
    """
    raw_g = 0.0
    cto_hired_days: int | None = None

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

        if etype not in BASE_SCORES_LEADERSHIP_GAP:
            continue
        if etype == "cto_hired":
            continue  # already handled

        if etype in ("cto_role_posted", "fractional_request", "advisor_request"):
            if days > WINDOW_LEADERSHIP_POSITIVE_DAYS:
                continue
        elif etype == "no_cto_detected":
            if days > 365:  # 365 days per spec
                continue
        else:
            continue

        base = BASE_SCORES_LEADERSHIP_GAP[etype]
        # State-based: no decay; spec does not mention confidence for G
        raw_g += base

    g = int(round(max(0, min(raw_g, CAP_DIMENSION_MAX))))

    if cto_hired_days is not None:
        if cto_hired_days <= 60:
            g = max(0, g - SUPPRESS_CTO_HIRED_60_DAYS)
        else:
            g = max(0, g - SUPPRESS_CTO_HIRED_180_DAYS)

    return g
