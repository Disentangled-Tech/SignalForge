"""Monitor schemas: ChangeEvent (M3, Issue #280)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChangeEvent(BaseModel):
    """Structured change event for a monitored page (before/after diff)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page_url: str = Field(..., min_length=1, max_length=2048)
    timestamp: datetime = Field(...)
    before_hash: str = Field(..., min_length=1, max_length=64)
    after_hash: str = Field(..., min_length=1, max_length=64)
    diff_summary: str = Field(..., max_length=2000)
    snippet_before: str | None = Field(None, max_length=2000)
    snippet_after: str | None = Field(None, max_length=2000)
    company_id: int = Field(..., ge=1)
    source_type: str | None = Field(None, max_length=32)
