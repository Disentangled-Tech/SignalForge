"""v2 Readiness scoring constants and decay functions (Issue #85).

Centralized configuration for the Readiness Scoring Engine. No magic numbers
inside the scoring engine — all values defined here.

Reference: docs/v2-spec.md §4.
"""

from __future__ import annotations

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
