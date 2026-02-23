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

from app.models import Company, ReadinessSnapshot, SignalPack

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

    # Stored in outreach_recommendations
    assert rec.company_id == company.id
    assert rec.as_of == as_of


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
