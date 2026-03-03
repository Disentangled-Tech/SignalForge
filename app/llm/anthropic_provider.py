"""
Anthropic LLM provider implementation.

Uses the anthropic Python SDK (>=0.39.0) with synchronous client.
Supports retry with exponential backoff for rate-limit, timeout, and connection errors.

Security: API keys are never logged; only model, prompt preview, token counts, and
latency are logged at INFO/DEBUG.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from anthropic import (
    Anthropic,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)

from app.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Retry configuration (mirror openai_provider)
INITIAL_BACKOFF = 1.0  # seconds
BACKOFF_MULTIPLIER = 2.0
DEFAULT_MAX_TOKENS = 4096

# Errors that trigger retry
_RETRYABLE_ERRORS = (RateLimitError, APITimeoutError, APIConnectionError)

# Instruction appended when caller requests JSON output (prompt-based; no structured output)
_JSON_INSTRUCTION = " Respond with valid JSON only, no markdown or explanation."


class AnthropicProvider(LLMProvider):
    """Concrete LLM provider backed by the Anthropic Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        timeout: float = 60.0,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = Anthropic(api_key=api_key, timeout=timeout)

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send prompt to Anthropic and return the completion text.

        Supported kwargs:
            temperature (float): Sampling temperature (default 0.7).
            max_tokens (int): Maximum tokens in the response (default 4096).
            response_format (dict): E.g. {"type": "json_object"} — adds JSON instruction to prompt.
        """
        max_tokens = kwargs.get("max_tokens", DEFAULT_MAX_TOKENS)
        temperature = kwargs.get("temperature", 0.7)
        response_format = kwargs.get("response_format")

        system = system_prompt or ""
        user_content = prompt
        if response_format == {"type": "json_object"}:
            user_content = prompt.rstrip() + _JSON_INSTRUCTION

        return self._call_with_retry(
            system=system or None,
            user_content=user_content,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_with_retry(
        self,
        *,
        system: str | None,
        user_content: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Call the Anthropic API with exponential-backoff retry on rate limit/timeout/connection."""
        backoff = INITIAL_BACKOFF

        for attempt in range(1, self.max_retries + 1):
            try:
                start = time.monotonic()
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                    temperature=temperature,
                )
                elapsed = time.monotonic() - start

                # Content is a list of blocks; extract text from the first text block
                text = ""
                if getattr(response, "content", None):
                    for block in response.content:
                        if getattr(block, "type", None) == "text":
                            text = getattr(block, "text", "") or ""
                            break

                # Token usage (Anthropic exposes input_tokens, output_tokens)
                input_tokens = getattr(response, "input_tokens", None) or 0
                output_tokens = getattr(response, "output_tokens", None) or 0
                prompt_preview = (
                    (user_content[:100] + "...") if len(user_content) > 100 else user_content
                )
                logger.info(
                    "LLM call: model=%s prompt_preview=%r tokens_in=%s tokens_out=%s latency=%.2fs",
                    self.model,
                    prompt_preview,
                    input_tokens,
                    output_tokens,
                    elapsed,
                )
                logger.debug("LLM prompt (full): %s", user_content)

                return text

            except _RETRYABLE_ERRORS as exc:
                if attempt == self.max_retries:
                    logger.error(
                        "Anthropic retryable error: giving up after %d attempts: %s",
                        self.max_retries,
                        exc,
                    )
                    raise
                logger.warning(
                    "Anthropic %s: retry %d/%d in %.1fs",
                    type(exc).__name__,
                    attempt,
                    self.max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
