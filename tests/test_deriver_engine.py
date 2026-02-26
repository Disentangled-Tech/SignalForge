"""Tests for deriver engine (Phase 2, Issue #192)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models import Company, SignalEvent, SignalInstance
from app.pipeline.deriver_engine import (
    _evaluate_event_derivers,
    _load_core_derivers,
    run_deriver,
)

_DERIVER_TEST_DOMAINS = (
    "deriver.example.com",
    "idem.example.com",
    "skip.example.com",
    "fail.example.com",
    "multievent.example.com",
    "pattern.example.com",
    "log.example.com",
    "evidence.example.com",
    "merge.example.com",
    "merge_null.example.com",
    "singleev.example.com",
    "crosspack.example.com",
    "stablecore.example.com",
    "noderivers.example.com",
    "patternfallback.example.com",
    "v2noderivers.example.com",  # M5: pack without derivers.yaml (example_v2)
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
        db.query(SignalInstance).filter(SignalInstance.entity_id.in_(company_ids)).delete(
            synchronize_session="fetch"
        )
        db.query(SignalEvent).filter(SignalEvent.company_id.in_(company_ids)).delete(
            synchronize_session="fetch"
        )
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
        db.query(SignalInstance).filter(SignalInstance.entity_id.in_(company_ids)).delete(
            synchronize_session="fetch"
        )
        db.query(SignalEvent).filter(SignalEvent.company_id.in_(company_ids)).delete(
            synchronize_session="fetch"
        )
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
    *,
    title: str | None = None,
    summary: str | None = None,
    confidence: float | None = None,
) -> SignalEvent:
    ev = SignalEvent(
        source="test",
        event_type=event_type,
        event_time=event_time or datetime(2026, 2, 18, 12, 0, 0, tzinfo=UTC),
        company_id=company_id,
        pack_id=pack_id,
        title=title,
        summary=summary,
        confidence=confidence,
    )
    db.add(ev)
    db.flush()
    return ev


class TestLoadCoreDerivers:
    """Tests for _load_core_derivers (Issue #285: core derivers only)."""

    def test_load_core_derivers_returns_passthrough_and_patterns(self) -> None:
        """_load_core_derivers returns (passthrough_map, pattern_derivers)."""
        passthrough, pattern_derivers = _load_core_derivers()
        assert isinstance(passthrough, dict)
        assert isinstance(pattern_derivers, list)
        assert len(passthrough) > 0, "Core derivers must define passthrough mappings"
        assert passthrough.get("funding_raised") == "funding_raised"
        assert passthrough.get("cto_role_posted") == "cto_role_posted"


class TestEvaluateEventDerivers:
    """Tests for _evaluate_event_derivers (Phase 1, Issue #173)."""

    def test_passthrough_match(self) -> None:
        """Passthrough deriver matches event_type."""
        ev = SimpleNamespace(
            event_type="funding_raised",
            title=None,
            summary=None,
            confidence=0.8,
        )
        passthrough = {"funding_raised": "funding_raised"}
        pattern: list = []
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == [("funding_raised", "passthrough")]

    def test_pattern_match(self) -> None:
        """Pattern deriver matches title/summary."""
        ev = SimpleNamespace(
            event_type="other",
            title="Company achieves SOC2 compliance",
            summary=None,
            confidence=0.8,
        )
        passthrough = {}
        pattern = [
            {
                "signal_id": "compliance_mentioned",
                "compiled": re.compile(r"(?i)(soc2|compliance)"),
                "source_fields": ["title", "summary"],
                "min_confidence": None,
            },
        ]
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == [("compliance_mentioned", "pattern")]

    def test_pattern_no_match(self) -> None:
        """Pattern deriver does not match when text lacks pattern."""
        ev = SimpleNamespace(
            event_type="other",
            title="New product launch",
            summary="Exciting news",
            confidence=0.8,
        )
        passthrough = {}
        pattern = [
            {
                "signal_id": "compliance_mentioned",
                "compiled": re.compile(r"(?i)(soc2|gdpr)"),
                "source_fields": ["title", "summary"],
                "min_confidence": None,
            },
        ]
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == []

    def test_min_confidence_threshold_skips_low_confidence(self) -> None:
        """Pattern deriver with min_confidence skips events below threshold."""
        ev = SimpleNamespace(
            event_type="other",
            title="SOC2 compliance achieved",
            summary=None,
            confidence=0.5,
        )
        passthrough = {}
        pattern = [
            {
                "signal_id": "compliance_mentioned",
                "compiled": re.compile(r"(?i)soc2"),
                "source_fields": ["title", "summary"],
                "min_confidence": 0.6,
            },
        ]
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == []

    def test_min_confidence_threshold_allows_high_confidence(self) -> None:
        """Pattern deriver with min_confidence allows events at or above threshold."""
        ev = SimpleNamespace(
            event_type="other",
            title="SOC2 compliance achieved",
            summary=None,
            confidence=0.7,
        )
        passthrough = {}
        pattern = [
            {
                "signal_id": "compliance_mentioned",
                "compiled": re.compile(r"(?i)soc2"),
                "source_fields": ["title", "summary"],
                "min_confidence": 0.6,
            },
        ]
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == [("compliance_mentioned", "pattern")]

    def test_pattern_matches_on_url_when_source_fields_includes_url(self) -> None:
        """Pattern deriver matches when pattern is in url and source_fields includes url."""
        ev = SimpleNamespace(
            event_type="other",
            title="Generic news",
            summary=None,
            url="https://example.com/compliance-report",
            source="news",
            confidence=0.8,
        )
        passthrough = {}
        pattern = [
            {
                "signal_id": "compliance_mentioned",
                "compiled": re.compile(r"compliance"),
                "source_fields": ["url"],
                "min_confidence": None,
            },
        ]
        result = _evaluate_event_derivers(ev, passthrough, pattern)
        assert result == [("compliance_mentioned", "pattern")]


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

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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
        # Pack isolation: every instance must have pack_id equal to job pack_id (no cross-pack)
        for inst in instances:
            assert inst.pack_id == fractional_cto_pack_id, (
                f"SignalInstance pack_id must match job pack_id; got {inst.pack_id}"
            )

    def test_deriver_output_instances_all_have_job_pack_id(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Regression: every SignalInstance created by deriver has pack_id == run_deriver pack_id."""
        company = Company(
            name="PackScopeCo",
            domain="packscope.example.com",
            website_url="https://packscope.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        _make_event(db, company.id, "cto_role_posted", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"
        assert result["instances_upserted"] == 2

        instances = (
            db.query(SignalInstance)
            .filter(SignalInstance.entity_id == company.id)
            .all()
        )
        assert len(instances) == 2
        for inst in instances:
            assert inst.pack_id == fractional_cto_pack_id, (
                f"Deriver must only create instances for job pack_id; "
                f"entity_id={inst.entity_id} signal_id={inst.signal_id} pack_id={inst.pack_id}"
            )

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

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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

    def test_deriver_idempotent_rerun_same_count(self, db: Session, fractional_cto_pack_id) -> None:
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

        result1 = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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

        result2 = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"
        assert result["instances_upserted"] == 1
        assert result["events_skipped"] == 1

    def test_deriver_exception_marks_job_failed(self, db: Session, fractional_cto_pack_id) -> None:
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
            result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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

    def test_deriver_pattern_produces_signal_instance(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Core derivers passthrough produces SignalInstance (Issue #285 M6: core only).

        Derive uses core derivers only; no pack fallback. Passthrough yields one instance.
        """
        company = Company(
            name="PatternTestCo",
            domain="pattern.example.com",
            website_url="https://pattern.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(
            db,
            company.id,
            "funding_raised",
            fractional_cto_pack_id,
            title="Series A and SOC2 compliance achieved",
            summary="We completed our compliance audit",
        )
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

        assert result["status"] == "completed"
        assert result["instances_upserted"] == 1
        assert result["events_processed"] == 1

        instances = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .all()
        )
        signal_ids = {i.signal_id for i in instances}
        assert signal_ids == {"funding_raised"}

    def test_deriver_evidence_populated(self, db: Session, fractional_cto_pack_id) -> None:
        """Deriver populates evidence_event_ids with contributing SignalEvent IDs (Phase 2)."""
        company = Company(
            name="EvidenceCo",
            domain="evidence.example.com",
            website_url="https://evidence.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        ev1 = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        ev2 = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
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
        assert inst.evidence_event_ids is not None
        assert set(inst.evidence_event_ids) == {ev1.id, ev2.id}

    def test_deriver_evidence_single_event(self, db: Session, fractional_cto_pack_id) -> None:
        """Single event produces evidence_event_ids with one ID."""
        company = Company(
            name="SingleEvCo",
            domain="singleev.example.com",
            website_url="https://singleev.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        ev = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"

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
        assert inst.evidence_event_ids == [ev.id]

    def test_deriver_evidence_merge_on_rerun(self, db: Session, fractional_cto_pack_id) -> None:
        """Re-run merges evidence_event_ids instead of replacing (idempotency, traceability)."""
        company = Company(
            name="MergeCo",
            domain="merge.example.com",
            website_url="https://merge.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        ev1 = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        ev2 = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"
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
        assert set(inst.evidence_event_ids) == {ev1.id, ev2.id}

        # Add third event and re-run; evidence must merge, not replace
        ev3 = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()
        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"

        db.expire_all()  # Force reload from DB after run_deriver commit
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
        assert inst.evidence_event_ids is not None
        assert set(inst.evidence_event_ids) == {ev1.id, ev2.id, ev3.id}, (
            f"Expected merge of [ev1, ev2, ev3], got {inst.evidence_event_ids}"
        )

    def test_deriver_evidence_merge_handles_null_and_empty_existing(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Merge works when existing evidence_event_ids is NULL or [] (idempotency)."""
        company = Company(
            name="MergeNullCo",
            domain="merge_null.example.com",
            website_url="https://merge_null.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        ev = _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        # First run creates instance with evidence
        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"

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
        assert inst.evidence_event_ids == [ev.id]

        # Simulate empty array [] (e.g. manual reset)
        from sqlalchemy import text

        db.execute(
            text(
                "UPDATE signal_instances SET evidence_event_ids = '[]'::jsonb "
                "WHERE entity_id = :eid AND signal_id = :sid AND pack_id = CAST(:pid AS uuid)"
            ),
            {"eid": company.id, "sid": "funding_raised", "pid": str(fractional_cto_pack_id)},
        )
        db.commit()

        # Re-run: merge from [] must produce [ev.id]
        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"

        db.expire_all()
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
        assert inst.evidence_event_ids == [ev.id], (
            f"Merge from [] failed: got {inst.evidence_event_ids}"
        )

        # Simulate NULL (pre-migration row); merge must preserve ev.id
        from sqlalchemy import update

        stmt = (
            update(SignalInstance)
            .where(
                SignalInstance.entity_id == company.id,
                SignalInstance.signal_id == "funding_raised",
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .values(evidence_event_ids=None)
        )
        db.execute(stmt)
        db.commit()

        result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
        assert result["status"] == "completed"

        db.expire_all()
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
        # Merge from NULL: ev.id must be present (COALESCE treats NULL as [])
        ids = [x for x in (inst.evidence_event_ids or []) if x is not None]
        assert ev.id in ids, f"Merge from NULL failed: ev.id not in {inst.evidence_event_ids}"

    def test_deriver_logs_triggered(self, db: Session, fractional_cto_pack_id, caplog) -> None:
        """Deriver logs deriver_triggered at INFO for each signal produced (Phase 3)."""
        import logging

        company = Company(
            name="LogTestCo",
            domain="log.example.com",
            website_url="https://log.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        with caplog.at_level(logging.INFO):
            result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

        assert result["status"] == "completed"
        assert result["instances_upserted"] == 1

        triggered = [r for r in caplog.records if "deriver_triggered" in r.message]
        assert len(triggered) == 1
        assert triggered[0].levelname == "INFO"
        assert "pack_id=" in triggered[0].message
        assert "signal_id=funding_raised" in triggered[0].message
        assert "event_id=" in triggered[0].message
        assert "deriver_type=passthrough" in triggered[0].message

    def test_cross_pack_different_signals_from_same_events(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Core derivers override pack-specific mappings; pack isolation via event filtering.

        Issue #285, Milestone 3: core derivers produce the same signal_ids regardless of
        pack-specific deriver config. Pack isolation is maintained by event filtering
        (SignalEvent.pack_id == pack_uuid): each pack's run processes only its own events,
        producing signal_instances in its own pack namespace.
        """
        from app.models import SignalPack
        from app.packs.loader import Pack

        company = Company(
            name="CrossPackCo",
            domain="crosspack.example.com",
            website_url="https://crosspack.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        # Create second pack in DB (required for signal_events FK)
        pack_b_row = SignalPack(
            pack_id="bookkeeping_test",
            version="1",
            is_active=True,
        )
        db.add(pack_b_row)
        db.commit()
        db.refresh(pack_b_row)
        pack_b_id = pack_b_row.id

        # Same event content, but pack-scoped: one event per pack
        _make_event(
            db,
            company.id,
            "funding_raised",
            fractional_cto_pack_id,
            title="Series A and SOC2",
            summary="Compliance achieved",
        )
        _make_event(
            db,
            company.id,
            "funding_raised",
            pack_b_id,
            title="Series A and SOC2",
            summary="Compliance achieved",
        )
        db.commit()

        # Pack A (fractional_cto): custom derivers — funding_raised + compliance pattern
        pack_cto = Pack(
            manifest={"id": "cto", "version": "1", "name": "CTO", "schema_version": "1"},
            taxonomy={"signal_ids": ["funding_raised", "compliance_mentioned"]},
            scoring={},
            esl_policy={},
            playbooks={},
            derivers={
                "derivers": {
                    "passthrough": [
                        {"event_type": "funding_raised", "signal_id": "funding_raised"},
                    ],
                    "pattern": [
                        {
                            "pattern": r"(?i)(soc2|compliance)",
                            "signal_id": "compliance_mentioned",
                            "source_fields": ["title", "summary"],
                        },
                    ],
                }
            },
            config_checksum="",
        )

        # Pack B (bookkeeping): custom derivers — funding_raised -> revenue_milestone
        pack_bookkeeping = Pack(
            manifest={
                "id": "bookkeeping",
                "version": "1",
                "name": "Bookkeeping",
                "schema_version": "1",
            },
            taxonomy={"signal_ids": ["revenue_milestone"]},
            scoring={},
            esl_policy={},
            playbooks={},
            derivers={
                "derivers": {
                    "passthrough": [
                        {"event_type": "funding_raised", "signal_id": "revenue_milestone"},
                    ],
                }
            },
            config_checksum="",
        )

        with patch(
            "app.pipeline.deriver_engine.resolve_pack",
            side_effect=[pack_cto, pack_bookkeeping],
        ):
            # Core derivers only (Issue #285 M6): both packs get same signal_ids from core.
            # Run deriver with pack A (CTO)
            run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
            instances_cto = (
                db.query(SignalInstance)
                .filter(
                    SignalInstance.entity_id == company.id,
                    SignalInstance.pack_id == fractional_cto_pack_id,
                )
                .all()
            )
            signal_ids_cto = {i.signal_id for i in instances_cto}

            # Run deriver with pack B (bookkeeping) - use different pack_id
            run_deriver(db, pack_id=pack_b_id, company_ids=[company.id])
            instances_b = (
                db.query(SignalInstance)
                .filter(
                    SignalInstance.entity_id == company.id,
                    SignalInstance.pack_id == pack_b_id,
                )
                .all()
            )
            signal_ids_b = {i.signal_id for i in instances_b}

        # Core overrides both packs: funding_raised -> funding_raised (not pack-custom signals)
        assert signal_ids_cto == {"funding_raised"}, (
            f"Core override: expected {{'funding_raised'}}, got {signal_ids_cto!r}"
        )
        assert signal_ids_b == {"funding_raised"}, (
            f"Core override: expected {{'funding_raised'}}, got {signal_ids_b!r}"
        )
        # Both produce same signal_ids (core is pack-agnostic)
        assert signal_ids_cto == signal_ids_b
        # Pack isolation maintained: each pack has its own signal_instances (separate pack_id)
        assert len(instances_cto) == 1
        assert len(instances_b) == 1
        assert instances_cto[0].pack_id == fractional_cto_pack_id
        assert instances_b[0].pack_id == pack_b_id

        # Cleanup: remove test pack (cascade deletes its signal_instances)
        db.query(SignalPack).filter(SignalPack.id == pack_b_id).delete()
        db.commit()


class TestMilestone3CoreDeriverBehavior:
    """Issue #285: deriver uses core derivers only (Milestone 6: pack fallback removed)."""

    def test_deriver_missing_pack_does_not_block(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """When pack has no derivers, core derivers are used; derive succeeds (not skipped).

        Issue #285, Milestone 3: pack.derivers = {} / None must not block derive.
        """
        from app.packs.loader import Pack

        company = Company(
            name="NoDeriversCo",
            domain="noderivers.example.com",
            website_url="https://noderivers.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        # Pack with empty derivers dict (no passthrough, no pattern)
        mock_pack = Pack(
            manifest={"id": "empty", "version": "1", "name": "Empty", "schema_version": "1"},
            taxonomy={"signal_ids": ["funding_raised"]},
            scoring={},
            esl_policy={},
            playbooks={},
            derivers={},
            config_checksum="",
        )

        with patch("app.pipeline.deriver_engine.resolve_pack", return_value=mock_pack):
            result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

        # Core derivers succeed; derive is not skipped even though pack has no derivers
        assert result["status"] == "completed", (
            f"Expected 'completed' (core derivers used), got {result['status']!r}: "
            f"{result.get('error')}"
        )
        assert result["instances_upserted"] == 1
        assert result["events_processed"] == 1

        instances = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .all()
        )
        signal_ids = {i.signal_id for i in instances}
        assert signal_ids == {"funding_raised"}, (
            f"Core passthrough must produce funding_raised; got {signal_ids!r}"
        )

    def test_deriver_with_v2_pack_without_derivers_file_uses_core(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """Pack that omits derivers.yaml (example_v2) loads and derive uses core derivers (M5).

        Issue #285, Milestone 5: load_pack('example_v2', '1') has no derivers.yaml on disk;
        resolve_pack returns that pack; deriver uses core derivers and completes.
        """
        from app.packs.loader import load_pack

        company = Company(
            name="V2NoDeriversCo",
            domain="v2noderivers.example.com",
            website_url="https://v2noderivers.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        v2_pack = load_pack("example_v2", "1")
        assert v2_pack.derivers == {}, "example_v2 must have no derivers (omits derivers.yaml)"

        with patch("app.pipeline.deriver_engine.resolve_pack", return_value=v2_pack):
            result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

        assert result["status"] == "completed", (
            f"Expected 'completed' (core derivers used for pack without derivers), "
            f"got {result['status']!r}: {result.get('error')}"
        )
        assert result["instances_upserted"] == 1
        assert result["events_processed"] == 1

        instances = (
            db.query(SignalInstance)
            .filter(
                SignalInstance.entity_id == company.id,
                SignalInstance.pack_id == fractional_cto_pack_id,
            )
            .all()
        )
        signal_ids = {i.signal_id for i in instances}
        assert signal_ids == {"funding_raised"}, (
            f"Core passthrough must produce funding_raised; got {signal_ids!r}"
        )

    def test_core_derivers_load_failure_marks_job_failed(
        self, db: Session, fractional_cto_pack_id
    ) -> None:
        """When core derivers fail to load, job is marked failed (no pack fallback).

        Issue #285, Milestone 6: pack deriver fallback removed; core-only derive.
        """
        company = Company(
            name="CoreFailCo",
            domain="patternfallback.example.com",
            website_url="https://patternfallback.example.com",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        _make_event(db, company.id, "funding_raised", fractional_cto_pack_id)
        db.commit()

        with patch(
            "app.pipeline.deriver_engine._load_core_derivers",
            side_effect=FileNotFoundError("core derivers.yaml not found"),
        ):
            result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

        assert result["status"] == "failed", (
            f"Expected 'failed' (core load failure, no fallback), got {result['status']!r}"
        )
        assert result["instances_upserted"] == 0
        assert "error" in result and result["error"]
