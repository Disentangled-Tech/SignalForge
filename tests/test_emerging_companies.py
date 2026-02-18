"""Tests for get_emerging_companies (Issue #93)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot
from app.services.briefing import get_emerging_companies


def test_get_emerging_companies_returns_top_10_by_composite(db: Session) -> None:
    """Returns up to 10 companies ordered by composite descending."""
    companies = [
        Company(name=f"Emerging Co {i}", website_url=f"https://emerging{i}.example.com")
        for i in range(15)
    ]
    db.add_all(companies)
    db.commit()
    for c in companies:
        db.refresh(c)

    as_of = date(2050, 2, 18)
    # Create 15 snapshots with composites 65-79 (all >= 60)
    for i, c in enumerate(companies):
        snap = ReadinessSnapshot(
            company_id=c.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=65 + i,
        )
        db.add(snap)
    db.commit()

    result = get_emerging_companies(db, as_of, limit=10, threshold=60)

    assert len(result) == 10
    # Should be ordered by composite desc: 79, 78, ..., 70
    composites = [snap.composite for snap, _ in result]
    assert composites == list(range(79, 69, -1))


def test_get_emerging_companies_respects_threshold(db: Session) -> None:
    """Snapshots with composite < threshold are excluded."""
    c1 = Company(name="Above Co", website_url="https://above.example.com")
    c2 = Company(name="Below Co", website_url="https://below.example.com")
    db.add_all([c1, c2])
    db.commit()
    db.refresh(c1)
    db.refresh(c2)

    as_of = date(2050, 2, 19)
    snap1 = ReadinessSnapshot(
        company_id=c1.id, as_of=as_of,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=65,
    )
    snap2 = ReadinessSnapshot(
        company_id=c2.id, as_of=as_of,
        momentum=50, complexity=40, pressure=35, leadership_gap=30, composite=59,
    )
    db.add_all([snap1, snap2])
    db.commit()

    result = get_emerging_companies(db, as_of, limit=10, threshold=60)

    assert len(result) == 1
    assert result[0][0].composite == 65
    assert result[0][1].name == "Above Co"


def test_get_emerging_companies_respects_date(db: Session) -> None:
    """Snapshots for different date are excluded."""
    company = Company(name="Date Co", website_url="https://date.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of_target = date(2050, 2, 20)
    as_of_other = date(2050, 2, 19)
    snap = ReadinessSnapshot(
        company_id=company.id, as_of=as_of_other,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=70,
    )
    db.add(snap)
    db.commit()

    result = get_emerging_companies(db, as_of_target, limit=10, threshold=60)

    assert len(result) == 0


def test_get_emerging_companies_empty_when_no_snapshots(db: Session) -> None:
    """Returns empty list when no snapshots exist for date."""
    result = get_emerging_companies(db, date(2050, 2, 21), limit=10, threshold=60)
    assert result == []


def test_get_emerging_companies_returns_fewer_than_limit(db: Session) -> None:
    """Returns all available when fewer than limit qualify."""
    c1 = Company(name="Only Co", website_url="https://only.example.com")
    db.add(c1)
    db.commit()
    db.refresh(c1)

    as_of = date(2050, 2, 22)
    snap = ReadinessSnapshot(
        company_id=c1.id, as_of=as_of,
        momentum=70, complexity=60, pressure=55, leadership_gap=40, composite=65,
    )
    db.add(snap)
    db.commit()

    result = get_emerging_companies(db, as_of, limit=10, threshold=60)

    assert len(result) == 1
    assert result[0][1].name == "Only Co"
