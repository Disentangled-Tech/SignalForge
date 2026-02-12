"""Signal record schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SignalRecordRead(BaseModel):
    """Schema for reading a signal record (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    source_url: str
    source_type: Optional[str] = None
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

