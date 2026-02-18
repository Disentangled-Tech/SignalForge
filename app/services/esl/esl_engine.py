"""ESL engine — OutreachScore and full ESL composite (Issue #124, #106).

OutreachScore = round(trs * esl) when ESL is 0–1.
ESL = BE × SM × CM × AM (BaseEngageability × StabilityModifier × CadenceModifier × AlignmentModifier).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from app.services.esl.esl_constants import (
    ALIGNMENT_NULL_MODIFIER,
    ALIGNMENT_NOT_OK_MODIFIER,
    ALIGNMENT_OK_MODIFIER,
    CADENCE_COOLDOWN_DAYS,
    CSI_GAP_PENALTY,
    CSI_SILENCE_GAP_DAYS,
    RECOMMENDATION_BOUNDARIES,
    SVI_EVENT_TYPES,
    SVI_WINDOW_DAYS,
    SPI_HIGH_VALUE,
    SPI_PRESSURE_THRESHOLD,
    SPI_SUSTAINED_DAYS,
    SM_WEIGHT_CSI,
    SM_WEIGHT_SPI,
    SM_WEIGHT_SVI,
)


class _EventLike(Protocol):
    """Minimal interface for event-like objects."""

    event_type: str
    event_time: datetime
    confidence: float | None


class _SnapshotLike(Protocol):
    """Minimal interface for readiness snapshot-like objects."""

    as_of: date
    pressure: int


def compute_outreach_score(trs: int, stability_modifier: float) -> int:
    """Compute OutreachScore from TRS and ESL composite (or stability modifier).

    Args:
        trs: Total Readiness Score (0–100).
        stability_modifier: ESL factor 0–1 (e.g. 0.5 for high pressure).

    Returns:
        round(trs * stability_modifier), e.g. TRS=82, SM=0.5 → 41.
    """
    return round(trs * stability_modifier)


def compute_base_engageability(trs: int) -> float:
    """Compute BaseEngageability from TRS (Issue #106).

    BE = TRS / 100, clamped to 0..1.
    """
    clamped = max(0, min(100, trs))
    return round(clamped / 100, 2)


def compute_stability_modifier(svi: float, spi: float, csi: float) -> float:
    """Compute StabilityModifier from SVI, SPI, CSI (Issue #106).

    SM = 1 - (w_svi*SVI + w_spi*SPI + w_csi*(1-CSI)).
    High stress in any dimension → lower SM.
    """
    contrib = SM_WEIGHT_SVI * svi + SM_WEIGHT_SPI * spi + SM_WEIGHT_CSI * (1.0 - csi)
    return round(max(0.0, min(1.0, 1.0 - contrib)), 2)


def compute_svi(events: list[Any], as_of: date) -> float:
    """Compute Stress Volatility Index from recent urgency events (Issue #106).

    Events in last SVI_WINDOW_DAYS with event_type in SVI_EVENT_TYPES.
    Returns 0 (low volatility) to 1 (high volatility).
    """
    cutoff = datetime.combine(
        as_of - timedelta(days=SVI_WINDOW_DAYS), datetime.min.time()
    ).replace(tzinfo=timezone.utc)

    count = 0
    for ev in events:
        etype = getattr(ev, "event_type", None)
        if etype not in SVI_EVENT_TYPES:
            continue
        ev_time = getattr(ev, "event_time", None)
        if ev_time is None:
            continue
        if ev_time.tzinfo is None:
            ev_time = ev_time.replace(tzinfo=timezone.utc)
        if ev_time >= cutoff:
            conf = getattr(ev, "confidence", None) or 0.7
            count += conf

    if count == 0:
        return 0.0
    # Scale: 1 event with conf 0.7 → ~0.35, 3+ events → cap at 1
    return round(min(1.0, count * 0.5), 2)


def compute_spi(snapshots: list[Any], as_of: date) -> float:
    """Compute Sustained Pressure Index from readiness snapshots (Issue #106).

    If pressure >= SPI_PRESSURE_THRESHOLD for SPI_SUSTAINED_DAYS+ → SPI high.
    Returns 0..1.
    """
    cutoff = as_of - timedelta(days=SPI_SUSTAINED_DAYS)
    high_pressure_count = 0
    for snap in snapshots:
        s_date = getattr(snap, "as_of", None)
        pressure = getattr(snap, "pressure", None)
        if s_date is None or pressure is None:
            continue
        if s_date >= cutoff and pressure >= SPI_PRESSURE_THRESHOLD:
            high_pressure_count += 1

    if high_pressure_count >= 1:
        return SPI_HIGH_VALUE
    return 0.0


def compute_csi(events: list[Any], as_of: date) -> float:
    """Compute Communication Stability Index from event timing (Issue #106).

    Large gaps (> CSI_SILENCE_GAP_DAYS) between events reduce CSI.
    Default 1.0 when few events.
    """
    if len(events) < 2:
        return 1.0

    sorted_events = sorted(
        events,
        key=lambda e: getattr(e, "event_time", datetime.min.replace(tzinfo=timezone.utc)),
    )
    gaps = 0
    for i in range(1, len(sorted_events)):
        prev = getattr(sorted_events[i - 1], "event_time", None)
        curr = getattr(sorted_events[i], "event_time", None)
        if prev is None or curr is None:
            continue
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        if curr.tzinfo is None:
            curr = curr.replace(tzinfo=timezone.utc)
        delta = (curr - prev).days
        if delta > CSI_SILENCE_GAP_DAYS:
            gaps += 1

    penalty = gaps * CSI_GAP_PENALTY
    return round(max(0.0, min(1.0, 1.0 - penalty)), 2)


def compute_cadence_modifier(
    last_outreach_at: datetime | None, as_of: date, cooldown_days: int = CADENCE_COOLDOWN_DAYS
) -> float:
    """Compute CadenceModifier from last outreach date (Issue #106).

    Returns 0 if last outreach within cooldown, else 1.
    """
    if last_outreach_at is None:
        return 1.0
    if last_outreach_at.tzinfo is None:
        last_outreach_at = last_outreach_at.replace(tzinfo=timezone.utc)
    cutoff = datetime.combine(
        as_of - timedelta(days=cooldown_days), datetime.min.time()
    ).replace(tzinfo=timezone.utc)
    return 0.0 if last_outreach_at >= cutoff else 1.0


def compute_alignment_modifier(alignment_ok_to_contact: bool | None) -> float:
    """Compute AlignmentModifier from company alignment flag (Issue #106)."""
    if alignment_ok_to_contact is True:
        return ALIGNMENT_OK_MODIFIER
    if alignment_ok_to_contact is False:
        return ALIGNMENT_NOT_OK_MODIFIER
    return ALIGNMENT_NULL_MODIFIER


def compute_esl_composite(
    base_engageability: float,
    stability_modifier: float,
    cadence_modifier: float,
    alignment_modifier: float,
) -> float:
    """Compute ESL composite = BE × SM × CM × AM (Issue #106)."""
    result = base_engageability * stability_modifier * cadence_modifier * alignment_modifier
    return round(max(0.0, min(1.0, result)), 3)


def map_esl_to_recommendation(esl: float) -> str:
    """Map ESL score to engagement type (Issue #106, v2PRD §3)."""
    esl = max(0.0, min(1.0, esl))
    for boundary, rec_type in reversed(RECOMMENDATION_BOUNDARIES):
        if esl >= boundary:
            return rec_type
    return "Observe Only"


def build_esl_explain(
    *,
    base_engageability: float,
    stability_modifier: float,
    cadence_modifier: float,
    alignment_modifier: float,
    svi: float,
    spi: float,
    csi: float,
    esl_composite: float,
    recommendation_type: str,
    cadence_blocked: bool | None = None,
) -> dict[str, Any]:
    """Build explain payload with all ESL components (Issue #106)."""
    if cadence_blocked is None:
        cadence_blocked = cadence_modifier == 0.0
    return {
        "base_engageability": base_engageability,
        "stability_modifier": stability_modifier,
        "cadence_modifier": cadence_modifier,
        "alignment_modifier": alignment_modifier,
        "svi": svi,
        "spi": spi,
        "csi": csi,
        "esl_composite": esl_composite,
        "cadence_blocked": cadence_blocked,
        "recommendation_type": recommendation_type,
        "weights": {"be": 1.0, "sm": 1.0, "cm": 1.0, "am": 1.0},
    }
