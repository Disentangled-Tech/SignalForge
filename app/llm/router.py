"""
LLM provider router / factory.

Returns the correct LLMProvider implementation based on application settings.
Provider instances are cached (one per provider type) to reuse connections.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.llm.provider import LLMProvider

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

# Module-level cache: provider_name -> instance
_provider_cache: dict[str, LLMProvider] = {}


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Return an LLMProvider instance for the configured provider.

    Args:
        settings: Application settings. If *None*, loads from ``get_settings()``.

    Returns:
        A cached LLMProvider instance.

    Raises:
        ValueError: If the configured provider is not supported or API key is missing.
    """
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    provider_name = settings.llm_provider.lower()

    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    if provider_name == "openai":
        if not settings.llm_api_key:
            raise ValueError(
                "LLM_API_KEY is required for the OpenAI provider. "
                "Set it in your environment or .env file."
            )

        from app.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported providers: openai"
        )

    _provider_cache[provider_name] = provider
    logger.info("Created LLM provider: %s (model=%s)", provider_name, settings.llm_model)
    return provider


def clear_provider_cache() -> None:
    """Clear the provider cache. Useful for testing."""
    _provider_cache.clear()

