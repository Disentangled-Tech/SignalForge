"""
Pytest configuration and fixtures.
"""

import os

import pytest
from fastapi.testclient import TestClient

# Load .env for tests
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/signalforge_test")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("INTERNAL_JOB_TOKEN", "test-internal-token")


@pytest.fixture
def client() -> TestClient:
    """FastAPI test client."""
    from app.main import app
    return TestClient(app)
