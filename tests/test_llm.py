"""
Tests for the LLM provider layer: OpenAIProvider and router.

All OpenAI API calls are mocked — no real network requests.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from anthropic import (
    APITimeoutError as AnthropicAPITimeoutError,
)
from anthropic import (
    RateLimitError as AnthropicRateLimitError,
)
from openai import APITimeoutError, RateLimitError

from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.router import ModelRole, clear_provider_cache, get_llm_provider

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Ensure a clean provider cache for every test."""
    clear_provider_cache()
    yield
    clear_provider_cache()


def _make_mock_response(
    content: str = "Hello!", prompt_tokens: int = 10, completion_tokens: int = 5
):
    """Build a fake ChatCompletion response object."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with LLM defaults, without reading env."""
    from tests.test_constants import TEST_LLM_API_KEY

    s = object.__new__(Settings)  # skip __init__ (avoids env reads)
    s.llm_provider = "openai"
    s.llm_api_key = TEST_LLM_API_KEY
    s.llm_model = "gpt-4o-mini"
    s.llm_model_reasoning = "gpt-4o"
    s.llm_model_json = "gpt-4o-mini"
    s.llm_model_outreach = "gpt-4o-mini"
    s.llm_timeout = 60.0
    s.llm_max_retries = 3
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------------------
# OpenAIProvider — initialisation
# ---------------------------------------------------------------------------


class TestOpenAIProviderInit:
    def test_stores_model_and_timeout(self):
        with patch("app.llm.openai_provider.OpenAI"):
            provider = OpenAIProvider(api_key="k", model="gpt-4o", timeout=30.0)
        assert provider.model == "gpt-4o"
        assert provider.timeout == 30.0

    def test_default_model_timeout_and_retries(self):
        with patch("app.llm.openai_provider.OpenAI"):
            provider = OpenAIProvider(api_key="k")
        assert provider.model == "gpt-4o-mini"
        assert provider.timeout == 60.0
        assert provider.max_retries == 3


# ---------------------------------------------------------------------------
# OpenAIProvider.complete()
# ---------------------------------------------------------------------------


class TestOpenAIProviderComplete:
    def test_basic_complete(self):
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _make_mock_response("world")

            provider = OpenAIProvider(api_key="k")
            result = provider.complete("hello")

        assert result == "world"
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["messages"] == [{"role": "user", "content": "hello"}]

    def test_complete_with_system_prompt(self):
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _make_mock_response("ok")

            provider = OpenAIProvider(api_key="k")
            result = provider.complete("hi", system_prompt="be brief")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"][0] == {"role": "system", "content": "be brief"}
        assert call_kwargs["messages"][1] == {"role": "user", "content": "hi"}
        assert result == "ok"

    def test_complete_passes_kwargs(self):
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _make_mock_response("{}")

            provider = OpenAIProvider(api_key="k")
            provider.complete(
                "json please",
                temperature=0.0,
                max_tokens=100,
                response_format={"type": "json_object"},
            )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_retry_on_rate_limit(self):
        with (
            patch("app.llm.openai_provider.OpenAI") as MockOpenAI,
            patch("app.llm.openai_provider.time") as mock_time,
        ):
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_time.monotonic.return_value = 0.0

            # Fail twice with rate limit, succeed on third attempt
            rate_err = RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )
            mock_client.chat.completions.create.side_effect = [
                rate_err,
                rate_err,
                _make_mock_response("finally"),
            ]

            provider = OpenAIProvider(api_key="k")
            result = provider.complete("test")

        assert result == "finally"
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_time.sleep.call_count == 2


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestRouter:
    def test_returns_openai_provider(self):
        with patch("app.llm.openai_provider.OpenAI"):
            provider = get_llm_provider(settings=_make_settings())
        assert isinstance(provider, OpenAIProvider)

    def test_caches_provider(self):
        with patch("app.llm.openai_provider.OpenAI"):
            s = _make_settings()
            p1 = get_llm_provider(settings=s)
            p2 = get_llm_provider(settings=s)
        assert p1 is p2

    def test_raises_for_unknown_provider(self):
        with pytest.raises(
            ValueError,
            match=r"Unknown LLM provider.*Supported providers: openai, anthropic",
        ):
            get_llm_provider(settings=_make_settings(llm_provider="azure"))

    def test_raises_when_api_key_missing(self):
        with pytest.raises(ValueError, match="LLM_API_KEY is required"):
            get_llm_provider(settings=_make_settings(llm_api_key=None))

    def test_router_returns_different_models_per_role(self):
        """Different roles get providers configured with different models."""
        with patch("app.llm.openai_provider.OpenAI"):
            s = _make_settings(
                llm_model_reasoning="gpt-4o",
                llm_model_json="gpt-4o-mini",
                llm_model_outreach="gpt-4o-mini",
            )
            p_reasoning = get_llm_provider(role=ModelRole.REASONING, settings=s)
            p_json = get_llm_provider(role=ModelRole.JSON, settings=s)
        assert p_reasoning.model == "gpt-4o"
        assert p_json.model == "gpt-4o-mini"

    def test_router_passes_timeout_and_retries(self):
        """OpenAIProvider receives timeout and max_retries from settings."""
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            s = _make_settings(llm_timeout=90.0, llm_max_retries=5)
            get_llm_provider(role=ModelRole.REASONING, settings=s)
        # OpenAI client is created with timeout
        MockOpenAI.assert_called_once()
        call_kwargs = MockOpenAI.call_args.kwargs
        assert call_kwargs["timeout"] == 90.0
        # Provider stores max_retries (used in _call_with_retry)
        provider = get_llm_provider(role=ModelRole.REASONING, settings=s)
        assert provider.max_retries == 5

    def test_router_default_role_is_reasoning(self):
        """Omitting role defaults to REASONING."""
        with patch("app.llm.openai_provider.OpenAI"):
            s = _make_settings(llm_model_reasoning="gpt-4o")
            provider = get_llm_provider(settings=s)
        assert provider.model == "gpt-4o"

    def test_returns_anthropic_provider_when_configured(self):
        """When llm_provider=anthropic and API key is set, returns AnthropicProvider."""
        with patch("app.llm.anthropic_provider.Anthropic"):
            provider = get_llm_provider(
                settings=_make_settings(
                    llm_provider="anthropic", llm_model_reasoning="claude-3-5-sonnet"
                )
            )
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-3-5-sonnet"

    def test_raises_when_anthropic_and_api_key_missing(self):
        """When llm_provider=anthropic and no API key, raises with clear message."""
        with pytest.raises(
            ValueError,
            match="LLM_API_KEY or ANTHROPIC_API_KEY required for Anthropic provider",
        ):
            get_llm_provider(settings=_make_settings(llm_provider="anthropic", llm_api_key=None))

    def test_anthropic_caches_by_role(self):
        """Anthropic provider is cached per role (anthropic:role)."""
        with patch("app.llm.anthropic_provider.Anthropic"):
            s = _make_settings(llm_provider="anthropic")
            p1 = get_llm_provider(role=ModelRole.REASONING, settings=s)
            p2 = get_llm_provider(role=ModelRole.REASONING, settings=s)
        assert p1 is p2


class TestAnthropicProviderInit:
    def test_stores_model_timeout_retries(self):
        with patch("app.llm.anthropic_provider.Anthropic"):
            provider = AnthropicProvider(
                api_key="k", model="claude-3-5-haiku", timeout=30.0, max_retries=5
            )
        assert provider.model == "claude-3-5-haiku"
        assert provider.timeout == 30.0
        assert provider.max_retries == 5


class TestAnthropicProviderComplete:
    def test_complete_returns_text_from_content_block(self):
        """complete() extracts text from first text block in response.content."""
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="Hello from Claude")],
                input_tokens=10,
                output_tokens=5,
            )
            provider = AnthropicProvider(api_key="k")
            result = provider.complete("Hi")
        assert result == "Hello from Claude"
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"
        assert call_kwargs["messages"] == [{"role": "user", "content": "Hi"}]

    def test_complete_with_system_prompt(self):
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                input_tokens=0,
                output_tokens=0,
            )
            provider = AnthropicProvider(api_key="k")
            provider.complete("q", system_prompt="Be brief")
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be brief"

    def test_complete_passes_temperature_max_tokens_response_format(self):
        """AnthropicProvider passes temperature, max_tokens and appends JSON instruction when response_format is json_object."""
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="{}")],
                input_tokens=0,
                output_tokens=0,
            )
            provider = AnthropicProvider(api_key="k", model="claude-3-5-haiku")
            provider.complete(
                "json please",
                temperature=0.0,
                max_tokens=100,
                response_format={"type": "json_object"},
            )
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.0
        assert call_kwargs["max_tokens"] == 100
        messages = call_kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert "json please" in messages[0]["content"]
        assert "valid JSON only" in messages[0]["content"] or "JSON only" in messages[0]["content"]

    def test_complete_defaults_max_tokens_when_omitted(self):
        """When max_tokens not in kwargs, AnthropicProvider uses default 4096."""
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                input_tokens=0,
                output_tokens=0,
            )
            provider = AnthropicProvider(api_key="k")
            provider.complete("hello")
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 4096


class TestAnthropicProviderRetry:
    """AnthropicProvider retries on rate-limit and timeout (mocked SDK)."""

    def test_retry_on_rate_limit(self):
        with (
            patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic,
            patch("app.llm.anthropic_provider.time") as mock_time,
        ):
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_time.monotonic.return_value = 0.0
            rate_err = AnthropicRateLimitError(
                message="rate limited",
                response=MagicMock(),
                body=None,
            )
            mock_client.messages.create.side_effect = [
                rate_err,
                rate_err,
                SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="finally")],
                    input_tokens=0,
                    output_tokens=0,
                ),
            ]
            provider = AnthropicProvider(api_key="k", max_retries=3)
            result = provider.complete("test")
        assert result == "finally"
        assert mock_client.messages.create.call_count == 3
        assert mock_time.sleep.call_count == 2

    def test_retry_on_timeout(self):
        with (
            patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic,
            patch("app.llm.anthropic_provider.time") as mock_time,
        ):
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_time.monotonic.return_value = 0.0
            timeout_err = AnthropicAPITimeoutError(request=MagicMock())
            mock_client.messages.create.side_effect = [
                timeout_err,
                timeout_err,
                SimpleNamespace(
                    content=[SimpleNamespace(type="text", text="success")],
                    input_tokens=0,
                    output_tokens=0,
                ),
            ]
            provider = AnthropicProvider(api_key="k", max_retries=3)
            result = provider.complete("test")
        assert result == "success"
        assert mock_client.messages.create.call_count == 3
        assert mock_time.sleep.call_count == 2


class TestProviderRetryOnTimeout:
    def test_provider_retries_on_timeout(self):
        """Provider retries on APITimeoutError and eventually succeeds."""
        with (
            patch("app.llm.openai_provider.OpenAI") as MockOpenAI,
            patch("app.llm.openai_provider.time") as mock_time,
        ):
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_time.monotonic.return_value = 0.0
            timeout_err = APITimeoutError(request=MagicMock())
            mock_client.chat.completions.create.side_effect = [
                timeout_err,
                timeout_err,
                _make_mock_response("success"),
            ]
            provider = OpenAIProvider(api_key="k", max_retries=3)
            result = provider.complete("test")
        assert result == "success"
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_time.sleep.call_count == 2


class TestPromptLogging:
    def test_prompt_logged_at_info_with_preview(self, caplog):
        """INFO log contains prompt_preview and token usage."""
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _make_mock_response(
                "hi", prompt_tokens=50, completion_tokens=10
            )
            provider = OpenAIProvider(api_key="k")
            with caplog.at_level("INFO"):
                provider.complete("Hello world")
        assert "prompt_preview" in caplog.text
        assert "tokens_in=50" in caplog.text or "tokens_in= 50" in caplog.text
        assert "tokens_out=10" in caplog.text or "tokens_out= 10" in caplog.text

    def test_full_prompt_logged_at_debug(self, caplog):
        """DEBUG log contains full prompt when DEBUG enabled."""
        long_prompt = "x" * 200
        with patch("app.llm.openai_provider.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = _make_mock_response("ok")
            provider = OpenAIProvider(api_key="k")
            with caplog.at_level("DEBUG"):
                provider.complete(long_prompt)
        assert long_prompt in caplog.text


class TestAnthropicPromptLogging:
    """AnthropicProvider logs prompt preview and token usage at INFO, full prompt at DEBUG."""

    def test_prompt_logged_at_info_with_preview(self, caplog):
        """INFO log contains prompt_preview and token usage."""
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="hi")],
                input_tokens=50,
                output_tokens=10,
            )
            provider = AnthropicProvider(api_key="k")
            with caplog.at_level("INFO"):
                provider.complete("Hello world")
        assert "prompt_preview" in caplog.text
        assert "tokens_in=50" in caplog.text or "tokens_in= 50" in caplog.text
        assert "tokens_out=10" in caplog.text or "tokens_out= 10" in caplog.text

    def test_full_prompt_logged_at_debug(self, caplog):
        """DEBUG log contains full prompt when DEBUG enabled."""
        long_prompt = "y" * 200
        with patch("app.llm.anthropic_provider.Anthropic") as MockAnthropic:
            mock_client = MagicMock()
            MockAnthropic.return_value = mock_client
            mock_client.messages.create.return_value = SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                input_tokens=0,
                output_tokens=0,
            )
            provider = AnthropicProvider(api_key="k")
            with caplog.at_level("DEBUG"):
                provider.complete(long_prompt)
        assert long_prompt in caplog.text
