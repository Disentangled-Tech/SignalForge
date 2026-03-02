"""Unit tests for Watchlist Seeder (Issue #279 M2): seed_from_bundles."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.evidence import store_evidence_bundle
from app.models import EvidenceBundle as EvidenceBundleORM
from app.models import SignalEvent
from app.schemas.core_events import (
    CoreEventCandidate,
    ExtractionEntityCompany,
    StructuredExtractionPayload,
)
from app.schemas.scout import EvidenceBundle as ScoutEvidenceBundle
from app.schemas.scout import EvidenceItem
from app.services.watchlist_seeder import seed_from_bundles


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
