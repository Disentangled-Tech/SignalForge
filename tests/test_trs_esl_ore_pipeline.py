"""Integration test: TRS → ESL → ORE pipeline (Issue #124).

Simulates: Company with TRS=82, StabilityModifier=0.5, Cooldown inactive, High alignment.
Expects: Recommendation capped at Soft Value Share, No surveillance language,
         Single CTA, OutreachScore computed correctly.
Fixture strategy: Insert Company and ReadinessSnapshot directly (no SignalEvents).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot, SignalPack

# Critic-compliant draft for integration test (no surveillance, single CTA, opt-out)
_ORE_DRAFT = {
    "subject": "Quick question about TestCo",
    "message": (
        "Hi Jane Founder,\n\n"
        "When products add integrations and enterprise asks, systems often need a stabilization pass.\n\n"
        "I have a 2-page Tech Inflection Checklist that might help. Want me to send that checklist? "
        "No worries if now isn't the time."
    ),
}


def test_trs_esl_ore_pipeline_integration(db: Session) -> None:
    """Full pipeline: TRS=82, SM=0.5, cooldown off, high alignment.

    - OutreachScore = round(82 * 0.5) = 41
    - Recommendation capped at Soft Value Share (SM < 0.7)
    - draft_variants: no surveillance phrases, single CTA
    - Snapshot + recommendation stored
    """
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    # Seed: Company + ReadinessSnapshot directly (no SignalEvents)
    company = Company(
        name="TestCo",
        website_url="https://testco.example.com",
        founder_name="Jane Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 18)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    # Call ORE pipeline (mock draft generator for deterministic test)
    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert rec.recommendation_type == "Soft Value Share"
    assert rec.outreach_score == 41  # round(82 * 0.5)

    # draft_variants: primary variant with no surveillance phrases, single CTA
    variants = rec.draft_variants or []
    assert len(variants) >= 1
    primary = variants[0]
    subject = primary.get("subject", "")
    message = primary.get("message", "")

    # No surveillance language (critic rules)
    surveillance_phrases = [
        "I noticed you",
        "I saw that you",
        "After your recent funding",
        "You're hiring",
    ]
    combined = f"{subject} {message}".lower()
    for phrase in surveillance_phrases:
        assert phrase.lower() not in combined, f"Surveillance phrase '{phrase}' found"

    # Single CTA (critic rules)
    cta_count = sum(1 for c in ["Want me to send", "Open to a", "If helpful"] if c in message)
    assert cta_count <= 1, "Multiple CTAs detected"

    # Stored in outreach_recommendations (Issue #189: pack_id set by ORE pipeline)
    assert rec.company_id == company.id
    assert rec.as_of == as_of
    assert rec.pack_id == pack_id, "ORE pipeline must set pack_id on OutreachRecommendation"
    # Issue #115 M1: generation_version set from pack manifest
    assert rec.generation_version is not None
    assert rec.generation_version == "1", "fractional_cto_v1 pack version is 1"


def test_ore_pipeline_uses_computed_esl(db: Session) -> None:
    """ORE computes ESL from context when stability_modifier not passed (Issue #106).

    With no SignalEvents, no OutreachHistory: SVI=0, SPI=0, CSI=1 → SM high.
    ESL composite ≈ BE (TRS/100). Recommendation and outreach_score from computed ESL.
    """
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ComputedESLCo",
        website_url="https://computed.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 18)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=80,
        complexity=80,
        pressure=50,
        leadership_gap=70,
        composite=75,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            # No stability_modifier → compute from context
        )

    assert rec is not None
    # No stress signals → SM high → not capped at Soft Value Share
    assert rec.recommendation_type in (
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    )
    # OutreachScore = round(TRS * ESL_composite)
    assert rec.outreach_score >= 50
    assert rec.company_id == company.id
    assert rec.pack_id == pack_id, "ORE pipeline must set pack_id when computing ESL from context"


def test_ore_suppress_no_draft(db: Session) -> None:
    """M4: When esl_decision is suppress, ORE returns Observe Only and no draft_variants."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="SuppressCo",
        website_url="https://suppress.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 20)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    rec = generate_ore_recommendation(
        db,
        company_id=company.id,
        as_of=as_of,
        stability_modifier=0.9,
        cooldown_active=False,
        alignment_high=True,
        esl_decision="suppress",
        sensitivity_level=None,
    )

    assert rec is not None
    assert rec.recommendation_type == "Observe Only"
    assert rec.draft_variants is None or rec.draft_variants == []
    assert rec.safeguards_triggered is not None
    assert any("suppress" in (s or "").lower() for s in rec.safeguards_triggered)


def test_ore_playbook_sensitivity_excluded_no_draft(db: Session) -> None:
    """M4: When playbook has sensitivity_levels and entity level not in list, no draft, Soft Value Share."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="HighSensCo",
        website_url="https://highsens.example.com",
        founder_name="Founder",
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
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.ore_pipeline import generate_ore_recommendation
    from app.services.ore.draft_generator import PATTERN_FRAMES, VALUE_ASSETS, CTAS

    # Playbook that only allows low/medium; entity has high → no draft
    restricted_playbook = {
        "pattern_frames": PATTERN_FRAMES,
        "value_assets": VALUE_ASSETS,
        "ctas": CTAS,
        "sensitivity_levels": ["low", "medium"],
    }

    with patch(
        "app.services.ore.ore_pipeline.get_ore_playbook",
        return_value=restricted_playbook,
    ):
        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
            esl_decision="allow",
            sensitivity_level="high",
        )

    assert rec is not None
    assert rec.recommendation_type == "Soft Value Share"
    assert rec.draft_variants is None or rec.draft_variants == []
    assert rec.safeguards_triggered is not None
    assert any("Playbook excludes" in (s or "") for s in rec.safeguards_triggered)


def test_ore_playbook_sensitivity_included_draft_generated(db: Session) -> None:
    """M4: When playbook has sensitivity_levels and entity level is in list, draft is generated."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="LowSensCo",
        website_url="https://lowsens.example.com",
        founder_name="Founder",
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
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.draft_generator import PATTERN_FRAMES, VALUE_ASSETS, CTAS

    allowed_playbook = {
        "pattern_frames": PATTERN_FRAMES,
        "value_assets": VALUE_ASSETS,
        "ctas": CTAS,
        "sensitivity_levels": ["low", "medium"],
    }

    with patch(
        "app.services.ore.ore_pipeline.get_ore_playbook",
        return_value=allowed_playbook,
    ), patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
            esl_decision="allow",
            sensitivity_level="low",
        )

    assert rec is not None
    assert rec.recommendation_type in ("Low-Pressure Intro", "Standard Outreach", "Direct Strategic Outreach")
    assert rec.draft_variants and len(rec.draft_variants) >= 1


def test_ore_playbook_no_sensitivity_levels_unchanged(db: Session) -> None:
    """M4: When playbook has no sensitivity_levels, behavior unchanged (draft when gate allows)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="NoFilterCo",
        website_url="https://nofilter.example.com",
        founder_name="Founder",
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
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
            # no esl_decision/sensitivity_level → no suppress, no playbook filter
        )

    assert rec is not None
    assert rec.recommendation_type in ("Low-Pressure Intro", "Standard Outreach", "Direct Strategic Outreach")
    assert rec.draft_variants and len(rec.draft_variants) >= 1


def test_ore_returns_none_when_company_not_found(db: Session) -> None:
    """generate_ore_recommendation returns None when company_id does not exist."""
    from app.services.ore.ore_pipeline import generate_ore_recommendation

    rec = generate_ore_recommendation(
        db,
        company_id=999999,
        as_of=date(2026, 2, 18),
        stability_modifier=0.5,
        cooldown_active=False,
        alignment_high=True,
    )
    assert rec is None


def test_ore_returns_none_when_snapshot_missing(db: Session) -> None:
    """generate_ore_recommendation returns None when ReadinessSnapshot missing for (company, as_of, pack)."""
    company = Company(
        name="NoSnapshotCo",
        website_url="https://nosnapshot.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    # No ReadinessSnapshot for this company/as_of/pack
    from app.services.ore.ore_pipeline import generate_ore_recommendation

    rec = generate_ore_recommendation(
        db,
        company_id=company.id,
        as_of=date(2026, 2, 18),
        stability_modifier=0.5,
        cooldown_active=False,
        alignment_high=True,
    )
    assert rec is None


def test_ore_returns_none_when_no_default_pack(db: Session) -> None:
    """generate_ore_recommendation returns None when get_default_pack_id returns None."""
    from app.services.ore.ore_pipeline import generate_ore_recommendation

    company = Company(
        name="NoPackCo",
        website_url="https://nopack.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    with patch(
        "app.services.ore.ore_pipeline.get_default_pack_id",
        return_value=None,
    ):
        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=date(2026, 2, 18),
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )
    assert rec is None


def test_ore_upsert_two_calls_same_key_yield_one_row_updated(db: Session) -> None:
    """Issue #115 M2: Two ORE calls for same (company_id, as_of, pack_id) upsert to one row.

    First call inserts; second call updates same row (same id). Recommendation type and
    outreach_score reflect the second call. created_at is preserved on update.
    """
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="UpsertCo",
        website_url="https://upsert.example.com",
        founder_name="Upsert Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 19)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=85,
        complexity=80,
        pressure=75,
        leadership_gap=70,
        composite=82,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec1 = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )
    assert rec1 is not None
    assert rec1.recommendation_type == "Soft Value Share"
    assert rec1.outreach_score == 41

    count_before = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company.id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == pack_id,
        )
        .count()
    )
    assert count_before == 1, "First call must insert exactly one row"

    # Second call: higher SM → not capped; same key → must update, not insert
    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec2 = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )
    assert rec2 is not None
    assert rec1.id == rec2.id, "Second call must update same row (same id)"
    assert rec2.created_at == rec1.created_at, "Update must preserve created_at"
    assert rec2.recommendation_type != "Soft Value Share", "Second call SM=0.9 → not capped"
    assert rec2.outreach_score == 74, "round(82 * 0.9) = 74"

    count_after = (
        db.query(OutreachRecommendation)
        .filter(
            OutreachRecommendation.company_id == company.id,
            OutreachRecommendation.as_of == as_of,
            OutreachRecommendation.pack_id == pack_id,
        )
        .count()
    )
    assert count_after == 1, "Second call must not insert a duplicate row"
