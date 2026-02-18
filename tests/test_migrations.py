"""Alembic migration tests."""

import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect

from app.db import engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic command and return result."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_alembic_upgrade_downgrade_cycle(_ensure_migrations: None) -> None:
    """Full migration cycle: upgrade creates tables, downgrade removes them."""
    # Downgrade to base (clean slate)
    result = run_alembic("downgrade", "base")
    assert result.returncode == 0, f"downgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "companies" not in tables
    assert "signal_records" not in tables
    assert "job_runs" not in tables

    # Upgrade creates tables
    result = run_alembic("upgrade", "head")
    assert result.returncode == 0, f"upgrade failed: {result.stderr}"

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "companies" in tables
    assert "signal_records" in tables
    assert "job_runs" in tables
    assert "analysis_records" in tables
    assert "briefing_items" in tables
    assert "readiness_snapshots" in tables
    assert "watchlist" in tables
    assert "users" in tables
    assert "operator_profiles" in tables
    assert "app_settings" in tables
    assert "signal_events" in tables
