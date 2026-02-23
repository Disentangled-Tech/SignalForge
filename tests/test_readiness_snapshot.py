"""ReadinessSnapshot model tests (Issue #82)."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, ReadinessSnapshot


def test_readiness_snapshot_model_creation() -> None:
    """Model instantiates with all fields."""
    snapshot = ReadinessSnapshot(
        company_id=1,
        as_of=date(2026, 2, 18),
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=62,
        explain={
            "weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
            "top_events": [{"event_type": "funding_raised", "contribution_points": 35}],
        },
    )
    assert snapshot.company_id == 1
    assert snapshot.as_of == date(2026, 2, 18)
    assert snapshot.momentum == 70
    assert snapshot.complexity == 60
    assert snapshot.pressure == 55
    assert snapshot.leadership_gap == 40
    assert snapshot.composite == 62
    assert snapshot.explain["weights"]["M"] == 0.30
    assert len(snapshot.explain["top_events"]) == 1
    # computed_at is set on insert; before persist it may be None


def test_readiness_snapshot_explain_jsonb_persists(db: Session) -> None:
    """JSON explain payload round-trips correctly."""
    company = Company(name="ExplainCo", website_url="https://explain.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    explain_payload = {
        "weights": {"M": 0.30, "C": 0.30, "P": 0.25, "G": 0.15},
        "dimensions": {"M": 70, "C": 60, "P": 55, "G": 40, "R": 62},
        "top_events": [
            {
                "event_type": "funding_raised",
                "event_time": "2026-02-01T00:00:00Z",
                "source": "crunchbase",
                "url": "https://example.com/round",
                "contribution_points": 35,
                "confidence": 0.9,
            }
        ],
        "suppressors_applied": [],
        "notes": "Sample snapshot",
    }

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=62,
        explain=explain_payload,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    assert snapshot.explain == explain_payload
    assert snapshot.explain["top_events"][0]["event_type"] == "funding_raised"
    assert snapshot.explain["top_events"][0]["contribution_points"] == 35


def test_readiness_snapshot_unique_constraint(
    db: Session, fractional_cto_pack_id
) -> None:
    """Duplicate (company_id, as_of, pack_id) raises IntegrityError (Issue #189)."""
    company = Company(name="UniqueCo", website_url="https://unique.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 18)
    s1 = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=62,
        pack_id=fractional_cto_pack_id,
    )
    db.add(s1)
    db.commit()

    s2 = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=50,
        pressure=60,
        leadership_gap=30,
        composite=65,
        pack_id=fractional_cto_pack_id,
    )
    db.add(s2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_readiness_snapshot_index_supports_top_n(db: Session) -> None:
    """Query as_of=X ORDER BY composite DESC LIMIT N works."""
    company1 = Company(name="TopN Co 1", website_url="https://topn1.example.com")
    company2 = Company(name="TopN Co 2", website_url="https://topn2.example.com")
    company3 = Company(name="TopN Co 3", website_url="https://topn3.example.com")
    db.add_all([company1, company2, company3])
    db.commit()
    for c in [company1, company2, company3]:
        db.refresh(c)

    # Use a unique far-future date to avoid collisions with leftover test data
    as_of = date(2099, 12, 31)
    company_ids = [company1.id, company2.id, company3.id]
    snapshots = [
        ReadinessSnapshot(company_id=company1.id, as_of=as_of, momentum=80, complexity=70, pressure=60, leadership_gap=50, composite=70),
        ReadinessSnapshot(company_id=company2.id, as_of=as_of, momentum=60, complexity=50, pressure=40, leadership_gap=30, composite=50),
        ReadinessSnapshot(company_id=company3.id, as_of=as_of, momentum=70, complexity=65, pressure=55, leadership_gap=45, composite=65),
    ]
    db.add_all(snapshots)
    db.commit()

    # Filter to our test companies only (db fixture does not rollback; other tests may leave data)
    top_n = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.as_of == as_of,
            ReadinessSnapshot.company_id.in_(company_ids),
        )
        .order_by(ReadinessSnapshot.composite.desc())
        .limit(2)
        .all()
    )
    assert len(top_n) == 2
    assert top_n[0].composite == 70
    assert top_n[1].composite == 65


def test_readiness_snapshot_company_relationship(db: Session) -> None:
    """Company.readiness_snapshots loads correctly."""
    company = Company(name="RelCo", website_url="https://rel.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=date(2026, 2, 18),
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=62,
    )
    db.add(snapshot)
    db.commit()

    db.refresh(company)
    assert len(company.readiness_snapshots) == 1
    assert company.readiness_snapshots[0].composite == 62
    assert company.readiness_snapshots[0].company_id == company.id
