"""Daily briefing pipeline — top-company selection + briefing generation."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from app.llm.router import ModelRole, get_llm_provider
from app.models.analysis_record import AnalysisRecord
from app.models.briefing_item import BriefingItem
from app.models.company import Company
from app.models.job_run import JobRun
from app.models.readiness_snapshot import ReadinessSnapshot
from app.models.signal_record import SignalRecord
from app.prompts.loader import render_prompt
from app.services.email_service import send_briefing_email
from app.services.outreach import generate_outreach
from app.services.settings_resolver import get_resolved_settings

logger = logging.getLogger(__name__)

# Companies must have activity within this window to be considered.
_ACTIVITY_WINDOW_DAYS = 14

# Companies that appeared in a briefing within this window are excluded.
_DEDUP_WINDOW_DAYS = 7


def select_top_companies(db: Session, limit: int = 5) -> list[Company]:
    """Select the top N companies for today's briefing.

    Criteria:
    1. Activity within 14 days (last_scan_at OR signal created_at).
    2. At least one AnalysisRecord (required for briefing generation).
    3. Sorted by cto_need_score descending (nulls last).
    4. Exclude companies with a BriefingItem in the last 7 days.

    Returns up to ``limit`` companies (default 5). Fewer may be returned if
    fewer qualify. No padding.
    """
    now = datetime.now(timezone.utc)
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
    recently_briefed_ids = (
        db.query(BriefingItem.company_id)
        .filter(BriefingItem.created_at >= dedup_cutoff)
        .distinct()
        .subquery()
    )

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


def get_emerging_companies(
    db: Session,
    as_of: date,
    limit: int = 10,
    threshold: int = 60,
) -> list[tuple[ReadinessSnapshot, Company]]:
    """Query top N companies by readiness composite for a date (Issue #93).

    Returns (snapshot, company) pairs for companies with composite >= threshold,
    sorted by composite descending. Uses readiness_snapshots.
    """
    snapshots = (
        db.query(ReadinessSnapshot)
        .options(joinedload(ReadinessSnapshot.company))
        .filter(ReadinessSnapshot.as_of == as_of)
        .filter(ReadinessSnapshot.composite >= threshold)
        .order_by(ReadinessSnapshot.composite.desc())
        .limit(limit)
        .all()
    )
    return [(s, s.company) for s in snapshots if s.company]


def _parse_json_safe(text: str) -> dict | None:
    """Try to parse *text* as JSON.  Return ``None`` on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def generate_briefing(db: Session) -> list[BriefingItem]:
    """Generate today's briefing for the top companies.

    For each selected company:
    1. Fetch the latest AnalysisRecord.
    2. Call the LLM with ``briefing_entry_v1`` to get why_now / risk / angle.
    3. Call ``generate_outreach()`` for the outreach draft.
    4. Persist a ``BriefingItem``.

    One company failing does **not** stop the whole run.

    Creates a JobRun record (issue #27) to track start, finish, and errors.
    Sends briefing email when enabled (issue #29).
    """
    job = JobRun(job_type="briefing", status="running")
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
                job.finished_at = datetime.now(timezone.utc)
                job.status = "completed"
                job.companies_processed = 0
                job.error_message = None
                db.commit()
                return []

        companies = select_top_companies(db)
        items: list[BriefingItem] = []
        errors: list[str] = []

        for company in companies:
            try:
                item = _generate_for_company(db, company)
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

        job.finished_at = datetime.now(timezone.utc)
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
        job.finished_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        raise


def _generate_for_company(db: Session, company: Company) -> BriefingItem | None:
    """Build a single BriefingItem for *company*.  Returns ``None`` when skipped."""
    today = date.today()
    existing = (
        db.query(BriefingItem)
        .filter(
            BriefingItem.company_id == company.id,
            BriefingItem.briefing_date == today,
        )
        .first()
    )
    if existing:
        logger.info(
            "BriefingItem already exists for %s (id=%s) on %s — skipping",
            company.name,
            company.id,
            today,
        )
        return None

    # Latest analysis record.
    analysis: AnalysisRecord | None = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.company_id == company.id)
        .order_by(AnalysisRecord.created_at.desc())
        .first()
    )
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

    # Outreach draft.
    outreach = generate_outreach(db, company, analysis)

    item = BriefingItem(
        company_id=company.id,
        analysis_id=analysis.id,
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

