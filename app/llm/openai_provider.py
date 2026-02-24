"""
OpenAI LLM provider implementation.

Uses the openai Python SDK (>=1.0.0) with synchronous client.
Supports retry with exponential backoff for rate-limit, timeout, and connection errors.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Retry configuration
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0

# Errors that trigger retry
_RETRYABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError)


class OpenAIProvider(LLMProvider):
    """Concrete LLM provider backed by the OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
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
        """Call the OpenAI API with exponential-backoff retry on rate limit/timeout/connection."""
        backoff = INITIAL_BACKOFF
        messages = create_kwargs.get("messages", [])
        prompt = ""
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user":
                prompt = m.get("content", "") or ""
                break

        for attempt in range(1, self.max_retries + 1):
            try:
                start = time.monotonic()
                response = self._client.chat.completions.create(**create_kwargs)
                elapsed = time.monotonic() - start

                text = response.choices[0].message.content or ""

                # Log usage and prompt preview (issue #15)
                usage = response.usage
                prompt_tokens = usage.prompt_tokens if usage else 0
                completion_tokens = usage.completion_tokens if usage else 0
                prompt_preview = (prompt[:100] + "...") if len(prompt) > 100 else prompt
                logger.info(
                    "LLM call: model=%s prompt_preview=%r tokens_in=%d tokens_out=%d latency=%.2fs",
                    create_kwargs["model"],
                    prompt_preview,
                    prompt_tokens,
                    completion_tokens,
                    elapsed,
                )
                logger.debug("LLM prompt (full): %s", prompt)

                return text

            except _RETRYABLE_ERRORS as exc:
                if attempt == self.max_retries:
                    logger.error(
                        "OpenAI retryable error: giving up after %d attempts: %s",
                        self.max_retries,
                        exc,
                    )
                    raise
                logger.warning(
                    "OpenAI %s: retry %d/%d in %.1fs",
                    type(exc).__name__,
                    attempt,
                    self.max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

            except APIError as exc:
                logger.error("OpenAI API error: %s", exc)
                raise

