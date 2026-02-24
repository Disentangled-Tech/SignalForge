"""Tests for scripts/clean_test_data_from_dev.py."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


class TestCleanTestDataScript:
    """Tests for the clean_test_data_from_dev script."""

    def test_refuses_signalforge_test(self) -> None:
        """Script exits with error when DATABASE_URL points to signalforge_test."""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://localhost:5432/signalforge_test"}
        result = subprocess.run(
            [sys.executable, "scripts/clean_test_data_from_dev.py"],
            env=env,
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        assert result.returncode != 0
        assert "signalforge_test" in (result.stderr + result.stdout)
