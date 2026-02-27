"""Tests for Evidence Store (M3, Issue #276): write path, versioning, immutability, source dedupe, claims."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.evidence.store import store_evidence_bundle
from app.models import (
    EvidenceBundle as EvidenceBundleORM,
)
from app.models import (
    EvidenceBundleSource,
    EvidenceClaim,
    EvidenceSource,
)
from app.schemas.evidence import EvidenceBundleRecord
from app.schemas.scout import EvidenceBundle, EvidenceItem


def _make_item(url: str, snippet: str, source_type: str = "web") -> EvidenceItem:
    return EvidenceItem(
        url=url,
        quoted_snippet=snippet,
        timestamp_seen=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC),
        source_type=source_type,
        confidence_score=0.9,
    )


def test_store_evidence_bundle_returns_records_with_versions(db: Session) -> None:
    """store_evidence_bundle returns list of EvidenceBundleRecord with core versions set from loaders."""
    from app.core_derivers.loader import get_core_derivers_version
    from app.core_taxonomy.loader import get_core_taxonomy_version

    bundle = EvidenceBundle(
        candidate_company_name="Acme Inc",
        company_website="https://acme.example.com",
        why_now_hypothesis="",
        evidence=[
            _make_item("https://example.com/p1", "snippet one"),
        ],
    )
    run_context = {"run_id": "run-001"}
    records = store_evidence_bundle(
        db,
        run_id="run-001",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context=run_context,
        raw_model_output=None,
    )
    assert len(records) == 1
    assert isinstance(records[0], EvidenceBundleRecord)
    assert records[0].id is not None
    assert records[0].created_at is not None
    assert records[0].scout_version == "scout-v1"
    assert records[0].core_taxonomy_version == get_core_taxonomy_version()
    assert records[0].core_derivers_version == get_core_derivers_version()


def test_store_evidence_bundle_one_bundle_two_sources(db: Session) -> None:
    """Store one bundle with two evidence items; assert two sources and two bundle-source links."""
    bundle = EvidenceBundle(
        candidate_company_name="Beta Co",
        company_website="https://beta.example.com",
        why_now_hypothesis="Hiring CTO.",
        evidence=[
            _make_item("https://example.com/a", "quote A"),
            _make_item("https://example.com/b", "quote B"),
        ],
    )
    records = store_evidence_bundle(
        db,
        run_id="run-002",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-002"},
        raw_model_output=None,
    )
    assert len(records) == 1
    bundle_id = records[0].id

    links = db.query(EvidenceBundleSource).filter(EvidenceBundleSource.bundle_id == bundle_id).all()
    assert len(links) == 2
    source_ids = {link.source_id for link in links}
    assert len(source_ids) == 2

    sources = db.query(EvidenceSource).filter(EvidenceSource.id.in_(source_ids)).all()
    urls = {s.url for s in sources}
    assert urls == {"https://example.com/a", "https://example.com/b"}


def test_store_evidence_bundle_source_dedupe_by_content_hash(db: Session) -> None:
    """Two bundles sharing same (url, snippet) reuse one EvidenceSource row."""
    snippet = "Same quoted snippet for dedupe."
    bundle1 = EvidenceBundle(
        candidate_company_name="Company One",
        company_website="https://one.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://shared.com/page", snippet)],
    )
    bundle2 = EvidenceBundle(
        candidate_company_name="Company Two",
        company_website="https://two.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://shared.com/page", snippet)],
    )
    store_evidence_bundle(
        db,
        run_id="run-dedupe",
        scout_version="scout-v1",
        bundles=[bundle1, bundle2],
        run_context={"run_id": "run-dedupe"},
        raw_model_output=None,
    )

    # One EvidenceSource for (content_hash of snippet, url)
    all_sources = db.query(EvidenceSource).all()
    assert len(all_sources) == 1
    assert all_sources[0].url == "https://shared.com/page"

    # Two bundles, each linked to that source
    all_links = db.query(EvidenceBundleSource).all()
    assert len(all_links) == 2
    assert all(link.source_id == all_sources[0].id for link in all_links)


def test_store_evidence_bundle_immutability_insert_only(db: Session) -> None:
    """Store only inserts evidence_bundles; no UPDATE (immutability)."""
    bundle = EvidenceBundle(
        candidate_company_name="Immut Co",
        company_website="https://immut.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://x.com/1", "x")],
    )
    store_evidence_bundle(
        db,
        run_id="run-immut",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-immut"},
        raw_model_output=None,
    )
    count = (
        db.query(EvidenceBundleORM)
        .filter(EvidenceBundleORM.run_context["run_id"].astext == "run-immut")
        .count()
    )
    assert count == 1
    row = (
        db.query(EvidenceBundleORM)
        .filter(EvidenceBundleORM.run_context["run_id"].astext == "run-immut")
        .first()
    )
    assert row is not None
    assert not hasattr(EvidenceBundleORM, "updated_at")


def test_store_evidence_bundle_claims_with_source_ids(db: Session) -> None:
    """Store bundle with structured_payload.claims; claims get source_ids from evidence order."""
    bundle = EvidenceBundle(
        candidate_company_name="Claims Co",
        company_website="https://claims.example.com",
        why_now_hypothesis="Funded.",
        evidence=[
            _make_item("https://example.com/s1", "snippet one"),
            _make_item("https://example.com/s2", "snippet two"),
        ],
    )
    # source_refs: 0 = first evidence item, 1 = second
    structured_payload = {
        "claims": [
            {
                "entity_type": "company",
                "field": "funding",
                "value": "Series A",
                "source_refs": [0],
                "confidence": 0.95,
            },
            {
                "entity_type": "company",
                "field": "name",
                "value": "Claims Co",
                "source_refs": [0, 1],
                "confidence": 0.9,
            },
        ],
    }
    records = store_evidence_bundle(
        db,
        run_id="run-claims",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-claims"},
        raw_model_output=None,
        structured_payloads=[structured_payload],
    )
    assert len(records) == 1
    bundle_id = records[0].id

    claims = (
        db.query(EvidenceClaim)
        .filter(EvidenceClaim.bundle_id == bundle_id)
        .order_by(EvidenceClaim.id)
        .all()
    )
    assert len(claims) == 2
    # First claim: one source_ref -> one source_id
    assert claims[0].entity_type == "company"
    assert claims[0].field == "funding"
    assert claims[0].value == "Series A"
    assert claims[0].confidence == 0.95
    assert isinstance(claims[0].source_ids, list)
    assert len(claims[0].source_ids) == 1
    # source_ids are UUIDs (stored as str in JSONB)
    assert claims[0].source_ids[0] is not None

    # Second claim: two source_refs -> two source_ids
    assert claims[1].field == "name"
    assert claims[1].value == "Claims Co"
    assert len(claims[1].source_ids) == 2


def test_store_evidence_bundle_empty_bundles_returns_empty(db: Session) -> None:
    """store_evidence_bundle with empty list returns empty list."""
    records = store_evidence_bundle(
        db,
        run_id="run-empty",
        scout_version="scout-v1",
        bundles=[],
        run_context={"run_id": "run-empty"},
        raw_model_output=None,
    )
    assert records == []


def test_store_evidence_bundle_structured_payloads_length_mismatch_raises() -> None:
    """store_evidence_bundle raises ValueError when structured_payloads length != len(bundles)."""
    bundle = EvidenceBundle(
        candidate_company_name="Acme",
        company_website="https://acme.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://x.com", "s")],
    )
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="structured_payloads length must match bundles"):
        store_evidence_bundle(
            mock_db,
            run_id="r",
            scout_version="v1",
            bundles=[bundle],
            run_context=None,
            raw_model_output=None,
            structured_payloads=[],  # length 0 != 1
        )


def test_store_evidence_bundle_run_context_stored(db: Session) -> None:
    """run_context is stored on evidence_bundles row."""
    bundle = EvidenceBundle(
        candidate_company_name="Ctx Co",
        company_website="https://ctx.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://u.com", "s")],
    )
    run_context = {"run_id": "run-ctx", "workspace_id": "ws-1"}
    records = store_evidence_bundle(
        db,
        run_id="run-ctx",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context=run_context,
        raw_model_output=None,
    )
    assert len(records) == 1
    row = db.query(EvidenceBundleORM).filter(EvidenceBundleORM.id == records[0].id).first()
    assert row is not None
    assert row.run_context == run_context


def test_store_evidence_bundle_pack_id_and_raw_model_output_stored(
    db: Session, fractional_cto_pack_id
) -> None:
    """pack_id and raw_model_output are stored on evidence_bundles row when provided."""
    bundle = EvidenceBundle(
        candidate_company_name="Pack Co",
        company_website="https://pack.example.com",
        why_now_hypothesis="",
        evidence=[_make_item("https://u.com", "s")],
    )
    raw_output = {"raw": "model", "tokens": 100}
    records = store_evidence_bundle(
        db,
        run_id="run-pack",
        scout_version="scout-v1",
        bundles=[bundle],
        run_context={"run_id": "run-pack"},
        raw_model_output=raw_output,
        pack_id=fractional_cto_pack_id,
    )
    assert len(records) == 1
    row = db.query(EvidenceBundleORM).filter(EvidenceBundleORM.id == records[0].id).first()
    assert row is not None
    assert row.pack_id == fractional_cto_pack_id
    assert row.raw_model_output == raw_output
