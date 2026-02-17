"""Scan metrics service – 30-day change rate for scan-all jobs (issue #61)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.job_run import JobRun


def get_scan_change_rate_30d(
    db: Session,
) -> tuple[float | None, int, int]:
    """Compute scan change rate over the last 30 days.

    Queries JobRun where job_type == "scan" and started_at >= 30 days ago.
    Sums companies_analysis_changed (NULL treated as 0) and companies_processed.

    Returns
    -------
    tuple[float | None, int, int]
        (percentage, total_changed, total_processed).
        percentage is None if total_processed == 0.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = (
        db.query(
            func.coalesce(func.sum(JobRun.companies_analysis_changed), 0).label(
                "total_changed"
            ),
            func.coalesce(func.sum(JobRun.companies_processed), 0).label(
                "total_processed"
            ),
        )
        .filter(JobRun.job_type == "scan", JobRun.started_at >= cutoff)
        .first()
    )
    if rows is None:
        return None, 0, 0
    total_changed = int(rows.total_changed or 0)
    total_processed = int(rows.total_processed or 0)
    if total_processed == 0:
        return None, total_changed, total_processed
    pct = round(100.0 * total_changed / total_processed, 1)
    return pct, total_changed, total_processed
