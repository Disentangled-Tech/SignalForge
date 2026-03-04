"""Outreach recommendation schema tests (Issue #115 M1, M3, M4; Issue #123 M1).

Model and insert/retrieve for generation_version; unique constraint in M3;
Pydantic read schema and docs in M4. Issue #123 M1: draft_generation_number and
draft_version_history columns and defaults.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, SignalPack
from app.schemas.outreach import OutreachRecommendationRead


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
def test_outreach_recommendation_draft_generation_number_defaults_to_zero_on_persist(
    db: Session,
) -> None:
    """Persisted row without draft_generation_number gets default 0 (Issue #123 M1)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="DefaultGenCo",
        website_url="https://defaultgen.example.com",
        founder_name="Default Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    rec = OutreachRecommendation(
        company_id=company.id,
        as_of=date(2026, 3, 7),
        recommendation_type="Observe Only",
        outreach_score=0,
        pack_id=pack.id,
        playbook_id="default",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    assert rec.draft_generation_number == 0


def test_outreach_recommendation_model_draft_version_history_nullable() -> None:
    """OutreachRecommendation has draft_version_history nullable (Issue #123 M1)."""
    rec = OutreachRecommendation(
        company_id=1,
        as_of=date(2026, 2, 18),
        recommendation_type="Observe Only",
        outreach_score=0,
    )
    assert rec.draft_version_history is None
    rec.draft_version_history = [
        {"version": 1, "subject": "S", "message": "M", "created_at_utc": "2026-03-09T12:00:00Z"}
    ]
    assert len(rec.draft_version_history) == 1
    assert rec.draft_version_history[0]["version"] == 1


@pytest.mark.integration
def test_insert_and_retrieve_outreach_recommendation_with_draft_version_fields(
    db: Session,
) -> None:
    """Insert and retrieve row with draft_generation_number and draft_version_history (Issue #123 M1)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="VersionHistoryCo",
        website_url="https://versionhistory.example.com",
        founder_name="Version Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    history = [
        {
            "version": 1,
            "subject": "Old subj",
            "message": "Old msg",
            "created_at_utc": "2026-03-09T10:00:00Z",
        },
    ]
    rec = OutreachRecommendation(
        company_id=company.id,
        as_of=date(2026, 3, 6),
        recommendation_type="Standard Outreach",
        outreach_score=55,
        draft_variants=[{"subject": "Current", "message": "Current draft"}],
        draft_generation_number=2,
        draft_version_history=history,
        pack_id=pack.id,
        playbook_id="default",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    assert rec.draft_generation_number == 2
    assert rec.draft_version_history == history
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
    assert found.draft_generation_number == 2
    assert found.draft_version_history == history


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


@pytest.mark.integration
def test_outreach_recommendation_duplicate_company_as_of_pack_raises_integrity_error(
    db: Session,
) -> None:
    """Duplicate (company_id, as_of, pack_id) raises IntegrityError (Issue #115 M3).

    Raw insert of a second row with same company_id, as_of, pack_id must fail;
    ORE uses upsert so application path does not hit this.
    """
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="DupTestCo",
        website_url="https://duptest.example.com",
        founder_name="Dup Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 3, 5)
    rec1 = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Observe Only",
        outreach_score=0,
        generation_version="1",
        pack_id=pack.id,
        playbook_id="default",
    )
    db.add(rec1)
    db.commit()

    rec2 = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Standard Outreach",
        outreach_score=50,
        generation_version="1",
        pack_id=pack.id,
        playbook_id="default",
    )
    db.add(rec2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_outreach_recommendation_read_from_orm_attributes() -> None:
    """OutreachRecommendationRead can be built from ORM instance (Issue #115 M4)."""
    rec = OutreachRecommendation(
        id=1,
        company_id=10,
        as_of=date(2026, 3, 4),
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[{"subject": "Hi", "message": "Hello"}],
        strategy_notes={"note": "test"},
        safeguards_triggered=["cooldown"],
        generation_version="1",
        pack_id=None,
        playbook_id="fractional_cto_standard_v1",
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
    )
    read = OutreachRecommendationRead.model_validate(rec)
    assert read.id == 1
    assert read.company_id == 10
    assert read.as_of == date(2026, 3, 4)
    assert read.recommendation_type == "Soft Value Share"
    assert read.outreach_score == 41
    assert read.channel == "LinkedIn DM"
    assert read.draft_variants == [{"subject": "Hi", "message": "Hello"}]
    assert read.strategy_notes == {"note": "test"}
    assert read.safeguards_triggered == ["cooldown"]
    assert read.generation_version == "1"
    assert read.pack_id is None
    assert read.playbook_id == "fractional_cto_standard_v1"
    assert read.created_at == datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)


def test_outreach_recommendation_read_roundtrip_from_dict() -> None:
    """OutreachRecommendationRead validates from dict (future API payload)."""
    payload = {
        "id": 2,
        "company_id": 20,
        "as_of": "2026-03-05",
        "recommendation_type": "Observe Only",
        "outreach_score": 0,
        "channel": None,
        "draft_variants": None,
        "strategy_notes": None,
        "safeguards_triggered": None,
        "generation_version": "v1",
        "pack_id": None,
        "playbook_id": None,
        "created_at": "2026-03-05T14:00:00+00:00",
    }
    read = OutreachRecommendationRead.model_validate(payload)
    assert read.id == 2
    assert read.company_id == 20
    assert read.recommendation_type == "Observe Only"
    assert read.outreach_score == 0
    assert read.generation_version == "v1"
