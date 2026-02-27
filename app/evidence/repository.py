"""Evidence Repository read interface (M4, Issue #276). Read-only; no pack logic or derivation.

Workspace/tenant contract:
    This layer does NOT enforce workspace_id or tenant boundaries. Evidence bundles
    are keyed by id and run_context (e.g. run_id); there is no workspace_id column.
    Any API or caller that exposes get_bundle(bundle_id) or list_bundles_by_run(run_id)
    MUST ensure the caller is only allowed to request runs/bundles for their workspace
    (e.g. resolve run_id from a workspace-scoped scout run, or verify
    EvidenceBundleRead.run_context after get_bundle). Failure to enforce in the
    calling layer can allow cross-tenant data access.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.evidence_bundle import EvidenceBundle
from app.models.evidence_bundle_source import EvidenceBundleSource
from app.models.evidence_claim import EvidenceClaim
from app.models.evidence_source import EvidenceSource
from app.schemas.evidence import (
    EvidenceBundleRead,
    EvidenceClaimRead,
    EvidenceSourceRead,
)


def get_bundle(db: Session, bundle_id: uuid.UUID) -> EvidenceBundleRead | None:
    """Return one evidence bundle by id, or None if not found.

    Caller must enforce workspace/tenant: this function does not filter by workspace.
    """
    row = db.query(EvidenceBundle).filter(EvidenceBundle.id == bundle_id).first()
    if row is None:
        return None
    return _row_to_bundle_read(row)


def list_bundles_by_run(db: Session, run_id: str) -> list[EvidenceBundleRead]:
    """Return all evidence bundles whose run_context.run_id equals run_id.

    Caller must enforce workspace/tenant: only pass run_id for runs the caller
    is allowed to see (e.g. runs belonging to the current workspace).
    """
    rows = (
        db.query(EvidenceBundle)
        .filter(EvidenceBundle.run_context["run_id"].astext == run_id)
        .order_by(EvidenceBundle.created_at.asc())
        .all()
    )
    return [_row_to_bundle_read(r) for r in rows]


def list_sources_for_bundle(db: Session, bundle_id: uuid.UUID) -> list[EvidenceSourceRead]:
    """Return all evidence sources linked to the given bundle (via evidence_bundle_sources)."""
    rows = (
        db.query(EvidenceSource)
        .join(EvidenceBundleSource, EvidenceBundleSource.source_id == EvidenceSource.id)
        .filter(EvidenceBundleSource.bundle_id == bundle_id)
        .order_by(EvidenceBundleSource.source_id.asc())
        .all()
    )
    return [_row_to_source_read(r) for r in rows]


def list_claims_for_bundle(db: Session, bundle_id: uuid.UUID) -> list[EvidenceClaimRead]:
    """Return all evidence claims for the given bundle."""
    rows = (
        db.query(EvidenceClaim)
        .filter(EvidenceClaim.bundle_id == bundle_id)
        .order_by(EvidenceClaim.id.asc())
        .all()
    )
    return [_row_to_claim_read(r) for r in rows]


def _row_to_bundle_read(row: EvidenceBundle) -> EvidenceBundleRead:
    return EvidenceBundleRead(
        id=row.id,
        created_at=row.created_at,
        scout_version=row.scout_version,
        core_taxonomy_version=row.core_taxonomy_version,
        core_derivers_version=row.core_derivers_version,
        pack_id=row.pack_id,
        run_context=row.run_context,
        raw_model_output=row.raw_model_output,
        structured_payload=row.structured_payload,
    )


def _row_to_source_read(row: EvidenceSource) -> EvidenceSourceRead:
    return EvidenceSourceRead(
        id=row.id,
        url=row.url,
        retrieved_at=row.retrieved_at,
        snippet=row.snippet,
        content_hash=row.content_hash,
        source_type=row.source_type,
    )


def _row_to_claim_read(row: EvidenceClaim) -> EvidenceClaimRead:
    source_ids: list[str] | None = None
    if row.source_ids is not None and isinstance(row.source_ids, list):
        source_ids = [str(x) for x in row.source_ids]
    return EvidenceClaimRead(
        id=row.id,
        bundle_id=row.bundle_id,
        entity_type=row.entity_type,
        field=row.field,
        value=row.value,
        source_ids=source_ids,
        confidence=row.confidence,
    )
