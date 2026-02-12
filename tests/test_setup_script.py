"""Tests for the setup script."""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETUP_SCRIPT = PROJECT_ROOT / "scripts" / "setup.sh"


@pytest.fixture
def setup_script():
    """Path to setup script."""
    return SETUP_SCRIPT


class TestSetupScript:
    """Tests for scripts/setup.sh."""

    def test_script_exists_and_is_executable(self, setup_script):
        """Setup script should exist and be executable."""
        assert setup_script.exists(), "scripts/setup.sh should exist"
        assert setup_script.is_file(), "scripts/setup.sh should be a file"
        # On Unix, check executable bit
        assert os.access(setup_script, os.X_OK), "scripts/setup.sh should be executable"

    def test_help_flag_exits_successfully(self, setup_script):
        """Running with --help should exit 0."""
        result = subprocess.run(
            [str(setup_script), "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Expected exit 0, got {result.returncode}"

    def test_help_output_contains_usage(self, setup_script):
        """Help output should include usage instructions."""
        result = subprocess.run(
            [str(setup_script), "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert "SignalForge" in result.stdout
        assert "--dev" in result.stdout
        assert "--start" in result.stdout
        assert "--help" in result.stdout

    def test_script_has_valid_syntax(self, setup_script):
        """Script should pass bash syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(setup_script)],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"
