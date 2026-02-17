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


# ---------------------------------------------------------------------------
# LLM model roles (issue #15)
# ---------------------------------------------------------------------------


def test_llm_model_roles_defaults() -> None:
    """Settings has llm_model_reasoning, llm_model_json, llm_model_outreach, timeout, retries."""
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert hasattr(settings, "llm_model_reasoning")
        assert hasattr(settings, "llm_model_json")
        assert hasattr(settings, "llm_model_outreach")
        assert hasattr(settings, "llm_timeout")
        assert hasattr(settings, "llm_max_retries")
    finally:
        get_settings.cache_clear()


def test_llm_model_roles_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """llm_model_reasoning, llm_model_json, llm_model_outreach load from env."""
    monkeypatch.setenv("LLM_MODEL_REASONING", "gpt-4o")
    monkeypatch.setenv("LLM_MODEL_JSON", "gpt-4o-mini")
    monkeypatch.setenv("LLM_MODEL_OUTREACH", "gpt-4o-mini")
    monkeypatch.setenv("LLM_TIMEOUT", "90")
    monkeypatch.setenv("LLM_MAX_RETRIES", "5")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_model_reasoning == "gpt-4o"
        assert settings.llm_model_json == "gpt-4o-mini"
        assert settings.llm_model_outreach == "gpt-4o-mini"
        assert settings.llm_timeout == 90.0
        assert settings.llm_max_retries == 5
    finally:
        get_settings.cache_clear()


def test_llm_model_legacy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When only LLM_MODEL is set, it is used for all three roles."""
    monkeypatch.delenv("LLM_MODEL_REASONING", raising=False)
    monkeypatch.delenv("LLM_MODEL_JSON", raising=False)
    monkeypatch.delenv("LLM_MODEL_OUTREACH", raising=False)
    monkeypatch.setenv("LLM_MODEL", "gpt-4-turbo")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_model_reasoning == "gpt-4-turbo"
        assert settings.llm_model_json == "gpt-4-turbo"
        assert settings.llm_model_outreach == "gpt-4-turbo"
    finally:
        get_settings.cache_clear()
