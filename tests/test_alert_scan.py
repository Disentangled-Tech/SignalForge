"""Tests for readiness delta alert scan job (Issue #92)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.models import Alert, Company, ReadinessSnapshot
from app.services.readiness.alert_scan import run_alert_scan


def _create_snapshots(
    db: Session,
    company_id: int,
    as_of: date,
    composite: int,
) -> ReadinessSnapshot:
    """Create a readiness snapshot for a company."""
    snap = ReadinessSnapshot(
        company_id=company_id,
        as_of=as_of,
        momentum=composite // 4,
        complexity=composite // 4,
        pressure=composite // 4,
        leadership_gap=composite // 4,
        composite=composite,
        explain={"delta_1d": 0},
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


class TestRunAlertScan:
    """Alert scan job."""

    def test_alert_created_when_delta_meets_threshold(self, db: Session) -> None:
        """Alert created when delta >= threshold (default 15)."""
        company = Company(name="JumpCo", website_url="https://jump.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, company.id, prev_date, 50)
        _create_snapshots(db, company.id, as_of, 70)

        result = run_alert_scan(db, as_of=as_of)

        assert result["status"] == "completed"
        assert result["alerts_created"] >= 1

        alert = (
            db.query(Alert)
            .filter(
                Alert.company_id == company.id,
                Alert.alert_type == "readiness_jump",
            )
            .first()
        )
        assert alert is not None, f"No alert for company {company.id}"
        assert alert.payload["old_composite"] == 50
        assert alert.payload["new_composite"] == 70
        assert alert.payload["delta"] == 20
        assert alert.payload["as_of"] == str(as_of)

    def test_no_alert_when_delta_below_threshold(self, db: Session) -> None:
        """No alert when delta < threshold."""
        company = Company(name="StableCo", website_url="https://stable.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, company.id, prev_date, 55)
        _create_snapshots(db, company.id, as_of, 62)  # delta=7

        result = run_alert_scan(db, as_of=as_of)

        assert result["status"] == "completed"
        assert result["alerts_created"] == 0

        count = (
            db.query(Alert)
            .filter(
                Alert.company_id == company.id,
                Alert.alert_type == "readiness_jump",
            )
            .count()
        )
        assert count == 0

    def test_no_duplicate_alerts(self, db: Session) -> None:
        """Running scan twice for same company/date creates only one alert."""
        company = Company(name="DupCo", website_url="https://dup.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, company.id, prev_date, 40)
        _create_snapshots(db, company.id, as_of, 60)  # delta=20

        run_alert_scan(db, as_of=as_of)
        result = run_alert_scan(db, as_of=as_of)

        assert result["alerts_created"] == 0

        count = (
            db.query(Alert)
            .filter(
                Alert.company_id == company.id,
                Alert.alert_type == "readiness_jump",
            )
            .count()
        )
        assert count == 1

    def test_skip_when_no_previous_snapshot(self, db: Session) -> None:
        """No alert when company has snapshot today but not yesterday."""
        company = Company(name="NewCo", website_url="https://new.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        _create_snapshots(db, company.id, as_of, 80)

        result = run_alert_scan(db, as_of=as_of)

        assert result["status"] == "completed"
        assert result["alerts_created"] == 0

    def test_negative_delta_creates_alert(self, db: Session) -> None:
        """Alert created when score drops (negative delta) and |delta| >= threshold."""
        company = Company(name="DropCo", website_url="https://drop.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, company.id, prev_date, 75)
        _create_snapshots(db, company.id, as_of, 55)  # delta=-20

        result = run_alert_scan(db, as_of=as_of)

        assert result["status"] == "completed"
        assert result["alerts_created"] >= 1

        alert = (
            db.query(Alert)
            .filter(
                Alert.company_id == company.id,
                Alert.alert_type == "readiness_jump",
            )
            .first()
        )
        assert alert is not None, f"No alert for company {company.id}"
        assert alert.payload["delta"] == -20
        assert alert.payload["old_composite"] == 75
        assert alert.payload["new_composite"] == 55

    def test_multiple_companies(self, db: Session) -> None:
        """Two companies crossing threshold yield two alerts."""
        c1 = Company(name="Jump1", website_url="https://j1.example.com")
        c2 = Company(name="Jump2", website_url="https://j2.example.com")
        db.add_all([c1, c2])
        db.commit()
        db.refresh(c1)
        db.refresh(c2)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, c1.id, prev_date, 50)
        _create_snapshots(db, c1.id, as_of, 70)
        _create_snapshots(db, c2.id, prev_date, 30)
        _create_snapshots(db, c2.id, as_of, 50)

        result = run_alert_scan(db, as_of=as_of)

        assert result["alerts_created"] >= 2

        alerts = (
            db.query(Alert)
            .filter(
                Alert.alert_type == "readiness_jump",
                Alert.company_id.in_([c1.id, c2.id]),
            )
            .all()
        )
        assert len(alerts) == 2
        company_ids = {a.company_id for a in alerts}
        assert company_ids == {c1.id, c2.id}

    def test_respects_config_threshold(self, db: Session) -> None:
        """When threshold is 25, delta=20 does not create alert."""
        company = Company(name="ThresholdCo", website_url="https://thresh.example.com")
        db.add(company)
        db.commit()
        db.refresh(company)

        as_of = date.today()
        prev_date = as_of - timedelta(days=1)

        _create_snapshots(db, company.id, prev_date, 50)
        _create_snapshots(db, company.id, as_of, 70)  # delta=20

        with patch("app.services.readiness.alert_scan.get_settings") as mock_settings:
            mock_settings.return_value.alert_delta_threshold = 25
            result = run_alert_scan(db, as_of=as_of)

        assert result["alerts_created"] == 0
