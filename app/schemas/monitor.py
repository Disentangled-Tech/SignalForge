"""Monitor change event and snapshot DTOs (Diff-Based Monitor — M3).

ChangeEvent is the structured output of diff detection; consumed by LLM
interpretation (M5) and optional persistence. SnapshotLike is the contract
for "latest snapshot" used by the detector (implemented by M2 snapshot store).
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class SnapshotLike(TypedDict, total=True):
    """Contract for a page snapshot used by the diff detector.

    M2 snapshot store returns objects that satisfy this (e.g. ORM row or
    a small DTO). Detector only needs content_text, content_hash, fetched_at.
    """

    content_text: str
    content_hash: str
    fetched_at: datetime


class ChangeEvent(BaseModel):
    """Structured change event: one page changed between two fetches.

    Emitted by the diff detector when current content differs from the
    latest stored snapshot. Used by LLM interpretation (M5) and optional
    persistence. Pack-agnostic; no pack_id.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    page_url: str = Field(..., min_length=1, max_length=2048)
    timestamp: datetime = Field(..., description="When the new content was fetched")
    before_hash: str = Field(..., min_length=1, max_length=64)
    after_hash: str = Field(..., min_length=1, max_length=64)
    diff_summary: str = Field(..., min_length=1, max_length=2000)
    snippet_before: str | None = Field(None, max_length=2000)
    snippet_after: str | None = Field(None, max_length=2000)
