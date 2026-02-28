"""Settings and operator profile service functions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.app_settings import AppSettings
from app.models.operator_profile import OperatorProfile

logger = logging.getLogger(__name__)


def get_app_settings(db: Session) -> dict:
    """Load all AppSettings rows and return as a dict.

    Returns a dict mapping key -> value for every row in the app_settings table.
    """
    rows = db.query(AppSettings).all()
    return {row.key: row.value for row in rows}


def update_app_settings(db: Session, updates: dict) -> dict:
    """Upsert key-value pairs into AppSettings.

    For each key in *updates*, creates or updates the corresponding row.
    Returns the full settings dict after the update.
    """
    for key, value in updates.items():
        row = db.query(AppSettings).filter(AppSettings.key == key).first()
        if row is None:
            row = AppSettings(key=key, value=value)
            db.add(row)
        else:
            row.value = value
    db.commit()
    return get_app_settings(db)


def get_operator_profile(db: Session) -> str:
    """Get the first OperatorProfile content, or empty string if none exists."""
    row = db.query(OperatorProfile).first()
    if row is None or row.content is None:
        return ""
    return row.content


def update_operator_profile(db: Session, content: str) -> OperatorProfile:
    """Upsert the singleton operator profile row.

    Creates a new row if none exists, otherwise updates the existing one.
    Returns the OperatorProfile instance.
    """
    row = db.query(OperatorProfile).first()
    if row is None:
        row = OperatorProfile(content=content, updated_at=datetime.now(UTC))
        db.add(row)
    else:
        row.content = content
        row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return row
