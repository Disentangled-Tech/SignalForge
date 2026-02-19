"""ESL constants, thresholds, and recommendation mapping (Issue #106).

Deterministic formulas for Engagement Suitability Layer. No ML.
Reference: docs/v2PRD.md, GitHub issue #106.
"""

from __future__ import annotations

# ── Cadence (v2PRD §6.2) ─────────────────────────────────────────────────

CADENCE_COOLDOWN_DAYS: int = 60

# ── Outreach governance (Issue #109) ──────────────────────────────────────

DECLINED_COOLDOWN_DAYS: int = 180

# ── Stability indices (SVI, SPI, CSI) ────────────────────────────────────

# SVI: Stress Volatility — window for recent urgency events
SVI_WINDOW_DAYS: int = 14

# SPI: Sustained Pressure — pressure threshold and duration
SPI_PRESSURE_THRESHOLD: int = 60
SPI_SUSTAINED_DAYS: int = 60
SPI_HIGH_VALUE: float = 0.7  # SPI when sustained pressure detected

# CSI: Communication Stability — gap penalty
CSI_SILENCE_GAP_DAYS: int = 30
CSI_GAP_PENALTY: float = 0.3  # Reduce CSI by this per long gap

# SM: StabilityModifier = 1 - weighted_avg(SVI, SPI, 1-CSI)
# We use: SM = 1 - (w_svi*SVI + w_spi*SPI + w_csi*(1-CSI))
# High stress in any dimension → lower SM
SM_WEIGHT_SVI: float = 0.4
SM_WEIGHT_SPI: float = 0.35
SM_WEIGHT_CSI: float = 0.25

# ── Alignment ─────────────────────────────────────────────────────────────

ALIGNMENT_OK_MODIFIER: float = 1.0
ALIGNMENT_NOT_OK_MODIFIER: float = 0.5
ALIGNMENT_NULL_MODIFIER: float = 1.0  # Default when alignment not set

# ── Policy gate (ORE design spec) ──────────────────────────────────────────

STABILITY_CAP_THRESHOLD: float = 0.7  # SM < 0.7 → Soft Value Share only

# ── Recommendation mapping (v2PRD §3) ─────────────────────────────────────

RECOMMENDATION_BOUNDARIES: list[tuple[float, str]] = [
    (0.0, "Observe Only"),
    (0.2, "Soft Value Share"),
    (0.4, "Low-Pressure Intro"),
    (0.7, "Standard Outreach"),
    (0.9, "Direct Strategic Outreach"),
]

# Event types that contribute to SVI (stress/urgency)
SVI_EVENT_TYPES: frozenset[str] = frozenset({
    "founder_urgency_language",
    "regulatory_deadline",
    "enterprise_customer",
    "revenue_milestone",
    "funding_raised",
})
