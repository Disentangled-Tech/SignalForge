"""
OpenAI LLM provider implementation.

Uses the openai Python SDK (>=1.0.0) with synchronous client.
Supports retry with exponential backoff for rate-limit errors.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIError, OpenAI, RateLimitError

from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0


class OpenAIProvider(LLMProvider):
    """Concrete LLM provider backed by the OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self._client = OpenAI(api_key=api_key, timeout=timeout)

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send prompt to OpenAI and return the completion text.

        Supported kwargs:
            temperature (float): Sampling temperature (default 0.7).
            max_tokens (int): Maximum tokens in the response.
            response_format (dict): E.g. {"type": "json_object"} for JSON mode.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        create_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
        }
        if "max_tokens" in kwargs:
            create_kwargs["max_tokens"] = kwargs["max_tokens"]
        if "response_format" in kwargs:
            create_kwargs["response_format"] = kwargs["response_format"]

        return self._call_with_retry(create_kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_with_retry(self, create_kwargs: dict[str, Any]) -> str:
        """Call the OpenAI API with exponential-backoff retry on rate limits."""
        backoff = INITIAL_BACKOFF

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                start = time.monotonic()
                response = self._client.chat.completions.create(**create_kwargs)
                elapsed = time.monotonic() - start

                text = response.choices[0].message.content or ""

                # Log usage info
                usage = response.usage
                if usage:
                    logger.info(
                        "OpenAI call: model=%s tokens_in=%d tokens_out=%d latency=%.2fs",
                        create_kwargs["model"],
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        elapsed,
                    )
                else:
                    logger.info(
                        "OpenAI call: model=%s latency=%.2fs (no usage data)",
                        create_kwargs["model"],
                        elapsed,
                    )

                return text

            except RateLimitError:
                if attempt == MAX_RETRIES:
                    logger.error(
                        "OpenAI rate limit: giving up after %d attempts", MAX_RETRIES
                    )
                    raise
                logger.warning(
                    "OpenAI rate limit: retry %d/%d in %.1fs",
                    attempt,
                    MAX_RETRIES,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

            except APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                raise

