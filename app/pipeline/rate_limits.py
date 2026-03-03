"""Per-workspace rate limits for pipeline jobs (Phase 1, Issue #192)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.job_run import JobRun

logger = logging.getLogger(__name__)


def check_workspace_rate_limit(
    db: Session,
    workspace_id: str,
    job_type: str,
) -> bool:
    """Return True if workspace is within rate limit, False if exceeded.

    Disabled when WORKSPACE_JOB_RATE_LIMIT_PER_HOUR is 0 or negative.
    """
    limit = getattr(
        get_settings(),
        "workspace_job_rate_limit_per_hour",
        0,
    )
    if limit <= 0:
        return True

    cutoff = datetime.now(UTC) - timedelta(hours=1)
    count = (
        db.scalar(
            select(func.count(JobRun.id)).where(
                JobRun.workspace_id == workspace_id,
                JobRun.job_type == job_type,
                JobRun.started_at >= cutoff,
            )
        )
        or 0
    )

    if count >= limit:
        logger.warning(
            "Rate limit exceeded: workspace_id=%s job_type=%s count=%d limit=%d",
            workspace_id,
            job_type,
            count,
            limit,
        )
        return False
    return True
