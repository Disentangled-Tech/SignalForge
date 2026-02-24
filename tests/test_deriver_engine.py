"""Tests for deriver engine (Phase 2, Issue #192)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Company, SignalEvent, SignalInstance
from app.pipeline.deriver_engine import _build_passthrough_map, run_deriver

_DERIVER_TEST_DOMAINS = (
    "deriver.example.com",
    "idem.example.com",
    "skip.example.com",
    "fail.example.com",
    "multievent.example.com",
)


@pytest.fixture(autouse=True)
def _cleanup_deriver_test_data(db: Session):
    """Remove deriver test data before and after each test for isolation.

    run_deriver commits internally, so test data persists across tests.
    Cleanup before (remove stale data) and after (leave clean for next file).
    """
    company_ids = [
        row[0]
        for row in db.query(Company.id).filter(Company.domain.in_(_DERIVER_TEST_DOMAINS)).all()
    ]
    if company_ids:
        db.query(SignalInstance).filter(
            SignalInstance.entity_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(SignalEvent).filter(
            SignalEvent.company_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(Company).filter(Company.domain.in_(_DERIVER_TEST_DOMAINS)).delete(
            synchronize_session="fetch"
        )
    # Orphan events (company deleted -> SET NULL): remove test-source events with no company
    db.query(SignalEvent).filter(
        SignalEvent.company_id.is_(None),
        SignalEvent.source == "test",
    ).delete(synchronize_session="fetch")
    db.commit()
    yield
    # Teardown: remove our test data (run_deriver commits, so rollback won't undo)
    company_ids = [
        row[0]
        for row in db.query(Company.id).filter(Company.domain.in_(_DERIVER_TEST_DOMAINS)).all()
    ]
    if company_ids:
        db.query(SignalInstance).filter(
            SignalInstance.entity_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(SignalEvent).filter(
            SignalEvent.company_id.in_(company_ids)
        ).delete(synchronize_session="fetch")
        db.query(Company).filter(Company.domain.in_(_DERIVER_TEST_DOMAINS)).delete(
            synchronize_session="fetch"
        )
    # Orphan events (company deleted -> SET NULL): remove test-source events with no company
    db.query(SignalEvent).filter(
        SignalEvent.company_id.is_(None),
        SignalEvent.source == "test",
    ).delete(synchronize_session="fetch")
    db.commit()


def _make_event(
    db: Session,
    company_id: int,
    event_type: str,
    pack_id,
    event_time: datetime | None = None,
) -> SignalEvent:
    ev = SignalEvent(
        source="test",
        event_type=event_type,
        event_time=event_time or datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        company_id=company_id,
        pack_id=pack_id,
    )
    db.add(ev)
    db.flush()
    return ev


class TestBuildPassthroughMap:
    """Tests for _build_passthrough_map."""

    def test_empty_pack_returns_empty(self) -> None:
        """None or empty pack returns empty map."""
        assert _build_passthrough_map(None) == {}
        from types import SimpleNamespace

        empty = SimpleNamespace(derivers=None)
        assert _build_passthrough_map(empty) == {}

    def test_passthrough_from_pack(self) -> None:
        """Pack with passthrough derivers produces event_type -> signal_id map."""
        from types import SimpleNamespace

        pack = SimpleNamespace(
            derivers={
                "passthrough": [
                    {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    {"event_type": "cto_role_posted", "signal_id": "cto_role_posted"},
                ]
            }
        )
        m = _build_passthrough_map(pack)
        assert m["funding_raised"] == "funding_raised"
        assert m["cto_role_posted"] == "cto_role_posted"


class TestRunDeriver:
    """Tests for run_deriver."""

    def test_no_pack_skipped(self, db: Session) -> None:
        """When no pack available, returns skipped."""
        with patch("app.pipeline.deriver_engine.get_default_pack_id", return_value=None):
            result = run_deriver(db, pack_id=None)
        assert result["status"] == "skipped"
        assert result["instances_upserted"] == 0
        assert "No pack" in (result.get("error") or "")

    def test_deriver_passthrough_populates_signal_instances(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Deriver applies passthrough, upserts signal_instances from SignalEvents."""
        company = Company(
            name="DeriverTestCo",
            domain="deriver.example.com",
            website_url="https://deriver.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        _make_event(db, company.id, "job_posted_engineering", fractional_cto_pack_id)
        _make_event(db, company.id, "cto_role_posted", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
        )
        assert result["status"] == "completed"
        assert result["instances_upserted"] == 3
        assert result["events_processed"] == 3

        instances = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .all()
        )
        assert len(instances) == 3
        signal_ids = {i.signal_id for i in instances}
        assert signal_ids == {"funding_raised", "job_posted_engineering", "cto_role_posted"}

    def test_deriver_aggregates_multiple_events_same_signal(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Multiple events for same (entity, signal) aggregate first_seen/last_seen."""
        company = Company(
            name="MultiEventCo",
            domain="multievent.example.com",
            website_url="https://multievent.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        t1 = datetime(2026, 2, 10, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC)
        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id, t1)
        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id, t2)
        db.commit()

        result = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
        )
        assert result["status"] == "completed"
        assert result["instances_upserted"] == 1
        inst = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.signal_id == "funding_raised",
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .first()
        )
        assert inst is not None
        assert inst.first_seen == t1
        assert inst.last_seen == t2

    def test_deriver_idempotent_rerun_same_count(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Run derive twice; second run produces same signal_instances (idempotent)."""
        company = Company(
            name="IdemCo",
            domain="idem.example.com",
            website_url="https://idem.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        result1 = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
        )
        assert result1["status"] == "completed"
        assert result1["instances_upserted"] == 1

        count_after_first = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .count()
        )
        assert count_after_first == 1

        result2 = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
        )
        assert result2["status"] == "completed"
        assert result2["instances_upserted"] == 1

        count_after_second = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .count()
        )
        assert count_after_second == 1, "Idempotent: rerun must not duplicate"

    def test_deriver_skips_events_not_in_passthrough(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Events with event_type not in pack passthrough are skipped."""
        company = Company(
            name="SkipCo",
            domain="skip.example.com",
            website_url="https://skip.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        _make_event(db, company.id, "unknown_event_type", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(
            db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
        )
        assert result["status"] == "completed"
        assert result["instances_upserted"] == 1
        assert result["events_skipped"] == 1

    def test_deriver_exception_marks_job_failed(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """When deriver raises, job is marked failed and result returned."""
        company = Company(
            name="FailCo",
            domain="fail.example.com",
            website_url="https://fail.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        with patch(
            "app.pipeline.deriver_engine._run_deriver_core",
            side_effect=RuntimeError("simulated failure"),
        ):
            result = run_deriver(
                db, pack_id=fractional_cto_pack_id, company_ids=[company.id]
            )
        assert result["status"] == "failed"
        assert result["instances_upserted"] == 0
        assert "simulated failure" in (result.get("error") or "")

    def test_deriver_skips_events_without_company(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """SignalEvents with company_id=None are skipped (not processed)."""
        ev = SignalEvent(
            source="test",
            event_type="funding_raised",
            event_time=datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
            company_id=None,
            pack_id=fractional_cto_pack_id,
        )
        db.add(ev)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id)
        # Events with company_id=None are skipped; we must skip at least our 1
        assert result["status"] == "completed"
        assert result["events_skipped"] >= 1
