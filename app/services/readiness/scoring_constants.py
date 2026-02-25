"""v2 Readiness scoring constants and decay functions (Issue #85).

Centralized configuration for the Readiness Scoring Engine. No magic numbers
inside the scoring engine — all values defined here.

Defaults match fractional_cto_v1; used when pack=None (legacy path or
pre-backfill) or when pack scoring config omits a section (fallback in
from_pack()). When a pack is provided, use from_pack() to build
engine-compatible constants from pack scoring config.

When pack is provided, no startup assumptions. All values come from pack or
explicit fallback in from_pack(). No code path uses module constants when
_cfg has a value for that key.

Reference: docs/v2-spec.md §4.
"""

from __future__ import annotations

from typing import Any

# ── Base scores per event type (v2-spec §4.3) ───────────────────────────

BASE_SCORES_MOMENTUM: dict[str, int] = {
    "funding_raised": 35,
    "job_posted_engineering": 10,
    "job_posted_infra": 10,
    "headcount_growth": 20,
    "launch_major": 15,
}

BASE_SCORES_COMPLEXITY: dict[str, int] = {
    "api_launched": 25,
    "ai_feature_launched": 25,
    "enterprise_feature": 20,
    "compliance_mentioned": 15,
    "job_posted_infra": 10,
}

BASE_SCORES_PRESSURE: dict[str, int] = {
    "enterprise_customer": 25,
    "regulatory_deadline": 30,
    "founder_urgency_language": 15,
    "revenue_milestone": 15,
    "funding_raised": 20,
}

BASE_SCORES_LEADERSHIP_GAP: dict[str, int] = {
    "cto_role_posted": 70,
    "fractional_request": 60,
    "advisor_request": 60,
    "no_cto_detected": 40,
}

# ── Quiet Signal Amplification (Issue #113, v2PRD §6.4) ────────────────────
# When company has NO funding_raised in lookback window, apply higher base
# for: job_posted_infra, compliance_mentioned, api_launched. Prevents venture-only bias.
QUIET_SIGNAL_LOOKBACK_DAYS: int = 365
QUIET_SIGNAL_AMPLIFIED_BASE: dict[str, dict[str, int]] = {
    "job_posted_infra": {"M": 20, "C": 20},
    "compliance_mentioned": {"C": 25},
    "api_launched": {"C": 35},
}

# ── Caps (v2-spec §4.3) ─────────────────────────────────────────────────

CAP_JOBS_MOMENTUM: int = 30
CAP_JOBS_COMPLEXITY: int = 20
CAP_FOUNDER_URGENCY: int = 30
CAP_DIMENSION_MAX: int = 100

# ── Composite weights (v2-spec §4.1) ───────────────────────────────────

COMPOSITE_WEIGHTS: dict[str, float] = {
    "M": 0.30,
    "C": 0.30,
    "P": 0.25,
    "G": 0.15,
}

# ── Decay breakpoints (v2-spec §4.2) ───────────────────────────────────

# Momentum: fast decay — 0–30: 1.0, 31–60: 0.7, 61–90: 0.4, 91+: 0.0
DECAY_MOMENTUM_0_30: float = 1.0
DECAY_MOMENTUM_31_60: float = 0.7
DECAY_MOMENTUM_61_90: float = 0.4
DECAY_MOMENTUM_91_PLUS: float = 0.0

# Pressure: medium decay — 0–30: 1.0, 31–60: 0.85, 61–120: 0.6, 121+: 0.2
DECAY_PRESSURE_0_30: float = 1.0
DECAY_PRESSURE_31_60: float = 0.85
DECAY_PRESSURE_61_120: float = 0.6
DECAY_PRESSURE_121_PLUS: float = 0.2

# Complexity: slow decay — 0–90: 1.0, 91–180: 0.8, 181–365: 0.6, 366+: 0.4
DECAY_COMPLEXITY_0_90: float = 1.0
DECAY_COMPLEXITY_91_180: float = 0.8
DECAY_COMPLEXITY_181_365: float = 0.6
DECAY_COMPLEXITY_366_PLUS: float = 0.4

# ── Leadership gap suppressors (v2-spec §4.4, Issue #174) ─────────────────
# cto_hired within 60 days: subtract 70 from G; within 180 days: subtract 50
SUPPRESS_CTO_HIRED_60_DAYS: int = 70
SUPPRESS_CTO_HIRED_180_DAYS: int = 50

# Default decay breakpoints as (max_days_inclusive, multiplier) for _decay_from_cfg
# Momentum: 0–30: 1.0, 31–60: 0.7, 61–90: 0.4, 91+: 0.0
DEFAULT_DECAY_MOMENTUM: list[tuple[int, float]] = [
    (30, DECAY_MOMENTUM_0_30),
    (60, DECAY_MOMENTUM_31_60),
    (90, DECAY_MOMENTUM_61_90),
    (9999, DECAY_MOMENTUM_91_PLUS),
]
# Pressure: 0–30: 1.0, 31–60: 0.85, 61–120: 0.6, 121+: 0.2
DEFAULT_DECAY_PRESSURE: list[tuple[int, float]] = [
    (30, DECAY_PRESSURE_0_30),
    (60, DECAY_PRESSURE_31_60),
    (120, DECAY_PRESSURE_61_120),
    (9999, DECAY_PRESSURE_121_PLUS),
]
# Complexity: 0–90: 1.0, 91–180: 0.8, 181–365: 0.6, 366+: 0.4
DEFAULT_DECAY_COMPLEXITY: list[tuple[int, float]] = [
    (90, DECAY_COMPLEXITY_0_90),
    (180, DECAY_COMPLEXITY_91_180),
    (365, DECAY_COMPLEXITY_181_365),
    (9999, DECAY_COMPLEXITY_366_PLUS),
]


def decay_momentum(days: int) -> float:
    """Return momentum decay multiplier for given days since event.

    Momentum decays fast (v2-spec §4.2):
    - 0–30 days: 1.0
    - 31–60 days: 0.7
    - 61–90 days: 0.4
    - 91+ days: 0.0

    Negative days are treated as 0.
    """
    if days < 0:
        days = 0
    if days <= 30:
        return DECAY_MOMENTUM_0_30
    if days <= 60:
        return DECAY_MOMENTUM_31_60
    if days <= 90:
        return DECAY_MOMENTUM_61_90
    return DECAY_MOMENTUM_91_PLUS


def decay_pressure(days: int) -> float:
    """Return pressure decay multiplier for given days since event.

    Pressure decays medium (v2-spec §4.2):
    - 0–30 days: 1.0
    - 31–60 days: 0.85
    - 61–120 days: 0.6
    - 121+ days: 0.2

    Negative days are treated as 0.
    """
    if days < 0:
        days = 0
    if days <= 30:
        return DECAY_PRESSURE_0_30
    if days <= 60:
        return DECAY_PRESSURE_31_60
    if days <= 120:
        return DECAY_PRESSURE_61_120
    return DECAY_PRESSURE_121_PLUS


def decay_complexity(days: int) -> float:
    """Return complexity decay multiplier for given days since event.

    Complexity decays slow (v2-spec §4.2):
    - 0–90 days: 1.0
    - 91–180 days: 0.8
    - 181–365 days: 0.6
    - 366+ days: 0.4

    Negative days are treated as 0.
    """
    if days < 0:
        days = 0
    if days <= 90:
        return DECAY_COMPLEXITY_0_90
    if days <= 180:
        return DECAY_COMPLEXITY_91_180
    if days <= 365:
        return DECAY_COMPLEXITY_181_365
    return DECAY_COMPLEXITY_366_PLUS


def _parse_decay_breakpoints(decay_dict: dict[str, float] | None) -> list[tuple[int, float]]:
    """Convert pack decay format {"0-30": 1.0, "31-60": 0.7, "91+": 0.0} to sorted breakpoints.

    Returns list of (max_days_inclusive, multiplier) sorted by max_days ascending.
    Used by _decay_from_cfg. Falls back to None when decay_dict is empty/invalid.
    """
    if not decay_dict or not isinstance(decay_dict, dict):
        return []
    breakpoints: list[tuple[int, float]] = []
    for key, val in decay_dict.items():
        if not isinstance(key, str) or not isinstance(val, (int, float)):
            continue
        key = key.strip()
        if "+" in key:
            # "91+" -> max_days=9999
            prefix = key.replace("+", "").strip()
            try:
                int(prefix)  # validate prefix is numeric
                breakpoints.append((9999, float(val)))
            except ValueError:
                continue
        elif "-" in key:
            # "0-30" -> max_days=30
            parts = key.split("-", 1)
            if len(parts) != 2:
                continue
            try:
                int(parts[0].strip())  # validate low is numeric
                high = int(parts[1].strip())
                breakpoints.append((high, float(val)))
            except ValueError:
                continue
        else:
            continue
    if not breakpoints:
        return []
    breakpoints.sort(key=lambda x: x[0])
    return breakpoints


def from_pack(scoring_config: dict) -> dict:
    """Build engine-compatible constants from pack scoring config (Issue #189, #174).

    Returns dict with keys: base_scores_momentum, base_scores_complexity, base_scores_pressure,
    base_scores_leadership_gap, quiet_signal_amplified_base, quiet_signal_lookback_days,
    cap_jobs_momentum, cap_jobs_complexity, cap_founder_urgency, cap_dimension_max,
    composite_weights, decay_momentum, decay_pressure, decay_complexity,
    suppress_cto_hired_60_days, suppress_cto_hired_180_days,
    minimum_threshold, disqualifier_signals (Phase 2, Issue #174),
    recommendation_bands (Phase 2, Issue #242).
    """
    bs = scoring_config.get("base_scores") or {}
    qs = scoring_config.get("quiet_signal") or {}
    caps = scoring_config.get("caps") or {}
    cw = scoring_config.get("composite_weights") or {}
    decay = scoring_config.get("decay") or {}
    suppressors = scoring_config.get("suppressors") or {}

    decay_m = _parse_decay_breakpoints(decay.get("momentum") if isinstance(decay, dict) else None)
    decay_p = _parse_decay_breakpoints(decay.get("pressure") if isinstance(decay, dict) else None)
    decay_c = _parse_decay_breakpoints(decay.get("complexity") if isinstance(decay, dict) else None)

    return {
        "base_scores_momentum": bs.get("momentum") or BASE_SCORES_MOMENTUM,
        "base_scores_complexity": bs.get("complexity") or BASE_SCORES_COMPLEXITY,
        "base_scores_pressure": bs.get("pressure") or BASE_SCORES_PRESSURE,
        "base_scores_leadership_gap": bs.get("leadership_gap") or BASE_SCORES_LEADERSHIP_GAP,
        "quiet_signal_amplified_base": _norm_quiet(qs.get("amplified_base")),
        "quiet_signal_lookback_days": qs.get("lookback_days", QUIET_SIGNAL_LOOKBACK_DAYS),
        "cap_jobs_momentum": caps.get("jobs_momentum", CAP_JOBS_MOMENTUM),
        "cap_jobs_complexity": caps.get("jobs_complexity", CAP_JOBS_COMPLEXITY),
        "cap_founder_urgency": caps.get("founder_urgency", CAP_FOUNDER_URGENCY),
        "cap_dimension_max": caps.get("dimension_max", CAP_DIMENSION_MAX),
        "composite_weights": cw or COMPOSITE_WEIGHTS,
        "decay_momentum": decay_m if decay_m else DEFAULT_DECAY_MOMENTUM,
        "decay_pressure": decay_p if decay_p else DEFAULT_DECAY_PRESSURE,
        "decay_complexity": decay_c if decay_c else DEFAULT_DECAY_COMPLEXITY,
        "suppress_cto_hired_60_days": _int_or(
            suppressors.get("cto_hired_60_days") if isinstance(suppressors, dict) else None,
            SUPPRESS_CTO_HIRED_60_DAYS,
        ),
        "suppress_cto_hired_180_days": _int_or(
            suppressors.get("cto_hired_180_days") if isinstance(suppressors, dict) else None,
            SUPPRESS_CTO_HIRED_180_DAYS,
        ),
        "minimum_threshold": _int_or(
            scoring_config.get("minimum_threshold") if isinstance(scoring_config, dict) else None,
            0,
        ),
        "disqualifier_signals": _norm_disqualifier_signals(
            scoring_config.get("disqualifier_signals")
        ),
        "recommendation_bands": _norm_recommendation_bands(
            scoring_config.get("recommendation_bands")
        ),
    }


def _norm_recommendation_bands(bands: dict | None) -> dict[str, int] | None:
    """Normalize recommendation_bands to {ignore_max, watch_max, high_priority_min}.

    Pack format: {ignore_max: int, watch_max: int, high_priority_min: int}.
    Returns None when bands is None or invalid (no bands configured).
    """
    if not bands or not isinstance(bands, dict):
        return None
    ignore_max = _int_or(bands.get("ignore_max"), -1)
    watch_max = _int_or(bands.get("watch_max"), -1)
    high_priority_min = _int_or(bands.get("high_priority_min"), -1)
    if ignore_max < 0 or watch_max < 0 or high_priority_min < 0:
        return None
    if not (ignore_max < watch_max < high_priority_min):
        return None
    return {"ignore_max": ignore_max, "watch_max": watch_max, "high_priority_min": high_priority_min}


def _norm_disqualifier_signals(signals: dict | None) -> dict[str, int]:
    """Normalize disqualifier_signals to {event_type: window_days}.

    Pack format: {event_type: window_days}. When event present within window, R=0.
    Returns empty dict when signals is None or invalid.
    """
    if not signals or not isinstance(signals, dict):
        return {}
    result: dict[str, int] = {}
    for etype, days in signals.items():
        if isinstance(etype, str) and etype.strip():
            w = _int_or(days, 0) if days is not None else 0
            if w > 0:
                result[etype.strip()] = w
    return result


def _int_or(val: Any, default: int) -> int:
    """Return int(val) if val is convertible, else default."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _norm_quiet(amplified: dict | None) -> dict:
    """Normalize quiet_signal amplified_base to {etype: {dim: base}}."""
    if not amplified:
        return QUIET_SIGNAL_AMPLIFIED_BASE
    result: dict = {}
    for etype, dims in amplified.items():
        if isinstance(dims, dict):
            result[etype] = {k: int(v) for k, v in dims.items()}
        else:
            result[etype] = dims
    return result
