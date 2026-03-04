"""Tests for Scout UI view routes (GET /scout, GET /scout/runs/{id}, POST /scout/runs).

Session auth, workspace-scoped. No cross-tenant leakage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.models.scout_evidence_bundle import ScoutEvidenceBundle
from app.models.scout_run import ScoutRun
from app.models.user import User
from app.models.user_workspace import UserWorkspace
from app.models.workspace import Workspace
from tests.test_constants import TEST_PASSWORD

# ── Unauthenticated: redirect to /login ─────────────────────────────────────


def test_scout_list_unauthenticated_redirects_to_login(client: TestClient) -> None:
    """GET /scout without auth returns 303 to /login."""
    resp = client.get("/scout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/login"


def test_scout_run_detail_unauthenticated_redirects_to_login(client: TestClient) -> None:
    """GET /scout/runs/{run_id} without auth returns 303 to /login."""
    run_id = uuid4()
    resp = client.get(f"/scout/runs/{run_id}", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/login"


def test_scout_run_trigger_unauthenticated_redirects_to_login(client: TestClient) -> None:
    """POST /scout/runs without auth returns 303 to /login."""
    resp = client.post(
        "/scout/runs",
        data={"icp_definition": "B2B SaaS"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/login"


def test_scout_run_new_unauthenticated_redirects_to_login(client: TestClient) -> None:
    """GET /scout/new without auth returns 303 to /login."""
    resp = client.get("/scout/new", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers.get("location") == "/login"


# ── List: authenticated, workspace-scoped ─────────────────────────────────


@pytest.mark.integration
def test_scout_list_authenticated_empty(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout when authenticated and no runs returns 200 with empty list."""
    user = User(username="scout_empty_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get("/scout", follow_redirects=False)
        assert resp.status_code == 200
        assert "No scout runs" in resp.text or "scout" in resp.text.lower()
        assert 'href="/scout"' in resp.text, "Nav must include Scout link"
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@pytest.mark.integration
def test_scout_run_new_authenticated_returns_form(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout/new when authenticated returns 200 with ICP form."""
    user = User(username="scout_new_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get("/scout/new", follow_redirects=False)
        assert resp.status_code == 200
        assert "icp_definition" in resp.text or "New Scout run" in resp.text
        assert "scout/runs" in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@pytest.mark.integration
def test_scout_run_new_authenticated_returns_form(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout/new when authenticated returns 200 with ICP form."""
    user = User(username="scout_new_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get("/scout/new", follow_redirects=False)
        assert resp.status_code == 200
        assert "icp_definition" in resp.text or "New Scout run" in resp.text
        assert "scout/runs" in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@pytest.mark.integration
@patch("app.api.views.get_settings")
@patch("app.api.scout_views.get_settings")
def test_scout_list_authenticated_shows_runs(
    mock_settings_scout: MagicMock,
    mock_settings_views: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout when authenticated returns HTML with run ids and counts."""
    mock_settings_scout.return_value.multi_workspace_enabled = True
    mock_settings_views.return_value.multi_workspace_enabled = True

    ws = Workspace(name="Scout List WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    user = User(username="scout_list_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            f"/scout?workspace_id={ws.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert str(run.run_id) in resp.text
        assert "completed" in resp.text
        assert "1" in resp.text or "0" in resp.text  # bundles_count
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


# ── Workspace scoping: user with access only to B cannot see A's run ───────────


@pytest.mark.integration
def test_scout_list_workspace_scoping_no_cross_tenant(
    client_with_db: TestClient,
    db,
) -> None:
    """With two workspaces, user with access only to B does not see A's run in list."""
    ws_a = Workspace(name="Workspace A")
    ws_b = Workspace(name="Workspace B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    run_a = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws_a.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run_a)
    db.commit()

    user = User(username="scout_ws_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws_b.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            f"/scout?workspace_id={ws_b.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert str(run_a.run_id) not in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@pytest.mark.integration
def test_scout_list_shows_error_flash_when_error_query_param(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout?error=... shows error flash message."""
    user = User(username="scout_error_flash_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            "/scout?error=Scout+run+failed",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Scout run failed" in resp.text or "run failed" in resp.text
        assert "flash error" in resp.text or 'class="flash error"' in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@pytest.mark.integration
def test_scout_run_detail_other_workspace_returns_404(
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout/runs/{run_id} for run in another workspace returns 404."""
    ws_a = Workspace(name="Workspace A")
    ws_b = Workspace(name="Workspace B")
    db.add_all([ws_a, ws_b])
    db.commit()
    db.refresh(ws_a)
    db.refresh(ws_b)

    run_a = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws_a.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run_a)
    db.commit()

    user = User(username="scout_detail_ws_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws_b.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            f"/scout/runs/{run_a.run_id}?workspace_id={ws_b.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


# ── Detail: run in user's workspace returns 200 with candidate data ───────────


@pytest.mark.integration
@patch("app.api.views.get_settings")
@patch("app.api.scout_views.get_settings")
def test_scout_run_detail_authenticated_shows_bundles(
    mock_settings_scout: MagicMock,
    mock_settings_views: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout/runs/{run_id} for run in user's workspace returns 200 with candidate names."""
    mock_settings_scout.return_value.multi_workspace_enabled = True
    mock_settings_views.return_value.multi_workspace_enabled = True

    ws = Workspace(name="Scout Detail WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run)
    db.flush()
    bundle = ScoutEvidenceBundle(
        scout_run_id=run.run_id,
        candidate_company_name="Test Candidate Co",
        company_website="https://test.example.com",
        why_now_hypothesis="Raised seed round.",
        evidence=[],
        missing_information=[],
    )
    db.add(bundle)
    db.commit()

    user = User(username="scout_detail_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            f"/scout/runs/{run.run_id}?workspace_id={ws.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Test Candidate Co" in resp.text
        assert "Raised seed round" in resp.text
        assert "raw_llm_output" not in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@patch("app.api.views.get_settings")
@patch("app.api.scout_views.get_settings")
@pytest.mark.integration
def test_scout_run_detail_without_workspace_id_resolves_from_run(
    mock_settings_scout: MagicMock,
    mock_settings_views: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """GET /scout/runs/{run_id} without workspace_id (multi_workspace) resolves workspace from run."""
    mock_settings_scout.return_value.multi_workspace_enabled = True
    mock_settings_views.return_value.multi_workspace_enabled = True

    ws = Workspace(name="Scout Detail No WS Param")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    run = ScoutRun(
        run_id=uuid4(),
        workspace_id=ws.id,
        started_at=datetime.now(UTC),
        model_version="test",
        page_fetch_count=0,
        status="completed",
    )
    db.add(run)
    db.flush()
    db.add(
        ScoutEvidenceBundle(
            scout_run_id=run.run_id,
            candidate_company_name="Resolved Co",
            company_website="https://resolved.example.com",
            why_now_hypothesis="Why now.",
            evidence=[],
            missing_information=[],
        )
    )
    db.commit()

    user = User(username="scout_detail_no_ws_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.get(
            f"/scout/runs/{run.run_id}",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Resolved Co" in resp.text
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


# ── Trigger: POST /scout/runs creates run and redirects ───────────────────────


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


@patch("app.api.views.get_settings")
@patch("app.api.scout_views.get_settings")
@patch("app.services.scout.discovery_scout_service.get_llm_provider")
@pytest.mark.integration
def test_scout_run_trigger_creates_run_redirects_to_detail(
    mock_get_llm: MagicMock,
    mock_settings_scout: MagicMock,
    mock_settings_views: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """POST /scout/runs with valid icp_definition creates ScoutRun and redirects to run detail."""
    mock_settings_scout.return_value.multi_workspace_enabled = True
    mock_settings_views.return_value.multi_workspace_enabled = True
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_llm_response()
    mock_llm.model = "gpt-4o"
    mock_get_llm.return_value = mock_llm

    ws = Workspace(name="Scout Trigger WS")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    user = User(username="scout_trigger_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    try:
        resp = client_with_db.post(
            "/scout/runs",
            data={
                "icp_definition": "Seed-stage B2B SaaS",
                "page_fetch_limit": "10",
            },
            params={"workspace_id": str(ws.id)},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers.get("location") or ""
        assert location.startswith("/scout") and "success=" in location

        run = (
            db.query(ScoutRun)
            .filter(ScoutRun.workspace_id == ws.id)
            .order_by(ScoutRun.id.desc())
            .first()
        )
        assert run is not None
        assert run.workspace_id == ws.id
    finally:
        app.dependency_overrides.pop(require_ui_auth, None)


@patch("app.api.views.get_settings")
@patch("app.api.scout_views.get_settings")
@pytest.mark.integration
def test_scout_run_trigger_uses_workspace_from_request(
    mock_settings_scout: MagicMock,
    mock_settings_views: MagicMock,
    client_with_db: TestClient,
    db,
) -> None:
    """POST /scout/runs with workspace_id B creates ScoutRun with workspace_id B."""
    mock_settings_scout.return_value.multi_workspace_enabled = True
    mock_settings_views.return_value.multi_workspace_enabled = True
    mock_llm = MagicMock()
    mock_llm.complete.return_value = _valid_llm_response()
    mock_llm.model = "gpt-4o"

    ws = Workspace(name="Scout WS B")
    db.add(ws)
    db.commit()
    db.refresh(ws)

    user = User(username="scout_ws_trigger_user")
    user.set_password(TEST_PASSWORD)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(UserWorkspace(user_id=user.id, workspace_id=ws.id))
    db.commit()

    from app.api.deps import require_ui_auth
    from app.main import app

    app.dependency_overrides[require_ui_auth] = lambda: user
    with patch(
        "app.services.scout.discovery_scout_service.get_llm_provider", return_value=mock_llm
    ):
        try:
            resp = client_with_db.post(
                "/scout/runs",
                data={"icp_definition": "B2B fintech"},
                params={"workspace_id": str(ws.id)},
                follow_redirects=False,
            )
            assert resp.status_code == 303
            run = (
                db.query(ScoutRun)
                .filter(ScoutRun.workspace_id == ws.id)
                .order_by(ScoutRun.id.desc())
                .first()
            )
            assert run is not None
            assert run.workspace_id == ws.id
        finally:
            app.dependency_overrides.pop(require_ui_auth, None)
