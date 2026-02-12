"""
Configuration tests.
"""

import pytest

from app.config import get_settings, Settings


def test_get_settings_returns_settings() -> None:
    """get_settings returns a Settings instance."""
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_settings_has_required_attributes() -> None:
    """Settings has all required attributes."""
    settings = get_settings()
    assert hasattr(settings, "app_name")
    assert hasattr(settings, "database_url")
    assert hasattr(settings, "secret_key")
    assert hasattr(settings, "internal_job_token")
    assert hasattr(settings, "llm_provider")
    assert settings.app_name == "SignalForge"
