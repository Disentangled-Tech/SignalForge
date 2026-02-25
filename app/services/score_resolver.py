"""Pack-scoped score resolution (Phase 2, Plan Step 3; Phase 3 workspace-scoped).

Resolution order: ReadinessSnapshot (pack_id match) > Company.cto_need_score
when pack is default (backward compat). Used by briefing, company list, detail.
When workspace_id provided, pack is resolved from workspace's active pack.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.readiness_snapshot import ReadinessSnapshot
from app.services.pack_resolver import get_default_pack_id, get_pack_for_workspace


def get_company_score(
    db: Session,
    company_id: int,
    pack_id: UUID | str | None = None,
    workspace_id: str | UUID | None = None,
) -> int | None:
    """Resolve display score for a company (pack-scoped).

    Resolution order:
    1. Latest ReadinessSnapshot for company where pack_id matches (or NULL when pack is default).
    2. Company.cto_need_score when pack is default (backward compat).

    When workspace_id is provided, pack is resolved from workspace's active pack.
    When pack_id is explicitly provided, it overrides workspace resolution.

    Parameters
    ----------
    db : Session
        Active database session.
    company_id : int
        Company to resolve score for.
    pack_id : UUID | str | None
        Pack to use. When None, resolved from workspace_id or default pack.
    workspace_id : str | UUID | None
        When provided, resolves pack via get_pack_for_workspace (Phase 3).

    Returns
    -------
    int | None
        Composite score (0-100) or cto_need_score fallback; None when no data.
    """
    pack_uuid: UUID | None = None
    if pack_id is not None:
        pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    elif workspace_id is not None:
        pack_uuid = get_pack_for_workspace(db, workspace_id)
    if pack_uuid is None:
        pack_uuid = get_default_pack_id(db)

    # 1. Try ReadinessSnapshot: pack_id match or NULL (legacy) when querying for default
    default_pack_uuid = get_default_pack_id(db)
    pack_filter = (
        or_(
            ReadinessSnapshot.pack_id == pack_uuid,
            (ReadinessSnapshot.pack_id.is_(None)) & (pack_uuid == default_pack_uuid),
        )
        if pack_uuid is not None and default_pack_uuid is not None
        else (ReadinessSnapshot.pack_id == pack_uuid if pack_uuid is not None else ReadinessSnapshot.pack_id.is_(None))
    )
    snapshot = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id == company_id,
            pack_filter,
        )
        .order_by(ReadinessSnapshot.as_of.desc())
        .first()
    )
    if snapshot is not None:
        return snapshot.composite

    # 2. Fallback to Company.cto_need_score when pack is default (backward compat)
    is_default_pack = pack_uuid is None or pack_uuid == get_default_pack_id(db)
    if is_default_pack:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is not None and company.cto_need_score is not None:
            return company.cto_need_score

    return None


def get_company_scores_batch(
    db: Session,
    company_ids: list[int],
    pack_id: UUID | str | None = None,
    workspace_id: str | UUID | None = None,
) -> dict[int, int]:
    """Resolve display scores for multiple companies (batched, avoids N+1).

    Same resolution order as get_company_score: ReadinessSnapshot first,
    then Company.cto_need_score when pack is default. Uses 2–3 queries
    total instead of 2–3 per company. When workspace_id provided, pack
    resolved from workspace's active pack (Phase 3).
    """
    if not company_ids:
        return {}

    pack_uuid: UUID | None = None
    if pack_id is not None:
        pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id
    elif workspace_id is not None:
        pack_uuid = get_pack_for_workspace(db, workspace_id)
    if pack_uuid is None:
        pack_uuid = get_default_pack_id(db)

    default_pack_uuid = get_default_pack_id(db)
    pack_filter = (
        or_(
            ReadinessSnapshot.pack_id == pack_uuid,
            (ReadinessSnapshot.pack_id.is_(None)) & (pack_uuid == default_pack_uuid),
        )
        if pack_uuid is not None and default_pack_uuid is not None
        else (
            ReadinessSnapshot.pack_id == pack_uuid
            if pack_uuid is not None
            else ReadinessSnapshot.pack_id.is_(None)
        )
    )

    # 1. Batch fetch ReadinessSnapshots; keep latest (max as_of) per company
    snapshots = (
        db.query(ReadinessSnapshot)
        .filter(
            ReadinessSnapshot.company_id.in_(company_ids),
            pack_filter,
        )
        .order_by(ReadinessSnapshot.company_id, ReadinessSnapshot.as_of.desc())
        .all()
    )
    latest_by_company: dict[int, ReadinessSnapshot] = {}
    for s in snapshots:
        if s.company_id not in latest_by_company:
            latest_by_company[s.company_id] = s

    result: dict[int, int] = {
        cid: latest_by_company[cid].composite
        for cid in company_ids
        if cid in latest_by_company
    }

    # 2. Fallback: batch fetch Company.cto_need_score for companies without snapshot
    missing = [cid for cid in company_ids if cid not in result]
    is_default_pack = pack_uuid is None or pack_uuid == default_pack_uuid
    if missing and is_default_pack:
        companies = (
            db.query(Company)
            .filter(Company.id.in_(missing), Company.cto_need_score.isnot(None))
            .all()
        )
        for c in companies:
            if c.cto_need_score is not None:
                result[c.id] = c.cto_need_score

    return result
