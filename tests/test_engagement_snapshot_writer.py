"""Tests for engagement snapshot writer (Issue #106)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, OutreachHistory, ReadinessSnapshot, SignalEvent
from app.services.esl.engagement_snapshot_writer import write_engagement_snapshot


def test_engagement_snapshot_writer_returns_none_without_readiness(db: Session) -> None:
    """Without ReadinessSnapshot, returns None."""
    company = Company(name="NoReadinessCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18))
    assert result is None


def test_engagement_snapshot_writer_persists(db: Session) -> None:
    """With ReadinessSnapshot, writes EngagementSnapshot with correct fields."""
    company = Company(name="EngagementTestCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        momentum=80,
        complexity=75,
        pressure=60,
        leadership_gap=70,
        composite=82,
    )
    db.add(readiness)
    db.commit()

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18))

    assert result is not None
    assert result.company_id == company.id
    assert result.as_of == date(2026, 2, 18)
    assert 0 <= result.esl_score <= 1
    assert result.engagement_type in (
        "Observe Only",
        "Soft Value Share",
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    )
    assert result.explain is not None
    assert "base_engageability" in result.explain
    assert "stability_modifier" in result.explain
    assert "esl_composite" in result.explain
    assert "recommendation_type" in result.explain
    assert "stability_cap_triggered" in result.explain
    # Issue #103: outreach_score = round(TRS × ESL)
    assert result.outreach_score is not None
    assert result.outreach_score == round(82 * result.esl_score)


def test_engagement_snapshot_writer_upserts(db: Session) -> None:
    """Second write upserts existing EngagementSnapshot."""
    company = Company(name="UpsertCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        momentum=50,
        complexity=50,
        pressure=50,
        leadership_gap=50,
        composite=50,
    )
    db.add(readiness)
    db.commit()

    first = write_engagement_snapshot(db, company.id, date(2026, 2, 18))
    assert first is not None
    first_id = first.id

    second = write_engagement_snapshot(db, company.id, date(2026, 2, 18))
    assert second is not None
    assert second.id == first_id
    assert second.esl_score == first.esl_score


def test_engagement_snapshot_with_outreach_history_cadence_blocked(db: Session) -> None:
    """Recent outreach sets cadence_blocked=True and lowers ESL."""
    company = Company(name="CadenceCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        momentum=80,
        complexity=80,
        pressure=80,
        leadership_gap=80,
        composite=82,
    )
    db.add(readiness)
    db.commit()

    # Outreach 10 days ago (within 60-day cooldown)
    history = OutreachHistory(
        company_id=company.id,
        outreach_type="email",
        sent_at=datetime(2026, 2, 8, tzinfo=timezone.utc),
    )
    db.add(history)
    db.commit()

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18))

    assert result is not None
    assert result.cadence_blocked is True
    assert result.esl_score == 0.0
    assert result.engagement_type == "Observe Only"


def test_stability_cap_under_pressure_spike(db: Session) -> None:
    """Pressure spike drives SM < 0.7; cap enforced to Soft Value Share (Issue #111)."""
    company = Company(name="PressureSpikeCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 18)
    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=75,
        pressure=70,  # >= SPI_PRESSURE_THRESHOLD (60)
        leadership_gap=70,
        composite=82,
    )
    db.add(readiness)
    db.commit()

    # SignalEvents with SVI types in last 14 days to drive SVI high
    for i, etype in enumerate(["founder_urgency_language", "funding_raised", "enterprise_customer"]):
        ev = SignalEvent(
            company_id=company.id,
            source="test",
            event_type=etype,
            event_time=datetime(2026, 2, 10 + i, tzinfo=timezone.utc),
            ingested_at=datetime(2026, 2, 10, tzinfo=timezone.utc),
            confidence=0.9,
        )
        db.add(ev)
    db.commit()

    result = write_engagement_snapshot(db, company.id, as_of)

    assert result is not None
    assert result.engagement_type == "Soft Value Share"
    assert result.explain.get("stability_cap_triggered") is True
    assert result.explain.get("stability_modifier") < 0.7
