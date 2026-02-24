"""Tests for lead_feed projection (Phase 1, Issue #225, ADR-004)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.models import Company, EngagementSnapshot, LeadFeed, ReadinessSnapshot, Workspace
from app.services.lead_feed import build_lead_feed_from_snapshots, upsert_lead_feed_row

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def lead_feed_company(db: Session, fractional_cto_pack_id: UUID) -> Company:
    """Company with snapshots for lead_feed projection tests."""
    c = Company(name="LeadFeed Co", website_url="https://leadfeed.example.com")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture
def lead_feed_snapshots(
    db: Session,
    lead_feed_company: Company,
    fractional_cto_pack_id: UUID,
) -> tuple[ReadinessSnapshot, EngagementSnapshot]:
    """ReadinessSnapshot + EngagementSnapshot for lead_feed_company."""
    as_of = date(2099, 2, 1)
    rs = ReadinessSnapshot(
        company_id=lead_feed_company.id,
        as_of=as_of,
        momentum=70,
        complexity=60,
        pressure=55,
        leadership_gap=40,
        composite=75,
        explain={
            "top_events": [
                {"event_type": "cto_role_posted", "contribution_points": 10},
                {"event_type": "funding_round", "contribution_points": 8},
            ],
        },
        pack_id=fractional_cto_pack_id,
    )
    es = EngagementSnapshot(
        company_id=lead_feed_company.id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Standard Outreach",
        cadence_blocked=False,
        pack_id=fractional_cto_pack_id,
        esl_decision="allow",
        sensitivity_level=None,
    )
    db.add(rs)
    db.add(es)
    db.commit()
    db.refresh(rs)
    db.refresh(es)
    return rs, es


class TestUpsertLeadFeedRow:
    """Tests for upsert_lead_feed_row."""

    def test_upsert_creates_new_row(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """upsert_lead_feed_row creates new row when none exists."""
        row = upsert_lead_feed_row(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            lead_feed_company.id,
            composite_score=80,
            top_signal_ids=["cto_role_posted", "funding_round"],
            esl_decision="allow",
            as_of=date(2099, 2, 1),
        )
        db.commit()

        assert row.entity_id == lead_feed_company.id
        assert row.composite_score == 80
        assert row.top_signal_ids == ["cto_role_posted", "funding_round"]
        assert row.esl_decision == "allow"

        found = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .first()
        )
        assert found is not None
        assert found.composite_score == 80

    def test_upsert_replaces_existing_row(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """upsert_lead_feed_row replaces existing row (idempotent)."""
        upsert_lead_feed_row(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            lead_feed_company.id,
            composite_score=50,
            as_of=date(2099, 2, 1),
        )
        db.commit()

        row = upsert_lead_feed_row(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            lead_feed_company.id,
            composite_score=90,
            as_of=date(2099, 2, 1),
        )
        db.commit()

        assert row.composite_score == 90
        count = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .count()
        )
        assert count == 1


class TestBuildLeadFeedFromSnapshots:
    """Tests for build_lead_feed_from_snapshots."""

    def test_build_creates_rows_from_snapshots(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """build_lead_feed_from_snapshots creates lead_feed rows from RS+ES."""
        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        count = build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        assert count == 1
        row = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .first()
        )
        assert row is not None
        assert row.composite_score == 75
        assert row.top_signal_ids == ["cto_role_posted", "funding_round"]
        assert row.esl_decision == "allow"
        assert row.as_of == as_of

    def test_build_excludes_suppressed_entities(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """build_lead_feed_from_snapshots excludes entities with esl_decision=suppress."""
        as_of = date(2099, 2, 2)
        rs = ReadinessSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=75,
            pack_id=fractional_cto_pack_id,
        )
        es = EngagementSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            esl_score=0.5,
            engagement_type="Observe Only",
            cadence_blocked=True,
            pack_id=fractional_cto_pack_id,
            esl_decision="suppress",
        )
        db.add(rs)
        db.add(es)
        db.commit()

        count = build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        assert count == 0
        row = db.query(LeadFeed).filter(LeadFeed.entity_id == lead_feed_company.id).first()
        assert row is None

    def test_build_excludes_entities_below_minimum_threshold(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """build_lead_feed_from_snapshots excludes entities with composite < minimum_threshold."""
        as_of = date(2099, 2, 3)
        rs = ReadinessSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=40,
            explain={"minimum_threshold": 60},
            pack_id=fractional_cto_pack_id,
        )
        es = EngagementSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            esl_score=0.8,
            engagement_type="Standard Outreach",
            pack_id=fractional_cto_pack_id,
            esl_decision="allow",
        )
        db.add(rs)
        db.add(es)
        db.commit()

        count = build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        assert count == 0
        row = (
            db.query(LeadFeed)
            .filter(LeadFeed.entity_id == lead_feed_company.id)
            .first()
        )
        assert row is None

    def test_build_returns_zero_when_pack_id_none(self, db: Session) -> None:
        """build_lead_feed_from_snapshots returns 0 when pack_id is None."""
        count = build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=None,
            as_of=date.today(),
        )
        assert count == 0

    def test_build_isolates_by_workspace_and_pack(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
        bookkeeping_pack_id: UUID,
    ) -> None:
        """run_update_lead_feed with workspace_id/pack_id only writes to that workspace+pack.

        No cross-tenant or cross-pack writes (multi-tenant safety).
        """
        from app.models.workspace import Workspace
        from app.services.lead_feed.run_update import run_update_lead_feed

        # Create second workspace for isolation test (JobRun FK requires it)
        other_workspace_id = UUID("11111111-1111-1111-1111-111111111111")
        other_ws = Workspace(id=other_workspace_id, name="Other WS", active_pack_id=fractional_cto_pack_id)
        db.add(other_ws)
        db.commit()

        as_of = date(2099, 2, 2)
        # Snapshots for fractional_cto pack only
        rs = ReadinessSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=75,
            pack_id=fractional_cto_pack_id,
        )
        es = EngagementSnapshot(
            company_id=lead_feed_company.id,
            as_of=as_of,
            esl_score=0.8,
            engagement_type="Standard Outreach",
            pack_id=fractional_cto_pack_id,
            esl_decision="allow",
        )
        db.add(rs)
        db.add(es)
        db.commit()

        run_update_lead_feed(
            db,
            workspace_id=str(other_workspace_id),
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )

        # Rows must be only for (other_workspace_id, fractional_cto_pack_id)
        rows_default_ws = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .all()
        )
        rows_other_ws = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == other_workspace_id,
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .all()
        )
        assert len(rows_default_ws) == 0, "No rows in default workspace (we used other_ws)"
        assert len(rows_other_ws) == 1, "Exactly one row in other workspace for our pack"

        # Run for different pack (bookkeeping) - no snapshots for it, so 0 rows
        run_update_lead_feed(
            db,
            workspace_id=str(other_workspace_id),
            pack_id=bookkeeping_pack_id,
            as_of=as_of,
        )
        rows_bookkeeping = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == other_workspace_id,
                LeadFeed.pack_id == bookkeeping_pack_id,
            )
            .all()
        )
        assert len(rows_bookkeeping) == 0, "Bookkeeping pack has no snapshots for this company"

    @pytest.mark.integration
    def test_score_incrementally_updates_lead_feed(
        self,
        db: Session,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """Phase 3: Score job incrementally updates lead_feed (no run_update needed)."""
        from app.models import Company, SignalEvent, Watchlist, Workspace
        from app.pipeline.stages import DEFAULT_WORKSPACE_ID
        from app.services.readiness.score_nightly import run_score_nightly

        company = Company(name="ScoreIncrCo", website_url="https://scoreincr.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        ws = db.query(Workspace).filter(Workspace.id == UUID(DEFAULT_WORKSPACE_ID)).first()
        if ws is None:
            ws = Workspace(
                id=UUID(DEFAULT_WORKSPACE_ID),
                name="Default",
                active_pack_id=fractional_cto_pack_id,
            )
            db.add(ws)
            db.commit()

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=datetime.now(UTC) - timedelta(days=5),
                confidence=0.9,
            )
        )
        db.add(Watchlist(company_id=company.id))
        db.commit()

        score_result = run_score_nightly(
            db, workspace_id=DEFAULT_WORKSPACE_ID, pack_id=fractional_cto_pack_id
        )
        assert score_result["status"] == "completed", score_result.get("error")
        assert score_result["companies_scored"] >= 1

        row = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == company.id,
            )
            .first()
        )
        assert row is not None, "Score job must incrementally update lead_feed (Phase 3)"
        assert row.composite_score >= 0
        assert row.as_of == date.today()

    @pytest.mark.integration
    def test_score_then_update_lead_feed_produces_expected_rows(
        self,
        db: Session,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """Integration: run score → run_update_lead_feed → assert lead_feed has rows."""
        from app.models import Company, SignalEvent, Watchlist, Workspace
        from app.pipeline.stages import DEFAULT_WORKSPACE_ID
        from app.services.lead_feed.run_update import run_update_lead_feed
        from app.services.readiness.score_nightly import run_score_nightly

        company = Company(name="IntegrationCo", website_url="https://integration.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        ws = db.query(Workspace).filter(Workspace.id == UUID(DEFAULT_WORKSPACE_ID)).first()
        if ws is None:
            ws = Workspace(
                id=UUID(DEFAULT_WORKSPACE_ID),
                name="Default",
                active_pack_id=fractional_cto_pack_id,
            )
            db.add(ws)
            db.commit()

        db.add(
            SignalEvent(
                company_id=company.id,
                source="test",
                event_type="funding_raised",
                event_time=datetime.now(UTC) - timedelta(days=5),
                confidence=0.9,
            )
        )
        db.add(Watchlist(company_id=company.id))
        db.commit()

        score_result = run_score_nightly(
            db, workspace_id=DEFAULT_WORKSPACE_ID, pack_id=fractional_cto_pack_id
        )
        assert score_result["status"] == "completed", score_result.get("error")
        assert score_result["companies_scored"] >= 1

        as_of = date.today()
        update_result = run_update_lead_feed(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        assert update_result["status"] == "completed", update_result.get("error")
        assert update_result["rows_upserted"] >= 1

        row = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == company.id,
            )
            .first()
        )
        assert row is not None
        assert row.composite_score >= 0
        assert row.as_of == as_of

    def test_run_update_lead_feed_with_as_of_past_uses_that_date(
        self,
        db: Session,
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """run_update_lead_feed with as_of in the past uses snapshots for that date."""
        from app.services.lead_feed.run_update import run_update_lead_feed

        past_date = date(2099, 1, 15)
        rs = ReadinessSnapshot(
            company_id=lead_feed_company.id,
            as_of=past_date,
            momentum=70,
            complexity=60,
            pressure=55,
            leadership_gap=40,
            composite=88,
            pack_id=fractional_cto_pack_id,
        )
        es = EngagementSnapshot(
            company_id=lead_feed_company.id,
            as_of=past_date,
            esl_score=0.8,
            engagement_type="Standard Outreach",
            cadence_blocked=False,
            pack_id=fractional_cto_pack_id,
            esl_decision="allow",
        )
        db.add(rs)
        db.add(es)
        db.commit()

        result = run_update_lead_feed(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=past_date,
        )
        assert result["status"] == "completed"
        assert result["rows_upserted"] == 1

        row = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.pack_id == fractional_cto_pack_id,
                LeadFeed.entity_id == lead_feed_company.id,
                LeadFeed.as_of == past_date,
            )
            .first()
        )
        assert row is not None
        assert row.composite_score == 88
        assert row.as_of == past_date

    def test_run_update_lead_feed_idempotent_rerun_no_duplicate_rows(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """run_update_lead_feed twice produces same rows (upsert idempotency), no duplicates."""
        from app.services.lead_feed.run_update import run_update_lead_feed

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        r1 = run_update_lead_feed(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        assert r1["status"] == "completed"
        assert r1["rows_upserted"] == 1

        count_before = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .count()
        )

        r2 = run_update_lead_feed(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        assert r2["status"] == "completed"
        assert r2["rows_upserted"] == 1

        count_after = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .count()
        )
        assert count_after == count_before, "Rerun must not create duplicate rows (upsert idempotency)"

    def test_outreach_event_refreshes_lead_feed_outreach_summary(
        self,
        db: Session,
        lead_feed_company: Company,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        fractional_cto_pack_id: UUID,
    ) -> None:
        """Phase 3: create_outreach_record refreshes outreach_status_summary in lead_feed."""
        from datetime import UTC, datetime

        from app.services.lead_feed import upsert_lead_feed_row
        from app.services.outreach_history import create_outreach_record

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        upsert_lead_feed_row(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            lead_feed_company.id,
            composite_score=75,
            as_of=as_of,
        )
        db.commit()

        row_before = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .first()
        )
        assert row_before is not None
        assert row_before.outreach_status_summary is None

        create_outreach_record(
            db,
            lead_feed_company.id,
            sent_at=datetime.now(UTC),
            outreach_type="email",
            message="Test outreach",
        )

        row_after = (
            db.query(LeadFeed)
            .filter(
                LeadFeed.workspace_id == UUID(DEFAULT_WORKSPACE_ID),
                LeadFeed.entity_id == lead_feed_company.id,
            )
            .first()
        )
        assert row_after is not None
        assert row_after.outreach_status_summary is not None
        assert "last_sent_at" in row_after.outreach_status_summary
        assert row_after.outreach_status_summary.get("outreach_type") == "email"

    def test_run_update_lead_feed_fails_when_no_pack_resolved(
        self,
        db: Session,
    ) -> None:
        """run_update_lead_feed returns status=failed when get_pack_for_workspace returns None."""
        from unittest.mock import patch

        from app.services.lead_feed.run_update import run_update_lead_feed

        with patch(
            "app.services.pack_resolver.get_pack_for_workspace",
            return_value=None,
        ):
            result = run_update_lead_feed(
                db,
                workspace_id=DEFAULT_WORKSPACE_ID,
                pack_id=None,
            )
        assert result["status"] == "failed"
        assert "No pack resolved" in (result.get("error") or "")


class TestPhase4DualPath:
    """Phase 4: Briefing and weekly review prefer lead_feed when populated (Issue #225)."""

    def test_get_emerging_companies_prefers_lead_feed_when_populated(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_emerging_companies() returns companies from lead_feed when feed has data."""
        from app.services.briefing import get_emerging_companies

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        result = get_emerging_companies(
            db,
            as_of,
            limit=5,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )

        assert len(result) == 1
        assert result[0][2].id == lead_feed_company.id
        assert result[0][0].composite == 75

    def test_get_emerging_companies_falls_back_to_join_when_feed_empty(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_emerging_companies() uses join query when lead_feed has no rows for as_of."""
        from app.services.briefing import get_emerging_companies

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of
        # Do NOT run build_lead_feed_from_snapshots - feed is empty

        result = get_emerging_companies(
            db,
            as_of,
            limit=5,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )

        assert len(result) == 1
        assert result[0][2].id == lead_feed_company.id

    def test_get_weekly_review_companies_prefers_lead_feed_when_populated(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_weekly_review_companies() returns companies from lead_feed when feed has data."""
        from app.services.outreach_review import get_weekly_review_companies

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        result = get_weekly_review_companies(
            db,
            as_of,
            limit=5,
            outreach_score_threshold=30,
            pack_id=fractional_cto_pack_id,
        )

        assert len(result) >= 1
        company_ids = [r["company_id"] for r in result]
        assert lead_feed_company.id in company_ids

    def test_feed_has_data_returns_true_when_populated(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """feed_has_data returns True when lead_feed has rows for workspace/pack/as_of."""
        from app.services.lead_feed.query_service import feed_has_data

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        assert not feed_has_data(db, DEFAULT_WORKSPACE_ID, fractional_cto_pack_id, as_of)

        build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        assert feed_has_data(db, DEFAULT_WORKSPACE_ID, fractional_cto_pack_id, as_of)

    def test_get_entity_ids_from_feed_returns_ordered_ids(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_entity_ids_from_feed returns entity_ids sorted by composite_score desc."""
        from app.services.lead_feed.query_service import get_entity_ids_from_feed

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        ids = get_entity_ids_from_feed(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            as_of,
            limit=10,
        )
        assert ids == [lead_feed_company.id]

    def test_get_leads_from_feed_returns_lead_cards(
        self,
        db: Session,
        lead_feed_snapshots: tuple[ReadinessSnapshot, EngagementSnapshot],
        lead_feed_company: Company,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_leads_from_feed returns lead cards with composite_score, outreach_score, etc."""
        from app.services.lead_feed import get_leads_from_feed

        rs, _ = lead_feed_snapshots
        as_of = rs.as_of

        build_lead_feed_from_snapshots(
            db,
            workspace_id=DEFAULT_WORKSPACE_ID,
            pack_id=fractional_cto_pack_id,
            as_of=as_of,
        )
        db.commit()

        leads = get_leads_from_feed(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            as_of,
            limit=10,
            outreach_score_threshold=30,
        )

        assert len(leads) == 1
        assert leads[0]["entity_id"] == lead_feed_company.id
        assert leads[0]["composite_score"] == 75
        assert "outreach_score" in leads[0]
        assert leads[0]["top_signal_ids"] == ["cto_role_posted", "funding_round"]
        assert leads[0]["esl_decision"] == "allow"


class TestLeadFeedIndices:
    """Phase 4: Verify lead_feed indices exist for performance (Issue #225)."""

    def test_lead_feed_indices_exist(self, db: Session) -> None:
        """lead_feed has required indices for composite_score and last_seen sorting."""
        from sqlalchemy import inspect

        inspector = inspect(db.get_bind())
        indexes = inspector.get_indexes("lead_feed")
        idx_names = [idx["name"] for idx in indexes]

        assert "ix_lead_feed_workspace_pack_composite" in idx_names
        assert "ix_lead_feed_workspace_pack_last_seen" in idx_names

    @pytest.mark.integration
    def test_get_leads_from_feed_performance_with_many_rows(
        self,
        db: Session,
        fractional_cto_pack_id: UUID,
    ) -> None:
        """get_leads_from_feed completes in reasonable time with many rows (Issue #225).

        Creates 100 lead_feed rows and asserts query returns them. Validates
        indices support efficient sorting. Full 10k load test run separately.
        """
        import time

        as_of = date(2099, 3, 1)
        ws_uuid = UUID(DEFAULT_WORKSPACE_ID)
        ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
        if ws is None:
            ws = Workspace(id=ws_uuid, name="Default", active_pack_id=fractional_cto_pack_id)
            db.add(ws)
            db.commit()

        companies = [
            Company(name=f"Perf Co {i}", website_url=f"https://perf{i}.example.com")
            for i in range(100)
        ]
        db.add_all(companies)
        db.commit()
        for c in companies:
            db.refresh(c)

        for i, c in enumerate(companies):
            upsert_lead_feed_row(
                db,
                DEFAULT_WORKSPACE_ID,
                fractional_cto_pack_id,
                c.id,
                composite_score=50 + (i % 50),
                as_of=as_of,
            )
        db.commit()

        from app.services.lead_feed import get_leads_from_feed

        start = time.perf_counter()
        leads = get_leads_from_feed(
            db,
            DEFAULT_WORKSPACE_ID,
            fractional_cto_pack_id,
            as_of,
            limit=50,
            outreach_score_threshold=0,
        )
        elapsed = time.perf_counter() - start

        assert len(leads) == 50
        assert elapsed < 2.0, f"Query took {elapsed:.2f}s; expected < 2s for 100 rows"
