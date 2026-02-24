"""Signal record and event schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── RawEvent (v2-spec §9, Issue #89) ────────────────────────────────────────


class RawEvent(BaseModel):
    """Raw event from source adapters before normalization.

    Adapters return RawEvent instances; the normalizer converts these to
    SignalEvent + CompanyCreate for storage and company resolution.
    """

    company_name: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(None, max_length=255)
    website_url: str | None = Field(None, max_length=2048)
    company_profile_url: str | None = Field(None, max_length=2048)
    event_type_candidate: str = Field(..., min_length=1, max_length=64)
    event_time: datetime
    title: str | None = Field(None, max_length=512)
    summary: str | None = None
    url: str | None = Field(None, max_length=2048)
    source_event_id: str | None = Field(None, max_length=255)
    raw_payload: dict | None = None


# ── SignalRecord (existing) ────────────────────────────────────────────────


class SignalRecordRead(BaseModel):
    """Schema for reading a signal record (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    source_url: str
    source_type: str | None = None
    content_text: str = Field(
        ..., description="Content text, may be truncated in list views"
    )
    created_at: datetime


class SignalRecordList(BaseModel):
    """Paginated list of signal records."""

    items: list[SignalRecordRead]
    total: int
    page: int = 1
    page_size: int = 20

