"""
Health endpoint tests.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_health_returns_ok_when_db_connected(client: TestClient) -> None:
    """Health endpoint returns 200 with database connected."""
    # Mock engine.connect() so test runs without real PostgreSQL
    from app.db import engine

    mock_conn = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_conn)
    mock_cm.__exit__ = MagicMock(return_value=False)
    with patch.object(engine, "connect", return_value=mock_cm):
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data


def test_health_returns_503_when_db_unreachable(client: TestClient) -> None:
    """Health endpoint returns 503 when database is unreachable."""
    from app.db import engine

    # Patch check_db_connection so lifespan succeeds regardless of execution order.
    # Patch engine.connect so health handler fails with 503.
    with (
        patch("app.main.check_db_connection"),  # no-op: lifespan succeeds
        patch.object(engine, "connect", side_effect=Exception("Connection refused")),
    ):
        response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert "version" in data
