"""Daily briefing pipeline — top-company selection + briefing generation."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.llm.router import ModelRole, get_llm_provider
from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.engagement_snapshot import EngagementSnapshot
from app.models.job_run import JobRun
from app.models.readiness_snapshot import ReadinessSnapshot
from app.models.signal_record import SignalRecord
from app.prompts.loader import render_prompt
from app.services.email_service import send_briefing_email
from app.services.esl.esl_engine import compute_outreach_score
from app.services.esl.esl_gate_filter import is_suppressed_from_engagement
from app.services.outreach import generate_outreach
from app.services.pack_resolver import (
    get_default_pack_id,
    get_pack_for_workspace,
    resolve_pack,
)
from app.services.settings_resolver import get_resolved_settings

logger = logging.getLogger(__name__)

# Companies must have activity within this window to be considered.
_ACTIVITY_WINDOW_DAYS = 14

# Companies that appeared in a briefing within this window are excluded.
_DEDUP_WINDOW_DAYS = 7


def select_top_companies(
    db: Session,
    limit: int = 5,
    workspace_id: str | None = None,
) -> list[Company]:
    """Select the top N companies for today's briefing.

    Criteria:
    1. Activity within 14 days (last_scan_at OR signal created_at).
    2. At least one AnalysisRecord (required for briefing generation).
    3. Sorted by cto_need_score descending (nulls last).
    4. Exclude companies with a BriefingItem in the last 7 days (workspace-scoped when workspace_id provided).

    Returns up to ``limit`` companies (default 5). Fewer may be returned if
    fewer qualify. No padding.
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    now = datetime.now(UTC)
    activity_cutoff = now - timedelta(days=_ACTIVITY_WINDOW_DAYS)
    dedup_cutoff = now - timedelta(days=_DEDUP_WINDOW_DAYS)

    # Sub-query: company IDs with at least one analysis (needed for briefing).
    companies_with_analysis = (
        db.query(AnalysisRecord.company_id).distinct().subquery()
    )

    # Sub-query: company IDs with a signal created recently.
    recent_signal_ids = (
        db.query(SignalRecord.company_id)
        .filter(SignalRecord.created_at >= activity_cutoff)
        .distinct()
        .subquery()
    )

    # Sub-query: company IDs already briefed in the dedup window.
    recently_briefed_q = (
        db.query(BriefingItem.company_id)
        .filter(BriefingItem.created_at >= dedup_cutoff)
    )
    default_ws_uuid = uuid.UUID(DEFAULT_WORKSPACE_ID)
    if workspace_id is not None:
        ws_uuid = (
            uuid.UUID(str(workspace_id)) if isinstance(workspace_id, str) else workspace_id
        )
        recently_briefed_q = recently_briefed_q.filter(
            BriefingItem.workspace_id == ws_uuid
        )
    else:
        recently_briefed_q = recently_briefed_q.filter(
            (BriefingItem.workspace_id == default_ws_uuid)
            | (BriefingItem.workspace_id.is_(None))
        )
    recently_briefed_ids = recently_briefed_q.distinct().subquery()

    companies = (
        db.query(Company)
        .filter(Company.id.in_(companies_with_analysis))
        .filter(
            (Company.last_scan_at >= activity_cutoff)
            | (Company.id.in_(recent_signal_ids))
        )
        .filter(~Company.id.in_(recently_briefed_ids))
        .order_by(Company.cto_need_score.desc().nullslast())
        .limit(limit)
        .all()
    )

    return companies


# Minimal view objects for lead_feed projection (Phase 3)
# Same interface as ReadinessSnapshot/EngagementSnapshot for briefing compatibility.
class _ReadinessView:
    def __init__(self, composite: int, top_reasons: list | None):
        self.composite = composite
        self.explain = {"top_events": top_reasons} if top_reasons else {}


class _EngagementView:
    def __init__(
        self,
        esl_score: float,
        engagement_type: str,
        cadence_blocked: bool,
        stability_cap_triggered: bool,
    ):
        self.esl_score = esl_score
        self.engagement_type = engagement_type
        self.cadence_blocked = cadence_blocked
        self.explain = (
            {"stability_cap_triggered": True} if stability_cap_triggered else {}
        )


def get_emerging_companies_from_lead_feed(
    db: Session,
    as_of: date,
    *,
    workspace_id: str = "00000000-0000-0000-0000-000000000001",
    limit: int = 5,
    outreach_score_threshold: int = 30,
    pack_id=None,
) -> list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]] | None:
    """Query emerging companies from lead_feed when populated (Phase 3).

    Returns None when lead_feed has no rows for this date (caller should fall back).
    Returns same structure as get_emerging_companies for briefing compatibility.
    """
    from uuid import UUID

    from app.services.lead_feed import get_emerging_companies_from_feed
    from app.services.lead_feed.query_service import feed_has_data

    if pack_id is None:
        pack_id = get_default_pack_id(db)
    if pack_id is None:
        return None

    ws_uuid = UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id
    pack_uuid = UUID(str(pack_id)) if isinstance(pack_id, str) else pack_id

    if not feed_has_data(db, ws_uuid, pack_uuid, as_of):
        return None

    result = get_emerging_companies_from_feed(
        db,
        as_of,
        workspace_id=ws_uuid,
        pack_id=pack_uuid,
        limit=limit,
        outreach_score_threshold=outreach_score_threshold,
    )
    # Return [] when feed has rows but all filtered out (distinct from None = feed empty)
    return result


def get_emerging_companies(
    db: Session,
    as_of: date,
    *,
    limit: int = 5,
    outreach_score_threshold: int = 30,
    pack_id=None,
    workspace_id: str | None = None,
) -> list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]]:
    """Query top N companies by OutreachScore for a date (Issue #102, #103, #189).

    Ranking contract (Issue #103): OutreachScore = round(TRS × ESL), 0–100.
    Companies are ranked by OutreachScore descending; threshold filter applied.
    Pack-scoped: only returns data for the given pack (Issue #189).

    Dual-path (Phase 4, Issue #225): Prefers lead_feed when populated for
    workspace/pack/as_of; falls back to join query when feed empty.

    Note: Pack minimum_threshold (R >= min) is not yet enforced here.
    See docs/MINIMUM_THRESHOLD_ENFORCEMENT.md for enforcement plan.
    """
    from app.pipeline.stages import DEFAULT_WORKSPACE_ID
    from app.services.lead_feed import get_emerging_companies_from_feed
    from app.services.pack_resolver import get_pack_for_workspace

    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    resolved_pack = pack_id or get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    if resolved_pack is None:
        return []

    # Phase 4: Prefer lead_feed when populated (Issue #225)
    feed_result = get_emerging_companies_from_feed(
        db,
        as_of,
        workspace_id=ws_id,
        pack_id=resolved_pack,
        limit=limit,
        outreach_score_threshold=outreach_score_threshold,
    )
    if feed_result:
        return feed_result

    pack_id = resolved_pack

    # Fallback: legacy join query
    # Treat pack_id IS NULL as default pack until backfill completes (Issue #189)
    pack_match = or_(
        ReadinessSnapshot.pack_id == EngagementSnapshot.pack_id,
        (ReadinessSnapshot.pack_id.is_(None)) & (EngagementSnapshot.pack_id.is_(None)),
    )
    pack_filter = or_(
        ReadinessSnapshot.pack_id == pack_id,
        ReadinessSnapshot.pack_id.is_(None),
    )
    pairs = (
        db.query(ReadinessSnapshot, EngagementSnapshot)
        .join(EngagementSnapshot, (ReadinessSnapshot.company_id == EngagementSnapshot.company_id) & (ReadinessSnapshot.as_of == EngagementSnapshot.as_of) & pack_match)
        .options(joinedload(ReadinessSnapshot.company))
        .filter(ReadinessSnapshot.as_of == as_of, pack_filter)
        .all()
    )
    results: list[tuple[ReadinessSnapshot, EngagementSnapshot, Company]] = []
    for rs, es in pairs:
        if not rs.company:
            continue
        # Exclude suppressed entities (Issue #175, Phase 3; Phase 4: prefer column)
        if is_suppressed_from_engagement(es.esl_decision, es.explain):
            continue
        outreach_score = compute_outreach_score(rs.composite, es.esl_score)
        # Include cadence_blocked companies (Observe Only) even when outreach_score < threshold
        if outreach_score < outreach_score_threshold and not es.cadence_blocked:
            continue
        results.append((rs, es, rs.company))

    # Rank by OutreachScore = round(TRS × ESL) descending (Issue #103)
    results.sort(key=lambda r: compute_outreach_score(r[0].composite, r[1].esl_score), reverse=True)
    return results[:limit]


def get_emerging_companies_for_briefing(
    db: Session,
    as_of: date,
    *,
    limit: int = 5,
    outreach_score_threshold: int = 30,
    pack_id=None,
    workspace_id: str | None = None,
) -> list[tuple[ReadinessSnapshot | _ReadinessView, EngagementSnapshot | _EngagementView, Company]]:
    """Get emerging companies for briefing: read from lead_feed when populated, else fallback (Phase 3)."""
    return get_emerging_companies(
        db,
        as_of,
        limit=limit,
        outreach_score_threshold=outreach_score_threshold,
        pack_id=pack_id,
        workspace_id=workspace_id,
    )


def _parse_json_safe(text: str) -> dict | None:
    """Try to parse *text* as JSON.  Return ``None`` on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def generate_briefing(
    db: Session,
    workspace_id: str | None = None,
) -> list[BriefingItem]:
    """Generate today's briefing for the top companies.

    For each selected company:
    1. Fetch the latest AnalysisRecord.
    2. Call the LLM with ``briefing_entry_v1`` to get why_now / risk / angle.
    3. Call ``generate_outreach()`` for the outreach draft.
    4. Persist a ``BriefingItem``.

    One company failing does **not** stop the whole run.

    Creates a JobRun record (issue #27) to track start, finish, and errors.
    Sends briefing email when enabled (issue #29).

    When workspace_id is provided, BriefingItems are scoped to that workspace.
    When None, uses default workspace (single-tenant mode).
    """
    from uuid import UUID

    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    ws_uuid = UUID(ws_id) if isinstance(ws_id, str) else ws_id
    pack_id = get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    job = JobRun(
        job_type="briefing",
        status="running",
        workspace_id=ws_uuid,
        pack_id=pack_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        resolved = get_resolved_settings(db)

        # Weekly frequency: skip if today is not the configured day
        if resolved.briefing_frequency == "weekly":
            today_weekday = date.today().weekday()  # 0=Monday, 6=Sunday
            if today_weekday != resolved.briefing_day_of_week:
                logger.info(
                    "Briefing skipped: weekly frequency, today weekday=%s != configured=%s",
                    today_weekday,
                    resolved.briefing_day_of_week,
                )
                job.finished_at = datetime.now(UTC)
                job.status = "completed"
                job.companies_processed = 0
                job.error_message = None
                db.commit()
                return []

        companies = select_top_companies(db, workspace_id=ws_id)
        items: list[BriefingItem] = []
        errors: list[str] = []

        for company in companies:
            try:
                item = _generate_for_company(db, company, workspace_id=ws_id)
                if item is not None:
                    items.append(item)
            except Exception as exc:
                msg = f"Company {company.id} ({company.name}): {exc}"
                logger.exception(
                    "Briefing generation failed for company %s (id=%s)",
                    company.name,
                    company.id,
                )
                errors.append(msg)

        job.finished_at = datetime.now(UTC)
        job.status = "completed"
        job.companies_processed = len(items)
        job.error_message = "; ".join(errors) if errors else None
        db.commit()

        # Send briefing email when enabled (issue #29, #32)
        failure_summary = job.error_message[:2000] if job.error_message else None
        if resolved.should_send_briefing_email():
            if items:
                _items_with_company = (
                    db.query(BriefingItem)
                    .options(joinedload(BriefingItem.company))
                    .filter(BriefingItem.id.in_([i.id for i in items]))
                    .all()
                )
                try:
                    ok = send_briefing_email(
                        _items_with_company,
                        resolved.briefing_email_recipient,
                        settings=resolved,
                        failure_summary=failure_summary,
                    )
                    if not ok:
                        logger.warning("Briefing email send returned False")
                except Exception:
                    logger.exception("Briefing email send failed (job still completed)")
            elif failure_summary:
                # All companies failed: send failure-only alert (issue #32)
                try:
                    ok = send_briefing_email(
                        [],
                        resolved.briefing_email_recipient,
                        settings=resolved,
                        failure_summary=failure_summary,
                    )
                    if not ok:
                        logger.warning("Briefing failure email send returned False")
                except Exception:
                    logger.exception("Briefing failure email send failed")

        return items

    except Exception as exc:
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        raise


def _generate_for_company(
    db: Session,
    company: Company,
    workspace_id: str | None = None,
) -> BriefingItem | None:
    """Build a single BriefingItem for *company*.  Returns ``None`` when skipped."""
    from uuid import UUID

    from app.pipeline.stages import DEFAULT_WORKSPACE_ID

    today = date.today()
    ws_id = workspace_id or DEFAULT_WORKSPACE_ID
    ws_uuid = UUID(str(ws_id)) if isinstance(ws_id, str) else ws_id
    default_uuid = UUID(DEFAULT_WORKSPACE_ID)

    existing_q = db.query(BriefingItem).filter(
        BriefingItem.company_id == company.id,
        BriefingItem.briefing_date == today,
    )
    if ws_uuid == default_uuid:
        existing_q = existing_q.filter(
            (BriefingItem.workspace_id == ws_uuid)
            | (BriefingItem.workspace_id.is_(None))
        )
    else:
        existing_q = existing_q.filter(BriefingItem.workspace_id == ws_uuid)
    existing = existing_q.first()
    if existing:
        logger.info(
            "BriefingItem already exists for %s (id=%s) on %s — skipping",
            company.name,
            company.id,
            today,
        )
        return None

    # Latest analysis record (pack-scoped: prefer workspace's active pack).
    pack_id = get_pack_for_workspace(db, ws_id) or get_default_pack_id(db)
    default_pack_id = get_default_pack_id(db)
    analysis_q = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company.id)
        .order_by(AnalysisRecord.created_at.desc())
    )
    if pack_id is not None and default_pack_id is not None:
        from sqlalchemy import or_

        analysis_q = analysis_q.filter(
            or_(
                AnalysisRecord.pack_id == pack_id,
                (AnalysisRecord.pack_id.is_(None)) & (pack_id == default_pack_id),
            )
        )
    analysis: AnalysisRecord | None = analysis_q.first()
    if analysis is None:
        logger.info("No analysis for company %s — skipping briefing", company.name)
        return None

    pain = analysis.pain_signals_json or {}
    evidence_bullets = analysis.evidence_bullets or []
    evidence_text = "\n".join(f"- {b}" for b in evidence_bullets) if evidence_bullets else ""

    prompt = render_prompt(
        "briefing_entry_v1",
        COMPANY_NAME=company.name or "",
        FOUNDER_NAME=company.founder_name or "",
        WEBSITE_URL=company.website_url or "",
        STAGE=analysis.stage or "",
        STAGE_CONFIDENCE=str(analysis.stage_confidence or 0),
        PAIN_SIGNALS_JSON=json.dumps(pain, indent=2),
        EVIDENCE_BULLETS=evidence_text,
    )

    llm = get_llm_provider(role=ModelRole.JSON)
    raw = llm.complete(
        prompt,
        response_format={"type": "json_object"},
        temperature=0.5,
    )

    parsed = _parse_json_safe(raw)
    why_now = parsed.get("why_now", "") if parsed else ""
    risk_summary = parsed.get("risk_summary", "") if parsed else ""
    suggested_angle = parsed.get("suggested_angle", "") if parsed else ""

    # Outreach draft (Phase 3: pass pack for offer_type from workspace's active pack).
    pack = resolve_pack(db, pack_id) if pack_id else None
    outreach = generate_outreach(db, company, analysis, pack=pack)
    item = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
        workspace_id=ws_uuid,
        why_now=why_now,
        risk_summary=risk_summary,
        suggested_angle=suggested_angle,
        outreach_subject=outreach.get("subject", ""),
        outreach_message=outreach.get("message", ""),
        briefing_date=today,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

