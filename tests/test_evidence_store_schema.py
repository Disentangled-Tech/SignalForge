"""Tests for evidence store schema (M2, Issue #276).

Covers: evidence_bundles, evidence_sources, evidence_bundle_sources,
evidence_claims, evidence_quarantine — table creation, constraints, relationships.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import (
    EvidenceBundle,
    EvidenceBundleSource,
    EvidenceClaim,
    EvidenceQuarantine,
    EvidenceSource,
)


def test_evidence_bundle_model_has_expected_table_and_columns() -> None:
    """EvidenceBundle maps to evidence_bundles with required columns."""
    assert EvidenceBundle.__tablename__ == "evidence_bundles"
    assert hasattr(EvidenceBundle, "id")
    assert hasattr(EvidenceBundle, "scout_version")
    assert hasattr(EvidenceBundle, "core_taxonomy_version")
    assert hasattr(EvidenceBundle, "core_derivers_version")
    assert hasattr(EvidenceBundle, "pack_id")
    assert hasattr(EvidenceBundle, "run_context")
    assert hasattr(EvidenceBundle, "raw_model_output")
    assert hasattr(EvidenceBundle, "structured_payload")
    assert hasattr(EvidenceBundle, "created_at")
    assert not hasattr(EvidenceBundle, "updated_at")


def test_evidence_source_model_has_expected_table_and_columns() -> None:
    """EvidenceSource maps to evidence_sources with content_hash and url."""
    assert EvidenceSource.__tablename__ == "evidence_sources"
    assert hasattr(EvidenceSource, "id")
    assert hasattr(EvidenceSource, "url")
    assert hasattr(EvidenceSource, "retrieved_at")
    assert hasattr(EvidenceSource, "snippet")
    assert hasattr(EvidenceSource, "content_hash")
    assert hasattr(EvidenceSource, "source_type")


def test_evidence_claim_model_has_expected_table_and_columns() -> None:
    """EvidenceClaim maps to evidence_claims with bundle_id and source_ids."""
    assert EvidenceClaim.__tablename__ == "evidence_claims"
    assert hasattr(EvidenceClaim, "id")
    assert hasattr(EvidenceClaim, "bundle_id")
    assert hasattr(EvidenceClaim, "entity_type")
    assert hasattr(EvidenceClaim, "field")
    assert hasattr(EvidenceClaim, "value")
    assert hasattr(EvidenceClaim, "source_ids")
    assert hasattr(EvidenceClaim, "confidence")


def test_evidence_quarantine_model_has_expected_table_and_columns() -> None:
    """EvidenceQuarantine maps to evidence_quarantine with payload and reason."""
    assert EvidenceQuarantine.__tablename__ == "evidence_quarantine"
    assert hasattr(EvidenceQuarantine, "id")
    assert hasattr(EvidenceQuarantine, "payload")
    assert hasattr(EvidenceQuarantine, "reason")
    assert hasattr(EvidenceQuarantine, "created_at")


def test_evidence_bundle_source_join_table_has_composite_pk() -> None:
    """EvidenceBundleSource is the join table with (bundle_id, source_id) PK."""
    assert EvidenceBundleSource.__tablename__ == "evidence_bundle_sources"
    assert hasattr(EvidenceBundleSource, "bundle_id")
    assert hasattr(EvidenceBundleSource, "source_id")


def test_evidence_bundle_insert_and_relationship_to_sources(
    db: Session,
) -> None:
    """Insert bundle and source, link via join table; assert relationship loads."""
    bundle = EvidenceBundle(
        scout_version="test-scout-1",
        core_taxonomy_version="tax-v1",
        core_derivers_version="deriv-v1",
        run_context={"run_id": str(uuid.uuid4())},
    )
    db.add(bundle)
    db.flush()

    source = EvidenceSource(
        url="https://example.com/page",
        content_hash="a" * 64,
        source_type="web",
    )
    db.add(source)
    db.flush()

    link = EvidenceBundleSource(bundle_id=bundle.id, source_id=source.id)
    db.add(link)
    db.flush()

    db.refresh(bundle)
    assert len(bundle.sources) == 1
    assert bundle.sources[0].source_id == source.id
    assert bundle.sources[0].source.url == "https://example.com/page"


def test_evidence_bundle_claims_relationship(db: Session) -> None:
    """Insert bundle and claim; assert claims relationship and source_ids JSONB."""
    bundle = EvidenceBundle(
        scout_version="scout-1",
        core_taxonomy_version="tax-v1",
        core_derivers_version="deriv-v1",
    )
    db.add(bundle)
    db.flush()

    source_id_list = [str(uuid.uuid4())]
    claim = EvidenceClaim(
        bundle_id=bundle.id,
        entity_type="company",
        field="name",
        value="Acme Inc",
        source_ids=source_id_list,
        confidence=0.9,
    )
    db.add(claim)
    db.flush()

    db.refresh(bundle)
    assert len(bundle.claims) == 1
    assert bundle.claims[0].value == "Acme Inc"
    assert bundle.claims[0].source_ids == source_id_list


def test_evidence_quarantine_insert(db: Session) -> None:
    """Insert quarantine row with payload and reason; no FK to bundles."""
    row = EvidenceQuarantine(
        payload={"rejected": True, "run_id": str(uuid.uuid4())},
        reason="Validation failed: missing url",
    )
    db.add(row)
    db.flush()
    assert row.id is not None
    assert row.created_at is not None


def test_evidence_sources_unique_content_hash_url(db: Session) -> None:
    """Duplicate (content_hash, url) raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    url = "https://example.com/dup"
    content_hash = "b" * 64
    db.add(
        EvidenceSource(
            url=url,
            content_hash=content_hash,
            source_type="web",
        )
    )
    db.flush()

    duplicate = EvidenceSource(
        url=url,
        content_hash=content_hash,
        source_type="web",
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()


def test_evidence_bundles_trigger_rejects_update_and_delete(db: Session) -> None:
    """M5: DB trigger rejects UPDATE and DELETE on evidence_bundles (immutability)."""
    from sqlalchemy.exc import InternalError, ProgrammingError

    from app.core_derivers.loader import get_core_derivers_version
    from app.core_taxonomy.loader import get_core_taxonomy_version

    bundle = EvidenceBundle(
        scout_version="v1",
        core_taxonomy_version=get_core_taxonomy_version(),
        core_derivers_version=get_core_derivers_version(),
        run_context={"run_id": "trigger-test"},
    )
    db.add(bundle)
    db.flush()
    bundle_id = bundle.id

    # Trigger rejects UPDATE
    row = db.query(EvidenceBundle).filter(EvidenceBundle.id == bundle_id).first()
    assert row is not None
    row.scout_version = "v2"
    with pytest.raises((InternalError, ProgrammingError)) as exc_info:
        db.flush()
    assert "immutable" in str(exc_info.value).lower() or "updates not allowed" in str(
        exc_info.value
    )
    db.rollback()

    # Re-insert bundle and verify trigger rejects DELETE
    bundle2 = EvidenceBundle(
        scout_version="v1",
        core_taxonomy_version=get_core_taxonomy_version(),
        core_derivers_version=get_core_derivers_version(),
        run_context={"run_id": "trigger-test-2"},
    )
    db.add(bundle2)
    db.flush()
    row2 = db.query(EvidenceBundle).filter(EvidenceBundle.id == bundle2.id).first()
    assert row2 is not None
    db.delete(row2)
    with pytest.raises((InternalError, ProgrammingError)) as exc_info2:
        db.flush()
    assert "immutable" in str(exc_info2.value).lower() or "deletes not allowed" in str(
        exc_info2.value
    )
