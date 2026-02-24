"""Tests for get_emerging_companies (Issue #93, #102, #103)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, ReadinessSnapshot, SignalPack
from app.services.briefing import get_emerging_companies
from app.services.esl.esl_engine import compute_outreach_score


@pytest.fixture(autouse=True)
def _clean_emerging_test_data(db: Session) -> None:
    """Remove readiness/engagement snapshots with future dates (handles pre-existing data)."""
    db.execute(delete(EngagementSnapshot).where(EngagementSnapshot.as_of >= date(2099, 1, 1)))
    db.execute(delete(ReadinessSnapshot).where(ReadinessSnapshot.as_of >= date(2099, 1, 1)))
    db.commit()


def _add_engagement_snapshot(
    db: Session,
    company_id: int,
    as_of: date,
    *,
    esl_score: float = 0.8,
    engagement_type: str = "Standard Outreach",
    cadence_blocked: bool = False,
    pack_id=None,
) -> EngagementSnapshot:
    """Helper to create EngagementSnapshot for a company (Issue #189: pack_id)."""
    if pack_id is None:
        pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
        pack_id = pack.id if pack else None
    es = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=esl_score,
        engagement_type=engagement_type,
        cadence_blocked=cadence_blocked,
        pack_id=pack_id,
    )
    db.add(es)
    db.commit()
    db.refresh(es)
    return es


def test_get_emerging_companies_returns_top_by_outreach_score(db: Session) -> None:
    """Returns companies ordered by OutreachScore descending (Issue #102)."""
    companies = [
        Company(name=f"Emerging Co {i}", website_url=f"https://emerging{i}.example.com")
        for i in range(5)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    # Use unique date to avoid collision with other tests
    as_of = date(2099, 1, 1)
    # TRS 70,80,90,60,65 with ESL 0.5,0.8,0.6,1.0,0.9 -> OutreachScore 35,64,54,60,58
    # Sorted by OutreachScore: 64, 60, 58, 54, 35
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=[70, 80, 90, 60, 65][i],
            pack_id=pack_id,
        )
        db.add(rs)
        esl = [0.5, 0.8, 0.6, 1.0, 0.9][i]
        _add_engagement_snapshot(db, c.id, as_of, esl_score=esl)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=5, outreach_score_threshold=30
    )

    assert len(result) == 5
    # OutreachScores: 35,64,54,60,58 -> sorted desc: 64,60,58,54,35
    outreach_scores = [
        round(rs.composite * es.esl_score)
        for rs, es, _ in result
    ]
    assert outreach_scores == [64, 60, 58, 54, 35]


def test_outreach_score_formula_matches_ranking(db: Session) -> None:
    """OutreachScore = round(TRS × ESL); ranking uses this formula (Issue #103)."""
    companies = [
        Company(name=f"Formula Co {i}", website_url=f"https://formula{i}.example.com")
        for i in range(3)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 20)
    # TRS 50, 80, 90 with ESL 0.5, 0.75, 0.9 -> OutreachScore 25, 60, 81
    # Distinct scores ensure deterministic ordering
    trs_esl_pairs = [(50, 0.5), (80, 0.75), (90, 0.9)]
    for c, (trs, esl) in zip(companies, trs_esl_pairs):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=50,
            complexity=50,
            pressure=50,
            leadership_gap=50,
            composite=trs,
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of, esl_score=esl)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=5, outreach_score_threshold=20
    )

    actual_scores = [
        compute_outreach_score(rs.composite, es.esl_score)
        for rs, es, _ in result
    ]
    # 90*0.9=81, 80*0.75=60, 50*0.5=25
    assert actual_scores == [81, 60, 25]
    assert actual_scores == sorted(actual_scores, reverse=True)


def test_get_emerging_companies_respects_outreach_threshold(db: Session) -> None:
    """Companies with OutreachScore < threshold are excluded."""
    c1 = Company(name="Above Co", website_url="https://above.example.com")
    c2 = Company(name="Below Co", website_url="https://below.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 2)
    for c, composite, esl in [(c1, 80, 0.5), (c2, 50, 0.5)]:
        rs = ReadinessSnapshot(
            company_id=c.id, as_of=as_of,
            momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=composite,
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of, esl_score=esl)
    db.commit()

    # c1: 80*0.5=40 >= 30; c2: 50*0.5=25 < 30
    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    assert result[0][0].composite == 80
    assert result[0][2].name == "Above Co"


def test_get_emerging_companies_excludes_without_engagement_snapshot(
    db: Session,
) -> None:
    """Companies without EngagementSnapshot are excluded."""
    c1 = Company(name="With ES", website_url="https://with.example.com")
    c2 = Company(name="No ES", website_url="https://no.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    # Use unique date to avoid collision with other tests' engagement snapshots
    as_of = date(2099, 1, 15)
    for c in [c1, c2]:
        rs = ReadinessSnapshot(
            company_id=c.id, as_of=as_of,
            momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=70,
            pack_id=pack_id,
        )
        db.add(rs)
    _add_engagement_snapshot(db, c1.id, as_of)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    # "With ES" has EngagementSnapshot and qualifies; "No ES" has no ES so excluded by join
    with_es = [r for r in result if r[2].name == "With ES"]
    no_es = [r for r in result if r[2].name == "No ES"]
    assert len(with_es) == 1
    assert len(no_es) == 0


def test_get_emerging_companies_respects_date(db: Session) -> None:
    """Snapshots for different date are excluded."""
    company = Company(name="Date Co", website_url="https://date.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of_target = date(2099, 1, 4)
    as_of_other = date(2099, 1, 3)
    rs = ReadinessSnapshot(
        company_id=company.id, as_of=as_of_other,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=70,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(db, company.id, as_of_other)
    db.commit()

    result = get_emerging_companies(
        db, as_of_target, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 0


def test_get_emerging_companies_empty_when_no_snapshots(db: Session) -> None:
    """Returns empty list when no snapshots exist for date."""
    result = get_emerging_companies(
        db, date(2099, 1, 5), limit=10, outreach_score_threshold=30
    )
    assert result == []


def test_get_emerging_companies_returns_fewer_than_limit(db: Session) -> None:
    """Returns all available when fewer than limit qualify."""
    c1 = Company(name="Only Co", website_url="https://only.example.com")
    db.add(c1)
    db.commit()
    db.refresh(c1)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 6)
    rs = ReadinessSnapshot(
        company_id=c1.id, as_of=as_of,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=65,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(db, c1.id, as_of)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    assert result[0][2].name == "Only Co"


def test_get_emerging_companies_weekly_review_limit_caps_results(
    db: Session,
) -> None:
    """Weekly review limit caps number of companies returned."""
    companies = [
        Company(name=f"Co {i}", website_url=f"https://co{i}.example.com")
        for i in range(5)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 7)
    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id, as_of=as_of,
            momentum=70, complexity=60, pressure=55, leadership_gap=40,
            composite=70 + i,
            pack_id=pack_id,
        )
        db.add(rs)
        _add_engagement_snapshot(db, c.id, as_of)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=3, outreach_score_threshold=30
    )

    assert len(result) == 3


def test_get_emerging_companies_cadence_blocked_included_with_observe_only(
    db: Session,
) -> None:
    """Companies with cadence_blocked appear with Observe Only recommendation."""
    company = Company(name="Cooldown Co", website_url="https://cooldown.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 8)
    rs = ReadinessSnapshot(
        company_id=company.id, as_of=as_of,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=80,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(
        db, company.id, as_of,
        esl_score=0.5,
        engagement_type="Observe Only",
        cadence_blocked=True,
    )
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    rs, es, co = result[0]
    assert es.cadence_blocked is True
    assert es.engagement_type == "Observe Only"


def test_get_emerging_companies_excludes_suppressed_entities(db: Session) -> None:
    """Companies with esl_decision=suppress in explain are excluded (Issue #175, Phase 3)."""
    c1 = Company(name="Allowed Co", website_url="https://allowed.example.com")
    c2 = Company(name="Suppressed Co", website_url="https://suppressed.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 25)
    for c in [c1, c2]:
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=80,
            pack_id=pack_id,
        )
        db.add(rs)
    _add_engagement_snapshot(db, c1.id, as_of, esl_score=0.8)
    es2 = EngagementSnapshot(
        company_id=c2.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=pack_id,
        explain={"esl_decision": "suppress", "esl_reason_code": "blocked_signal"},
    )
    db.add(es2)
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    assert result[0][2].name == "Allowed Co"


def test_get_emerging_companies_cadence_blocked_included_when_outreach_score_zero(
    db: Session,
) -> None:
    """cadence_blocked companies with outreach_score=0 (esl_score=0) are included.

    When CM=0, ESL=0 so OutreachScore=0. These should still appear with Observe Only
    badge per the docstring contract.
    """
    company = Company(name="Zero Outreach Co", website_url="https://zero.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    as_of = date(2099, 1, 9)
    rs = ReadinessSnapshot(
        company_id=company.id, as_of=as_of,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=80,
        pack_id=pack_id,
    )
    db.add(rs)
    _add_engagement_snapshot(
        db, company.id, as_of,
        esl_score=0.0,  # CM=0 → ESL=0 → outreach_score=0
        engagement_type="Observe Only",
        cadence_blocked=True,
    )
    db.commit()

    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30
    )

    assert len(result) == 1
    rs, es, co = result[0]
    assert es.cadence_blocked is True
    assert es.engagement_type == "Observe Only"
    assert compute_outreach_score(rs.composite, es.esl_score) == 0
