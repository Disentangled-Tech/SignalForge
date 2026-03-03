"""Tests for GET /internal/scout_analytics — token auth, workspace scoping, response shape (M5, Issue #282)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.models.workspace import Workspace
from tests.test_internal import VALID_TOKEN


def test_scout_analytics_missing_token_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics without X-Internal-Token returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        params={"workspace_id": str(uuid4())},
    )
    assert response.status_code == 422


def test_scout_analytics_wrong_token_returns_403(client: TestClient) -> None:
    """GET /internal/scout_analytics with wrong token returns 403."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": "wrong-token"},
        params={"workspace_id": str(uuid4())},
    )
    assert response.status_code == 403


def test_scout_analytics_missing_workspace_id_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics without workspace_id returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
    )
    assert response.status_code == 422


def test_scout_analytics_invalid_workspace_id_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics with invalid workspace_id UUID returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": "not-a-uuid"},
    )
    assert response.status_code == 422


def test_scout_analytics_whitespace_only_workspace_id_returns_422(client: TestClient) -> None:
    """GET /internal/scout_analytics with workspace_id that is only whitespace returns 422."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": "   "},
    )
    assert response.status_code == 422


def test_scout_analytics_nonexistent_workspace_returns_zeros(client: TestClient) -> None:
    """GET /internal/scout_analytics with valid UUID that has no runs returns 200 with zeros."""
    response = client.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(uuid4())},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 0
    assert data["total_bundles"] == 0
    assert data["by_family"] == []


def test_scout_analytics_empty_workspace_returns_zeros(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /internal/scout_analytics for workspace with no runs returns runs_count=0, total_bundles=0."""
    ws = Workspace(name="Analytics Empty WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    response = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 0
    assert data["total_bundles"] == 0
    assert data["by_family"] == []


def test_scout_analytics_returns_aggregates_for_workspace(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /internal/scout_analytics returns runs_count and total_bundles for workspace's runs."""
    ws = Workspace(name="Analytics WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run_id_1 = uuid4()
    run_id_2 = uuid4()
    sr1 = ScoutRun(
        run_id=run_id_1,
        workspace_id=ws.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={"query_count": 2},
        status="completed",
    )
    sr2 = ScoutRun(
        run_id=run_id_2,
        workspace_id=ws.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={"query_count": 1},
        status="completed",
    )
    db.add_all([sr1, sr2])
    db.flush()

    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_id_1,
            candidate_company_name="A",
            company_website="https://a.example.com",
            evidence=[],
            missing_information=[],
        )
    )
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_id_1,
            candidate_company_name="B",
            company_website="https://b.example.com",
            evidence=[],
            missing_information=[],
        )
    )
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_id_2,
            candidate_company_name="C",
            company_website="https://c.example.com",
            evidence=[],
            missing_information=[],
        )
    )
    db.commit()

    response = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 2
    assert data["total_bundles"] == 3
    assert "by_family" in data
    assert isinstance(data["by_family"], list)


def test_scout_analytics_workspace_scoping_no_cross_tenant(
    client_with_db: TestClient,
    db,
) -> None:
    """Analytics for workspace A does not include runs from workspace B."""
    ws_a = Workspace(name="WS A")
    ws_b = Workspace(name="WS B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    run_id_b = uuid4()
    sr_b = ScoutRun(
        run_id=run_id_b,
        workspace_id=ws_b.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        config_snapshot={},
        status="completed",
    )
    db.add(sr_b)
    db.flush()
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run_id_b,
            candidate_company_name="Other",
            company_website="https://other.example.com",
            evidence=[],
            missing_information=[],
        )
    )
    db.commit()

    response = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws_a.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 0
    assert data["total_bundles"] == 0


def test_scout_analytics_by_family_when_config_has_query_families(
    client_with_db: TestClient,
    db,
) -> None:
    """When config_snapshot has query_families, response includes by_family breakdown."""
    ws = Workspace(name="WS Families")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run_id = uuid4()
    db.add(
        ScoutRun(
            run_id=run_id,
            workspace_id=ws.id,
            started_at=datetime.now(UTC),
            model_version="test",
            page_fetch_count=0,
            config_snapshot={"query_families": ["hiring", "launch"]},
            status="completed",
        )
    )
    db.flush()
    db.add(
        ScoutRun(
            run_id=uuid4(),
            workspace_id=ws.id,
            started_at=datetime.now(UTC),
            model_version="test",
            page_fetch_count=0,
            config_snapshot={"query_families": ["hiring"]},
            status="completed",
        )
    )
    db.commit()

    response = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["runs_count"] == 2
    by_family = {b["family_id"]: b["runs_count"] for b in data["by_family"]}
    assert by_family.get("hiring") == 2
    assert by_family.get("launch") == 1


def test_scout_analytics_since_filters_by_started_at(
    client_with_db: TestClient,
    db,
) -> None:
    """Optional since param returns only runs started on or after that date."""
    ws = Workspace(name="WS Since")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    from datetime import timedelta

    old_date = datetime.now(UTC) - timedelta(days=10)
    run_old = uuid4()
    run_new = uuid4()
    db.add(
        ScoutRun(
            run_id=run_old,
            workspace_id=ws.id,
            started_at=old_date,
            model_version="test",
            page_fetch_count=0,
            config_snapshot={},
            status="completed",
        )
    )
    db.add(
        ScoutRun(
            run_id=run_new,
            workspace_id=ws.id,
            started_at=datetime.now(UTC),
            model_version="test",
            page_fetch_count=0,
            config_snapshot={},
            status="completed",
        )
    )
    db.commit()

    # Without since: both runs
    r1 = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id)},
    )
    assert r1.status_code == 200
    assert r1.json()["runs_count"] == 2

    # With since= today: only recent run (today or later)
    today = datetime.now(UTC).date()
    r2 = client_with_db.get(
        "/internal/scout_analytics",
        headers={"X-Internal-Token": VALID_TOKEN},
        params={"workspace_id": str(ws.id), "since": today.isoformat()},
    )
    assert r2.status_code == 200
    assert r2.json()["runs_count"] == 1
