"""Tests for regenerate_ore_draft service (Issue #123 M2).

Regenerate: policy gate + draft generation + version history append; no new row.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot, SignalPack
from app.services.ore.playbook_loader import DEFAULT_PLAYBOOK_NAME

# Critic-compliant draft for deterministic tests (no surveillance, single CTA, opt-out)
_ORE_DRAFT_V1 = {
    "subject": "Quick question about TestCo",
    "message": (
        "Hi Jane Founder,\n\n"
        "When products add integrations and enterprise asks, systems often need a stabilization pass.\n\n"
        "I have a 2-page Tech Inflection Checklist that might help. Want me to send that checklist? "
        "No worries if now isn't the time."
    ),
}

_ORE_DRAFT_V2 = {
    "subject": "Follow-up about TestCo",
    "message": (
        "Hi Jane Founder,\n\n"
        "Another angle on tech inflection.\n\n"
        "I have a 2-page checklist that might help. Want me to send it? "
        "No worries if now isn't the time."
    ),
}

# Critic-compliant so second regenerate uses it as-is (single CTA, opt-out, no surveillance)
_ORE_DRAFT_V3 = {
    "subject": "Third subject",
    "message": (
        "Hi Jane Founder,\n\n"
        "One more thought on tech inflection.\n\n"
        "I have a 2-page checklist that might help. Want me to send it? "
        "No worries if now isn't the time."
    ),
}


def test_regenerate_ore_draft_returns_none_when_no_recommendation(db: Session) -> None:
    """regenerate_ore_draft returns None when no OutreachRecommendation exists for (company, as_of, pack)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="NoRecCo",
        website_url="https://norec.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 2, 20)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=80,
        pressure=50,
        leadership_gap=70,
        composite=75,
        pack_id=pack.id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.ore_pipeline import regenerate_ore_draft

    result = regenerate_ore_draft(db, company_id=company.id, as_of=as_of, pack_id=pack.id)
    assert result is None


def test_regenerate_ore_draft_when_gate_allows_increments_version_and_appends_history(
    db: Session,
) -> None:
    """When policy gate allows, regenerate returns same row, increments draft_generation_number, appends to history."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="RegenCo",
        website_url="https://regen.example.com",
        founder_name="Jane Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 2, 21)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack.id,
    )
    db.add(snapshot)
    db.commit()

    # Create existing recommendation (as if from pipeline: draft_generation_number=0, no history)
    existing = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[_ORE_DRAFT_V1],
        generation_version="1",
        pack_id=pack.id,
        playbook_id=DEFAULT_PLAYBOOK_NAME,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)
    rec_id = existing.id
    assert existing.draft_generation_number == 0
    assert existing.draft_version_history is None

    from app.services.ore.ore_pipeline import regenerate_ore_draft

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT_V2,
    ):
        result = regenerate_ore_draft(db, company_id=company.id, as_of=as_of, pack_id=pack.id)

    assert result is not None
    assert result.id == rec_id
    assert result.draft_generation_number == 1
    assert result.draft_variants is not None
    assert len(result.draft_variants) == 1
    assert result.draft_variants[0]["subject"] == _ORE_DRAFT_V2["subject"]
    assert result.draft_version_history is not None
    assert len(result.draft_version_history) == 1
    assert result.draft_version_history[0]["version"] == 0
    assert result.draft_version_history[0]["subject"] == _ORE_DRAFT_V1["subject"]
    assert "created_at_utc" in result.draft_version_history[0]


def test_regenerate_ore_draft_when_gate_blocks_cooldown_returns_none(db: Session) -> None:
    """When policy gate blocks (e.g. cooldown active), regenerate returns None and does not change the row."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="CooldownCo",
        website_url="https://cooldown.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 2, 22)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack.id,
    )
    db.add(snapshot)
    db.commit()

    existing = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[_ORE_DRAFT_V1],
        generation_version="1",
        pack_id=pack.id,
        playbook_id=DEFAULT_PLAYBOOK_NAME,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)
    original_subject = existing.draft_variants[0]["subject"]
    original_version = existing.draft_generation_number

    from app.services.ore.ore_pipeline import regenerate_ore_draft

    # ESL context with cooldown active → policy gate blocks draft
    ctx_blocked = {
        "esl_composite": 0.5,
        "stability_modifier": 0.8,
        "recommendation_type": "Observe Only",
        "explain": {},
        "cadence_blocked": True,
        "alignment_high": True,
        "trs": 82.0,
        "pack_id": pack.id,
        "esl_decision": "allow",
        "esl_reason_code": "ok",
        "sensitivity_level": None,
        "signal_ids": set(),
    }
    with patch(
        "app.services.ore.ore_pipeline.compute_esl_from_context",
        return_value=ctx_blocked,
    ):
        result = regenerate_ore_draft(db, company_id=company.id, as_of=as_of, pack_id=pack.id)

    assert result is None
    db.refresh(existing)
    assert existing.draft_variants[0]["subject"] == original_subject
    assert existing.draft_generation_number == original_version


def test_regenerate_ore_draft_version_history_after_two_regenerates(db: Session) -> None:
    """After two regenerates, draft_generation_number is 2 and history contains two entries."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="TwoRegenCo",
        website_url="https://tworegen.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 2, 23)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack.id,
    )
    db.add(snapshot)
    db.commit()

    existing = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[_ORE_DRAFT_V1],
        generation_version="1",
        pack_id=pack.id,
        playbook_id=DEFAULT_PLAYBOOK_NAME,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    from app.services.ore.ore_pipeline import regenerate_ore_draft

    drafts = [_ORE_DRAFT_V2, _ORE_DRAFT_V3]
    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        side_effect=drafts,
    ):
        r1 = regenerate_ore_draft(db, company_id=company.id, as_of=as_of, pack_id=pack.id)
        assert r1 is not None
        assert r1.draft_generation_number == 1
        assert len(r1.draft_version_history or []) == 1

        r2 = regenerate_ore_draft(db, company_id=company.id, as_of=as_of, pack_id=pack.id)
        assert r2 is not None
        assert r2.id == r1.id
        assert r2.draft_generation_number == 2
        assert len(r2.draft_version_history or []) == 2
        assert r2.draft_version_history[0]["version"] == 0
        assert r2.draft_version_history[1]["version"] == 1
        assert r2.draft_variants[0]["subject"] == "Third subject"


def test_generate_ore_recommendation_does_not_clear_version_fields_on_update(
    db: Session,
) -> None:
    """Pipeline update preserves draft_generation_number and draft_version_history (backward compatibility)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    assert pack is not None
    company = Company(
        name="PreserveCo",
        website_url="https://preserve.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 2, 24)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack.id,
    )
    db.add(snapshot)
    db.commit()

    history = [
        {
            "version": 0,
            "subject": "Old",
            "message": "Old msg",
            "created_at_utc": "2026-02-24T12:00:00Z",
        }
    ]
    existing = OutreachRecommendation(
        company_id=company.id,
        as_of=as_of,
        recommendation_type="Soft Value Share",
        outreach_score=41,
        channel="LinkedIn DM",
        draft_variants=[_ORE_DRAFT_V1],
        generation_version="1",
        pack_id=pack.id,
        playbook_id=DEFAULT_PLAYBOOK_NAME,
        draft_generation_number=2,
        draft_version_history=history,
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT_V2,
    ):
        updated = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            pack_id=pack.id,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )

    assert updated is not None
    assert updated.id == existing.id
    # Pipeline must not clear version fields when updating existing row
    assert updated.draft_generation_number == 2
    assert updated.draft_version_history == history
