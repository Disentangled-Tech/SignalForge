"""Weekly outreach review service (Issue #108).

Returns top OutreachScore companies for weekly review, excluding cooldown companies.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models.company import Company
from app.models.engagement_snapshot import EngagementSnapshot
from app.models.readiness_snapshot import ReadinessSnapshot
from app.services.esl.esl_engine import compute_outreach_score
from app.services.outreach_history import check_outreach_cooldown


def get_latest_snapshot_date(db: Session) -> date | None:
    """Return the most recent as_of date with engagement snapshots, or None."""
    row = (
        db.query(EngagementSnapshot.as_of)
        .order_by(EngagementSnapshot.as_of.desc())
        .limit(1)
        .first()
    )
    return row[0] if row else None


def get_weekly_review_companies(
    db: Session,
    as_of: date,
    *,
    limit: int = 5,
    outreach_score_threshold: int = 30,
) -> list[dict]:
    """Query top N companies by OutreachScore for weekly review (Issue #108).

    Excludes companies in cooldown (60-day or 180-day declined per Issue #109).
    Returns list of dicts with company, outreach_score, and merged explain block.

    Args:
        db: Database session.
        as_of: Snapshot date to query.
        limit: Max companies to return (weekly_review_limit).
        outreach_score_threshold: Min OutreachScore to include.

    Returns:
        List of dicts: {company_id, company, readiness_snapshot, engagement_snapshot,
        outreach_score, explain}. Sorted by OutreachScore DESC. No duplicates.
    """
    as_of_dt = datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)

    pairs = (
        db.query(ReadinessSnapshot, EngagementSnapshot)
        .join(
            EngagementSnapshot,
            (ReadinessSnapshot.company_id == EngagementSnapshot.company_id)
            & (ReadinessSnapshot.as_of == EngagementSnapshot.as_of),
        )
        .options(joinedload(ReadinessSnapshot.company))
        .filter(ReadinessSnapshot.as_of == as_of)
        .all()
    )

    candidates: list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]] = []
    for rs, es in pairs:
        if not rs.company:
            continue
        outreach_score = es.outreach_score
        if outreach_score is None:
            outreach_score = compute_outreach_score(rs.composite, es.esl_score)
        if outreach_score < outreach_score_threshold:
            continue
        candidates.append((rs, es, rs.company))

    # Rank by OutreachScore descending
    def _score(c: tuple) -> int:
        rs, es = c[0], c[1]
        return es.outreach_score if es.outreach_score is not None else compute_outreach_score(rs.composite, es.esl_score)

    candidates.sort(key=_score, reverse=True)

    results: list[dict] = []
    for rs, es, company in candidates:
        if len(results) >= limit:
            break
        cooldown = check_outreach_cooldown(db, company.id, as_of_dt)
        if not cooldown.allowed:
            continue
        outreach_score = es.outreach_score if es.outreach_score is not None else compute_outreach_score(rs.composite, es.esl_score)
        explain = _merge_explain(rs.explain, es.explain)
        results.append({
            "company_id": company.id,
            "company": company,
            "readiness_snapshot": rs,
            "engagement_snapshot": es,
            "outreach_score": outreach_score,
            "explain": explain,
        })
    return results


def _merge_explain(
    readiness_explain: dict | None,
    engagement_explain: dict | None,
) -> dict:
    """Merge readiness and engagement explain blocks into one."""
    out: dict = {}
    if readiness_explain:
        out["readiness"] = readiness_explain
    if engagement_explain:
        out["engagement"] = engagement_explain
    return out if out else {}
