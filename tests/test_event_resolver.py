"""Tests for get_event_like_list_from_core_instances (Issue #287, M3)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models import Company, SignalEvent, SignalInstance
from app.services.pack_resolver import get_core_pack_id
from app.services.readiness.event_resolver import get_event_like_list_from_core_instances


def _days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


class TestGetEventLikeListFromCoreInstances:
    """get_event_like_list_from_core_instances returns event-like list from core instances."""

    @pytest.fixture
    def core_pack_id(self, db: Session) -> uuid.UUID | None:
        core_id = get_core_pack_id(db)
        if core_id is None:
            pytest.skip("core pack not installed (run migration 20260226_core_pack_sentinel)")
        return core_id

    def test_returns_empty_when_no_core_instances(
        self, db: Session, core_pack_id: uuid.UUID
    ) -> None:
        """No instances for company returns empty list."""
        company = Company(name="EmptyCo", website_url="https://empty.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)
        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert result == []

    def test_fallback_synthetic_event_when_no_evidence(
        self, db: Session, core_pack_id: uuid.UUID
    ) -> None:
        """When evidence_event_ids is empty, one synthetic event per instance (signal_id, last_seen)."""
        company = Company(name="SyntheticCo", website_url="https://synthetic.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        inst = SignalInstance(
            entity_id=company.id,
            signal_id="funding_raised",
            pack_id=core_pack_id,
            last_seen=_days_ago(5),
            confidence=0.9,
            evidence_event_ids=None,
        )
        db.add(inst)
        db.commit()

        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert len(result) == 1
        assert getattr(result[0], "event_type", None) == "funding_raised"
        assert getattr(result[0], "event_time", None) is not None
        assert getattr(result[0], "confidence", None) == 0.9

    def test_resolves_evidence_events_when_present(
        self, db: Session, core_pack_id: uuid.UUID
    ) -> None:
        """When evidence_event_ids is set, resolves to SignalEvents."""
        company = Company(name="EvidenceCo", website_url="https://evidence.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        ev = SignalEvent(
            company_id=company.id,
            source="test",
            event_type="funding_raised",
            event_time=_days_ago(3),
            confidence=0.85,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        inst = SignalInstance(
            entity_id=company.id,
            signal_id="funding_raised",
            pack_id=core_pack_id,
            last_seen=ev.event_time,
            confidence=0.85,
            evidence_event_ids=[ev.id],
        )
        db.add(inst)
        db.commit()

        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert len(result) == 1
        assert result[0].event_type == "funding_raised"
        assert result[0].event_time == ev.event_time
        assert result[0].confidence == 0.85

    def test_excludes_events_before_365_day_window(
        self, db: Session, core_pack_id: uuid.UUID
    ) -> None:
        """Events older than as_of - 365 days are excluded."""
        company = Company(name="OldCo", website_url="https://old.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        inst = SignalInstance(
            entity_id=company.id,
            signal_id="funding_raised",
            pack_id=core_pack_id,
            last_seen=_days_ago(400),
            confidence=0.8,
            evidence_event_ids=None,
        )
        db.add(inst)
        db.commit()

        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert len(result) == 0

    def test_deduplicates_evidence_events_shared_across_instances(
        self, db: Session, core_pack_id: uuid.UUID
    ) -> None:
        """Same SignalEvent in two instances' evidence is only included once."""
        company = Company(name="DedupCo", website_url="https://dedup.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        ev = SignalEvent(
            company_id=company.id,
            source="test",
            event_type="funding_raised",
            event_time=_days_ago(5),
            confidence=0.9,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        for signal_id in ("funding_raised", "launch_major"):
            inst = SignalInstance(
                entity_id=company.id,
                signal_id=signal_id,
                pack_id=core_pack_id,
                last_seen=ev.event_time,
                confidence=0.9,
                evidence_event_ids=[ev.id],
            )
            db.add(inst)
        db.commit()

        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert len(result) == 1
        assert result[0].event_type == "funding_raised"

    def test_ignores_instances_from_other_pack(
        self, db: Session, core_pack_id: uuid.UUID, fractional_cto_pack_id: uuid.UUID
    ) -> None:
        """Only instances with pack_id == core_pack_id are considered."""
        company = Company(name="OtherPackCo", website_url="https://other.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        inst_core = SignalInstance(
            entity_id=company.id,
            signal_id="funding_raised",
            pack_id=core_pack_id,
            last_seen=_days_ago(5),
            confidence=0.9,
            evidence_event_ids=None,
        )
        inst_other = SignalInstance(
            entity_id=company.id,
            signal_id="launch_major",
            pack_id=fractional_cto_pack_id,
            last_seen=_days_ago(5),
            confidence=0.8,
            evidence_event_ids=None,
        )
        db.add_all([inst_core, inst_other])
        db.commit()

        result = get_event_like_list_from_core_instances(db, company.id, date.today(), core_pack_id)
        assert len(result) == 1
        assert getattr(result[0], "event_type", None) == "funding_raised"
