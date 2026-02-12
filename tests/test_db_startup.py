"""
Database startup and fail-fast tests.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_app_fails_to_start_when_db_unreachable() -> None:
    """App fails fast when database is unreachable at startup."""
    with patch("app.main.check_db_connection") as mock_check:
        mock_check.side_effect = Exception("Database unreachable")

        from app.main import create_app

        app = create_app()

        with pytest.raises(Exception, match="Database unreachable"):
            with TestClient(app) as test_client:
                test_client.get("/health")
