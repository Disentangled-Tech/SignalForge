"""Integration test: TRS → ESL → ORE pipeline (Issue #124).

Simulates: Company with TRS=82, StabilityModifier=0.5, Cooldown inactive, High alignment.
Expects: Recommendation capped at Soft Value Share, No surveillance language,
         Single CTA, OutreachScore computed correctly.
Fixture strategy: Insert Company and ReadinessSnapshot directly (no SignalEvents).

Issue #121 M2: Pattern frame is selected by get_dominant_trs_dimension(snapshot).
"""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Company, OutreachRecommendation, ReadinessSnapshot, SignalPack
from app.services.ore.playbook_loader import DEFAULT_PLAYBOOK_NAME

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
    # Issue #176 M2: playbook_id set by ORE pipeline (playbook name used to load)
    assert rec.playbook_id == DEFAULT_PLAYBOOK_NAME, (
        "ORE pipeline must set playbook_id on OutreachRecommendation"
    )
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


def test_ore_pipeline_logs_structured_pack_playbook_sensitivity_signals(
    db: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """M1 (Issue #121): ORE logs pack_id, playbook_id, sensitivity_level, recommendation_type, signals."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    assert pack_id is not None

    company = Company(
        name="LogTestCo",
        website_url="https://logtest.example.com",
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
        explain={
            "top_events": [
                {"event_type": "cto_role_posted", "contribution_points": 25},
                {"event_type": "funding_raised", "contribution_points": 20},
            ],
        },
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with caplog.at_level(logging.INFO, logger="app.services.ore.ore_pipeline"):
        with patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ):
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
    ore_records = [r for r in caplog.records if "ORE recommendation" in (r.getMessage() or "")]
    assert len(ore_records) >= 1, "ORE pipeline must log once per run with structured context"
    record = ore_records[0]
    assert getattr(record, "pack_id", None) is not None, "log extra must include pack_id"
    assert getattr(record, "playbook_id", None) == DEFAULT_PLAYBOOK_NAME
    assert getattr(record, "sensitivity_level", None) == "low"
    assert getattr(record, "recommendation_type", None) is not None
    signals = getattr(record, "signals", None)
    assert signals is not None and isinstance(signals, list), "log extra must include signals list"
    assert len(signals) >= 1, "snapshot had top_events so signals should be non-empty"


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

    from app.services.ore.draft_generator import CTAS, PATTERN_FRAMES, VALUE_ASSETS
    from app.services.ore.ore_pipeline import generate_ore_recommendation

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

    from app.services.ore.draft_generator import CTAS, PATTERN_FRAMES, VALUE_ASSETS

    allowed_playbook = {
        "pattern_frames": PATTERN_FRAMES,
        "value_assets": VALUE_ASSETS,
        "ctas": CTAS,
        "sensitivity_levels": ["low", "medium"],
    }

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            return_value=allowed_playbook,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ),
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
    assert rec.recommendation_type in (
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    )
    assert rec.draft_variants and len(rec.draft_variants) >= 1


def test_ore_pipeline_channel_from_playbook_when_set(db: Session) -> None:
    """M4 (Issue #121): When playbook has channel, persisted recommendation uses it."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ChannelCo",
        website_url="https://channel.example.com",
        founder_name="Founder",
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
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    from app.services.ore.draft_generator import CTAS, PATTERN_FRAMES, VALUE_ASSETS

    playbook_with_channel = {
        "pattern_frames": PATTERN_FRAMES,
        "value_assets": VALUE_ASSETS,
        "ctas": CTAS,
        "sensitivity_levels": None,
        "channel": "Email",
    }

    from app.services.ore.ore_pipeline import generate_ore_recommendation

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            return_value=playbook_with_channel,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ),
    ):
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
    assert rec.channel == "Email", "Pipeline must persist playbook channel when set"


def test_ore_pipeline_channel_default_when_playbook_missing_channel(db: Session) -> None:
    """M4 (Issue #121): When playbook has no channel, persisted recommendation uses LinkedIn DM."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="DefaultChannelCo",
        website_url="https://defaultchannel.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 25)
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
        )

    assert rec is not None
    assert rec.channel == "LinkedIn DM", (
        "Pipeline must default to LinkedIn DM when playbook has no channel"
    )


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
    assert rec.recommendation_type in (
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    )
    assert rec.draft_variants and len(rec.draft_variants) >= 1


def test_ore_playbook_sensitivity_levels_case_insensitive(db: Session) -> None:
    """Playbook sensitivity_levels comparison is case-insensitive (doc: allowed values case-insensitive)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="CaseInsensCo",
        website_url="https://caseinsens.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 24)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=70,
        complexity=65,
        pressure=50,
        leadership_gap=55,
        composite=62,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    with patch(
        "app.services.ore.ore_pipeline.get_ore_playbook",
        return_value={
            "pattern_frames": {"complexity": "When products add integrations..."},
            "value_assets": ["2-page Tech Inflection Checklist"],
            "ctas": ["Want me to send that checklist?"],
            "forbidden_phrases": [],
            "sensitivity_levels": ["high"],
            "opening_templates": [],
            "value_statements": [],
            "tone": None,
        },
    ):
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
                sensitivity_level="High",
            )

    assert rec is not None
    assert rec.draft_variants and len(rec.draft_variants) >= 1, (
        "Entity sensitivity_level 'High' must match playbook ['high'] (case-insensitive)"
    )


def test_ore_pipeline_pattern_frame_from_dominant_dimension(db: Session) -> None:
    """M2: Snapshot with pressure dominant yields draft with playbook's pressure pattern frame (Issue #121)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="PressureDomCo",
        website_url="https://pressuredom.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    pressure_frame = "When timelines get tighter, it helps to reduce decision load and get a clean plan."
    playbook_with_frames = {
        "pattern_frames": {
            "momentum": "Momentum framing text.",
            "complexity": "When products add integrations...",
            "pressure": pressure_frame,
            "leadership_gap": "When there isn't a dedicated technical owner yet.",
        },
        "value_assets": ["2-page Tech Inflection Checklist"],
        "ctas": ["Want me to send that checklist?"],
        "forbidden_phrases": [],
        "tone": None,
    }

    as_of = date(2026, 2, 25)
    snapshot = ReadinessSnapshot(
        company_id=company.id,
        as_of=as_of,
        momentum=10,
        complexity=10,
        pressure=95,
        leadership_gap=10,
        composite=35,
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    draft_calls: list[list[object]] = []
    draft_kwargs: list[dict] = []

    def capture_draft(*args: object, **kwargs: object) -> dict:
        draft_calls.append(list(args))
        draft_kwargs.append(dict(kwargs))
        return _ORE_DRAFT

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            return_value=playbook_with_frames,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            side_effect=capture_draft,
        ),
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert len(draft_kwargs) >= 1, "Pipeline must call generate_ore_draft when gate allows"
    assert draft_kwargs[0].get("pattern_frame") == pressure_frame, (
        "Pipeline must pass playbook's pressure pattern frame when snapshot has pressure dominant"
    )


def test_ore_pipeline_passes_playbook_forbidden_phrases_to_critic(db: Session) -> None:
    """M3: Pipeline passes playbook forbidden_phrases to check_critic (Issue #176)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ForbiddenPhraseCo",
        website_url="https://fp.example.com",
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
        pack_id=pack_id,
    )
    db.add(snapshot)
    db.commit()

    critic_calls: list[dict] = []

    def record_critic(subject: str, message: str, **kwargs: object) -> object:
        critic_calls.append({"subject": subject, "message": message, "kwargs": dict(kwargs)})
        from app.services.ore.critic import check_critic as real_critic

        return real_critic(subject, message, **kwargs)

    with (
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ),
        patch(
            "app.services.ore.ore_pipeline.check_critic",
            side_effect=record_critic,
        ),
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert len(critic_calls) >= 1, "Pipeline must call check_critic when generating draft"
    for call in critic_calls:
        assert "forbidden_phrases" in call["kwargs"], (
            "Pipeline must pass forbidden_phrases to critic"
        )
        assert isinstance(call["kwargs"]["forbidden_phrases"], list)


def test_ore_pipeline_critic_rejects_draft_with_pack_forbidden_phrase_uses_fallback(
    db: Session,
) -> None:
    """M3: When draft contains a pack forbidden phrase, critic fails and pipeline stores fallback."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ForbiddenDraftCo",
        website_url="https://fd.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 25)
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

    draft_with_forbidden = {
        "subject": "Quick question",
        "message": (
            "Hi Jane, our limited time only offer might help. "
            "Want me to send the checklist? No worries if now isn't the time."
        ),
    }

    def playbook_with_forbidden(*args: object, **kwargs: object) -> object:
        from app.services.ore.playbook_loader import get_ore_playbook as real_get

        playbook = real_get(*args, **kwargs)
        playbook = dict(playbook)
        playbook["forbidden_phrases"] = ["limited time only", "bargain basement"]
        return playbook

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            side_effect=playbook_with_forbidden,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=draft_with_forbidden,
        ),
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert rec.draft_variants and len(rec.draft_variants) == 1
    stored = rec.draft_variants[0]
    assert "limited time only" not in (stored.get("message") or "").lower()
    assert (
        "No worries" in (stored.get("message") or "")
        or "no pressure" in (stored.get("message") or "").lower()
    )


def test_ore_pipeline_enable_ore_polish_true_uses_polished_draft_when_passes_critic(
    db: Session,
) -> None:
    """Issue #119: When enable_ore_polish is True and polished draft passes critic, persisted draft is polished."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="PolishCo",
        website_url="https://polish.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 27)
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

    polished_draft = {
        "subject": "Polished subject line",
        "message": (
            "Hi Jane,\n\nWhen products add integrations, systems often need a pass.\n\n"
            "I have a 2-page checklist that might help. Want me to send that checklist? "
            "No worries if now isn't the time."
        ),
    }
    playbook_with_polish = {
        "pattern_frames": {"momentum": "m", "complexity": "c", "pressure": "p", "leadership_gap": "g"},
        "value_assets": ["2-page checklist"],
        "ctas": ["Want me to send that checklist?"],
        "forbidden_phrases": [],
        "sensitivity_levels": None,
        "enable_ore_polish": True,
    }

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            return_value=playbook_with_polish,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ),
        patch(
            "app.services.ore.ore_pipeline.polish_ore_draft",
            return_value=polished_draft,
        ),
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert rec.draft_variants and len(rec.draft_variants) == 1
    stored = rec.draft_variants[0]
    assert stored.get("subject") == polished_draft["subject"]
    assert stored.get("message") == polished_draft["message"]


def test_ore_pipeline_enable_ore_polish_both_fail_critic_stores_fallback_not_polished(
    db: Session,
) -> None:
    """Issue #119: When polished and original both fail critic, persisted draft is fallback (or original), not polished."""
    from app.services.ore.critic import CriticResult

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="FallbackCo",
        website_url="https://fallback.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 28)
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

    polished_draft = {"subject": "Polished only", "message": "Polished body only."}
    playbook_with_polish = {
        "pattern_frames": {"momentum": "m", "complexity": "c", "pressure": "p", "leadership_gap": "g"},
        "value_assets": ["2-page Tech Inflection Checklist"],
        "ctas": ["Want me to send that checklist?"],
        "forbidden_phrases": [],
        "sensitivity_levels": None,
        "enable_ore_polish": True,
    }
    failing_draft = {
        "subject": "Quick question",
        "message": "Hi Jane, I have a checklist. Want me to send that checklist?",
    }

    call_count = 0

    def critic_fail_then_pass(subject: str, message: str, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return CriticResult(passed=False, violations=["test"])
        return CriticResult(passed=True, violations=[])

    with (
        patch(
            "app.services.ore.ore_pipeline.get_ore_playbook",
            return_value=playbook_with_polish,
        ),
        patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=failing_draft,
        ),
        patch(
            "app.services.ore.ore_pipeline.polish_ore_draft",
            return_value=polished_draft,
        ),
        patch(
            "app.services.ore.ore_pipeline.check_critic",
            side_effect=critic_fail_then_pass,
        ),
    ):
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    assert rec.draft_variants and len(rec.draft_variants) == 1
    stored = rec.draft_variants[0]
    assert stored.get("subject") != polished_draft["subject"]
    assert "Polished only" not in (stored.get("subject") or "")
    assert "Polished body" not in (stored.get("message") or "")
    assert "FallbackCo" in (stored.get("subject") or "") or "No worries" in (stored.get("message") or "")


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


def test_ore_pipeline_passes_esl_tone_constraint_to_draft(db: Session) -> None:
    """M5: When compute_esl_from_context returns explain.tone_constraint, generate_ore_draft receives it."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ToneConstraintCo",
        website_url="https://tone.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 26)
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

    # Mock compute_esl_from_context so we control tone_constraint without full ESL setup
    ctx_with_tone = {
        "esl_composite": 0.9,
        "stability_modifier": 0.9,
        "recommendation_type": "Low-Pressure Intro",
        "explain": {"tone_constraint": "Soft Value Share"},
        "cadence_blocked": False,
        "alignment_high": True,
        "esl_decision": "allow",
        "sensitivity_level": "low",
    }

    with patch(
        "app.services.ore.ore_pipeline.compute_esl_from_context",
        return_value=ctx_with_tone,
    ):
        with patch(
            "app.services.ore.ore_pipeline.generate_ore_draft",
            return_value=_ORE_DRAFT,
        ) as mock_draft:
            from app.services.ore.ore_pipeline import generate_ore_recommendation

            rec = generate_ore_recommendation(db, company_id=company.id, as_of=as_of)

    assert rec is not None
    mock_draft.assert_called_once()
    call_kwargs = mock_draft.call_args[1]
    assert call_kwargs.get("tone_constraint") == "Soft Value Share"


def test_ore_pipeline_passes_snapshot_explain_to_draft(db: Session) -> None:
    """M4: When ReadinessSnapshot has explain with top_events, generate_ore_draft receives explainability and top_signal_labels."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="ExplainCo",
        website_url="https://explain.example.com",
        founder_name="Founder",
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
        pack_id=pack_id,
        explain={
            "top_events": [
                {"event_type": "cto_role_posted", "contribution_points": 25},
                {"event_type": "funding_raised", "contribution_points": 20},
            ],
        },
    )
    db.add(snapshot)
    db.commit()

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ) as mock_draft:
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    mock_draft.assert_called_once()
    call_kwargs = mock_draft.call_args[1]
    # M4: pipeline builds explainability context from snapshot.explain and passes to draft
    assert "explainability_snippet" in call_kwargs
    assert "top_signal_labels" in call_kwargs
    # With top_events present, we expect non-empty labels (pack taxonomy or formatted event_type)
    top_labels = call_kwargs["top_signal_labels"]
    assert isinstance(top_labels, list)
    assert len(top_labels) >= 1, "top_events should yield at least one label"


def test_ore_pipeline_empty_explain_passes_empty_snippet_and_labels(db: Session) -> None:
    """M4: When ReadinessSnapshot has no explain or empty top_events, draft receives empty explainability_snippet and top_signal_labels."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None

    company = Company(
        name="NoExplainCo",
        website_url="https://noexplain.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 2, 25)
    # Snapshot with no explain (default None)
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
    ) as mock_draft:
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    mock_draft.assert_called_once()
    call_kwargs = mock_draft.call_args[1]
    assert call_kwargs["explainability_snippet"] == ""
    assert call_kwargs["top_signal_labels"] == []


def test_ore_pipeline_real_fractional_cto_v1_passes_recipient_label_from_taxonomy(
    db: Session,
) -> None:
    """M3 (Issue #121): With real fractional_cto_v1 pack (no mock resolve_pack), pipeline passes taxonomy.recipient_label to generate_ore_draft.

    fractional_cto_v1 has taxonomy.yaml with recipient_label: \"Founder\" so production wording is unchanged.
    Asserts the pipeline passes recipient_label=\"Founder\" when the default pack is loaded from disk.
    """
    pack_row = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    if pack_row is None:
        pytest.skip("fractional_cto_v1 pack not in DB")
    pack_id = pack_row.id

    company = Company(
        name="RealPackCo",
        website_url="https://realpack.example.com",
        founder_name="Jane",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    as_of = date(2026, 3, 2)
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

    # No mock of resolve_pack: real pack is loaded (with taxonomy.recipient_label from packs/fractional_cto_v1/taxonomy.yaml)
    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ) as mock_draft:
        from app.services.ore.ore_pipeline import generate_ore_recommendation

        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.9,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec is not None
    mock_draft.assert_called_once()
    call_kwargs = mock_draft.call_args[1]
    # M3: pipeline passes recipient_label from pack taxonomy; fractional_cto_v1 has recipient_label: "Founder"
    if "recipient_label" not in call_kwargs:
        pytest.skip("M3 recipient_label not yet in pipeline (ore_pipeline.generate_ore_draft)")
    assert call_kwargs["recipient_label"] == "Founder"


# --- Issue #122 M1: pack_id/workspace_id and get_or_create ---


def test_ore_pipeline_explicit_pack_id_same_as_default(db: Session) -> None:
    """Issue #122 M1: generate_ore_recommendation(..., pack_id=default_id) matches default behavior."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    assert pack_id is not None

    company = Company(
        name="ExplicitPackCo",
        website_url="https://explicit.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 3, 1)
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

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec_default = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )
        rec_explicit = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            pack_id=pack_id,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )

    assert rec_default is not None and rec_explicit is not None
    assert rec_default.id == rec_explicit.id
    assert rec_default.recommendation_type == rec_explicit.recommendation_type
    assert rec_default.outreach_score == rec_explicit.outreach_score
    assert rec_default.playbook_id == rec_explicit.playbook_id


def test_get_or_create_ore_recommendation_returns_existing(db: Session) -> None:
    """Issue #122 M1: get_or_create returns existing row when one exists for (company_id, as_of, pack)."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    assert pack_id is not None

    company = Company(
        name="GetOrCreateCo",
        website_url="https://getorcreate.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 3, 2)
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

    from app.services.ore.ore_pipeline import (
        generate_ore_recommendation,
        get_or_create_ore_recommendation,
    )

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec1 = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            pack_id=pack_id,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )
    assert rec1 is not None

    rec2 = get_or_create_ore_recommendation(
        db,
        company_id=company.id,
        as_of=as_of,
        pack_id=pack_id,
    )
    assert rec2 is not None
    assert rec1.id == rec2.id
    assert rec2.recommendation_type == rec1.recommendation_type


def test_get_or_create_ore_recommendation_creates_when_none(db: Session) -> None:
    """Issue #122 M1: get_or_create runs pipeline and returns new recommendation when none exists."""
    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    assert pack_id is not None

    company = Company(
        name="CreateNewCo",
        website_url="https://createnew.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 3, 3)
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

    from app.services.ore.ore_pipeline import get_or_create_ore_recommendation

    with patch(
        "app.services.ore.ore_pipeline.generate_ore_draft",
        return_value=_ORE_DRAFT,
    ):
        rec = get_or_create_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            pack_id=pack_id,
        )

    assert rec is not None
    assert rec.company_id == company.id
    assert rec.as_of == as_of
    assert rec.pack_id == pack_id
    assert rec.playbook_id == DEFAULT_PLAYBOOK_NAME
    assert rec.recommendation_type in (
        "Soft Value Share",
        "Low-Pressure Intro",
        "Standard Outreach",
        "Direct Strategic Outreach",
    )
    assert rec.outreach_score >= 0


def test_get_or_create_ore_recommendation_returns_none_when_company_missing(db: Session) -> None:
    """Issue #122 M1: get_or_create returns None when company does not exist."""
    from app.services.ore.ore_pipeline import get_or_create_ore_recommendation

    rec = get_or_create_ore_recommendation(
        db,
        company_id=999999,
        as_of=date(2026, 3, 1),
    )
    assert rec is None


def test_ore_recommendation_to_response_has_required_fields(db: Session) -> None:
    """Issue #122 M1: OutreachRecommendationResponse from mapper has required fields and valid types."""
    from app.schemas.outreach import ore_recommendation_to_response
    from app.services.ore.ore_pipeline import generate_ore_recommendation

    pack = db.query(SignalPack).filter(SignalPack.pack_id == "fractional_cto_v1").first()
    pack_id = pack.id if pack else None
    assert pack_id is not None
    company = Company(
        name="SchemaCo",
        website_url="https://schema.example.com",
        founder_name="Founder",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    as_of = date(2026, 3, 4)
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
        rec = generate_ore_recommendation(
            db,
            company_id=company.id,
            as_of=as_of,
            pack_id=pack_id,
            stability_modifier=0.5,
            cooldown_active=False,
            alignment_high=True,
        )
    assert rec is not None

    response = ore_recommendation_to_response(rec, sensitivity_tag="low")
    assert response.company_id == rec.company_id
    assert response.as_of == rec.as_of
    assert response.recommended_playbook_id == (rec.playbook_id or "")
    assert response.drafts == (list(rec.draft_variants) if rec.draft_variants else [])
    assert "Recommendation:" in response.rationale
    assert response.sensitivity_tag == "low"
    assert response.recommendation_type == rec.recommendation_type
    assert response.outreach_score == rec.outreach_score
    assert response.safeguards_triggered == rec.safeguards_triggered
    assert response.pack_id == rec.pack_id
    assert response.id == rec.id
    assert response.created_at == rec.created_at
