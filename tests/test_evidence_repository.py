"""Tests for Evidence Repository (M4, Issue #276): read interface after store."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.evidence import (
    get_bundle,
    list_bundles_by_run,
    list_bundles_by_run_for_workspace,
    list_claims_for_bundle,
    list_sources_for_bundle,
    store_evidence_bundle,
)
from app.schemas.evidence import (
    EvidenceBundleRead,
    EvidenceClaimRead,
    EvidenceSourceRead,
)
from app.schemas.scout import EvidenceBundle, EvidenceItem


def _make_item(url: str, snippet: str, source_type: str = "web") -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,
        confidence_score=0.9,
    )


def test_get_bundle_after_store_returns_matching_content(db: Session) -> None:
    """After store, get_bundle by id returns EvidenceBundleRead with matching content."""
    bundle = EvidenceBundle(
        candidate_company_name="Repo Co",
        company_website="https://repo.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://example.com/p1", "snippet one")],
    )
    run_context = {"run_id": "run-repo"}
    records = store_evidence_bundle(
        db,
        run_id="run-repo",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context=run_context,
        raw_model_output={"tokens": 10},
    )
    assert len(records) == 1
    bundle_id = records[0].id

    read = get_bundle(db, bundle_id)
    assert read is not None
    assert isinstance(read, EvidenceBundleRead)
    assert read.id == bundle_id
    assert read.scout_version == "scout-v1"
    assert read.run_context == run_context
    assert read.raw_model_output == {"tokens": 10}
    assert read.created_at is not None


def test_get_bundle_returns_none_for_unknown_id(db: Session) -> None:
    """get_bundle returns None when bundle_id does not exist."""
    import uuid

    unknown = uuid.uuid4()
    read = get_bundle(db, unknown)
    assert read is None


def test_list_bundles_by_run_after_store_returns_matching_bundles(db: Session) -> None:
    """After storing two bundles with same run_id, list_bundles_by_run returns both in created order."""
    run_id = "run-list"
    run_context = {"run_id": run_id}
    b1 = EvidenceBundle(
        candidate_company_name="First Co",
        company_website="https://first.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://a.com", "a")],
    )
    b2 = EvidenceBundle(
        candidate_company_name="Second Co",
        company_website="https://second.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://b.com", "b")],
    )
    records = store_evidence_bundle(
        db,
        run_id=run_id,
        scout_version="scout-v1",
        bundles=[b1, b2],
        run_context=run_context,
        raw_model_output=None,
    )
    assert len(records) == 2

    listed = list_bundles_by_run(db, run_id)
    assert len(listed) == 2
    assert listed[0].id == records[0].id
    assert listed[1].id == records[1].id
    assert listed[0].run_context == run_context
    assert listed[1].run_context == run_context


def test_list_bundles_by_run_returns_empty_for_unknown_run_id(db: Session) -> None:
    """list_bundles_by_run returns [] when run_id has no bundles."""
    listed = list_bundles_by_run(db, "nonexistent-run-999")
    assert listed == []


def test_list_bundles_by_run_for_workspace_returns_bundles_only_when_run_in_workspace(
    db: Session,
) -> None:
    """list_bundles_by_run_for_workspace returns bundles only if run belongs to workspace; else []."""
    import uuid

    from app.models import ScoutRun, Workspace

    ws = Workspace(name="Repo WS")
    db.add(ws)
    db.flush()
    run_id = "cccccccc-0000-4000-8000-000000000003"
    db.add(
        ScoutRun(
            run_id=uuid.UUID(run_id),
            workspace_id=ws.id,
            model_version="test",
            page_fetch_count=0,
            status="completed",
        )
    )
    db.flush()

    bundle = EvidenceBundle(
        candidate_company_name="WS Co",
        company_website="https://ws.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://u.com", "s")],
    )
    store_evidence_bundle(
        db,
        run_id=run_id,
        scout_version="v1",
        bundles=[bundle],
        run_context={"run_id": run_id},
        raw_model_output=None,
    )

    in_ws = list_bundles_by_run_for_workspace(db, run_id, ws.id)
    assert len(in_ws) == 1
    assert in_ws[0].run_context == {"run_id": run_id}

    other_ws_id = uuid.uuid4()
    not_in_ws = list_bundles_by_run_for_workspace(db, run_id, other_ws_id)
    assert not_in_ws == []


def test_list_sources_for_bundle_returns_linked_sources(db: Session) -> None:
    """list_sources_for_bundle returns sources linked to the bundle via evidence_bundle_sources."""
    bundle = EvidenceBundle(
        candidate_company_name="Sources Co",
        company_website="https://sources.example.com",
        why_now_hypothesis="Hiring.",
        evidence=[
            _make_item("https://example.com/x", "quote X"),
            _make_item("https://example.com/y", "quote Y"),
        ],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-sources",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-sources"},
        raw_model_output=None,
    )
    assert len(records) == 1
    bundle_id = records[0].id

    sources = list_sources_for_bundle(db, bundle_id)
    assert len(sources) == 2
    assert all(isinstance(s, EvidenceSourceRead) for s in sources)
    urls = {s.url for s in sources}
    assert urls == {"https://example.com/x", "https://example.com/y"}
    for s in sources:
        assert s.content_hash
        assert s.retrieved_at is not None or s.snippet is not None


def test_list_sources_for_bundle_returns_empty_for_bundle_with_no_sources(
    db: Session,
) -> None:
    """list_sources_for_bundle returns [] when bundle has no evidence items (edge case)."""
    bundle = EvidenceBundle(
        candidate_company_name="Empty Co",
        company_website="https://empty.example.com",
        why_now_hypothesis="",
        evidence=[],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-empty-src",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-empty-src"},
        raw_model_output=None,
    )
    assert len(records) == 1
    sources = list_sources_for_bundle(db, records[0].id)
    assert sources == []


def test_list_claims_for_bundle_returns_claims_when_stored(db: Session) -> None:
    """list_claims_for_bundle returns claims from structured_payload when store wrote them."""
    bundle = EvidenceBundle(
        candidate_company_name="Claims Co",
        company_website="https://claims.example.com",
        why_now_hypothesis="Need CTO",
        evidence=[
            _make_item("https://c1.com", "quote 1"),
            _make_item("https://c2.com", "quote 2"),
        ],
    )
    payload = {
        "claims": [
            {
                "entity_type": "company",
                "field": "stage",
                "value": "Series A",
                "source_refs": [0],
                "confidence": 0.85,
            },
            {
                "entity_type": "company",
                "field": "hiring",
                "value": "CTO",
                "source_refs": [1],
                "confidence": 0.9,
            },
        ]
    }
    records = store_evidence_bundle(
        db,
        run_id="run-claims",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-claims"},
        raw_model_output=None,
        structured_payloads=[payload],
    )
    assert len(records) == 1
    bundle_id = records[0].id

    claims = list_claims_for_bundle(db, bundle_id)
    assert len(claims) == 2
    assert all(isinstance(c, EvidenceClaimRead) for c in claims)
    entity_fields = [(c.entity_type, c.field, c.value) for c in claims]
    assert ("company", "stage", "Series A") in entity_fields
    assert ("company", "hiring", "CTO") in entity_fields
    for c in claims:
        assert c.bundle_id == bundle_id
        assert c.source_ids is None or len(c.source_ids) >= 0


def test_list_claims_for_bundle_returns_empty_when_no_claims(db: Session) -> None:
    """list_claims_for_bundle returns [] when bundle has no claims."""
    bundle = EvidenceBundle(
        candidate_company_name="NoClaims Co",
        company_website="https://noclaims.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://u.com", "s")],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-noclaims",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-noclaims"},
        raw_model_output=None,
    )
    assert len(records) == 1
    claims = list_claims_for_bundle(db, records[0].id)
    assert claims == []


def test_repository_read_after_store_content_matches(db: Session) -> None:
    """Integration: store one bundle with run_context and structured_payload; read and assert match."""
    run_context = {"run_id": "run-int", "workspace_id": "ws-1"}
    raw_output = {"raw": "data"}
    structured = {"claims": []}
    bundle = EvidenceBundle(
        candidate_company_name="Int Co",
        company_website="https://int.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://i.com", "snippet")],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-int",
        scout_version="scout-v2",
        bundles=[bundle],
        run_context=run_context,
        raw_model_output=raw_output,
        structured_payloads=[structured],
    )
    bundle_id = records[0].id

    by_id = get_bundle(db, bundle_id)
    assert by_id is not None
    assert by_id.run_context == run_context
    assert by_id.raw_model_output == raw_output
    assert by_id.structured_payload == structured
    assert by_id.scout_version == "scout-v2"

    by_run = list_bundles_by_run(db, "run-int")
    assert len(by_run) == 1
    assert by_run[0].id == bundle_id
    assert by_run[0].run_context == run_context

    sources = list_sources_for_bundle(db, bundle_id)
    assert len(sources) == 1
    assert sources[0].url == "https://i.com"
    assert sources[0].snippet == "snippet"
