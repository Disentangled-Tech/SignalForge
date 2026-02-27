"""Pack-scoped query tests (Issue #189, Plan §4.3).

Integration tests: get_emerging_companies and briefing data must be pack-scoped.
No cross-pack leakage.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.api.briefing_views import get_briefing_data
from app.models import (
    AnalysisRecord,
    BriefingItem,
    Company,
    EngagementSnapshot,
    ReadinessSnapshot,
    SignalPack,
)
from app.services.briefing import get_emerging_companies


@pytest.fixture
def fractional_cto_pack(db: Session) -> SignalPack:
    """Fractional CTO pack from migration."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None, "fractional_cto_v1 pack must exist (run migration)"
    return pack


@pytest.mark.integration
def test_get_emerging_companies_excludes_other_pack(
    db: Session,
    fractional_cto_pack: SignalPack,
    second_pack: SignalPack,
) -> None:
    """get_emerging_companies(pack_id=A) returns only pack A data; pack B excluded (Issue #289 M1)."""
    c_cto = Company(name="CTO Co", website_url="https://cto.example.com")
    c_book = Company(name="Second Pack Co", website_url="https://second.example.com")
    db.add_all([c_cto, c_book])
    db.commit()
    db.refresh(c_cto)
    db.refresh(c_book)

    as_of = date(2099, 9, 1)

    rs_cto = ReadinessSnapshot(
        company_id=c_cto.id,
        as_of=as_of,
        momentum=80,
        complexity=70,
        pressure=60,
        leadership_gap=50,
        composite=75,
        pack_id=fractional_cto_pack.id,
    )
    es_cto = EngagementSnapshot(
        company_id=c_cto.id,
        as_of=as_of,
        esl_score=0.85,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=fractional_cto_pack.id,
    )
    rs_book = ReadinessSnapshot(
        company_id=c_book.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=50,
        leadership_gap=40,
        composite=65,
        pack_id=second_pack.id,
    )
    es_book = EngagementSnapshot(
        company_id=c_book.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Low-Pressure Intro",
        cadence_blocked=False,
        pack_id=second_pack.id,
    )
    db.add_all([rs_cto, es_cto, rs_book, es_book])
    db.commit()

    result_cto = get_emerging_companies(db, as_of, limit=10, pack_id=fractional_cto_pack.id)
    result_book = get_emerging_companies(db, as_of, limit=10, pack_id=second_pack.id)

    cto_company_ids = {c.id for _, _, c in result_cto}
    book_company_ids = {c.id for _, _, c in result_book}

    assert c_cto.id in cto_company_ids
    assert c_book.id not in cto_company_ids, "Pack B company must not appear when querying pack A"

    assert c_book.id in book_company_ids
    assert c_cto.id not in book_company_ids, "Pack A company must not appear when querying pack B"


@pytest.mark.integration
def test_get_briefing_data_emerging_companies_single_pack(
    db: Session,
    fractional_cto_pack: SignalPack,
) -> None:
    """get_briefing_data returns emerging_companies with consistent pack_id (no cross-pack mix)."""
    c = Company(name="Briefing Co", website_url="https://brief.example.com")
    db.add(c)
    db.commit()
    db.refresh(c)

    as_of = date.today()
    rs = ReadinessSnapshot(
        company_id=c.id,
        as_of=as_of,
        momentum=75,
        complexity=65,
        pressure=55,
        leadership_gap=45,
        composite=70,
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

    data = get_briefing_data(db, as_of)
    emerging = data["emerging_companies"]

    for ec in emerging:
        assert ec["snapshot"].pack_id == ec["engagement_snapshot"].pack_id
        assert ec["snapshot"].pack_id in (fractional_cto_pack.id, None)


@pytest.mark.integration
def test_get_briefing_data_filters_suppressed_items(
    db: Session,
    fractional_cto_pack: SignalPack,
) -> None:
    """get_briefing_data excludes BriefingItems for companies with esl_decision=suppress (Issue #175)."""
    c1 = Company(name="Allowed Co", website_url="https://allowed.example.com")
    c2 = Company(name="Suppressed Co", website_url="https://suppressed.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    as_of = date.today()

    # AnalysisRecord required for BriefingItem
    a1 = AnalysisRecord(company_id=c1.id, source_type="full_analysis", stage="mvp")
    a2 = AnalysisRecord(company_id=c2.id, source_type="full_analysis", stage="mvp")
    db.add_all([a1, a2])
    db.commit()
    db.refresh(a1)
    db.refresh(a2)

    bi1 = BriefingItem(
        company_id=c1.id,
        analysis_id=a1.id,
        why_now="Test",
        briefing_date=as_of,
    )
    bi2 = BriefingItem(
        company_id=c2.id,
        analysis_id=a2.id,
        why_now="Test",
        briefing_date=as_of,
    )
    db.add_all([bi1, bi2])

    for c in [c1, c2]:
        rs = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=80,
            pack_id=fractional_cto_pack.id,
        )
        db.add(rs)
    es1 = EngagementSnapshot(
        company_id=c1.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=fractional_cto_pack.id,
    )
    es2 = EngagementSnapshot(
        company_id=c2.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=fractional_cto_pack.id,
        explain={"esl_decision": "suppress", "esl_reason_code": "blocked_signal"},
    )
    db.add_all([es1, es2])
    db.commit()

    data = get_briefing_data(db, as_of)

    company_ids_in_items = {i.company_id for i in data["items"]}
    assert c1.id in company_ids_in_items
    assert c2.id not in company_ids_in_items
