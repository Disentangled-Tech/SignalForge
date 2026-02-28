"""Tests for POST /internal/run_scout — token auth, response shape, scout_runs row created."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from tests.test_internal import VALID_TOKEN


def _valid_llm_response() -> str:
    return """{
  "bundles": [
    {
      "candidate_company_name": "API Test Co",
      "company_website": "https://apitest.example.com",
      "why_now_hypothesis": "Raised seed.",
      "evidence": [
        {
          "url": "https://apitest.example.com/news",
          "quoted_snippet": "Seed round.",
          "timestamp_seen": "2026-02-27T12:00:00Z",
          "source_type": "news",
          "confidence_score": 0.9
        }
      ],
      "missing_information": []
    }
  ]
}"""


def test_run_scout_missing_token_returns_422(client: TestClient) -> None:
    """POST /internal/run_scout without X-Internal-Token returns 422."""
    response = client.post(
        "/internal/run_scout",
        json={"icp_definition": "Seed-stage B2B"},
    )
    assert response.status_code == 422


def test_run_scout_wrong_token_returns_403(client: TestClient) -> None:
    """POST /internal/run_scout with wrong token returns 403."""
    response = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": "wrong-token"},
        json={"icp_definition": "Seed-stage B2B"},
    )
    assert response.status_code == 403


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_scout_valid_token_returns_run_id_and_bundles_count(
    mock_get_llm: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """POST /internal/run_scout with valid token returns run_id, bundles_count, status."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_llm_response()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    response = client_with_db.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={
            "icp_definition": "Seed-stage B2B SaaS",
            "exclusion_rules": None,
            "pack_id": None,
            "page_fetch_limit": 10,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "completed"
    assert data["bundles_count"] == 1
    assert data.get("error") is None

    # Scout run row created (client_with_db uses same db)
    run_row = db.query(ScoutRun).order_by(ScoutRun.id.desc()).first()
    assert run_row is not None
    assert run_row.status == "completed"


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_scout_creates_scout_runs_row_no_companies_or_events(
    mock_get_llm: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """With valid token, run_scout creates scout_runs row; no new companies or signal_events."""
    from app.models.company import Company
    from app.models.signal_event import SignalEvent

    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_llm_response()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    companies_before = db.query(Company).count()
    events_before = db.query(SignalEvent).count()

    response = client_with_db.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "Fintech startup", "page_fetch_limit": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

    runs = db.query(ScoutRun).all()
    assert len(runs) >= 1
    bundles = db.query(ScoutEvidenceBundle).all()
    assert len(bundles) >= 1

    assert db.query(Company).count() == companies_before
    assert db.query(SignalEvent).count() == events_before


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_scout_also_persists_to_evidence_store(
    mock_get_llm: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """M6: run_scout persists to Evidence Store; list_bundles_by_run returns stored bundles."""
    from app.evidence.repository import list_bundles_by_run

    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_llm_response()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    response = client_with_db.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "B2B SaaS", "page_fetch_limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    run_id = data["run_id"]
    assert run_id
    assert data["bundles_count"] == 1

    bundles = list_bundles_by_run(db, run_id)
    assert len(bundles) == 1
    assert bundles[0].run_context is not None
    assert bundles[0].run_context.get("run_id") == run_id
    assert bundles[0].scout_version == "gpt-4o"


def test_run_scout_missing_body_returns_422(client: TestClient) -> None:
    """POST /internal/run_scout without body returns 422."""
    response = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 422


def test_run_scout_invalid_body_returns_422(client: TestClient) -> None:
    """POST /internal/run_scout returns 422 for invalid body (missing/empty icp, page_fetch_limit out of range)."""
    # Missing icp_definition
    r1 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"page_fetch_limit": 10},
    )
    assert r1.status_code == 422

    # Empty icp_definition
    r2 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "", "page_fetch_limit": 10},
    )
    assert r2.status_code == 422

    # page_fetch_limit > 100
    r3 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "B2B SaaS", "page_fetch_limit": 101},
    )
    assert r3.status_code == 422

    # page_fetch_limit < 0
    r4 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "B2B SaaS", "page_fetch_limit": -1},
    )
    assert r4.status_code == 422
