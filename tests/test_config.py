"""
Configuration tests.
"""

import pytest

from app.config import Settings, get_settings


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
    assert hasattr(settings, "anthropic_api_key")
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


# ---------------------------------------------------------------------------
# Anthropic API key (M2: optional ANTHROPIC_API_KEY, fallback to LLM_API_KEY)
# ---------------------------------------------------------------------------


def test_anthropic_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ANTHROPIC_API_KEY is set, settings.anthropic_api_key is that value."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("LLM_API_KEY", "sk-openai")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.anthropic_api_key == "sk-ant-test"
    finally:
        get_settings.cache_clear()


def test_anthropic_api_key_fallback_to_llm_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ANTHROPIC_API_KEY is unset, anthropic_api_key falls back to LLM_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-common-key")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.anthropic_api_key == "sk-common-key"
    finally:
        get_settings.cache_clear()


def test_llm_provider_openai_coerced_to_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LLM_PROVIDER=openai (or any non-anthropic), config coerces to anthropic (ADR-012)."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_provider == "anthropic"
    finally:
        get_settings.cache_clear()


def test_anthropic_provider_claude_model_names_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LLM_PROVIDER=anthropic and role env vars are set, settings load Claude model names."""
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL_REASONING", "claude-3-5-sonnet-20241022")
    monkeypatch.setenv("LLM_MODEL_JSON", "claude-3-5-haiku-20241022")
    monkeypatch.setenv("LLM_MODEL_OUTREACH", "claude-3-5-haiku-20241022")
    monkeypatch.setenv("LLM_MODEL_SCOUT", "claude-sonnet-4-20250514")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_provider == "anthropic"
        assert settings.llm_model_reasoning == "claude-3-5-sonnet-20241022"
        assert settings.llm_model_json == "claude-3-5-haiku-20241022"
        assert settings.llm_model_outreach == "claude-3-5-haiku-20241022"
        assert settings.llm_model_scout == "claude-sonnet-4-20250514"
    finally:
        get_settings.cache_clear()
