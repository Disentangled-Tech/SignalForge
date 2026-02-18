"""Alert model tests (Issue #84)."""

import pytest
from sqlalchemy.orm import Session

from app.models import Alert, Company


def test_alert_model_creation() -> None:
    """Model instantiates with alert_type, payload, status."""
    alert = Alert(
        company_id=1,
        alert_type="readiness_jump",
        payload={"delta": 15, "prev_composite": 55, "new_composite": 70},
        status="pending",
    )
    assert alert.company_id == 1
    assert alert.alert_type == "readiness_jump"
    assert alert.payload["delta"] == 15
    assert alert.payload["new_composite"] == 70
    assert alert.status == "pending"
    # created_at is set on insert; before persist it may be None


def test_alert_jsonb_persists(db: Session) -> None:
    """JSON payload round-trips correctly."""
    company = Company(name="PayloadCo", website_url="https://payload.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    payload = {
        "delta": 18,
        "prev_composite": 52,
        "new_composite": 70,
        "as_of": "2026-02-18",
        "top_events": [{"event_type": "funding_raised", "contribution_points": 35}],
    }

    alert = Alert(
        company_id=company.id,
        alert_type="readiness_jump",
        payload=payload,
        status="pending",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    assert alert.payload == payload
    assert alert.payload["delta"] == 18
    assert alert.payload["top_events"][0]["event_type"] == "funding_raised"


def test_alert_status_transitions(db: Session) -> None:
    """Create pending, update to sent, then failed."""
    company = Company(name="StatusCo", website_url="https://status.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    alert = Alert(
        company_id=company.id,
        alert_type="ctohire",
        payload={"source": "signal_event"},
        status="pending",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    assert alert.status == "pending"

    alert.status = "sent"
    db.commit()
    db.refresh(alert)
    assert alert.status == "sent"

    alert.status = "failed"
    db.commit()
    db.refresh(alert)
    assert alert.status == "failed"


def test_alert_company_relationship(db: Session) -> None:
    """Company.alerts loads correctly."""
    company = Company(name="RelCo", website_url="https://rel.example.com")
    db.add(company)
    db.commit()
    db.refresh(company)

    alert = Alert(
        company_id=company.id,
        alert_type="new_signal",
        payload={"event_id": "evt-123"},
        status="pending",
    )
    db.add(alert)
    db.commit()

    db.refresh(company)
    assert len(company.alerts) == 1
    assert company.alerts[0].company_id == company.id
    assert company.alerts[0].alert_type == "new_signal"
