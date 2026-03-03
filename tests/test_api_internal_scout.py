"""Tests for POST /internal/run_scout and GET /internal/scout_analytics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from tests.test_constants import TEST_WORKSPACE_ID
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
        json={"icp_definition": "Seed-stage B2B", "workspace_id": str(TEST_WORKSPACE_ID)},
    )
    assert response.status_code == 422


def test_run_scout_wrong_token_returns_403(client: TestClient) -> None:
    """POST /internal/run_scout with wrong token returns 403."""
    response = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": "wrong-token"},
        json={"icp_definition": "Seed-stage B2B", "workspace_id": str(TEST_WORKSPACE_ID)},
    )
    assert response.status_code == 403


@patch("app.services.scout.discovery_scout_service.get_llm_provider")
def test_run_scout_valid_token_returns_run_id_and_bundles_count(
    mock_get_llm: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """POST /internal/run_scout with valid token returns run_id, bundles_count, status."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Test WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

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
            "workspace_id": str(ws.id),
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

    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Test WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    response = client_with_db.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={
            "icp_definition": "Fintech startup",
            "page_fetch_limit": 5,
            "workspace_id": str(ws.id),
        },
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

    from app.models.workspace import Workspace

    ws = Workspace(name="Scout Test WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    response = client_with_db.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "B2B SaaS", "page_fetch_limit": 5, "workspace_id": str(ws.id)},
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
    """POST /internal/run_scout returns 422 for invalid body (missing icp/workspace_id, empty icp, page_fetch_limit out of range)."""
    # Missing icp_definition
    r1 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"page_fetch_limit": 10, "workspace_id": str(TEST_WORKSPACE_ID)},
    )
    assert r1.status_code == 422

    # Missing workspace_id
    r1b = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "B2B SaaS", "page_fetch_limit": 10},
    )
    assert r1b.status_code == 422

    # Empty icp_definition
    r2 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={"icp_definition": "", "page_fetch_limit": 10, "workspace_id": str(TEST_WORKSPACE_ID)},
    )
    assert r2.status_code == 422

    # page_fetch_limit > 100
    r3 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={
            "icp_definition": "B2B SaaS",
            "page_fetch_limit": 101,
            "workspace_id": str(TEST_WORKSPACE_ID),
        },
    )
    assert r3.status_code == 422

    # page_fetch_limit < 0
    r4 = client.post(
        "/internal/run_scout",
        headers={"X-Internal-Token": VALID_TOKEN},
        json={
            "icp_definition": "B2B SaaS",
            "page_fetch_limit": -1,
            "workspace_id": str(TEST_WORKSPACE_ID),
        },
    )
    assert r4.status_code == 422


# ── GET /internal/scout_runs (workspace-scoped list) ─────────────────────────


def test_list_scout_runs_missing_workspace_id_returns_422(client: TestClient) -> None:
    """GET /internal/scout_runs without workspace_id returns 422."""
    response = client.get(
        "/internal/scout_runs",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 422


def test_list_scout_runs_wrong_token_returns_403(client: TestClient) -> None:
    """GET /internal/scout_runs with wrong token returns 403."""
    response = client.get(
        "/internal/scout_runs",
        headers={"X-Internal-Token": "wrong-token"},
        params={"workspace_id": "a1b2c3d4-e5f6-7890-abcd-000000000001"},
    )
    assert response.status_code == 403


def test_list_scout_runs_requires_workspace_id_for_tenant_scoping(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /internal/scout_runs returns only runs for the given workspace_id (no cross-tenant)."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.models import ScoutRun, Workspace

    ws_a = Workspace(name="Workspace A")
    ws_b = Workspace(name="Workspace B")
    db.add(ws_a)
    db.add(ws_b)
    db.flush()

    run_a = ScoutRun(
        run_id=uuid4(),
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
        workspace_id=ws_a.id,
    )
    run_b = ScoutRun(
        run_id=uuid4(),
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
        workspace_id=ws_b.id,
    )
    db.add(run_a)
    db.add(run_b)
    db.commit()

    response = client_with_db.get(
        "/internal/scout_runs",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws_a.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == str(ws_a.id)
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == str(run_a.run_id)
    assert data["runs"][0]["status"] == "completed"

    response_b = client_with_db.get(
        "/internal/scout_runs",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws_b.id)},
    )
    assert response_b.status_code == 200
    assert len(response_b.json()["runs"]) == 1
    assert response_b.json()["runs"][0]["run_id"] == str(run_b.run_id)


# ── GET /internal/scout_analytics ─────────────────────────────────────────────


def test_scout_analytics_missing_token_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics without X-Internal-Token returns 422 (missing required header)."""
    response = client.get(
        "/internal/scout_analytics",
        params={"workspace_id": str(TEST_WORKSPACE_ID)},
    )
    assert response.status_code == 422


def test_scout_analytics_invalid_workspace_id_returns_422(
    client: TestClient,
) -> None:
    """GET /internal/scout_analytics with invalid workspace_id returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_scout_analytics_empty_workspace_id_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics with empty workspace_id returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": ""},
    )
    assert response.status_code == 422


def test_scout_analytics_returns_only_requested_workspace_data(
    client_with_db: TestClient,
    db,
) -> None:
    """Scout analytics filters by workspace_id; no data from other workspaces."""
    from app.models.workspace import Workspace

    ws_a = Workspace(name="Workspace A")
    ws_b = Workspace(name="Workspace B")
    db.add(ws_a)
    db.add(ws_b)
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    # Run 1: workspace A, 1 bundle
    run_a = ScoutRun(
        run_id=uuid.uuid4(),
        workspace_id=ws_a.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={"query_count": 5},
        status="completed",
    )
    db.add(run_a)
    db.flush()
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_a.run_id,
            candidate_company_name="Co A",
            company_website="https://a.example.com",
            why_now_hypothesis="",
            evidence=[],
            missing_information=[],
        )
    )

    # Run 2: workspace B, 2 bundles
    run_b = ScoutRun(
        run_id=uuid.uuid4(),
        workspace_id=ws_b.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={"query_count": 10},
        status="completed",
    )
    db.add(run_b)
    db.flush()
    for i in range(2):
        db.add(
            ScoutEvidenceBundle(
                scout_run_id=run_b.run_id,
                candidate_company_name=f"Co B{i}",
                company_website=f"https://b{i}.example.com",
                why_now_hypothesis="",
                evidence=[],
                missing_information=[],
            )
        )
    db.commit()

    # Request analytics for workspace A only
    response = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws_a.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 1
    assert data["total_bundles"] == 1

    # Request analytics for workspace B only
    response_b = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws_b.id)},
    )
    assert response_b.status_code == 200
    data_b = response_b.json()
    assert data_b["runs_count"] == 1
    assert data_b["total_bundles"] == 2


def test_scout_analytics_since_filters_runs(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /internal/scout_analytics with since returns only runs started on or after that date (UTC)."""
    from app.models.workspace import Workspace

    ws = Workspace(name="Since Test WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    # Run before since date (2025-01-01 00:00 UTC)
    run_old = ScoutRun(
        run_id=uuid.uuid4(),
        workspace_id=ws.id,
        started_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={},
        status="completed",
    )
    db.add(run_old)
    db.flush()
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_old.run_id,
            candidate_company_name="Old",
            company_website="https://old.example.com",
            why_now_hypothesis="",
            evidence=[],
            missing_information=[],
        )
    )

    # Run on since date (2025-01-02 12:00 UTC)
    run_new = ScoutRun(
        run_id=uuid.uuid4(),
        workspace_id=ws.id,
        started_at=datetime(2025, 1, 2, 12, 0, 0, tzinfo=UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={},
        status="completed",
    )
    db.add(run_new)
    db.flush()
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_new.run_id,
            candidate_company_name="New",
            company_website="https://new.example.com",
            why_now_hypothesis="",
            evidence=[],
            missing_information=[],
        )
    )
    db.commit()

    # Without since: both runs
    r_all = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id)},
    )
    assert r_all.status_code == 200
    assert r_all.json()["runs_count"] == 2
    assert r_all.json()["total_bundles"] == 2

    # With since=2025-01-02: only run_new (start of day 2025-01-02 UTC)
    r_since = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id), "since": "2025-01-02"},
    )
    assert r_since.status_code == 200
    data = r_since.json()
    assert data["runs_count"] == 1
    assert data["total_bundles"] == 1
