"""Tests for monthly bias audit service (Issue #112)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import BiasReport, Company, EngagementSnapshot, ReadinessSnapshot, SignalEvent
from app.services.bias_audit import (
    compute_alignment_skew,
    compute_funding_concentration,
    compute_stage_skew,
    get_surfaced_company_ids,
    run_bias_audit,
)

VALID_TOKEN = "test-internal-token"  # matches conftest.py env setup


def _create_company(
    db: Session,
    name: str,
    *,
    alignment_ok_to_contact: bool | None = None,
    current_stage: str | None = None,
) -> Company:
    c = Company(
        name=name,
        website_url=f"https://{name.lower().replace(' ', '')}.example.com",
        alignment_ok_to_contact=alignment_ok_to_contact,
        current_stage=current_stage,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _create_engagement_snapshot(db: Session, company_id: int, as_of: date) -> EngagementSnapshot:
    db.add(
        ReadinessSnapshot(
            company_id=company_id,
            as_of=as_of,
            momentum=50,
            complexity=50,
            pressure=50,
            leadership_gap=50,
            composite=50,
        )
    )
    es = EngagementSnapshot(
        company_id=company_id,
        as_of=as_of,
        esl_score=0.8,
        engagement_type="Direct Value Share",
        cadence_blocked=False,
    )
    db.add(es)
    db.commit()
    db.refresh(es)
    return es


def _create_signal_event(
    db: Session,
    company_id: int,
    event_type: str,
    event_time: datetime | None = None,
) -> SignalEvent:
    if event_time is None:
        event_time = datetime.now(UTC) - timedelta(days=1)
    ev = SignalEvent(
        company_id=company_id,
        source="test",
        event_type=event_type,
        event_time=event_time,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


# Use future months (2030, 2035) to avoid collisions with existing test DB data
_REPORT_MONTH = date(2030, 2, 1)  # used by GetSurfacedCompanyIds


class TestGetSurfacedCompanyIds:
    def test_returns_empty_when_no_snapshots(self, db: Session) -> None:
        """Use 2030-12 to avoid collision with other tests that use 2030-02."""
        ids = get_surfaced_company_ids(db, date(2030, 12, 1))
        assert ids == []

    def test_returns_company_ids_when_snapshots_exist(self, db: Session) -> None:
        c1 = _create_company(db, "Co1")
        c2 = _create_company(db, "Co2")
        _create_engagement_snapshot(db, c1.id, date(2030, 2, 15))
        _create_engagement_snapshot(db, c2.id, date(2030, 2, 20))

        ids = get_surfaced_company_ids(db, _REPORT_MONTH)
        assert c1.id in ids
        assert c2.id in ids

    def test_excludes_other_months(self, db: Session) -> None:
        c1 = _create_company(db, "Co1")
        _create_engagement_snapshot(db, c1.id, date(2030, 1, 15))

        ids = get_surfaced_company_ids(db, _REPORT_MONTH)
        assert c1.id not in ids


class TestComputeFundingConcentration:
    def test_empty_companies_returns_zero(self, db: Session) -> None:
        result = compute_funding_concentration(db, [], date(2026, 2, 28))
        assert result["with_funding"] == 0
        assert result["pct"] == 0.0

    def test_counts_companies_with_funding_event(self, db: Session) -> None:
        c1 = _create_company(db, "Co1")
        c2 = _create_company(db, "Co2")
        _create_signal_event(db, c1.id, "funding_raised")

        result = compute_funding_concentration(db, [c1.id, c2.id], date(2026, 2, 28))
        assert result["with_funding"] == 1
        assert result["pct"] == 50.0

    def test_ignores_old_events(self, db: Session) -> None:
        c1 = _create_company(db, "Co1")
        _create_signal_event(
            db,
            c1.id,
            "funding_raised",
            datetime(2024, 1, 1, tzinfo=UTC),
        )

        result = compute_funding_concentration(db, [c1.id], date(2026, 2, 28))
        assert result["with_funding"] == 0
        assert result["pct"] == 0.0


class TestComputeAlignmentSkew:
    def test_empty_companies_returns_zero(self, db: Session) -> None:
        result = compute_alignment_skew(db, [])
        assert result["true"] == 0
        assert result["false"] == 0
        assert result["null"] == 0

    def test_counts_alignment_segments(self, db: Session) -> None:
        c1 = _create_company(db, "Co1", alignment_ok_to_contact=True)
        c2 = _create_company(db, "Co2", alignment_ok_to_contact=False)
        c3 = _create_company(db, "Co3", alignment_ok_to_contact=None)

        result = compute_alignment_skew(db, [c1.id, c2.id, c3.id])
        assert result["true"] == 1
        assert result["false"] == 1
        assert result["null"] == 1
        assert result["max_pct"] == 33.3


class TestComputeStageSkew:
    def test_empty_companies_returns_empty_dict(self, db: Session) -> None:
        result = compute_stage_skew(db, [])
        assert result == {}

    def test_counts_stages(self, db: Session) -> None:
        c1 = _create_company(db, "Co1", current_stage="early_customers")
        c2 = _create_company(db, "Co2", current_stage="early_customers")
        c3 = _create_company(db, "Co3", current_stage="scaling_team")

        result = compute_stage_skew(db, [c1.id, c2.id, c3.id])
        assert result["early_customers"] == 2
        assert result["scaling_team"] == 1


class TestRunBiasAudit:
    def test_creates_report_with_surfaced_companies(self, db: Session) -> None:
        month = date(2040, 1, 1)  # far future to avoid DB pollution from other tests
        c1 = _create_company(db, "Co1", alignment_ok_to_contact=True)
        _create_engagement_snapshot(db, c1.id, date(2040, 1, 15))

        result = run_bias_audit(db, report_month=month)

        assert result["status"] == "completed"
        assert result["surfaced_count"] == 1
        assert result["report_id"] is not None

        report = db.query(BiasReport).filter(BiasReport.id == result["report_id"]).first()
        assert report is not None
        assert report.report_month == month
        assert report.surfaced_count == 1
        assert "funding_concentration" in report.payload
        assert "alignment_skew" in report.payload
        assert "stage_skew" in report.payload
        assert "flags" in report.payload

    def test_flags_when_stage_skew_exceeds_70(self, db: Session) -> None:
        """Synthetic data: 8 of 10 companies in same stage triggers flag."""
        month = date(2040, 4, 1)
        for i in range(10):
            c = _create_company(
                db,
                f"Co{i}",
                current_stage="early_customers" if i < 8 else "scaling_team",
            )
            _create_engagement_snapshot(db, c.id, date(2040, 4, 15))

        result = run_bias_audit(db, report_month=month)

        assert result["status"] == "completed"
        assert result["surfaced_count"] == 10
        assert "stage_skew" in result["flags"]

    def test_upserts_existing_report_for_same_month(self, db: Session) -> None:
        month = date(2040, 5, 1)
        c1 = _create_company(db, "Co1")
        _create_engagement_snapshot(db, c1.id, date(2040, 5, 15))

        result1 = run_bias_audit(db, report_month=month)
        result2 = run_bias_audit(db, report_month=month)

        assert result1["report_id"] == result2["report_id"]
        count = db.query(BiasReport).filter(BiasReport.report_month == month).count()
        assert count == 1


class TestInternalRunBiasAudit:
    @patch("app.services.bias_audit.run_bias_audit")
    def test_valid_token_calls_run_bias_audit(self, mock_audit, client: TestClient) -> None:
        """POST /internal/run_bias_audit with valid token triggers audit."""
        mock_audit.return_value = {
            "status": "completed",
            "job_run_id": 1,
            "report_id": 42,
            "surfaced_count": 5,
            "flags": [],
        }

        response = client.post(
            "/internal/run_bias_audit",
            headers={"X-Internal-Token": VALID_TOKEN},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["report_id"] == 42
        assert data["surfaced_count"] == 5
        assert data["flags"] == []
        mock_audit.assert_called_once()

    def test_missing_token_returns_422(self, client: TestClient) -> None:
        response = client.post("/internal/run_bias_audit")
        assert response.status_code == 422

    def test_wrong_token_returns_403(self, client: TestClient) -> None:
        response = client.post(
            "/internal/run_bias_audit",
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert response.status_code == 403
