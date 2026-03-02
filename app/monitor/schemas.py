"""Schemas for the diff-based monitor (M3). ChangeEvent used by diff detector and interpretation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChangeEvent(BaseModel):
    """Structured change event from monitor diff detection (M3).

    Emitted when page content changes; consumed by LLM interpretation (M5)
    to produce Core Event candidates. Pack-agnostic.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page_url: str = Field(..., min_length=1, max_length=2048)
    timestamp: datetime = Field(...)
    before_hash: str | None = Field(None, max_length=64)
    after_hash: str | None = Field(None, max_length=64)
    diff_summary: str = Field(..., min_length=1, max_length=10_000)
    snippet_before: str | None = Field(None, max_length=2000)
    snippet_after: str | None = Field(None, max_length=2000)
