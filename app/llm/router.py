"""
LLM provider router / factory.

Returns the correct LLMProvider implementation based on application settings.
Provider instances are cached per (provider_name, role) to reuse connections.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from app.llm.provider import LLMProvider

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)


class ModelRole(str, Enum):
    """Model role for task-based routing (issue #15)."""

    REASONING = "reasoning"  # analyze_model: stage, pain, explanation
    JSON = "json"  # cheap_model: briefing entry JSON
    OUTREACH = "outreach"  # conversational_model: outreach draft


# Module-level cache: "provider_name:role" -> instance
_provider_cache: dict[str, LLMProvider] = {}


def get_llm_provider(
    role: ModelRole = ModelRole.REASONING,
    settings: Settings | None = None,
) -> LLMProvider:
    """Return an LLMProvider instance for the configured provider and role.

    Args:
        role: Model role (REASONING, JSON, OUTREACH) for task-based routing.
        settings: Application settings. If *None*, loads from ``get_settings()``.

    Returns:
        A cached LLMProvider instance configured for the role.

    Raises:
        ValueError: If the configured provider is not supported or API key is missing.
    """
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    provider_name = settings.llm_provider.lower()
    cache_key = f"{provider_name}:{role.value}"

    if cache_key in _provider_cache:
        return _provider_cache[cache_key]

    if provider_name == "openai":
        if not settings.llm_api_key:
            raise ValueError(
                "LLM_API_KEY is required for the OpenAI provider. "
                "Set it in your environment or .env file."
            )

        from app.llm.openai_provider import OpenAIProvider

        model = {
            ModelRole.REASONING: settings.llm_model_reasoning,
            ModelRole.JSON: settings.llm_model_json,
            ModelRole.OUTREACH: settings.llm_model_outreach,
        }[role]

        provider = OpenAIProvider(
            api_key=settings.llm_api_key,
            model=model,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider_name}'. "
            f"Supported providers: openai"
        )

    _provider_cache[cache_key] = provider
    logger.info("Created LLM provider: %s role=%s model=%s", provider_name, role.value, model)
    return provider


def clear_provider_cache() -> None:
    """Clear the provider cache. Useful for testing."""
    _provider_cache.clear()

