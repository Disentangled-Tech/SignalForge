"""Tests for Watchlist Seeder (Issue #279): unit (M2), orchestration (M3), integration (M4)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.evidence import store_evidence_bundle
from app.models import Company, ReadinessSnapshot, SignalEvent, SignalInstance
from app.models import EvidenceBundle as EvidenceBundleORM
from app.pipeline.deriver_engine import run_deriver
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    StructuredExtractionPayload,
)
from app.schemas.scout import EvidenceBundle as ScoutEvidenceBundle
from app.schemas.scout import EvidenceItem
from app.services.readiness.score_nightly import run_score_nightly
from app.services.watchlist_seeder import run_watchlist_seed, seed_from_bundles


def _make_scout_item(url: str, snippet: str) -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC),
        source_type="web",
        confidence_score=0.9,
    )


def _make_seeder_bundle_with_payload(
    db: Session,
    company_name: str,
    website: str,
    domain: str | None,
    events: list[CoreEventCandidate],
    run_id: str = "run-seeder-test",
) -> uuid.UUID:
    """Create one evidence bundle via store_evidence_bundle with structured_payload; return bundle id."""
    scout_bundle = ScoutEvidenceBundle(
        candidate_company_name=company_name,
        company_website=website,
        why_now_hypothesis="",
        evidence=[_make_scout_item("https://example.com/p", "snippet")],
    )
    company = ExtractionEntityCompany(
        name=company_name,
        domain=domain,
        website_url=website,
    )
    payload = StructuredExtractionPayload(
        version="1.0",
        events=events,
        company=company,
        persons=[],
        claims=[],
    )
    records = store_evidence_bundle(
        db,
        run_id=run_id,
        scout_version="scout-v1",
        bundles=[scout_bundle],
        run_context={"run_id": run_id},
        raw_model_output=None,
        structured_payloads=[payload.model_dump(mode="json")],
    )
    assert len(records) == 1
    return records[0].id


def test_seed_from_bundles_creates_company_and_stores_events(db: Session) -> None:
    """seed_from_bundles with valid bundle creates company and stores events with correct source/evidence_bundle_id."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
            title="Series A",
            summary="Raised Series A",
            url="https://example.com/news",
            confidence=0.9,
            source_refs=[0],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Seeder Co",
        website="https://seeder.example.com",
        domain="seeder.example.com",
        events=events,
    )

    result = seed_from_bundles(db, [bundle_id])

    assert result.companies_created == 1
    assert result.companies_matched == 0
    assert result.events_stored == 1
    assert result.events_skipped_duplicate == 0
    assert result.errors == []

    row = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.source == "watchlist_seeder",
            SignalEvent.evidence_bundle_id == bundle_id,
        )
        .first()
    )
    assert row is not None
    assert row.source_event_id == f"{bundle_id}:0"
    assert row.event_type == "funding_raised"
    assert row.evidence_bundle_id == bundle_id


def test_seed_from_bundles_resolves_existing_company(db: Session) -> None:
    """When company already exists (e.g. same domain), companies_matched increments."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
            title="Series A",
            summary="Raised",
            url=None,
            confidence=0.85,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Match Co",
        website="https://match.example.com",
        domain="match.example.com",
        events=events,
    )

    result1 = seed_from_bundles(db, [bundle_id])
    assert result1.companies_created == 1
    assert result1.events_stored == 1

    # Second bundle, same company (same domain)
    bundle_id2 = _make_seeder_bundle_with_payload(
        db,
        company_name="Match Co",
        website="https://match.example.com",
        domain="match.example.com",
        events=[
            CoreEventCandidate(
                event_type="cto_role_posted",
                event_time=datetime(2026, 2, 20, 12, 0, 0, tzinfo=UTC),
                title="CTO role",
                summary="Hiring CTO",
                url=None,
                confidence=0.8,
                source_refs=[],
            ),
        ],
        run_id="run-seeder-test-2",
    )
    result2 = seed_from_bundles(db, [bundle_id2])
    assert result2.companies_matched == 1
    assert result2.companies_created == 0
    assert result2.events_stored == 1


def test_seed_from_bundles_idempotent_re_seed_skips_duplicates(db: Session) -> None:
    """Re-seeding same bundle increases events_skipped_duplicate, no duplicate SignalEvent rows."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
            title="Series A",
            summary="Raised",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Idem Co",
        website="https://idem.example.com",
        domain="idem.example.com",
        events=events,
    )

    result1 = seed_from_bundles(db, [bundle_id])
    assert result1.events_stored == 1
    assert result1.events_skipped_duplicate == 0

    result2 = seed_from_bundles(db, [bundle_id])
    assert result2.events_stored == 0
    assert result2.events_skipped_duplicate == 1

    count = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.source == "watchlist_seeder",
            SignalEvent.source_event_id == f"{bundle_id}:0",
        )
        .count()
    )
    assert count == 1


def test_seed_from_bundles_missing_bundle_appends_error(db: Session) -> None:
    """Unknown bundle_id appends error and does not raise."""
    unknown = uuid.uuid4()
    result = seed_from_bundles(db, [unknown])
    assert result.companies_created == 0
    assert result.companies_matched == 0
    assert result.events_stored == 0
    assert result.events_skipped_duplicate == 0
    assert len(result.errors) == 1
    assert "not found" in result.errors[0] or str(unknown) in result.errors[0]


def test_seed_from_bundles_no_structured_payload_appends_error(db: Session) -> None:
    """Bundle with no structured_payload appends error."""
    bundle = EvidenceBundleORM(
        scout_version="scout-v1",
        core_taxonomy_version="tax-v1",
        core_derivers_version="deriv-v1",
        structured_payload=None,
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)

    result = seed_from_bundles(db, [bundle.id])
    assert result.companies_created == 0
    assert result.events_stored == 0
    assert len(result.errors) == 1
    assert "no structured_payload" in result.errors[0]


def test_seed_from_bundles_no_company_in_payload_appends_error(db: Session) -> None:
    """Bundle with structured_payload but company=None appends error."""
    scout_bundle = ScoutEvidenceBundle(
        candidate_company_name="No Company Co",
        company_website="https://noco.example.com",
        why_now_hypothesis="",
        evidence=[_make_scout_item("https://x.com", "s")],
    )
    payload = StructuredExtractionPayload(
        version="1.0",
        events=[
            CoreEventCandidate(
                event_type="funding_raised",
                event_time=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
                title="Funded",
                summary="",
                url=None,
                confidence=0.8,
                source_refs=[],
            ),
        ],
        company=None,
        persons=[],
        claims=[],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-noco",
        scout_version="scout-v1",
        bundles=[scout_bundle],
        run_context={"run_id": "run-noco"},
        raw_model_output=None,
        structured_payloads=[payload.model_dump(mode="json")],
    )
    bundle_id = records[0].id

    result = seed_from_bundles(db, [bundle_id])
    assert result.companies_created == 0
    assert result.events_stored == 0
    assert len(result.errors) == 1
    assert "no company" in result.errors[0]


def test_seed_from_bundles_no_events_in_payload_appends_error(db: Session) -> None:
    """Bundle with company but empty events appends error."""
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="No Events Co",
        website="https://noevents.example.com",
        domain="noevents.example.com",
        events=[],
        run_id="run-no-events",
    )

    result = seed_from_bundles(db, [bundle_id])
    assert result.companies_created == 0
    assert result.events_stored == 0
    assert len(result.errors) == 1
    assert "no events" in result.errors[0]


def test_seed_from_bundles_accepts_core_event_candidates_only(db: Session) -> None:
    """M2: structured_payload shaped as ExtractionResult (core_event_candidates, no events key) is accepted and events stored."""
    from app.extractor.schemas import ExtractionResult

    scout_bundle = ScoutEvidenceBundle(
        candidate_company_name="ExtractionResult Co",
        company_website="https://extractionresult.example.com",
        why_now_hypothesis="",
        evidence=[_make_scout_item("https://example.com/p", "snippet")],
    )
    company = ExtractionEntityCompany(
        name="ExtractionResult Co",
        domain="extractionresult.example.com",
        website_url="https://extractionresult.example.com",
    )
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
            title="Series A",
            summary="Raised",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    extraction = ExtractionResult(
        company=company,
        person=None,
        core_event_candidates=events,
        version="1.0",
    )
    raw_payload = extraction.model_dump(mode="json")
    assert "core_event_candidates" in raw_payload
    assert "events" not in raw_payload

    records = store_evidence_bundle(
        db,
        run_id="run-extraction-result",
        scout_version="scout-v1",
        bundles=[scout_bundle],
        run_context={"run_id": "run-extraction-result"},
        raw_model_output=None,
        structured_payloads=[raw_payload],
    )
    bundle_id = records[0].id

    result = seed_from_bundles(db, [bundle_id])
    assert result.errors == []
    assert result.companies_created == 1
    assert result.events_stored == 1
    row = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.source == "watchlist_seeder",
            SignalEvent.evidence_bundle_id == bundle_id,
        )
        .first()
    )
    assert row is not None
    assert row.event_type == "funding_raised"


def test_seed_from_bundles_invalid_payload_appends_error(db: Session) -> None:
    """Bundle with invalid structured_payload (e.g. wrong shape) appends error."""
    bundle = EvidenceBundleORM(
        scout_version="scout-v1",
        core_taxonomy_version="tax-v1",
        core_derivers_version="deriv-v1",
        structured_payload={"version": "1.0", "events": "not-a-list", "company": None},
    )
    db.add(bundle)
    db.commit()
    db.refresh(bundle)

    result = seed_from_bundles(db, [bundle.id])
    assert result.companies_created == 0
    assert result.events_stored == 0
    assert len(result.errors) == 1
    assert "invalid" in result.errors[0].lower() or "validation" in result.errors[0].lower()


def test_seed_from_bundles_source_event_id_format(db: Session) -> None:
    """Stored events use source_event_id {bundle_id}:{index}."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 10, 10, 0, 0, tzinfo=UTC),
            title="A",
            summary="",
            url=None,
            confidence=0.7,
            source_refs=[],
        ),
        CoreEventCandidate(
            event_type="cto_role_posted",
            event_time=datetime(2026, 2, 11, 11, 0, 0, tzinfo=UTC),
            title="B",
            summary="",
            url=None,
            confidence=0.8,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Format Co",
        website="https://format.example.com",
        domain="format.example.com",
        events=events,
    )

    seed_from_bundles(db, [bundle_id])

    rows = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.source == "watchlist_seeder", SignalEvent.evidence_bundle_id == bundle_id
        )
        .order_by(SignalEvent.source_event_id)
        .all()
    )
    assert len(rows) == 2
    assert rows[0].source_event_id == f"{bundle_id}:0"
    assert rows[1].source_event_id == f"{bundle_id}:1"


def test_seed_from_bundles_workspace_scoped_loads_only_workspace_bundle(
    db: Session,
) -> None:
    """When workspace_id is set, only bundles whose run belongs to that workspace are loaded."""
    from app.models.scout_run import ScoutRun
    from app.models.workspace import Workspace

    ws = Workspace(name="Seeder WS")
    db.add(ws)
    db.flush()
    workspace_id = ws.id
    run_id = uuid.uuid4()
    run_row = ScoutRun(
        run_id=run_id,
        workspace_id=workspace_id,
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run_row)
    db.flush()

    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            title="W",
            summary="",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    scout_bundle = ScoutEvidenceBundle(
        candidate_company_name="Workspace Co",
        company_website="https://workspace.example.com",
        why_now_hypothesis="",
        evidence=[_make_scout_item("https://w.com", "s")],
    )
    payload = StructuredExtractionPayload(
        version="1.0",
        events=events,
        company=ExtractionEntityCompany(
            name="Workspace Co",
            domain="workspace.example.com",
            website_url="https://workspace.example.com",
        ),
        persons=[],
        claims=[],
    )
    records = store_evidence_bundle(
        db,
        run_id=str(run_id),
        scout_version="scout-v1",
        bundles=[scout_bundle],
        run_context={"run_id": str(run_id)},
        raw_model_output=None,
        structured_payloads=[payload.model_dump(mode="json")],
    )
    bundle_id = records[0].id

    result = seed_from_bundles(db, [bundle_id], workspace_id=workspace_id)
    assert result.errors == []
    assert result.companies_created == 1
    assert result.events_stored == 1

    # Wrong workspace: bundle not found for workspace
    other_workspace = uuid.uuid4()
    result2 = seed_from_bundles(db, [bundle_id], workspace_id=other_workspace)
    assert len(result2.errors) == 1
    assert result2.companies_created == 0
    assert result2.events_stored == 0


def test_seed_from_bundles_multiple_bundles_aggregates_counts(db: Session) -> None:
    """Multiple bundle_ids aggregate companies_created/matched and events_stored."""
    events1 = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
            title="E1",
            summary="",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    events2 = [
        CoreEventCandidate(
            event_type="cto_role_posted",
            event_time=datetime(2026, 2, 2, 12, 0, 0, tzinfo=UTC),
            title="E2",
            summary="",
            url=None,
            confidence=0.8,
            source_refs=[],
        ),
    ]
    b1 = _make_seeder_bundle_with_payload(
        db, "Multi A", "https://multi-a.example.com", "multi-a.example.com", events1, "run-m1"
    )
    b2 = _make_seeder_bundle_with_payload(
        db, "Multi B", "https://multi-b.example.com", "multi-b.example.com", events2, "run-m2"
    )

    result = seed_from_bundles(db, [b1, b2])
    assert result.companies_created == 2
    assert result.events_stored == 2
    assert result.errors == []


# --- M4: Integration tests (Issue #279) ---

_AS_OF = date(2026, 2, 18)


@pytest.mark.integration
def test_seed_then_derive_then_score_creates_snapshots(
    db: Session,
    fractional_cto_pack_id: uuid.UUID,
    core_pack_id: uuid.UUID,
) -> None:
    """Integration: EvidenceBundle → seed_from_bundles → run_deriver → run_score_nightly → ReadinessSnapshot."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
            title="Series A",
            summary="Raised Series A",
            url="https://integrate.example.com/news",
            confidence=0.9,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Integrate Co",
        website="https://integrate.example.com",
        domain="integrate.example.com",
        events=events,
        run_id="run-m4-integrate",
    )

    result = seed_from_bundles(db, [bundle_id])
    assert result.errors == []
    assert result.companies_created == 1
    assert result.events_stored == 1

    company = db.query(Company).filter(Company.domain == "integrate.example.com").first()
    assert company is not None

    derive_result = run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])
    assert derive_result["status"] == "completed"
    assert derive_result["instances_upserted"] >= 1
    assert derive_result["events_processed"] >= 1

    instances = (
        db.query(SignalInstance)
        .filter(
            SignalInstance.entity_id == company.id,
            SignalInstance.pack_id == core_pack_id,
        )
        .all()
    )
    assert len(instances) >= 1

    with patch("app.services.readiness.score_nightly.date") as mock_date:
        mock_date.today.return_value = _AS_OF
        score_result = run_score_nightly(db, pack_id=fractional_cto_pack_id)

    assert score_result["status"] == "completed"
    assert score_result["companies_scored"] >= 1

    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == _AS_OF,
            ReadinessSnapshot.pack_id == fractional_cto_pack_id,
        )
        .first()
    )
    assert snapshot is not None
    assert snapshot.composite >= 0
    assert snapshot.explain is not None


@pytest.mark.integration
def test_seed_derive_same_core_instances_across_packs(
    db: Session,
    fractional_cto_pack_id: uuid.UUID,
    second_pack_id: uuid.UUID,
    core_pack_id: uuid.UUID,
) -> None:
    """Same core events produce same core SignalInstances; scoring with two packs yields two snapshots (Issue #279 M4)."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 14, 10, 0, 0, tzinfo=UTC),
            title="Seed Pack Parity",
            summary="Funding",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Pack Parity Co",
        website="https://packparity.example.com",
        domain="packparity.example.com",
        events=events,
        run_id="run-m4-pack-parity",
    )

    seed_from_bundles(db, [bundle_id])
    company = db.query(Company).filter(Company.domain == "packparity.example.com").first()
    assert company is not None

    run_deriver(db, pack_id=fractional_cto_pack_id, company_ids=[company.id])

    core_before = {
        (si.entity_id, si.signal_id)
        for si in db.query(SignalInstance)
        .filter(
            SignalInstance.entity_id == company.id,
            SignalInstance.pack_id == core_pack_id,
        )
        .all()
    }
    assert len(core_before) >= 1

    with patch("app.services.readiness.score_nightly.date") as mock_date:
        mock_date.today.return_value = _AS_OF
        run_score_nightly(db, pack_id=fractional_cto_pack_id)
        run_score_nightly(db, pack_id=second_pack_id)

    core_after = {
        (si.entity_id, si.signal_id)
        for si in db.query(SignalInstance)
        .filter(
            SignalInstance.entity_id == company.id,
            SignalInstance.pack_id == core_pack_id,
        )
        .all()
    }
    assert core_after == core_before, "Core SignalInstances must be identical across pack scoring"

    snapshots = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company.id,
            ReadinessSnapshot.as_of == _AS_OF,
        )
        .all()
    )
    pack_ids = {s.pack_id for s in snapshots}
    assert fractional_cto_pack_id in pack_ids
    assert second_pack_id in pack_ids
    assert len(snapshots) >= 2


# ── run_watchlist_seed orchestration (M3) ─────────────────────────────────────


def test_run_watchlist_seed_no_pack_returns_failed(db: Session) -> None:
    """When no pack is resolved, run_watchlist_seed returns failed with empty derive/score."""
    with (
        patch("app.services.watchlist_seeder.run_seed.get_pack_for_workspace", return_value=None),
        patch("app.services.watchlist_seeder.run_seed.get_default_pack_id", return_value=None),
    ):
        result = run_watchlist_seed(db, [uuid.uuid4()])
    assert result["status"] == "failed"
    assert result["error"] == "No pack resolved for workspace"
    assert result["derive_result"] == {}
    assert result["score_result"] == {}
    assert "seed_result" in result
    assert "events_stored" in result["seed_result"]


def test_run_watchlist_seed_success_returns_combined_result(db: Session) -> None:
    """run_watchlist_seed with pack resolved runs seed → derive → score and returns combined result."""
    events = [
        CoreEventCandidate(
            event_type="funding_raised",
            event_time=datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC),
            title="Seed",
            summary="",
            url=None,
            confidence=0.9,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db,
        company_name="Orch Co",
        website="https://orch.example.com",
        domain="orch.example.com",
        events=events,
        run_id="run-orch",
    )
    with (
        patch("app.pipeline.deriver_engine.run_deriver") as mock_deriver,
        patch("app.services.readiness.score_nightly.run_score_nightly") as mock_score,
    ):
        mock_deriver.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "instances_upserted": 1,
            "events_processed": 1,
            "events_skipped": 0,
            "error": None,
        }
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 2,
            "companies_scored": 1,
            "companies_skipped": 0,
            "error": None,
        }
        result = run_watchlist_seed(db, [bundle_id])
    assert result["status"] == "completed"
    assert result["seed_result"]["events_stored"] == 1
    assert result["derive_result"]["status"] == "completed"
    assert result["score_result"]["companies_scored"] == 1
    assert result.get("error") is None


def test_run_watchlist_seed_derive_raises_returns_failed(db: Session) -> None:
    """When run_deriver raises, run_watchlist_seed returns failed and still runs score."""
    events = [
        CoreEventCandidate(
            event_type="launch_major",
            event_time=datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC),
            title="Launch",
            summary="",
            url=None,
            confidence=0.8,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db, "Fail Co", "https://fail.example.com", "fail.example.com", events, "run-fail"
    )
    with (
        patch("app.pipeline.deriver_engine.run_deriver") as mock_deriver,
        patch("app.services.readiness.score_nightly.run_score_nightly") as mock_score,
    ):
        mock_deriver.side_effect = RuntimeError("Deriver failed")
        mock_score.return_value = {
            "status": "completed",
            "job_run_id": 3,
            "companies_scored": 0,
            "companies_skipped": 0,
            "error": None,
        }
        result = run_watchlist_seed(db, [bundle_id])
    assert result["status"] == "failed"
    assert "Deriver failed" in result["error"]
    assert result["derive_result"] == {"status": "failed", "error": "Deriver failed"}
    assert result["score_result"]["status"] == "completed"


def test_run_watchlist_seed_score_non_completed_sets_error(db: Session) -> None:
    """When run_score_nightly returns status != completed, overall status is failed."""
    events = [
        CoreEventCandidate(
            event_type="revenue_milestone",
            event_time=datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC),
            title="Rev",
            summary="",
            url=None,
            confidence=0.7,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db, "Score Co", "https://score.example.com", "score.example.com", events, "run-score"
    )
    with (
        patch("app.pipeline.deriver_engine.run_deriver") as mock_deriver,
        patch("app.services.readiness.score_nightly.run_score_nightly") as mock_score,
    ):
        mock_deriver.return_value = {
            "status": "completed",
            "job_run_id": 4,
            "instances_upserted": 1,
            "events_processed": 1,
            "events_skipped": 0,
            "error": None,
        }
        mock_score.return_value = {
            "status": "skipped",
            "job_run_id": 5,
            "companies_scored": 0,
            "companies_skipped": 0,
            "error": "No eligible companies",
        }
        result = run_watchlist_seed(db, [bundle_id])
    assert result["status"] == "failed"
    assert result["error"] is not None
    assert result["derive_result"]["status"] == "completed"
    assert result["score_result"]["status"] == "skipped"


def test_run_watchlist_seed_score_raises_returns_failed(db: Session) -> None:
    """When run_score_nightly raises, run_watchlist_seed returns failed with score_result error."""
    events = [
        CoreEventCandidate(
            event_type="api_launched",
            event_time=datetime(2026, 2, 10, 12, 0, 0, tzinfo=UTC),
            title="API",
            summary="",
            url=None,
            confidence=0.85,
            source_refs=[],
        ),
    ]
    bundle_id = _make_seeder_bundle_with_payload(
        db, "Raise Co", "https://raise.example.com", "raise.example.com", events, "run-raise"
    )
    with (
        patch("app.pipeline.deriver_engine.run_deriver") as mock_deriver,
        patch("app.services.readiness.score_nightly.run_score_nightly") as mock_score,
    ):
        mock_deriver.return_value = {
            "status": "completed",
            "job_run_id": 6,
            "instances_upserted": 1,
            "events_processed": 1,
            "events_skipped": 0,
            "error": None,
        }
        mock_score.side_effect = RuntimeError("Score DB error")
        result = run_watchlist_seed(db, [bundle_id])
    assert result["status"] == "failed"
    assert "Score DB error" in result["error"]
    assert result["score_result"] == {"status": "failed", "error": "Score DB error"}
