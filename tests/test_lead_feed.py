"""Tests for lead_feed writer and projection (Phase 3, Issue #192)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, LeadFeed, ReadinessSnapshot, SignalPack
from app.pipeline.lead_feed_writer import upsert_lead_feed
from app.services.briefing import (
    get_emerging_companies_for_briefing,
    get_emerging_companies_from_lead_feed,
)
from app.services.esl.esl_engine import compute_outreach_score


@pytest.fixture(autouse=True)
def _clean_lead_feed_test_data(db: Session) -> None:
    """Remove lead_feed and snapshots with future dates."""
    db.execute(delete(LeadFeed).where(LeadFeed.as_of >= date(2099, 1, 1)))
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of >= date(2099, 1, 1)))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of >= date(2099, 1, 1)))
    db.commit()


def _add_snapshots(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    composite: int = 70,
    esl_score: float = 0.8,
    engagement_type: str = "Standard Outreach",
    cadence_blocked: bool = False,
    top_events: list | None = None,
    stability_cap: bool = False,
) -> tuple[ReadinessSnapshot, EngagementSnapshot]:
    """Create ReadinessSnapshot + EngagementSnapshot for a company."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    rs = ReadinessSnapshot(
        company_id=company_id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=composite,
        pack_id=pack_id,
        explain={"top_events": top_events} if top_events else None,
    )
    db.add(rs)
    es = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=esl_score,
        engagement_type=engagement_type,
        cadence_blocked=cadence_blocked,
        pack_id=pack_id,
        explain={"stability_cap_triggered": stability_cap} if stability_cap else None,
    )
    db.add(es)
    db.commit()
    db.refresh(rs)
    db.refresh(es)
    return rs, es


def test_upsert_lead_feed_populates_from_snapshots(
    db: Session, fractional_cto_pack_id
) -> None:
    """upsert_lead_feed creates lead_feed rows from ReadinessSnapshot + EngagementSnapshot."""
    company = Company(name="Lead Co", website_url="https://lead.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 10)
    _add_snapshots(
        db,
        company.id,
        as_of,
        composite=80,
        esl_score=0.75,
        top_events=[{"event_type": "funding_raised"}],
    )

    count = upsert_lead_feed(
        db,
        workspace_id="00000000-0000-0000-0000-000000000001",
        pack_id=fractional_cto_pack_id,
        as_of=as_of,
    )

    assert count == 1
    row = db.query(LeadFeed).filter(LeadFeed.entity_id == company.id).first()
    assert row is not None
    assert row.composite_score == 80
    assert row.esl_score == 0.75
    assert row.outreach_score == 60  # round(80 * 0.75)
    assert row.top_reasons == [{"event_type": "funding_raised"}]


def test_upsert_lead_feed_idempotent_no_duplicates(
    db: Session, fractional_cto_pack_id
) -> None:
    """Re-running upsert_lead_feed produces same rows (upsert by natural key)."""
    company = Company(name="Idem Co", website_url="https://idem.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 11)
    _add_snapshots(db, company.id, as_of, composite=65, esl_score=0.9)

    count1 = upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)
    count2 = upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)

    assert count1 == 1
    assert count2 == 1
    total = db.query(LeadFeed).filter(LeadFeed.entity_id == company.id, LeadFeed.as_of == as_of).count()
    assert total == 1


def test_get_emerging_companies_from_lead_feed_returns_none_when_empty(db: Session) -> None:
    """When lead_feed has no rows for date, returns None."""
    result = get_emerging_companies_from_lead_feed(
        db, date(2099, 1, 12), limit=5, outreach_score_threshold=30
    )
    assert result is None


def test_get_emerging_companies_from_lead_feed_returns_data_when_populated(
    db: Session, fractional_cto_pack_id
) -> None:
    """When lead_feed has rows, returns same structure as get_emerging_companies."""
    company = Company(name="Feed Co", website_url="https://feed.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 13)
    _add_snapshots(db, company.id, as_of, composite=85, esl_score=0.8)

    upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)

    result = get_emerging_companies_from_lead_feed(
        db, as_of, limit=5, outreach_score_threshold=30
    )
    assert result is not None
    assert len(result) == 1
    rs_view, es_view, co = result[0]
    assert co.name == "Feed Co"
    assert rs_view.composite == 85
    assert es_view.esl_score == 0.8
    assert compute_outreach_score(rs_view.composite, es_view.esl_score) == 68


def test_get_emerging_companies_for_briefing_fallback_when_lead_feed_empty(
    db: Session, fractional_cto_pack_id
) -> None:
    """When lead_feed empty, falls back to get_emerging_companies."""
    company = Company(name="Fallback Co", website_url="https://fallback.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 14)
    _add_snapshots(db, company.id, as_of, composite=75, esl_score=0.7)

    # No lead_feed - should use get_emerging_companies
    result = get_emerging_companies_for_briefing(
        db, as_of, limit=5, outreach_score_threshold=30
    )

    assert len(result) == 1
    rs, es, co = result[0]
    assert co.name == "Fallback Co"
    assert rs.composite == 75


def test_get_emerging_companies_for_briefing_uses_lead_feed_when_populated(
    db: Session, fractional_cto_pack_id
) -> None:
    """When lead_feed populated, uses lead_feed (not snapshots)."""
    company = Company(name="LeadFeed Co", website_url="https://leadfeed.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 15)
    _add_snapshots(db, company.id, as_of, composite=90, esl_score=0.9)

    upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)

    result = get_emerging_companies_for_briefing(
        db, as_of, limit=5, outreach_score_threshold=30
    )

    assert len(result) == 1
    rs_view, es_view, co = result[0]
    assert co.name == "LeadFeed Co"
    assert rs_view.composite == 90
    assert es_view.esl_score == 0.9


def test_get_emerging_companies_for_briefing_cadence_blocked_observe_only_via_lead_feed(
    db: Session, fractional_cto_pack_id
) -> None:
    """cadence_blocked (Observe Only) companies appear when lead_feed path is used.

    Regression: Ensure same behavior as get_emerging_companies when reading from
    lead_feed projection.
    """
    company = Company(
        name="Observe Only Co",
        website_url="https://observe.example.com",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 16)
    _add_snapshots(
        db,
        company.id,
        as_of,
        composite=80,
        esl_score=0.0,  # CM=0 → ESL=0 → outreach_score=0
        engagement_type="Observe Only",
        cadence_blocked=True,
    )

    upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)

    result = get_emerging_companies_for_briefing(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    rs_view, es_view, co = result[0]
    assert co.name == "Observe Only Co"
    assert es_view.cadence_blocked is True
    assert es_view.engagement_type == "Observe Only"
    assert compute_outreach_score(rs_view.composite, es_view.esl_score) == 0


def test_get_emerging_companies_from_lead_feed_all_filtered_out_returns_empty(
    db: Session, fractional_cto_pack_id
) -> None:
    """When lead_feed has rows but all filtered out by threshold, returns empty list.

    lead_result is not None (rows exist) but len(lead_result)==0 after filter.
    """
    company = Company(name="Below Co", website_url="https://below.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 1, 17)
    _add_snapshots(db, company.id, as_of, composite=50, esl_score=0.5)  # outreach=25 < 30

    upsert_lead_feed(db, "00000000-0000-0000-0000-000000000001", fractional_cto_pack_id, as_of)

    result = get_emerging_companies_from_lead_feed(
        db, as_of, limit=5, outreach_score_threshold=30
    )

    assert result is not None
    assert len(result) == 0
