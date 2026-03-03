"""Evidence Repository read interface (M4, Issue #276). Read-only; no pack logic or derivation.

Workspace/tenant contract:
    This layer does NOT enforce workspace_id or tenant boundaries for get_bundle()
    or list_bundles_by_run(). Evidence bundles are keyed by id and run_context
    (e.g. run_id); there is no workspace_id column.
    - For bundle-by-id: use get_bundle_for_workspace(db, bundle_id, workspace_id)
      so the bundle is returned only if its run belongs to that workspace. Any API
      that exposes bundle-by-id must use this (or equivalent) to avoid cross-tenant
      data access.
    - For list by run: use list_bundles_by_run_for_workspace(db, run_id, workspace_id).
    - get_bundle() does not filter by workspace; callers must enforce if used directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.evidence_bundle import EvidenceBundle
from app.models.evidence_bundle_source import EvidenceBundleSource
from app.models.evidence_claim import EvidenceClaim
from app.models.evidence_source import EvidenceSource
from app.models.scout_run import ScoutRun
from app.schemas.evidence import (
    EvidenceBundleRead,
    EvidenceClaimRead,
    EvidenceSourceRead,
)


def get_bundle(db: Session, bundle_id: uuid.UUID) -> EvidenceBundleRead | None:
    """Return one evidence bundle by id, or None if not found.

    Caller must enforce workspace/tenant: this function does not filter by workspace.
    For workspace-scoped access, use get_bundle_for_workspace() so the bundle is only
    returned if its run belongs to the given workspace_id.
    """
    row = db.query(EvidenceBundle).filter(EvidenceBundle.id == bundle_id).first()
    if row is None:
        return None
    return _row_to_bundle_read(row)


def get_bundle_for_workspace(
    db: Session, bundle_id: uuid.UUID, workspace_id: uuid.UUID
) -> EvidenceBundleRead | None:
    """Return an evidence bundle by id only if its run belongs to the given workspace.

    Resolves run_id from the bundle's run_context, checks ScoutRun for
    (run_id, workspace_id), and returns the bundle only when the run belongs to
    that workspace. Returns None if the bundle does not exist, run_context has no
    run_id, or the run belongs to another workspace (no cross-tenant leak).

    Use this (not get_bundle) when exposing bundle-by-id in any API that must
    enforce tenant boundaries.
    """
    row = db.query(EvidenceBundle).filter(EvidenceBundle.id == bundle_id).first()
    if row is None:
        return None
    run_context = row.run_context
    if not isinstance(run_context, dict):
        return None
    run_id_raw = run_context.get("run_id")
    if not run_id_raw:
        return None
    try:
        run_uuid = uuid.UUID(str(run_id_raw))
    except (ValueError, TypeError):
        return None
    run_row = (
        db.query(ScoutRun)
        .filter(
            ScoutRun.run_id == run_uuid,
            ScoutRun.workspace_id == workspace_id,
        )
        .first()
    )
    if run_row is None:
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


def list_bundles_by_run_for_workspace(
    db: Session, run_id: str, workspace_id: uuid.UUID
) -> list[EvidenceBundleRead]:
    """Return evidence bundles for run_id only if the run belongs to workspace_id.

    Checks scout_runs for (run_id, workspace_id) before calling list_bundles_by_run.
    Returns [] if the run does not exist or belongs to another workspace (no leak).
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except (ValueError, TypeError):
        return []
    run_row = (
        db.query(ScoutRun)
        .filter(
            ScoutRun.run_id == run_uuid,
            ScoutRun.workspace_id == workspace_id,
        )
        .first()
    )
    if run_row is None:
        return []
    return list_bundles_by_run(db, run_id)


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
