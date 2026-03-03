"""Monthly bias audit service (Issue #112).

Analyzes surfaced companies for funding concentration, alignment skew, and stage skew.
Stores results in bias_reports. Flags when any segment exceeds 70%.
Does not auto-adjust scoring.
"""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import BiasReport, Company, EngagementSnapshot, JobRun, SignalEvent
from app.services.analysis import ALLOWED_STAGES

logger = logging.getLogger(__name__)

BIAS_THRESHOLD_PCT = 70
FUNDING_LOOKBACK_DAYS = 365


def get_surfaced_company_ids(db: Session, report_month: date) -> list[int]:
    """Return company IDs with EngagementSnapshot.as_of in the report month."""
    first_day = report_month.replace(day=1)
    _, last_day_num = calendar.monthrange(first_day.year, first_day.month)
    last_day = first_day.replace(day=last_day_num)

    rows = (
        db.query(EngagementSnapshot.company_id)
        .filter(
            EngagementSnapshot.as_of >= first_day,
            EngagementSnapshot.as_of <= last_day,
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]


def compute_funding_concentration(db: Session, company_ids: list[int], as_of: date) -> dict:
    """Count % of companies with funding_raised SignalEvent in last 365 days."""
    if not company_ids:
        return {"with_funding": 0, "pct": 0.0, "segment": "with_funding"}

    cutoff = as_of - timedelta(days=FUNDING_LOOKBACK_DAYS)
    cutoff_dt = datetime.combine(cutoff, datetime.min.time()).replace(tzinfo=UTC)

    # Companies with at least one funding_raised event
    with_funding = (
        db.query(SignalEvent.company_id)
        .filter(
            SignalEvent.company_id.in_(company_ids),
            SignalEvent.event_type == "funding_raised",
            SignalEvent.event_time >= cutoff_dt,
        )
        .distinct()
        .count()
    )

    pct = (with_funding / len(company_ids)) * 100.0 if company_ids else 0.0
    return {"with_funding": with_funding, "pct": round(pct, 1), "segment": "with_funding"}


def compute_alignment_skew(db: Session, company_ids: list[int]) -> dict:
    """Count True/False/None for alignment_ok_to_contact; return max segment and pct."""
    if not company_ids:
        return {"true": 0, "false": 0, "null": 0, "max_segment": "null", "max_pct": 0.0}

    companies = db.query(Company.alignment_ok_to_contact).filter(Company.id.in_(company_ids)).all()
    counts = {"true": 0, "false": 0, "null": 0}
    for (val,) in companies:
        if val is True:
            counts["true"] += 1
        elif val is False:
            counts["false"] += 1
        else:
            counts["null"] += 1

    total = len(company_ids)
    pcts = {k: (v / total) * 100.0 for k, v in counts.items()}
    max_segment = max(pcts, key=pcts.get)  # type: ignore[arg-type]
    max_pct = round(pcts[max_segment], 1)

    return {
        "true": counts["true"],
        "false": counts["false"],
        "null": counts["null"],
        "max_segment": max_segment,
        "max_pct": max_pct,
    }


def compute_stage_skew(db: Session, company_ids: list[int]) -> dict:
    """Count by current_stage (from Company). Return dict of stage -> count."""
    if not company_ids:
        return {}

    companies = db.query(Company.current_stage).filter(Company.id.in_(company_ids)).all()
    counts: dict[str, int] = {}
    for (stage,) in companies:
        key = (stage or "").strip().lower()
        if key and key in ALLOWED_STAGES:
            counts[key] = counts.get(key, 0) + 1
        else:
            counts["unknown"] = counts.get("unknown", 0) + 1

    return counts


def run_bias_audit(db: Session, report_month: date | None = None) -> dict:
    """Run monthly bias audit (Issue #112).

    Creates JobRun, computes metrics, persists BiasReport, returns summary.
    Default report_month is last month.
    """
    if report_month is None:
        today = date.today()
        first = today.replace(day=1)
        report_month = (first - timedelta(days=1)).replace(day=1)

    job = JobRun(job_type="bias_audit", status="running")
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        company_ids = get_surfaced_company_ids(db, report_month)
        surfaced_count = len(company_ids)

        # Use last day of report month for funding cutoff
        _, last_day = calendar.monthrange(report_month.year, report_month.month)
        as_of = report_month.replace(day=last_day)

        funding = compute_funding_concentration(db, company_ids, as_of)
        alignment = compute_alignment_skew(db, company_ids)
        stage = compute_stage_skew(db, company_ids)

        # Industry: N/A for MVP
        industry_concentration = {"segment": "N/A", "note": "industry not yet available"}

        # Stage skew: compute max pct for flagging
        total = len(company_ids)
        stage_pcts = {k: round((v / total) * 100.0, 1) if total else 0.0 for k, v in stage.items()}
        max_stage = max(stage_pcts, key=stage_pcts.get) if stage_pcts else None
        max_stage_pct = stage_pcts.get(max_stage, 0.0) if max_stage else 0.0

        # Detect flags (> 70%)
        flags: list[str] = []
        if funding["pct"] > BIAS_THRESHOLD_PCT:
            flags.append("funding_concentration")
        if alignment["max_pct"] > BIAS_THRESHOLD_PCT:
            flags.append("alignment_skew")
        if max_stage_pct > BIAS_THRESHOLD_PCT:
            flags.append("stage_skew")

        payload = {
            "funding_concentration": funding,
            "alignment_skew": alignment,
            "stage_skew": stage,
            "stage_skew_max_segment": max_stage,
            "stage_skew_max_pct": max_stage_pct,
            "industry_concentration": industry_concentration,
            "flags": flags,
            "threshold": BIAS_THRESHOLD_PCT,
        }

        # Upsert: replace existing report for same month
        existing = db.query(BiasReport).filter(BiasReport.report_month == report_month).first()
        if existing:
            existing.surfaced_count = surfaced_count
            existing.payload = payload
            db.commit()
            db.refresh(existing)
            report = existing
        else:
            report = BiasReport(
                report_month=report_month,
                surfaced_count=surfaced_count,
                payload=payload,
            )
            db.add(report)
            db.commit()
            db.refresh(report)

        job.finished_at = datetime.now(UTC)
        job.status = "completed"
        job.companies_processed = surfaced_count
        db.commit()

        logger.info(
            "Bias audit completed: report_month=%s surfaced=%d flags=%s",
            report_month,
            surfaced_count,
            flags,
        )

        return {
            "status": "completed",
            "job_run_id": job.id,
            "report_id": report.id,
            "surfaced_count": surfaced_count,
            "flags": flags,
        }

    except Exception as exc:
        logger.exception("Bias audit failed")
        job.finished_at = datetime.now(UTC)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        return {
            "status": "failed",
            "job_run_id": job.id,
            "report_id": None,
            "surfaced_count": 0,
            "flags": [],
            "error": str(exc),
        }
