"""Readiness delta alert scan job (Issue #92).

Compares latest readiness snapshot to previous day; creates Alert when
|delta| >= threshold. Prevents duplicate alerts per company+as_of.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert, ReadinessSnapshot

logger = logging.getLogger(__name__)

ALERT_TYPE_READINESS_JUMP = "readiness_jump"


def run_alert_scan(db: Session, as_of: date | None = None) -> dict:
    """Run daily alert scan for readiness score jumps (Issue #92).

    For each company with a snapshot on as_of, compares to previous day.
    Creates Alert when |delta| >= ALERT_DELTA_THRESHOLD. Prevents duplicates.

    Args:
        db: Database session.
        as_of: Snapshot date to scan (default: today).

    Returns:
        dict with status, alerts_created, companies_scanned.
    """
    if as_of is None:
        as_of = date.today()

    threshold = get_settings().alert_delta_threshold
    prev_date = as_of - timedelta(days=1)

    current_snapshots = db.query(ReadinessSnapshot).filter(ReadinessSnapshot.as_of == as_of).all()

    alerts_created = 0
    companies_scanned = len(current_snapshots)

    for snap in current_snapshots:
        prev_snap = (
            db.query(ReadinessSnapshot)
            .filter(
                ReadinessSnapshot.company_id == snap.company_id,
                ReadinessSnapshot.as_of == prev_date,
            )
            .first()
        )
        if prev_snap is None:
            continue

        delta = snap.composite - prev_snap.composite
        if abs(delta) < threshold:
            continue

        # Check for duplicate: existing alert for same company + as_of
        existing = (
            db.query(Alert)
            .filter(
                Alert.company_id == snap.company_id,
                Alert.alert_type == ALERT_TYPE_READINESS_JUMP,
                Alert.payload["as_of"].astext == str(as_of),
            )
            .first()
        )
        if existing is not None:
            continue

        payload = {
            "old_composite": prev_snap.composite,
            "new_composite": snap.composite,
            "delta": delta,
            "as_of": str(as_of),
        }
        alert = Alert(
            company_id=snap.company_id,
            alert_type=ALERT_TYPE_READINESS_JUMP,
            payload=payload,
            status="pending",
        )
        db.add(alert)
        alerts_created += 1
        logger.info(
            "Alert created: company_id=%s delta=%d (%.0f -> %.0f)",
            snap.company_id,
            delta,
            prev_snap.composite,
            snap.composite,
        )

    db.commit()

    logger.info(
        "Alert scan completed: as_of=%s scanned=%d alerts_created=%d",
        as_of,
        companies_scanned,
        alerts_created,
    )
    return {
        "status": "completed",
        "alerts_created": alerts_created,
        "companies_scanned": companies_scanned,
    }
