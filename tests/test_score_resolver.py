"""Tests for score_resolver (Phase 2, Plan Step 3)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot
from app.services.score_resolver import get_company_score, get_company_scores_batch


def test_get_company_score_from_snapshot(db: Session) -> None:
    """get_company_score returns composite from ReadinessSnapshot when available."""
    company = Company(name="Snapshot Co", website_url="https://snap.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date.today(),
        momentum=20,
        complexity=15,
        pressure=18,
        leadership_gap=12,
        composite=65,
        pack_id=None,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    score = get_company_score(db, company.id)
    assert score == 65


def test_get_company_score_fallback_to_cto_need_score(db: Session) -> None:
    """get_company_score falls back to Company.cto_need_score when no snapshot."""
    company = Company(
        name="Fallback Co",
        website_url="https://fallback.example.com",
        cto_need_score=72,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    score = get_company_score(db, company.id)
    assert score == 72


def test_get_company_score_returns_none_when_no_data(db: Session) -> None:
    """get_company_score returns None when company has no snapshot and no cto_need_score."""
    company = Company(name="Empty Co", website_url="https://empty.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    score = get_company_score(db, company.id)
    assert score is None


def test_get_company_score_prefers_snapshot_over_cto_need(db: Session) -> None:
    """When both exist, get_company_score prefers ReadinessSnapshot."""
    company = Company(
        name="Both Co",
        website_url="https://both.example.com",
        cto_need_score=50,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date.today(),
        momentum=25,
        complexity=20,
        pressure=22,
        leadership_gap=15,
        composite=82,
        pack_id=None,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    score = get_company_score(db, company.id)
    assert score == 82


def test_get_company_scores_batch_empty_input(db: Session) -> None:
    """get_company_scores_batch returns empty dict for empty input."""
    assert get_company_scores_batch(db, []) == {}


def test_get_company_scores_batch_matches_single_company(db: Session) -> None:
    """get_company_scores_batch returns same result as get_company_score for one company."""
    company = Company(name="Batch Co", website_url="https://batch.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date.today(),
        momentum=10,
        complexity=10,
        pressure=10,
        leadership_gap=10,
        composite=40,
        pack_id=None,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    single = get_company_score(db, company.id)
    batch = get_company_scores_batch(db, [company.id])
    assert single == 40
    assert batch == {company.id: 40}


def test_get_company_scores_batch_multiple_companies(db: Session) -> None:
    """get_company_scores_batch returns correct scores for multiple companies."""
    c1 = Company(name="C1", website_url="https://c1.example.com", cto_need_score=10)
    c2 = Company(name="C2", website_url="https://c2.example.com")
    c3 = Company(name="C3", website_url="https://c3.example.com", cto_need_score=30)
    db.add_all([c1, c2, c3])
    db.commit()
    for c in [c1, c2, c3]:
        db.refresh(c)

    snapshot = ReadinessSnapshot(
        company_id=c2.id,
        as_of=date.today(),
        momentum=5,
        complexity=5,
        pressure=5,
        leadership_gap=5,
        composite=20,
        pack_id=None,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    result = get_company_scores_batch(db, [c1.id, c2.id, c3.id])
    assert result == {c1.id: 10, c2.id: 20, c3.id: 30}


def test_get_company_scores_batch_prefers_snapshot_over_cto_need(db: Session) -> None:
    """get_company_scores_batch prefers ReadinessSnapshot over cto_need_score."""
    company = Company(
        name="Both Co",
        website_url="https://both.example.com",
        cto_need_score=50,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date.today(),
        momentum=25,
        complexity=20,
        pressure=22,
        leadership_gap=15,
        composite=82,
        pack_id=None,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    result = get_company_scores_batch(db, [company.id])
    assert result == {company.id: 82}


def test_get_company_score_uses_workspace_pack(
    db: Session, fractional_cto_pack_id
) -> None:
    """Phase 3: get_company_score with workspace_id resolves pack from workspace."""
    from uuid import uuid4

    from app.models import Workspace

    other_ws_id = uuid4()
    ws = Workspace(
        id=other_ws_id,
        name="Other Workspace",
        active_pack_id=fractional_cto_pack_id,
    )
    db.add(ws)
    db.commit()

    company = Company(name="Workspace Score Co", website_url="https://ws.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date.today(),
        momentum=30,
        complexity=25,
        pressure=20,
        leadership_gap=10,
        composite=88,
        pack_id=fractional_cto_pack_id,
        computed_at=datetime.now(UTC),
    )
    db.add(snapshot)
    db.commit()

    score = get_company_score(db, company.id, workspace_id=str(other_ws_id))
    assert score == 88
