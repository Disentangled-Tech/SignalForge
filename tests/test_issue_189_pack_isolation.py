"""Issue #189: Pack isolation integration tests.

Verifies that data is correctly scoped by pack_id:
- Insert data for two packs; query by pack returns only that pack's data
- No cross-pack signal contamination
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Company,
    EngagementSnapshot,
    OutreachRecommendation,
    ReadinessSnapshot,
    SignalPack,
)
from app.services.briefing import get_emerging_companies

_ORE_DRAFT = {
    "subject": "Quick question",
    "message": "Hi,\n\nValue proposition.\n\nWant me to send a checklist?",
}


@pytest.fixture
def fractional_cto_pack(db: Session) -> SignalPack:
    """Fractional CTO pack from migration."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None, "fractional_cto_v1 pack must exist (run migration)"
    return pack


@pytest.mark.integration
def test_pack_isolation_readiness_snapshots(
    db: Session,
    fractional_cto_pack: SignalPack,
    second_pack: SignalPack,
) -> None:
    """Query ReadinessSnapshot by pack_id returns only that pack's data."""
    company = Company(name="IsolationCo", website_url="https://iso.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 6, 15)

    rs_cto = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=65,
        pack_id=fractional_cto_pack.id,
    )
    rs_book = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=50,
        complexity=40,
        pressure=30,
        leadership_gap=20,
        composite=35,
        pack_id=second_pack.id,
    )
    db.add_all([rs_cto, rs_book])
    db.commit()

    cto_snapshots = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == fractional_cto_pack.id,
        )
        .all()
    )
    book_snapshots = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == second_pack.id,
        )
        .all()
    )

    assert len(cto_snapshots) == 1
    assert cto_snapshots[0].composite == 65
    assert len(book_snapshots) == 1
    assert book_snapshots[0].composite == 35


@pytest.mark.integration
def test_pack_isolation_engagement_snapshots(
    db: Session,
    fractional_cto_pack: SignalPack,
    second_pack: SignalPack,
) -> None:
    """Query EngagementSnapshot by pack_id returns only that pack's data."""
    company = Company(name="ESL IsolationCo", website_url="https://esl-iso.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 6, 16)

    es_cto = EngagementSnapshot(
        company_id=company.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=fractional_cto_pack.id,
    )
    es_book = EngagementSnapshot(
        company_id=company.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Observe Only",
        cadence_blocked=True,
        pack_id=second_pack.id,
    )
    db.add_all([es_cto, es_book])
    db.commit()

    cto_snapshots = (
        db.query(EngagementSnapshot)
        .filter(
            EngagementSnapshot.company_id == company.id,
            EngagementSnapshot.as_of == as_of,
            EngagementSnapshot.pack_id == fractional_cto_pack.id,
        )
        .all()
    )
    book_snapshots = (
        db.query(EngagementSnapshot)
        .filter(
            EngagementSnapshot.company_id == company.id,
            EngagementSnapshot.as_of == as_of,
            EngagementSnapshot.pack_id == second_pack.id,
        )
        .all()
    )

    assert len(cto_snapshots) == 1
    assert cto_snapshots[0].engagement_type == "Standard Outreach"
    assert len(book_snapshots) == 1
    assert book_snapshots[0].engagement_type == "Observe Only"


@pytest.mark.integration
def test_get_emerging_companies_respects_pack_when_filtered(
    db: Session,
    fractional_cto_pack: SignalPack,
    second_pack: SignalPack,
) -> None:
    """get_emerging_companies returns only pack-scoped data; excludes other packs."""
    companies = [
        Company(name=f"PackCo {i}", website_url=f"https://pack{i}.example.com") for i in range(3)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    as_of = date(2099, 7, 1)

    for i, c in enumerate(companies):
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=[70, 80, 90][i],
            pack_id=fractional_cto_pack.id,
        )
        es = EngagementSnapshot(
            company_id=c.id,
            as_of=as_of,
            esl_score=0.8,
            engagement_type="Standard Outreach",
            cadence_blocked=False,
            pack_id=fractional_cto_pack.id,
        )
        db.add_all([rs, es])
    db.commit()

    our_company_ids = {c.id for c in companies}
    result = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30, pack_id=fractional_cto_pack.id
    )

    assert len(result) >= 3, "Must include our 3 companies"
    for rs, es, _company in result:
        assert rs.pack_id == fractional_cto_pack.id
        assert es.pack_id == fractional_cto_pack.id
    result_company_ids = {c.id for _, _, c in result}
    assert our_company_ids <= result_company_ids, (
        "Our 3 companies must appear in pack-scoped results"
    )

    result_book = get_emerging_companies(
        db, as_of, limit=10, outreach_score_threshold=30, pack_id=second_pack.id
    )
    for rs, _es, _ in result_book:
        assert rs.pack_id == second_pack.id
    assert our_company_ids.isdisjoint({c.id for _, _, c in result_book}), (
        "Our fractional_cto companies must not appear when querying second pack"
    )


@pytest.mark.integration
def test_outreach_recommendation_stores_pack_id_and_playbook_id(
    db: Session,
    fractional_cto_pack: SignalPack,
) -> None:
    """OutreachRecommendation model persists pack_id and playbook_id (Issue #189).

    Verifies schema supports pack-scoped outreach. ORE pipeline will need to
    set pack_id from ReadinessSnapshot when implemented.
    """
    company = Company(
        name="ORECo",
        website_url="https://ore.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 20)
    rec = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Standard Outreach",
        outreach_score=60,
        pack_id=fractional_cto_pack.id,
        playbook_id="fractional_cto_standard_v1",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    assert rec.pack_id == fractional_cto_pack.id
    assert rec.playbook_id == "fractional_cto_standard_v1"

    # Query by pack_id
    found = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company.id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == fractional_cto_pack.id,
        )
        .first()
    )
    assert found is not None
    assert found.playbook_id == "fractional_cto_standard_v1"


@pytest.mark.integration
def test_cross_pack_no_contamination(
    db: Session,
    fractional_cto_pack: SignalPack,
    second_pack: SignalPack,
) -> None:
    """Querying by pack A does not return pack B's data."""
    company = Company(name="CrossPackCo", website_url="https://cross.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2099, 8, 1)

    rs_cto = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=90,
        complexity=80,
        pressure=70,
        leadership_gap=60,
        composite=85,
        pack_id=fractional_cto_pack.id,
    )
    rs_book = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=30,
        complexity=20,
        pressure=10,
        leadership_gap=5,
        composite=16,
        pack_id=second_pack.id,
    )
    db.add_all([rs_cto, rs_book])
    db.commit()

    cto_only = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == fractional_cto_pack.id,
        )
        .all()
    )
    book_only = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.pack_id == second_pack.id,
        )
        .all()
    )

    assert len(cto_only) == 1
    assert cto_only[0].composite == 85
    assert len(book_only) == 1
    assert book_only[0].composite == 16
