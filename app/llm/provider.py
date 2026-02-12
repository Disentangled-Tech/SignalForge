"""
LLM provider abstraction.

Per PRD: The LLM is a reasoning component only. It may:
- classify stage
- interpret operational signals
- generate explanations
- draft outreach

It may NOT: schedule jobs, access DB, make action decisions, initiate communication.
"""

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send prompt and return completion text."""
        ...
