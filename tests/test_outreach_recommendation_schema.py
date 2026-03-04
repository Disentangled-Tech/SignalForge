"""Outreach recommendation schema tests (Issue #115 M1).

Model and insert/retrieve for generation_version; unique constraint in M3.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, SignalPack


def test_outreach_recommendation_model_has_generation_version_nullable() -> None:
    """OutreachRecommendation model includes generation_version and it is nullable."""
    rec = OutreachRecommendation(
        company_id=1,
        as_of=date(2026, 2, 18),
        recommendation_type="Observe Only",
        outreach_score=0,
    )
    assert rec.generation_version is None
    rec.generation_version = "1"
    assert rec.generation_version == "1"


def test_outreach_recommendation_model_accepts_generation_version() -> None:
    """OutreachRecommendation accepts generation_version on construction."""
    rec = OutreachRecommendation(
        company_id=1,
        as_of=date(2026, 2, 18),
        recommendation_type="Standard Outreach",
        outreach_score=50,
        generation_version="2",
    )
    assert rec.generation_version == "2"


@pytest.mark.integration
def test_insert_and_retrieve_outreach_recommendation_with_generation_version(
    db: Session,
) -> None:
    """Insert and retrieve one row with all fields including generation_version (Issue #115).

    Can insert and retrieve test row with generation_version set.
    """
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="SchemaTestCo",
        website_url="https://schematest.example.com",
        founder_name="Test Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    rec = OutreachRecommendation(
        company_id=company.id,
        as_of=date(2026, 3, 4),
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[{"subject": "Hi", "message": "Hello"}],
        strategy_notes={"note": "test"},
        safeguards_triggered=["cooldown"],
        generation_version="1",
        pack_id=pack.id,
        playbook_id="fractional_cto_standard_v1",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    assert rec.id is not None
    assert rec.generation_version == "1"

    found = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company.id,
            OutreachRecommendation.as_of == rec.as_of,
            OutreachRecommendation.pack_id == pack.id,
        )
        .first()
    )
    assert found is not None
    assert found.id == rec.id
    assert found.generation_version == "1"
    assert found.recommendation_type == "Soft Value Share"
    assert found.draft_variants == [{"subject": "Hi", "message": "Hello"}]
    assert found.strategy_notes == {"note": "test"}
    assert found.safeguards_triggered == ["cooldown"]
