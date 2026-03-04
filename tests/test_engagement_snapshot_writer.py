"""Tests for engagement snapshot writer (Issue #106)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Company,
    OutreachHistory,
    ReadinessSnapshot,
    SignalEvent,
    SignalInstance,
)
from app.services.esl.engagement_snapshot_writer import (
    compute_esl_from_context,
    write_engagement_snapshot,
)


def test_compute_esl_from_context_return_includes_signal_ids(
    db: Session, fractional_cto_pack_id: UUID
) -> None:
    """M1 (Issue #120): compute_esl_from_context return includes signal_ids for pack-aware critic."""
    as_of = date(2026, 2, 18)
    company = Company(name="SignalIdsCtxCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=75,
        pressure=60,
        leadership_gap=70,
        composite=82,
        pack_id=fractional_cto_pack_id,
    )
    db.add(readiness)
    db.commit()

    ctx = compute_esl_from_context(
        db, company.id, as_of, pack_id=fractional_cto_pack_id
    )
    assert ctx is not None
    assert "signal_ids" in ctx
    assert ctx["signal_ids"] == set(), "No SignalInstances → signal_ids empty"

    # Add SignalInstance for this company/pack
    inst = SignalInstance(
        entity_id=company.id,
        signal_id="funding_raised",
        pack_id=fractional_cto_pack_id,
        first_seen=datetime(2026, 2, 1, tzinfo=UTC),
        last_seen=datetime(2026, 2, 10, tzinfo=UTC),
    )
    db.add(inst)
    db.commit()

    ctx2 = compute_esl_from_context(
        db, company.id, as_of, pack_id=fractional_cto_pack_id
    )
    assert ctx2 is not None
    assert "signal_ids" in ctx2
    assert ctx2["signal_ids"] == {"funding_raised"}


def test_engagement_snapshot_writer_returns_none_without_readiness(db: Session) -> None:
    """Without ReadinessSnapshot, returns None."""
    company = Company(name="NoReadinessCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18))
    assert result is None


def test_engagement_snapshot_writer_persists(db: Session, fractional_cto_pack_id) -> None:
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
        pack_id=fractional_cto_pack_id,
    )
    db.add(readiness)
    db.commit()

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18), pack_id=fractional_cto_pack_id)

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
    # Issue #175 Phase 2: ESL decision in explain (fractional CTO → allow)
    assert "esl_decision" in result.explain
    assert result.explain["esl_decision"] == "allow"
    assert "esl_reason_code" in result.explain
    # Phase 4: dedicated columns populated
    assert result.esl_decision == "allow"
    assert result.esl_reason_code is not None
    # Issue #103: outreach_score = round(TRS × ESL)
    assert result.outreach_score is not None
    assert result.outreach_score == round(82 * result.esl_score)


def test_engagement_snapshot_writer_upserts(db: Session, fractional_cto_pack_id) -> None:
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
        pack_id=fractional_cto_pack_id,
    )
    db.add(readiness)
    db.commit()

    first = write_engagement_snapshot(db, company.id, date(2026, 2, 18), pack_id=fractional_cto_pack_id)
    assert first is not None
    first_id = first.id

    second = write_engagement_snapshot(db, company.id, date(2026, 2, 18), pack_id=fractional_cto_pack_id)
    assert second is not None
    assert second.id == first_id
    assert second.esl_score == first.esl_score


def test_engagement_snapshot_with_outreach_history_cadence_blocked(db: Session, fractional_cto_pack_id) -> None:
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
        pack_id=fractional_cto_pack_id,
    )
    db.add(readiness)
    db.commit()

    # Outreach 10 days ago (within 60-day cooldown)
    history = OutreachHistory(
        company_id=company.id,
        outreach_type="email",
        sent_at=datetime(2026, 2, 8, tzinfo=UTC),
    )
    db.add(history)
    db.commit()

    result = write_engagement_snapshot(db, company.id, date(2026, 2, 18), pack_id=fractional_cto_pack_id)

    assert result is not None
    assert result.cadence_blocked is True
    assert result.esl_score == 0.0
    assert result.engagement_type == "Observe Only"


def test_stability_cap_under_pressure_spike(db: Session, fractional_cto_pack_id) -> None:
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
        pack_id=fractional_cto_pack_id,
    )
    db.add(readiness)
    db.commit()

    # SignalEvents with SVI types in last 14 days to drive SVI high
    for i, etype in enumerate(
        ["founder_urgency_language", "funding_raised", "enterprise_customer"]
    ):
        ev = SignalEvent(
            company_id=company.id,
            source="test",
            event_type=etype,
            event_time=datetime(2026, 2, 10 + i, tzinfo=UTC),
            ingested_at=datetime(2026, 2, 10, tzinfo=UTC),
            confidence=0.9,
            pack_id=fractional_cto_pack_id,
        )
        db.add(ev)
    db.commit()

    result = write_engagement_snapshot(db, company.id, as_of, pack_id=fractional_cto_pack_id)

    assert result is not None
    assert result.engagement_type == "Soft Value Share"
    assert result.explain.get("stability_cap_triggered") is True
    assert result.explain.get("stability_modifier") < 0.7


def test_compute_esl_from_context_signal_ids_from_core_pack_when_core_pack_id_provided(
    db: Session,
    core_pack_id: UUID,
    esl_blocked_pack_id: UUID,
) -> None:
    """M1 follow-up: ctx['signal_ids'] comes from core SignalInstances when core_pack_id set (Issue #287 M4).

    Same scenario as test_esl_signal_set_from_core_instances_when_core_pack_id_provided but asserts
    on compute_esl_from_context return dict. Signal only in core pack; with core_pack_id the
    context must expose signal_ids including funding_raised.
    """
    as_of = date(2026, 2, 18)
    company = Company(name="CoreSignalCtxCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=50,
        complexity=50,
        pressure=50,
        leadership_gap=50,
        composite=50,
        pack_id=esl_blocked_pack_id,
    )
    db.add(readiness)
    db.commit()

    # Signal only in core pack (no instance in workspace pack)
    inst = SignalInstance(
        entity_id=company.id,
        signal_id="funding_raised",
        pack_id=core_pack_id,
        first_seen=datetime(2026, 2, 1, tzinfo=UTC),
        last_seen=datetime(2026, 2, 10, tzinfo=UTC),
    )
    db.add(inst)
    db.commit()

    # Without core_pack_id: query uses workspace pack → no instances → signal_ids empty
    ctx_no_core = compute_esl_from_context(
        db, company.id, as_of, pack_id=esl_blocked_pack_id
    )
    assert ctx_no_core is not None
    assert ctx_no_core["signal_ids"] == set()

    # With core_pack_id: signal set from core pack → signal_ids includes funding_raised
    ctx = compute_esl_from_context(
        db,
        company.id,
        as_of,
        pack_id=esl_blocked_pack_id,
        core_pack_id=core_pack_id,
    )
    assert ctx is not None
    assert "signal_ids" in ctx
    assert ctx["signal_ids"] == {"funding_raised"}


def test_esl_signal_set_from_core_instances_when_core_pack_id_provided(
    db: Session,
    core_pack_id: UUID,
    esl_blocked_pack_id: UUID,
) -> None:
    """ESL signal set comes from core SignalInstances when core_pack_id is set (Issue #287 M4).

    example_esl_blocked pack blocks funding_raised (core signal). We create that signal
    only in the core pack. Without core_pack_id the signal set would be empty (query by
    workspace pack) and ESL would allow; with core_pack_id the signal set includes
    funding_raised and ESL must suppress (Issue #289 M1).
    """
    as_of = date(2026, 2, 18)
    company = Company(name="CoreSignalESLCo", source="manual")
    db.add(company)
    db.commit()
    db.refresh(company)

    readiness = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=50,
        complexity=50,
        pressure=50,
        leadership_gap=50,
        composite=50,
        pack_id=esl_blocked_pack_id,
    )
    db.add(readiness)
    db.commit()

    # Signal only in core pack (as after derive); no instance in workspace pack
    inst = SignalInstance(
        entity_id=company.id,
        signal_id="funding_raised",
        pack_id=core_pack_id,
        first_seen=datetime(2026, 2, 1, tzinfo=UTC),
        last_seen=datetime(2026, 2, 10, tzinfo=UTC),
    )
    db.add(inst)
    db.commit()

    result = write_engagement_snapshot(
        db,
        company.id,
        as_of,
        pack_id=esl_blocked_pack_id,
        core_pack_id=core_pack_id,
    )

    assert result is not None
    assert result.esl_decision == "suppress"
    assert result.explain["esl_reason_code"] == "blocked_signal"
