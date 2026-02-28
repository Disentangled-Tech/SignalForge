"""Integration tests for Scout persistence (M3, Issue #275).

Insert scout run + evidence bundle, read back; assert no writes to
companies or signal_events.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import (
    Company,
    ScoutEvidenceBundle,
    ScoutRun,
    SignalEvent,
    Workspace,
)


@pytest.mark.integration
def test_scout_run_and_bundle_persist_and_read_back(db: Session) -> None:
    """Insert ScoutRun + ScoutEvidenceBundle, commit, read back; fields match."""
    run_id = uuid.uuid4()
    started = datetime.now(UTC)
    run = ScoutRun(
        run_id=run_id,
        started_at=started,
        model_version="test-model-v1",
        tokens_used=100,
        latency_ms=500,
        page_fetch_count=3,
        config_snapshot={"icp": "B2B SaaS", "query_count": 5},
        status="completed",
    )
    db.add(run)
    db.flush()

    evidence = [
        {
            "url": "https://example.com/news",
            "quoted_snippet": "Company raised Series A.",
            "timestamp_seen": "2026-02-27T12:00:00Z",
            "source_type": "news",
            "confidence_score": 0.9,
        }
    ]
    bundle = ScoutEvidenceBundle(
        scout_run_id=run.run_id,
        candidate_company_name="Test Co",
        company_website="https://testco.example.com",
        why_now_hypothesis="Recent funding and hiring.",
        evidence=evidence,
        missing_information=["exact headcount"],
        raw_llm_output={"raw": "..."},
    )
    db.add(bundle)
    db.commit()

    read_run = db.query(ScoutRun).filter(ScoutRun.run_id == run_id).one()
    assert read_run.run_id == run_id
    assert read_run.model_version == "test-model-v1"
    assert read_run.tokens_used == 100
    assert read_run.latency_ms == 500
    assert read_run.page_fetch_count == 3
    assert read_run.status == "completed"
    assert read_run.config_snapshot == {"icp": "B2B SaaS", "query_count": 5}

    read_bundles = (
        db.query(ScoutEvidenceBundle)
        .filter(ScoutEvidenceBundle.scout_run_id == read_run.run_id)
        .all()
    )
    assert len(read_bundles) == 1
    rb = read_bundles[0]
    assert rb.candidate_company_name == "Test Co"
    assert rb.company_website == "https://testco.example.com"
    assert rb.why_now_hypothesis == "Recent funding and hiring."
    assert len(rb.evidence) == 1
    assert rb.evidence[0]["url"] == "https://example.com/news"
    assert rb.missing_information == ["exact headcount"]


@pytest.mark.integration
def test_scout_persistence_does_not_write_companies_or_signal_events(
    db: Session,
) -> None:
    """Persisting scout run + bundle must not create companies or signal_events."""
    companies_before = db.query(Company).count()
    events_before = db.query(SignalEvent).count()

    run_id = uuid.uuid4()
    run = ScoutRun(
        run_id=run_id,
        model_version="test-model-v1",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run)
    db.flush()
    bundle = ScoutEvidenceBundle(
        scout_run_id=run.run_id,
        candidate_company_name="Scout-Only Candidate Inc",
        company_website="https://scout-only.example.com",
        why_now_hypothesis="",
        evidence=[],
        missing_information=[],
    )
    db.add(bundle)
    db.commit()

    companies_after = db.query(Company).count()
    events_after = db.query(SignalEvent).count()
    assert companies_after == companies_before, "scout must not create companies"
    assert events_after == events_before, "scout must not create signal_events"


@pytest.mark.integration
def test_scout_run_workspace_id_persist_and_filter(db: Session) -> None:
    """workspace_id is stored and can be used to scope queries (tenant boundary)."""
    ws = Workspace(name="Scout Test Workspace")
    db.add(ws)
    db.flush()

    run_id = uuid.uuid4()
    run = ScoutRun(
        run_id=run_id,
        workspace_id=ws.id,
        model_version="test-model-v1",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run)
    db.commit()

    read_run = (
        db.query(ScoutRun).filter(ScoutRun.workspace_id == ws.id, ScoutRun.run_id == run_id).one()
    )
    assert read_run.workspace_id == ws.id
    # Unscoped query would see it; scoped by workspace_id must be enforced in API
    all_for_workspace = db.query(ScoutRun).filter(ScoutRun.workspace_id == ws.id).all()
    assert len(all_for_workspace) >= 1
    assert any(r.run_id == run_id for r in all_for_workspace)


@pytest.mark.integration
def test_scout_tables_exist_after_migration(db: Session) -> None:
    """scout_runs and scout_evidence_bundles tables exist after migration."""
    for table in ("scout_runs", "scout_evidence_bundles"):
        result = db.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = :t
                )
                """
            ),
            {"t": table},
        )
        assert result.scalar() is True, f"table {table} must exist"
